# Progress Log

## Session 1 — 2026-05-27 — Investigation

- Created `task_plan.md`, `findings.md`, `progress.md`.
- Mapped repo structure: backend (FastAPI on :8001), frontend (React+Vite on :5173), JSON persistence under `data/conversations/`.
- Phases 1–4 complete. Findings written to `findings.md`.
- Key surprises beyond CLAUDE.md: streaming SSE endpoint exists; title generation uses hardcoded `google/gemini-2.5-flash`; assistant message metadata is *not* persisted; the input form is single-turn-only (only rendered when `messages.length === 0`); current `config.py` model IDs differ from those documented in README/CLAUDE.md.

## Session 2 — 2026-05-27 — Databricks Apps research

- Moved planning files into `planning/` per user request.
- User goal received: convert to a Databricks App.
- Researched Databricks Apps via official docs + cookbook + reference starters.
- Findings persisted to `planning/databricks_apps_research.md` (12 sections, ~15 sources).
- Key facts: Python 3.11 + uvicorn/fastapi pre-installed; single port `$DATABRICKS_APP_PORT`; no local FS persistence; SPA + API single-process via FastAPI `StaticFiles` + sub-app at `/api`; secrets via `valueFrom`; OBO auth via `X-Forwarded-*` headers; Medium=2vCPU/6GB default.
- Phase 7 conversion plan written with 4 open decisions for the user.

## Session 3 — 2026-05-27 — Conversion executed

User decisions: workspace path `/Workspace/Users/bwise@redventures.com/data/conversations`; workspace-shared; keep both local-dev flows; keep `pyproject.toml`. Secret already exists at scope `finserv-ds-ai-api`, key `OPENROUTER_API_KEY`.

New files at repo root:
- `app.py` — top-level FastAPI; re-exports `backend.main:app` and mounts `frontend/dist/` at `/` when present.
- `run_app.py` — launcher; reads `DATABRICKS_APP_PORT`, calls `uvicorn.run("app:app", host="0.0.0.0", port=port)`.
- `app.yaml` — `command: ["python", "run_app.py"]`; `OPENROUTER_API_KEY` via `valueFrom: openrouter_api_key`; `DATA_DIR` set to the workspace conversations path.
- `requirements.txt` — mirrors `pyproject.toml` deps.

Files modified:
- `backend/config.py` — `DATA_DIR` now read from env (default `data/conversations`).
- `frontend/src/api.js` — `API_BASE = ''` (relative paths, same-origin).
- `frontend/vite.config.js` — proxy `/api → http://localhost:8001` for `npm run dev`.
- `README.md` — added "Deploy to Databricks Apps" section with one-time setup, deploy commands, and local-vs-Databricks comparison.
- `CLAUDE.md` — refreshed `config.py`/`main.py` notes; added "Databricks Apps Deployment" section; updated Port Configuration.

Smoke test: `uv run python -c "import app"` succeeded; 10 routes registered. Backend route surface unchanged.

Out of scope and explicitly skipped: `databricks.yml` bundle file (optional, can add later); `Makefile` build helper; deleting the vestigial root `main.py` stub.

User actions still required before first deploy:
1. Create the app in Databricks (`databricks apps create llm-council` or UI).
2. Add the secret as an app resource with resource key **`openrouter_api_key`** (must match `app.yaml`).
3. Create `/Workspace/Users/bwise@redventures.com/data/conversations/` and grant the app's service principal `Can Edit`.
4. `cd frontend && npm install && npm run build` before each deploy.
