#!/usr/bin/env bash
# Baby Watch: build the app and serve everything on http://localhost:8000 (macOS / Linux).
set -euo pipefail
cd "$(dirname "$0")/frontend" && npm install && npm run build
cd ../backend && pip install -r requirements.txt
[ -f .env ] || echo "Tip: copy .env.example to .env and add your GROQ_API_KEY for AI explanations."
exec uvicorn app.main:app --port 8000
