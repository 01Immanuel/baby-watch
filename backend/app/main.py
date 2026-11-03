import logging
import math
import mimetypes
import os
import time
from pathlib import Path
from typing import Literal, Optional

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import (
    config,  # noqa: F401  (loads .env before anything reads the environment)
    engine,
    rag,
)
from . import explain as ex
from .ratelimit import RateLimiter

# Windows can map these wrongly in its registry, which breaks ES-module scripts and the PWA manifest.
for _ext, _type in ((".js", "text/javascript"), (".mjs", "text/javascript"), (".css", "text/css"),
                    (".webmanifest", "application/manifest+json"), (".woff2", "font/woff2"), (".svg", "image/svg+xml")):
    mimetypes.add_type(_type, _ext)

if not logging.getLogger().handlers:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("babywatch")

ROOT = Path(__file__).resolve().parents[2]
DIST = ROOT / "frontend" / "dist"
MAX_BODY = 20_000

RULES = engine.load_rules()
PASSAGES = engine.load_corpus()
BM25 = rag.BM25(PASSAGES)
LIMITER = RateLimiter(int(os.environ.get("BW_RATE_LIMIT", "30")), 60.0)

app = FastAPI(title="Baby Watch API", version=RULES["version"])
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["GET", "POST"], allow_headers=["*"],
)


@app.middleware("http")
async def safety_headers(request: Request, call_next):
    try:
        too_big = int(request.headers.get("content-length") or 0) > MAX_BODY
    except ValueError:
        too_big = True
    if too_big:
        return JSONResponse({"detail": "Request too large"}, status_code=413)
    resp = await call_next(request)
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("Referrer-Policy", "no-referrer")
    resp.headers.setdefault("X-Frame-Options", "DENY")
    if request.url.path.startswith("/api/"):
        resp.headers.setdefault("Cache-Control", "no-store")
    return resp


def rate_limit(request: Request):
    key = request.client.host if request.client else "unknown"
    allowed, retry = LIMITER.allow(key)
    if not allowed:
        raise HTTPException(429, "Too many requests. Please wait a minute.", headers={"Retry-After": str(math.ceil(retry))})


class CaseInput(BaseModel):
    gestation_weeks: Optional[float] = Field(None, ge=1, le=45)
    hb: Optional[float] = Field(None, ge=2, le=20)
    pallor: Literal["none", "some", "severe"] = "none"
    bp_sys: Optional[float] = Field(None, ge=50, le=300)
    bp_dia: Optional[float] = Field(None, ge=30, le=200)
    distance_km: Optional[float] = Field(None, ge=0, le=1000)
    bp_age: Literal["today", "earlier"] = "today"
    hb_age: Literal["recent", "earlier"] = "recent"
    fatigue: bool = False
    dizzy_faint: bool = False
    palpitations: bool = False
    breathless_rest: bool = False
    vaginal_bleeding: bool = False
    severe_headache: bool = False
    blurred_vision: bool = False
    swelling_face_hands: bool = False
    fever: bool = False
    too_weak: bool = False
    severe_abdominal_pain: bool = False
    convulsions: bool = False
    previous_complications: bool = False


class ExplainRequest(BaseModel):
    input: CaseInput
    client_level: Optional[str] = None


@app.get("/api/health")
def health():
    return {
        "status": "ok", "rules_version": RULES["version"], "llm_provider": "groq", "llm_models": ex.MODELS,
        "llm_configured": ex.llm_configured(), "passages": len(PASSAGES),
    }


@app.post("/api/explain", dependencies=[Depends(rate_limit)])
def explain(req: ExplainRequest):
    t0 = time.perf_counter()
    result = engine.evaluate(RULES, req.input.model_dump())
    must = [p for t in result["triggered"] for p in t["passages"]] + [p for f in result["flags"] for p in f["passages"]]
    query = " ".join(t["why"] for t in result["triggered"])
    passages = rag.retrieve(BM25, query, must_include=must, k=max(4, len(set(must))))
    out = ex.explain(result, passages)
    # Privacy: never log the input, the client address or the rule ids. Level, mode and timing only.
    ms = (time.perf_counter() - t0) * 1000
    log.info("explain level=%s mode=%s note=%s ms=%d", result["level"], out["mode"], out["note"][:40], ms)
    return {
        "level": result["level"],  # always from the rule engine
        "incomplete": result["incomplete"],
        "level_info": result["level_info"],
        "anaemia_grade": result["anaemia_grade"],
        "bp_level": result["bp_level"],
        "triggered": result["triggered"],
        "flags": result["flags"],
        "explanation": out["text"],
        "explanation_mode": out["mode"],
        "explanation_note": out["note"],
        "passages": [{k: p[k] for k in ("id", "doc", "year", "section", "text")} for p in passages],
        "client_level_matches": (req.client_level == result["level"]) if req.client_level else None,
    }


class WebStatic(StaticFiles):
    """Hashed build assets are cached for a year; everything else (index, service worker) is always revalidated."""

    async def get_response(self, path, scope):
        resp = await super().get_response(path, scope)
        if resp.status_code == 200:
            resp.headers["Cache-Control"] = (
                "public, max-age=31536000, immutable" if path.replace("\\", "/").startswith("assets/") else "no-cache"
            )
        return resp


def mount_frontend(application, dist=DIST):
    """Serve the built React app from the same server, after all API routes. Returns True if mounted."""
    dist = Path(dist)
    if not (dist / "index.html").is_file():
        return False
    application.mount("/", WebStatic(directory=dist, html=True), name="web")
    return True


if not mount_frontend(app):
    log.info("frontend/dist not found: API only. Run `npm run build` in frontend/ to serve the app from here.")
