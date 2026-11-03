import os

os.environ["BW_NO_DOTENV"] = "1"  # tests must not read a developer's real .env

import pytest  # noqa: E402
from app import explain as ex  # noqa: E402
from app import main  # noqa: E402
from app.ratelimit import RateLimiter  # noqa: E402


@pytest.fixture(autouse=True)
def _isolate(monkeypatch):
    for k in ("GROQ_API_KEY", "BW_LLM_API_KEY"):
        monkeypatch.delenv(k, raising=False)
    ex.clear_cache()
    monkeypatch.setattr(main, "LIMITER", RateLimiter(1000, 60.0))
    yield
    ex.clear_cache()
