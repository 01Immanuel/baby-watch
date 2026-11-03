"""Explanation layer. The level is FIXED by the rule engine; the LLM only words it.
Any LLM output that fails validation is discarded and the stored rule text is used."""
import os
import re
import threading
from collections import OrderedDict

import httpx

# Provider: Groq (free tier) via its OpenAI-compatible API. Any OpenAI-compatible host works
# by changing BW_LLM_BASE_URL + the key. Models are tried in order; first success wins.
BASE_URL = os.environ.get("BW_LLM_BASE_URL", "https://api.groq.com/openai/v1")
MODELS = [m.strip() for m in os.environ.get("BW_MODEL", "llama-3.3-70b-versatile,llama-3.1-8b-instant").split(",") if m.strip()]


# Identical rule outcomes give identical explanations, so cache them. This saves free-tier quota and time.
_CACHE = OrderedDict()
_LOCK = threading.Lock()
CACHE_MAX = 256


def clear_cache():
    with _LOCK:
        _CACHE.clear()


def _cache_key(result, passages):
    return (result["level"], result["incomplete"], tuple(t["id"] for t in result["triggered"]),
            tuple(f["id"] for f in result["flags"]), tuple(p["id"] for p in passages))


def api_key():
    return os.environ.get("GROQ_API_KEY") or os.environ.get("BW_LLM_API_KEY")


def llm_configured():
    return bool(api_key())


def template_explanation(result, passages):
    info = result["level_info"]
    lines = [f"Result: {info['label']}."]
    for t in result["triggered"]:
        cites = "".join(f"[{p}]" for p in t["passages"])
        lines.append(f"- {t['why']} {cites}".strip())
    lines.append(f"What to do: {info['action']} ({info['window']}).")
    for fl in result["flags"]:
        lines.append(f"Also: {fl['text']}")
    return "\n".join(lines)


def build_prompt(result, passages):
    info = result["level_info"]
    reasons = "\n".join(f"- {t['why']}" for t in result["triggered"])
    ctx = "\n".join(f"[{p['id']}] ({p['doc']}, {p['year']}) {p['text']}" for p in passages)
    system = (
        "You explain a pregnancy danger-sign triage result to a woman or a community health worker, "
        "in short plain words (reading age 12). The result is FIXED by a rule engine: "
        f"\"{info['label']}\". Never change, soften, or question it. Never diagnose. "
        "Use only facts found in the PASSAGES. After each claim add its passage id like [P04]. "
        "Say the result label once. Max 45 words, 2 or 3 short sentences. No lists."
    )
    note = ""
    if result.get("incomplete"):
        note = "\nNOTE: no recent tests were done. Never say she is fine; say tests are still needed."
    user = (
        f"RESULT: {info['label']}{note}\nWHY (from rules):\n{reasons}\n"
        f"WHAT TO DO: {info['action']} ({info['window']})\nPASSAGES:\n{ctx}\n\nWrite the explanation."
    )
    return system, user


_LOWER_BAD = ["low risk", "not serious", "nothing to worry", "no need to", "not urgent", "can wait"]
_INCOMPLETE_BAD = ["you are fine", "you're fine", "all clear", "nothing to worry", "no problem"]


def validate(text, result, passages):
    """Return (ok, reason)."""
    if not text or len(text) > 1400:
        return False, "empty or too long"
    ids = {p["id"] for p in passages}
    cites = set(re.findall(r"\[(P\d+)\]", text))
    if not cites:
        return False, "no citations"
    if not cites <= ids:
        return False, "cites passage that was not retrieved"
    label = result["level_info"]["label"].lower()
    low = text.lower()
    if label not in low:
        return False, "does not state the fixed level"
    if result["level"] != "low" and any(b in low for b in _LOWER_BAD):
        return False, "softens a non-low result"
    if result.get("incomplete") and any(b in low for b in _INCOMPLETE_BAD):
        return False, "reassures without tests"
    if result["level"] == "low" and "go now" in low:
        return False, "escalates a low result"
    return True, "ok"


def call_llm(system, user, timeout=15.0):
    key = api_key()
    if not key:
        raise RuntimeError("no GROQ_API_KEY")
    last = None
    for model in MODELS:
        try:
            r = httpx.post(
                f"{BASE_URL}/chat/completions",
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                json={
                    "model": model, "temperature": 0.2, "max_tokens": 1500, "reasoning_effort": "low",
                    "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
                },
                timeout=timeout,
            )
            r.raise_for_status()
            return r.json()["choices"][0]["message"]["content"].strip()
        except Exception as e:  # bad/retired model, rate limit, timeout: try the next model
            last = e
    raise last or RuntimeError("no model configured")


def explain(result, passages):
    """Returns dict(text, mode, note). mode is 'llm' or 'template'."""
    fallback = template_explanation(result, passages)
    if not llm_configured():
        return {"text": fallback, "mode": "template", "note": "no LLM key set"}
    key = _cache_key(result, passages)
    with _LOCK:
        if key in _CACHE:
            _CACHE.move_to_end(key)
            return {"text": _CACHE[key], "mode": "llm", "note": "cached"}
    try:
        system, user = build_prompt(result, passages)
        text = call_llm(system, user)
        print("RAW LLM:", repr(text)[:600], flush=True)
    except Exception as e:  # network, auth, timeout: never block the result
        return {"text": fallback, "mode": "template", "note": f"LLM unavailable: {type(e).__name__}"}
    ok, why = validate(text, result, passages)
    if not ok:
        return {"text": fallback, "mode": "template", "note": f"LLM output rejected: {why}"}
    with _LOCK:
        _CACHE[key] = text
        while len(_CACHE) > CACHE_MAX:
            _CACHE.popitem(last=False)
    return {"text": text, "mode": "llm", "note": "ok"}
