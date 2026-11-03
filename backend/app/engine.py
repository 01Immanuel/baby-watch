"""Baby Watch rule engine (Python). Mirrors frontend/src/engine.js; parity is tested.
The engine alone decides the level. Nothing downstream (RAG, LLM) can change it.

Reading freshness: a BP counts only if taken today (bp_age='today'); Hb counts if taken in the last
few weeks (hb_age='recent'). Older readings ('earlier') can raise a result to Watch but never to
Go now, and never reassure. A missing age means current; an invalid age is treated as 'earlier'."""
import json
import math
import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RULES_DIR = Path(os.environ.get("BW_RULES_DIR", ROOT / "rules"))

LEVELS = ["low", "watch", "go_now"]
RANK = {name: i for i, name in enumerate(LEVELS)}
BOOLS = [
    "fatigue", "dizzy_faint", "palpitations", "breathless_rest", "vaginal_bleeding",
    "severe_headache", "blurred_vision", "swelling_face_hands", "fever", "too_weak",
    "severe_abdominal_pain", "convulsions", "previous_complications",
]
_NUM = re.compile(r"^ *-?[0-9]+(\.[0-9]+)? *\Z")


def load_rules(path=None):
    with open(path or RULES_DIR / "rules.json", encoding="utf-8") as f:
        return json.load(f)


def load_corpus(path=None):
    with open(path or RULES_DIR / "corpus.json", encoding="utf-8") as f:
        return json.load(f)["passages"]


def _num(v):
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        try:
            x = float(v)
        except OverflowError:
            return None
        return x if math.isfinite(x) else None
    if isinstance(v, str) and _NUM.match(v):
        return float(v)
    return None


def _age(v, allowed, default):
    if v is None:
        return default
    return v if (isinstance(v, str) and v in allowed) else "earlier"


def trimester(weeks):
    if weeks is None:
        return None
    return 1 if weeks < 14 else (2 if weeks < 28 else 3)


def anaemia_grade(hb, tri, cfg):
    if hb is None:
        return None
    c = cfg["by_trimester"].get(str(tri) if tri else "default", cfg["by_trimester"]["default"])
    if hb < cfg["severe_below"]:
        return "severe"
    if hb < c["moderate_below"]:
        return "moderate"
    if hb < c["any_below"]:
        return "mild"
    return "none"


def bp_level(sys_, dia, cfg):
    if sys_ is None and dia is None:
        return None
    if (sys_ is not None and sys_ >= cfg["severe_sys"]) or (dia is not None and dia >= cfg["severe_dia"]):
        return "severe"
    if (sys_ is not None and sys_ >= cfg["raised_sys"]) or (dia is not None and dia >= cfg["raised_dia"]):
        return "raised"
    return "normal"


def derive(inp, rules):
    if not isinstance(inp, dict):
        inp = {}
    f = {k: inp.get(k) is True for k in BOOLS}
    pallor = inp.get("pallor")
    f["pallor"] = pallor if pallor in ("none", "some", "severe") else "none"
    weeks, hb = _num(inp.get("gestation_weeks")), _num(inp.get("hb"))
    dist = _num(inp.get("distance_km"))
    bp_age = _age(inp.get("bp_age"), ("today", "earlier"), "today")
    hb_age = _age(inp.get("hb_age"), ("recent", "earlier"), "recent")
    f["trimester"] = trimester(weeks)
    grade = anaemia_grade(hb, f["trimester"], rules["hb_cutoffs"])
    bp = bp_level(_num(inp.get("bp_sys")), _num(inp.get("bp_dia")), rules["bp_cutoffs"])
    f["anaemia_grade"] = grade if hb_age == "recent" else None
    f["hb_earlier_low"] = hb_age == "earlier" and grade in ("mild", "moderate", "severe")
    f["bp_level"] = bp if bp_age == "today" else None
    f["bp_earlier_high"] = bp_age == "earlier" and bp in ("raised", "severe")
    f["hb_measured"] = f["anaemia_grade"] is not None
    f["bp_measured"] = f["bp_level"] is not None
    f["far_from_facility"] = dist is not None and dist >= rules["far_km"]
    return f


def match(cond, f):
    if "all" in cond:
        return all(match(c, f) for c in cond["all"])
    if "any" in cond:
        return any(match(c, f) for c in cond["any"])
    v = f.get(cond["f"])
    if "eq" in cond:
        return v == cond["eq"] and type(v) is type(cond["eq"])
    if "in" in cond:
        return v in cond["in"]
    raise ValueError(f"bad condition {cond}")


def evaluate(rules, inp):
    f = derive(inp, rules)
    fired = [r for r in rules["rules"] if match(r["when"], f)]
    level = "low"
    for r in fired:
        if RANK[r["level"]] > RANK[level]:
            level = r["level"]
    flags = [
        {"id": fl["id"], "kind": fl["kind"], "ask": fl.get("ask"), "text": fl["text"], "passages": fl["passages"]}
        for fl in rules["flags"]
        if match(fl["when"], f) and level in fl.get("only_levels", LEVELS)
    ]
    incomplete = level == "low" and not (f["hb_measured"] and f["bp_measured"])
    if fired:
        triggered = [
            {"id": r["id"], "level": r["level"], "short": r["short"], "why": r["why"], "passages": r["passages"]}
            for r in fired
        ]
    else:
        triggered = [{
            "id": "L00", "level": "low", "short": "No danger signs",
            "why": rules["default_why"], "passages": rules["default_passages"],
        }]
    return {
        "level": level,
        "incomplete": incomplete,
        "level_info": rules["level_info"]["low_incomplete" if incomplete else level],
        "anaemia_grade": f["anaemia_grade"],
        "bp_level": f["bp_level"],
        "triggered": triggered,
        "flags": flags,
    }


def signature(res):
    """What must be identical between the Python and JS engines."""
    return {
        "level": res["level"], "incomplete": res["incomplete"], "anaemia_grade": res["anaemia_grade"],
        "bp_level": res["bp_level"], "triggered": [t["id"] for t in res["triggered"]], "flags": [x["id"] for x in res["flags"]],
    }
