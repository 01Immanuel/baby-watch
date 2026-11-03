import pytest
from app import engine, rag
from app import explain as ex
from app.main import app
from fastapi.testclient import TestClient

RULES = engine.load_rules()
PASSAGES = engine.load_corpus()
BM = rag.BM25(PASSAGES)
client = TestClient(app)

def test_bm25_finds_bp_passage():
    top = rag.retrieve(BM, "high blood pressure swelling headache", k=2)
    assert top[0]["id"] == "P05"

def test_must_include_comes_first():
    got = rag.retrieve(BM, "iron tablets", must_include=["P08"], k=3)
    assert got[0]["id"] == "P08" and len(got) <= 3

GO = engine.evaluate(RULES, {"gestation_weeks": 30, "hb": 6.5})
GO_P = [p for p in PASSAGES if p["id"] in {"P01", "P07"}]

def test_template_has_level_and_cites():
    t = ex.template_explanation(GO, GO_P)
    assert "Go now" in t and "[P01]" in t
    ok, why = ex.validate(t, GO, GO_P)
    assert ok, why

@pytest.mark.parametrize("text,ok", [
    ("Go now. Your blood level is very low [P01].", True),
    ("Go now. Your blood level is very low.", False),
    ("Go now, it is low [P99].", False),
    ("This is low risk, go now maybe [P01].", False),
    ("Your blood level is very low [P01].", False),
    ("", False),
])
def test_validator(text, ok):
    assert ex.validate(text, GO, GO_P)[0] is ok

def test_llm_bad_output_falls_back(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "x")
    monkeypatch.setattr(ex, "call_llm", lambda s, u: "Nothing to worry about, low risk [P01].")
    out = ex.explain(GO, GO_P)
    assert out["mode"] == "template" and "rejected" in out["note"]

def test_llm_error_falls_back(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "x")
    def boom(s, u): raise TimeoutError()
    monkeypatch.setattr(ex, "call_llm", boom)
    assert ex.explain(GO, GO_P)["mode"] == "template"

def test_llm_good_output_used(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "x")
    monkeypatch.setattr(ex, "call_llm", lambda s, u: "Go now. Your blood level is under 7, which is severe anaemia [P01].")
    assert ex.explain(GO, GO_P)["mode"] == "llm"

def test_no_key_uses_template(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    assert ex.explain(GO, GO_P)["mode"] == "template"

def test_health():
    assert client.get("/api/health").json()["status"] == "ok"

def test_api_level_comes_from_engine_even_if_llm_lies(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "x")
    monkeypatch.setattr(ex, "call_llm", lambda s, u: "Low. You are fine [P03].")
    r = client.post("/api/explain", json={"input": {"gestation_weeks": 30, "hb": 6.5}, "client_level": "low"}).json()
    assert r["level"] == "go_now" and r["client_level_matches"] is False
    assert r["explanation_mode"] == "template"
    assert {"P01", "P07"} <= {p["id"] for p in r["passages"]}

def test_api_all_cited_passages_returned(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    r = client.post("/api/explain", json={"input": {"severe_headache": True, "swelling_face_hands": True}}).json()
    assert r["level"] == "go_now"
    ids = {p["id"] for p in r["passages"]}
    assert all(set(t["passages"]) <= ids for t in r["triggered"])

@pytest.mark.parametrize("bad", [{"hb": 99}, {"gestation_weeks": 0}, {"pallor": "purple"}, {"bp_sys": 10}])
def test_api_rejects_bad_input(bad):
    assert client.post("/api/explain", json={"input": bad}).status_code == 422


def test_call_llm_uses_groq_format_and_falls_back_to_second_model(monkeypatch):
    import httpx
    monkeypatch.setenv("GROQ_API_KEY", "gsk_test")
    calls = []
    class Resp:
        def __init__(self, ok):
            self.ok = ok

        def raise_for_status(self):
            if not self.ok:
                raise httpx.HTTPStatusError("gone", request=None, response=None)

        def json(self):
            return {"choices": [{"message": {"content": " Go now [P01]. "}}]}
    def fake_post(url, headers, json, timeout):
        calls.append((url, headers["Authorization"], json["model"], json["messages"][0]["role"]))
        return Resp(len(calls) > 1)
    monkeypatch.setattr(httpx, "post", fake_post)
    assert ex.call_llm("sys", "usr") == "Go now [P01]."
    assert calls[0][0] == "https://api.groq.com/openai/v1/chat/completions"
    assert calls[0][1] == "Bearer gsk_test" and calls[0][3] == "system"
    assert [c[2] for c in calls] == ex.MODELS[:2]

def test_all_models_fail_gives_template(monkeypatch):
    import httpx
    monkeypatch.setenv("GROQ_API_KEY", "gsk_test")
    def boom(*a, **k): raise httpx.ConnectError("offline")
    monkeypatch.setattr(httpx, "post", boom)
    out = ex.explain(GO, GO_P)
    assert out["mode"] == "template" and "unavailable" in out["note"]


def test_validator_blocks_reassurance_when_tests_are_missing():
    inc = engine.evaluate(RULES, {})
    pas = [p for p in PASSAGES if p["id"] == "P03"]
    assert not ex.validate("Low so far. You are fine [P03].", inc, pas)[0]
    assert ex.validate("Low so far. No danger signs, but tests are still needed [P03].", inc, pas)[0]

def test_api_accepts_reading_ages_and_flags_incomplete(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    r = client.post("/api/explain", json={"input": {"bp_sys": 120, "bp_dia": 80, "bp_age": "earlier"}}).json()
    assert r["level"] == "low" and r["incomplete"] is True

@pytest.mark.parametrize("bad", [{"bp_age": "yesterday"}, {"hb_age": "today"}])
def test_api_rejects_bad_age(bad):
    assert client.post("/api/explain", json={"input": bad}).status_code == 422
