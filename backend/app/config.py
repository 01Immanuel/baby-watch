"""Loads backend/.env (or repo-root .env) into os.environ without overriding real environment variables.
No third-party dependency. Set BW_NO_DOTENV=1 to skip (tests do this)."""
import os
from pathlib import Path


def load_dotenv(paths=None):
    if os.environ.get("BW_NO_DOTENV") == "1":
        return []
    here = Path(__file__).resolve()
    paths = paths or [here.parents[1] / ".env", here.parents[2] / ".env"]
    loaded = []
    for p in paths:
        p = Path(p)
        if not p.is_file():
            continue
        for raw in p.read_text(encoding="utf-8-sig").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key, value = key.strip(), value.strip()
            if key.startswith("export "):
                key = key[7:].strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                value = value[1:-1]
            if key and value and key not in os.environ:
                os.environ[key] = value
        loaded.append(str(p))
    return loaded


load_dotenv()
