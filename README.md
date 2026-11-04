# Baby Watch

Early-warning tool for pregnancy danger signs, with depth on anaemia, for two kinds of user: **a pregnant woman or her family** (tick the signs, no equipment needed) and **a health worker** (adds measured haemoglobin and blood pressure and gets a referral note). Both get **Low**, **Watch** or **Go now**, with one clear action and the WHO rule behind it. It works with no internet. It does not diagnose.

```
 signs + optional numbers ──► RULE ENGINE (in the browser) ──► Low | Watch | Go now   <- decides, alone
                                   │
                                   └─► /api/explain (FastAPI) ──► BM25 over WHO passages
                                            │                      (rule-linked passages always included)
                                            └─► Groq LLM ──► validator ──► cited explanation
                                                             (rejected? -> stored rule text)
```

The AI never changes the result. It only words it. The server re-runs the same rules; if the two ever disagree, the UI shows the more urgent level.

## Two modes, one rule engine

|        | Woman or family                                                     | Health worker                                                 |
| ------ | ------------------------------------------------------------------- | ------------------------------------------------------------- |
| Input  | Signs she can see or feel. Numbers optional.                        | Signs plus measured Hb and BP, with when they were taken.     |
| Output | Result, action, questions to ask at the clinic, "Show family" card. | Result, recommendation, copyable referral note with findings. |
| Why    | Most women have no Hb or BP at home, so symptoms must work alone.   | A worker has measured values, so the rules can use them.      |

The mode changes wording and the note only. The rules and the result are identical in both.

## Run it (one command)

1. Optional, for AI explanations: copy `backend/.env.example` to `backend/.env` and paste your free Groq key (console.groq.com). No `export` needed. `.env` is git-ignored.
2. Windows: double-click `run.bat`. macOS/Linux: `./run.sh`.
3. Open **http://localhost:8000**.

That builds the React app and serves it, the API and the offline files from one FastAPI process. First load installs the offline copy, after that the app opens with no network. Check `http://localhost:8000/api/health` for `"llm_configured": true`.

Two-terminal development mode (hot reload): `cd backend && uvicorn app.main:app --port 8000` and `cd frontend && npm run dev`, then open http://localhost:5173.

## What was engineered

| Concern              | How                                                                                                                                 |
| -------------------- | ----------------------------------------------------------------------------------------------------------------------------------- |
| Safe decisions       | Rule engine alone decides. Same rules in Python and JS, proven identical on 547 inputs (`rules/parity.json`).                       |
| Stale data           | BP counts only if taken today, Hb if taken in the last 4 weeks. Older readings can raise to Watch, never to Go now, never reassure. |
| False reassurance    | "Low" needs a current Hb and BP, otherwise it reads "Low so far" and says what to ask for.                                          |
| AI guardrails        | LLM text must cite retrieved passages, state the fixed level, not soften it, not reassure without tests. Otherwise dropped.         |
| Offline              | Service worker precaches the app, rules and sources. `/api` is never cached. Verified in a real browser with the network off.       |
| Privacy              | No database. Logs hold level, mode and timing only: never inputs, rule ids or client address (tested).                              |
| Free-tier protection | Per-client rate limit (30/min, `BW_RATE_LIMIT`), identical rule outcomes share one cached explanation, 2-model fallback.            |
| Hardening            | Input ranges validated twice, 20 KB body cap, security headers, `Cache-Control: no-store` on the API, error boundary in the UI.     |
| Windows quirks       | MIME types for `.js` and `.webmanifest` are forced, so module scripts and the PWA work on any machine.                              |

Environment variables (all optional): `GROQ_API_KEY`, `BW_MODEL` (comma-separated, tried in order), `BW_LLM_BASE_URL`, `BW_RATE_LIMIT` (0 disables).

## Test

```bash
python -m pytest -q                    # 196 backend tests (run from the repo root)
ruff check backend                     # lint
cd frontend && npm test                # 8 tests incl. Python/JS parity on 547 inputs
python backend/scripts/run_eval.py --write   # recall report -> docs/eval_report.md
python backend/scripts/gen_parity.py         # after editing rules/rules.json or cases.json
python e2e/test_flows.py               # browser flows incl. offline (needs the app running + playwright)
```

CI (`.github/workflows/ci.yml`) runs lint, tests, parity freshness, the evaluation (fails on any under-triage) and the frontend build.

## Layout

```
rules/rules.json    thresholds + rules (single source of truth, used by both engines)
rules/corpus.json   WHO passages for RAG and citations
rules/cases.json    47 synthetic vignettes (testing only, not clinician reviewed yet)
rules/parity.json   generated: Python results the JS engine must reproduce
backend/app/        engine, rag, explain, ratelimit, config, main (FastAPI)
frontend/src/       engine.js (same rules), App.jsx, validate.js, styles.css
docs/               eval report, failures found and fixed, questions for the clinician
e2e/                browser flow script
```

## Honest status

- Hb cutoffs (WHO 2024, trimester-specific) were cross-checked against secondary sources. BP cutoffs 140/90 and 160/110 follow WHO pre-eclampsia guidance.
- `rules/corpus.json` holds short summaries of WHO guidance, not verbatim quotes. Replace each `text` with the verbatim passage from the official PDF and set `verbatim: true`.
- The time windows for Watch and Go now, the reading freshness windows, and the 10 km far-facility flag are project parameters. See `docs/clinician_questions.md`.
- The 47 vignettes are mine, with labels from clinical reasoning, not clinician reviewed. The recall figure only counts once they are.
- AI explanations were verified live with Groq (`openai/gpt-oss-120b`, `explanation_mode=llm`). This model reasons before answering, so `explain.py` sets `reasoning_effort: low` and `max_tokens: 1500`. With a smaller limit the reply came back empty and the app fell back to the stored rule text.
- Health worker mode changes wording only and has not been reviewed by a clinician.
- English only for now. It needs a browser, so a woman without a phone depends on a companion or a health worker using it.
- Nothing here shows the app reduces maternal deaths. It is decision support.
