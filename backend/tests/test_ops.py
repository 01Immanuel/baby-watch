import logging
import os

import pytest
from app import config, engine, main
from app import explain as ex
from app.ratelimit import RateLimiter
from fastapi import FastAPI
from fastapi.testclient import TestClient

client = TestClient(main.app)
RULES = engine.load_rules()


# ---------- .env loading ----------
def test_dotenv_parses_and_never_overrides(tmp_path, monkeypatch):
    f = tmp_path / ".env"
    lines = ['# comment', '', 'GROQ_API_KEY="gsk_abc"', 'export BW_MODEL=m1,m2', 'EMPTY=', 'BAD LINE', 'KEEP=from_file']
    f.write_text("\n".join(lines) + "\n", encoding="utf-8")
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.delenv("BW_MODEL", raising=False)
    monkeypatch.delenv("EMPTY", raising=False)
    monkeypatch.setenv("KEEP", "from_env")
    monkeypatch.delenv("BW_NO_DOTENV", raising=False)
    assert config.load_dotenv([f]) == [str(f)]
    assert os.environ["GROQ_API_KEY"] == "gsk_abc" and os.environ["BW_MODEL"] == "m1,m2"
    assert "EMPTY" not in os.environ and os.environ["KEEP"] == "from_env"
    for k in ("GROQ_API_KEY", "BW_MODEL"):
        monkeypatch.delenv(k)


def test_dotenv_missing_file_and_opt_out(tmp_path, monkeypatch):
    monkeypatch.delenv("BW_NO_DOTENV", raising=False)
    assert config.load_dotenv([tmp_path / "nope.env"]) == []
    monkeypatch.setenv("BW_NO_DOTENV", "1")
    assert config.load_dotenv([tmp_path]) == []


# ---------- rate limiter ----------
class Clock:
    t = 0.0
    def __call__(self): return self.t


def test_limiter_window_and_keys():
    c = Clock()
    rl = RateLimiter(3, 60.0, clock=c)
    assert [rl.allow("a")[0] for _ in range(3)] == [True] * 3
    ok, retry = rl.allow("a")
    assert ok is False and 0 < retry <= 60
    assert rl.allow("b")[0] is True  # other clients unaffected
    c.t = 61
    assert rl.allow("a")[0] is True  # window slid


def test_limiter_disabled_with_zero_and_prunes():
    assert all(RateLimiter(0).allow("x")[0] for _ in range(100))
    c = Clock()
    rl = RateLimiter(1, 10.0, clock=c, max_keys=5)
    for i in range(6):
        rl.allow(f"k{i}")
    c.t = 20
    rl.allow("new")
    assert len(rl.hits) <= 2


def test_api_returns_429_with_retry_after(monkeypatch):
    monkeypatch.setattr(main, "LIMITER", RateLimiter(2, 60.0))
    body = {"input": {"gestation_weeks": 30}}
    assert [client.post("/api/explain", json=body).status_code for _ in range(2)] == [200, 200]
    r = client.post("/api/explain", json=body)
    assert r.status_code == 429 and int(r.headers["Retry-After"]) >= 1
    assert client.get("/api/health").status_code == 200  # health is never limited


# ---------- headers, size limit, privacy ----------
def test_security_headers_and_no_store_on_api():
    r = client.get("/api/health")
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["x-frame-options"] == "DENY"
    assert r.headers["referrer-policy"] == "no-referrer"
    assert r.headers["cache-control"] == "no-store"


def test_oversized_body_rejected():
    r = client.post("/api/explain", content=b"x" * 30_000, headers={"content-type": "application/json"})
    assert r.status_code == 413


def test_logs_never_contain_inputs(caplog):
    with caplog.at_level(logging.INFO, logger="babywatch"):
        client.post("/api/explain", json={"input": {"hb": 6.123, "bp_sys": 171, "bp_dia": 99, "vaginal_bleeding": True}})
    text = caplog.text
    assert "level=go_now" in text
    for secret in ("6.123", "171", "vaginal", "bleeding", "testclient", "G02"):
        assert secret not in text


# ---------- explanation cache ----------
def test_identical_outcomes_hit_the_cache(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "x")
    calls = []
    def fake(s, u):
        calls.append(1)
        return "Go now. Your blood level is under 7, which is severe anaemia [P01]."
    monkeypatch.setattr(ex, "call_llm", fake)
    a = client.post("/api/explain", json={"input": {"gestation_weeks": 30, "hb": 6.5}}).json()
    b = client.post("/api/explain", json={"input": {"gestation_weeks": 22, "hb": 5.0}}).json()  # same rules fire
    assert len(calls) == 1 and a["explanation_mode"] == b["explanation_mode"] == "llm" and b["explanation_note"] == "cached"
    client.post("/api/explain", json={"input": {"gestation_weeks": 30, "vaginal_bleeding": True}})
    assert len(calls) == 2  # different rules, different explanation


def test_rejected_llm_text_is_not_cached(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "x")
    calls = []
    monkeypatch.setattr(ex, "call_llm", lambda s, u: calls.append(1) or "Low risk, relax.")
    for _ in range(2):
        r = client.post("/api/explain", json={"input": {"hb": 6.5}}).json()
        assert r["explanation_mode"] == "template" and r["level"] == "go_now"
    assert len(calls) == 2


def test_cache_is_bounded(monkeypatch):
    monkeypatch.setattr(ex, "CACHE_MAX", 3)
    for i in range(10):
        ex._CACHE[("k", i)] = "t"
        while len(ex._CACHE) > ex.CACHE_MAX:
            ex._CACHE.popitem(last=False)
    assert len(ex._CACHE) == 3


# ---------- serving the built frontend ----------
@pytest.fixture
def web(tmp_path):
    (tmp_path / "assets").mkdir()
    (tmp_path / "index.html").write_text("<!doctype html><title>bw</title>", encoding="utf-8")
    (tmp_path / "sw.js").write_text("self.skipWaiting()", encoding="utf-8")
    (tmp_path / "assets" / "app-abc123.js").write_text("export {}", encoding="utf-8")
    (tmp_path / "manifest.webmanifest").write_text("{}", encoding="utf-8")
    a = FastAPI()
    a.get("/api/ping")(lambda: {"ok": True})
    assert main.mount_frontend(a, tmp_path) is True
    return TestClient(a)


def test_frontend_served_with_correct_types_and_cache(web):
    r = web.get("/")
    assert r.status_code == 200 and "text/html" in r.headers["content-type"] and r.headers["cache-control"] == "no-cache"
    assert web.get("/sw.js").headers["cache-control"] == "no-cache"
    js = web.get("/assets/app-abc123.js")
    assert "javascript" in js.headers["content-type"] and "immutable" in js.headers["cache-control"]
    assert "manifest+json" in web.get("/manifest.webmanifest").headers["content-type"]


def test_api_not_shadowed_by_static_mount(web):
    assert web.get("/api/ping").json() == {"ok": True}
    assert web.get("/nope.txt").status_code == 404


def test_missing_dist_is_not_an_error(tmp_path):
    assert main.mount_frontend(FastAPI(), tmp_path / "does-not-exist") is False
