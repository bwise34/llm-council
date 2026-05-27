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

## Session 5 — 2026-05-27 — Storage backend for `/Workspace/...`

Symptom after the SPA started rendering: "+ New Conversation" did nothing and no input field appeared. Root cause: `storage.py` was writing JSON via plain `open(path, "w")`, but `/Workspace/...` is the Databricks **Workspace Files API namespace** — not a directly mounted filesystem in the Databricks Apps container. The POSIX `open()` raised, `create_conversation` 500'd, the frontend caught the error silently in `App.jsx:51`, `currentConversationId` was never set, and `ChatInterface` stayed on the "Welcome" screen (where no input is rendered).

Fix: `backend/storage.py` now has two code paths, selected by `DATA_DIR.startswith("/Workspace/")`:
- **Local FS** (default): unchanged `open()` / `os.listdir`.
- **Workspace Files API**: `WorkspaceClient.workspace.{mkdirs, upload, download, list, get_status}`. The SDK is constructed with no args; it picks up `DATABRICKS_CLIENT_ID` / `DATABRICKS_CLIENT_SECRET` / `DATABRICKS_HOST` injected by the Databricks Apps runtime.

Helpers (`_ensure_dir`, `_read_json`, `_write_json`, `_list_json_paths`) abstract the two backends; the existing public functions (`create_conversation`, `list_conversations`, `add_user_message`, etc.) are unchanged in behavior. `NotFound` from `databricks.sdk.errors` is treated as "file doesn't exist" — matches the prior `os.path.exists` semantics. Also bumped `datetime.utcnow()` → `datetime.now(timezone.utc)` (the deprecated form).

Deps added to both `pyproject.toml` and `requirements.txt`: `databricks-sdk>=0.30.0`.

Smoke test: both branches initialize cleanly under `uv run`; SDK imports resolve in workspace mode.

User actions to redeploy:
1. `make deploy` (build + sync + apps deploy) — the sync will now also include the new `pyproject.toml`/`requirements.txt`/`storage.py`.
2. Confirm the app's service principal has **Can Edit** on `/Workspace/Users/bwise@redventures.com/llm-council-data/` (or pre-create that folder so the SP only needs permission on its parent).
3. If "New Conversation" still fails, open the app's page in Databricks and view the Logs tab — the SDK will raise `PermissionDenied` with a clear message if the SP lacks workspace write rights.

## Session 4 — 2026-05-27 — Post-deploy bug fixes

User's first deploy showed only `{"status":"ok","service":"LLM Council API"}` at the app root — no SPA. Two root causes, both real and compounding:

1. **Route shadowing.** `backend/main.py` had `@app.get("/")` returning the JSON health blob. In FastAPI, defined routes win over mounts, so `app.mount("/", StaticFiles(...))` in `app.py` could never serve `/`. Fix: renamed the health endpoint to `/api/health`.
2. **`databricks sync` respects `.gitignore` and `frontend/dist/` was gitignored.** `.databricksignore` is not yet a supported override (databricks/cli#1192). The build artifact was therefore silently skipped on upload; my `if os.path.isdir(FRONTEND_DIST)` guard in `app.py` meant the StaticFiles mount was never registered at all in the deployed container. Fix: removed `frontend/dist/` from `.gitignore` with an inline comment explaining the tradeoff. Recommended `.git/info/exclude` as a per-clone alternative for users who don't want dist tracked.

Verified locally: `uv run python -c "import app"` now shows 11 routes; `/` falls through to the StaticFiles mount; `/api/health` returns the status blob.

Added in same session (before the bug report): `databricks.yml` (bundle root with `resources.apps.llm_council`) and `Makefile` (`install`, `dev`, `local-databricks`, `build`, `sync`, `deploy`, `bundle-validate`, `bundle-deploy`, `clean`).

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
