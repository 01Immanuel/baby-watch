import copy
import json
import random

import pytest
from app import engine

RULES = engine.load_rules()
CORPUS = engine.load_corpus()
CASES = json.load(open(engine.RULES_DIR / "cases.json"))["cases"]
R = engine.RANK
SIGNS = engine.BOOLS


def ev(**kw):
    return engine.evaluate(RULES, kw)


def lvl(**kw):
    return ev(**kw)["level"]


# ---------- labelled vignettes ----------
@pytest.mark.parametrize("case", CASES, ids=[c["id"] for c in CASES])
def test_vignette(case):
    assert lvl(**case["input"]) == case["expected_level"]


def test_no_vignette_is_under_triaged():
    bad = [c["id"] for c in CASES if R[lvl(**c["input"])] < R[c["expected_level"]]]
    assert bad == []


def test_every_rule_is_exercised_by_a_vignette():
    fired = {t["id"] for c in CASES for t in ev(**c["input"])["triggered"]}
    assert {r["id"] for r in RULES["rules"]} <= fired


# ---------- WHO thresholds and boundaries ----------
@pytest.mark.parametrize("weeks,hb,grade", [
    (8, 11.0, "none"), (8, 10.9, "mild"), (8, 10.0, "mild"), (8, 9.9, "moderate"), (8, 7.0, "moderate"), (8, 6.9, "severe"),
    (20, 10.5, "none"), (20, 10.4, "mild"), (20, 9.5, "mild"), (20, 9.4, "moderate"), (20, 7.0, "moderate"), (20, 6.9, "severe"),
    (30, 11.0, "none"), (30, 10.9, "mild"), (30, 9.9, "moderate"), (30, 6.9, "severe"),
    (None, 10.9, "mild"), (None, 10.0, "mild"), (None, 9.9, "moderate"), (None, 11.0, "none"),
])
def test_hb_grade_by_trimester(weeks, hb, grade):
    assert engine.evaluate(RULES, {"gestation_weeks": weeks, "hb": hb})["anaemia_grade"] == grade


@pytest.mark.parametrize("weeks,tri", [(1, 1), (13, 1), (13.9, 1), (14, 2), (27, 2), (27.9, 2), (28, 3), (42, 3), (None, None)])
def test_trimester_edges(weeks, tri):
    assert engine.trimester(weeks) == tri


@pytest.mark.parametrize("sys_,dia,want", [
    (139, 89, "normal"), (140, 70, "raised"), (120, 90, "raised"), (159, 109, "raised"),
    (160, 70, "severe"), (120, 110, "severe"), (None, 95, "raised"), (145, None, "raised"),
    (None, 115, "severe"), (None, None, None), (90, 60, "normal"),
])
def test_bp_boundaries(sys_, dia, want):
    assert engine.evaluate(RULES, {"bp_sys": sys_, "bp_dia": dia})["bp_level"] == want


# ---------- reading freshness ----------
def test_earlier_bp_never_counts_as_current():
    r = ev(bp_sys=170, bp_dia=112, bp_age="earlier")
    assert r["bp_level"] is None and r["level"] == "watch" and r["triggered"][0]["id"] == "W11"

def test_earlier_normal_bp_does_not_reassure():
    r = ev(hb=12, gestation_weeks=20, bp_sys=110, bp_dia=70, bp_age="earlier")
    assert r["level"] == "low" and r["incomplete"] is True

def test_earlier_hb_caps_at_watch():
    assert lvl(hb=5.0, hb_age="earlier") == "watch"

def test_earlier_normal_hb_does_not_reassure():
    assert ev(hb=13, hb_age="earlier", bp_sys=110, bp_dia=70)["incomplete"] is True

def test_missing_age_means_current():
    assert lvl(hb=5.0) == "go_now" and lvl(bp_sys=170, bp_dia=100) == "go_now"

@pytest.mark.parametrize("bad", ["weird", 5, True, [], {}])
def test_invalid_age_is_treated_as_earlier(bad):
    assert lvl(bp_sys=170, bp_dia=110, bp_age=bad) == "watch"
    assert lvl(hb=5.0, hb_age=bad) == "watch"

def test_earlier_readings_alone_can_never_cause_go_now():
    r = random.Random(11)
    for _ in range(500):
        kw = dict(bp_age="earlier", hb_age="earlier", gestation_weeks=r.choice([None, 10, 20, 30]),
                  hb=r.choice([None, 4.0, 6.5, 9.0, 12.0]), bp_sys=r.choice([None, 120, 150, 180]),
                  bp_dia=r.choice([None, 80, 100, 120]))
        assert lvl(**kw) != "go_now"


# ---------- Low so far ----------
def test_low_without_numbers_is_incomplete():
    r = ev()
    assert (r["level"], r["incomplete"], r["level_info"]["label"]) == ("low", True, "Low so far")
    assert [f["id"] for f in r["flags"]] == ["F01", "F03"]

def test_low_with_both_current_numbers_is_complete():
    r = ev(gestation_weeks=24, hb=12, bp_sys=110, bp_dia=70)
    assert (r["level"], r["incomplete"], r["level_info"]["label"], r["flags"]) == ("low", False, "Low", [])

def test_only_one_number_is_still_incomplete():
    assert ev(hb=12)["incomplete"] and ev(bp_sys=110, bp_dia=70)["incomplete"]

def test_incomplete_only_ever_when_low():
    r = random.Random(5)
    for _ in range(300):
        kw = {k: r.random() < 0.2 for k in SIGNS}
        res = engine.evaluate(RULES, kw)
        assert (not res["incomplete"]) or res["level"] == "low"

def test_ask_flags_hidden_on_go_now():
    assert not [f for f in ev(vaginal_bleeding=True)["flags"] if f["kind"] == "ask"]

def test_far_flag_only_when_not_low():
    assert "F02" not in [f["id"] for f in ev(hb=12, distance_km=30)["flags"]]
    assert "F02" in [f["id"] for f in ev(hb=9, gestation_weeks=30, distance_km=30)["flags"]]
    assert "F02" not in [f["id"] for f in ev(hb=9, gestation_weeks=30, distance_km=9.9)["flags"]]


# ---------- clinical logic fixed after the first evaluation ----------
def test_pallor_is_overridden_by_a_normal_current_hb():
    assert lvl(pallor="some", hb=12.5, gestation_weeks=28) == "low"
    assert lvl(pallor="severe", hb=12.5, gestation_weeks=28) == "watch"

def test_pallor_without_hb_still_escalates():
    assert lvl(pallor="some") == "watch" and lvl(pallor="severe") == "go_now"

def test_too_weak_alone_is_watch_and_with_fever_go_now():
    assert lvl(too_weak=True) == "watch" and lvl(too_weak=True, fever=True) == "go_now"

def test_preeclampsia_sign_pairs_are_go_now_without_bp():
    pairs = [("severe_headache", "blurred_vision"), ("severe_headache", "swelling_face_hands"),
             ("blurred_vision", "swelling_face_hands")]
    for a, b in pairs:
        assert lvl(**{a: True, b: True}) == "go_now"
        assert lvl(**{a: True}) == "watch"


# ---------- robustness ----------
@pytest.mark.parametrize("junk", [None, [], "x", 5, 1.5, True, (1, 2)])
def test_non_dict_input_is_safe(junk):
    r = engine.evaluate(RULES, junk)
    assert r["level"] == "low" and r["incomplete"] is True

UNPARSEABLE = ["abc", "", " ", "0x10", "1e2", ".5", "5.", "-", True, False, [], {},
               float("nan"), float("inf"), -float("inf"), 10 ** 400]


@pytest.mark.parametrize("val", UNPARSEABLE)
def test_unparseable_numbers_are_ignored(val):
    assert engine._num(val) is None
    assert ev(hb=val, bp_sys=val, bp_dia=val, gestation_weeks=val, distance_km=val)["level"] == "low"

@pytest.mark.parametrize("val,want", [("8.5", 8.5), (" 8.5 ", 8.5), ("-3", -3.0), (7, 7.0), (7.25, 7.25), ("0", 0.0)])
def test_numeric_strings_are_accepted(val, want):
    assert engine._num(val) == want

def test_numeric_string_matches_number():
    assert ev(hb="6.5", gestation_weeks="30") == ev(hb=6.5, gestation_weeks=30)

def test_signs_must_be_real_booleans():
    for v in ("true", "True", 1, "yes", [True]):
        assert lvl(vaginal_bleeding=v) == "low"
    assert lvl(vaginal_bleeding=True) == "go_now"

def test_unknown_keys_ignored_and_input_not_mutated():
    inp = {"hb": 6.5, "gestation_weeks": 30, "banana": 1, "nested": {"a": [1]}}
    before = copy.deepcopy(inp)
    r = engine.evaluate(RULES, inp)
    assert inp == before and r["level"] == "go_now"

def test_every_sign_true_is_go_now():
    assert lvl(**{k: True for k in SIGNS}, pallor="severe") == "go_now"

def test_level_is_the_maximum_of_triggered_levels():
    r = random.Random(2)
    for _ in range(300):
        res = engine.evaluate(RULES, {k: r.random() < 0.25 for k in SIGNS} | {"hb": r.choice([None, 6, 9, 12])})
        top = max((R[t["level"]] for t in res["triggered"]), default=0)
        assert R[res["level"]] == top

def test_result_always_has_text_for_the_ui():
    r = ev(severe_headache=True)
    assert r["level_info"]["label"] and r["level_info"]["action"]
    assert all(t["short"] and t["why"] for t in r["triggered"])


# ---------- safety properties ----------
def test_monotonic_hb_current():
    for w in (8, 20, 32, None):
        prev = 99
        for i in range(40, 150):
            cur = R[lvl(gestation_weeks=w, hb=i / 10)]
            assert cur <= prev, f"level rose as Hb rose at w={w} hb={i/10}"
            prev = cur

def test_monotonic_bp_current():
    prev = -1
    for s in range(100, 190):
        cur = R[lvl(bp_sys=s, bp_dia=70)]
        assert cur >= prev
        prev = cur

def test_adding_a_sign_never_lowers_level():
    r = random.Random(3)
    for _ in range(400):
        base = {k: r.random() < 0.2 for k in SIGNS}
        base.update(hb=r.choice([None, 6.5, 9, 10.5, 12]), gestation_weeks=r.choice([None, 10, 20, 30]))
        b = R[lvl(**base)]
        for k in SIGNS:
            assert R[lvl(**dict(base, **{k: True}))] >= b, f"adding {k} lowered level"


# ---------- rule pack integrity ----------
def _fields(cond):
    if "all" in cond:
        return {f for c in cond["all"] for f in _fields(c)}
    if "any" in cond:
        return {f for c in cond["any"] for f in _fields(c)}
    return {cond["f"]}

def test_every_condition_field_exists_in_derived_state():
    state = engine.derive({}, RULES).keys()
    for item in RULES["rules"] + RULES["flags"]:
        assert _fields(item["when"]) <= set(state), item["id"]

def test_every_sign_input_is_used_by_some_rule():
    used = {f for r in RULES["rules"] for f in _fields(r["when"])}
    assert set(SIGNS) <= used

def test_rule_ids_unique_and_levels_valid():
    ids = [r["id"] for r in RULES["rules"]] + [f["id"] for f in RULES["flags"]]
    assert len(ids) == len(set(ids))
    assert all(r["level"] in engine.LEVELS for r in RULES["rules"])
    assert {"low", "low_incomplete", "watch", "go_now"} <= set(RULES["level_info"])

def test_rule_text_is_short_enough_for_the_ui():
    for r in RULES["rules"]:
        assert 0 < len(r["short"]) <= 40, r["id"]
        assert 0 < len(r["why"]) <= 220, r["id"]
    assert all(len(v["action"]) <= 70 for v in RULES["level_info"].values())

def test_every_rule_cites_existing_passages():
    ids = {p["id"] for p in CORPUS}
    for r in RULES["rules"]:
        assert r["passages"] and set(r["passages"]) <= ids, r["id"]
    for f in RULES["flags"]:
        assert set(f["passages"]) <= ids
    assert set(RULES["default_passages"]) <= ids

def test_corpus_passages_are_well_formed():
    ids = [p["id"] for p in CORPUS]
    assert len(ids) == len(set(ids))
    for p in CORPUS:
        assert all(p.get(k) for k in ("id", "doc", "year", "section", "text"))

def test_ask_flags_have_ask_text():
    for f in RULES["flags"]:
        assert f["kind"] in ("ask", "note")
        assert f["kind"] != "ask" or f.get("ask")

def test_parity_file_current():
    rows = json.load(open(engine.RULES_DIR / "parity.json"))
    assert len(rows) >= 500
    for row in rows:
        assert engine.signature(engine.evaluate(RULES, row["input"])) == row["expected"]
