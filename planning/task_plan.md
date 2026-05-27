# Task Plan: LLM Council → Databricks App

## Goal
Convert this generic web app (FastAPI + React/Vite + local JSON persistence) into a properly constructed Databricks App hosted on the Databricks platform. Investigation and research come first; no code changes until the user approves the plan.

## Phases

### Phase 1: Backend deep-dive — complete
Read every file in `backend/`. Captured API surface, 3-stage flow, anonymization, ranking parser, persistence shape, SSE event types, hardcoded model IDs, title-gen flow. See `planning/findings.md`.

### Phase 2: Frontend deep-dive — complete
Read all `frontend/src/**` plus build config. Captured state shape, optimistic SSE-driven UI updates, single-turn input gating, client-side de-anonymization. See `planning/findings.md`.

### Phase 3: Glue & config — complete
Read `start.sh`, `pyproject.toml`, `.gitignore`. Confirmed `data/conversations/` is empty.

### Phase 4: Cross-cutting synthesis — complete
End-to-end request trace; 12 constraints/gotchas; 9 likely refactor seams; CLAUDE.md staleness flagged.

### Phase 5: Refactor goal received — complete
Convert to a Databricks App.

### Phase 6: Databricks Apps research — complete
See `planning/databricks_apps_research.md` for the full body. Highlights:
- Python 3.11; FastAPI + uvicorn pre-installed.
- App must bind `0.0.0.0:$DATABRICKS_APP_PORT`.
- No local-FS persistence; use UC Volumes or Lakebase Postgres.
- Secrets via `valueFrom` against a declared resource — never inline.
- OAuth requires routes under `/api` — current code already complies.
- Single-process SPA pattern: mount `/api` first, then `StaticFiles(frontend/dist, html=True)` at `/`.
- Compute: Medium (2 vCPU / 6 GB, 0.5 DBU/hr) default; Large is 4 vCPU / 12 GB / 1 DBU/hr.
- Ingress idle timeout ~30s — current SSE cadence is safe.
- Deploy via `databricks sync` + `databricks apps deploy`, or Asset Bundles.

### Phase 7: Conversion plan — complete (user approved all four decisions)

#### Current → Databricks-App mapping
| Current | Target | Change |
|---|---|---|
| Two processes (`:8001` API + `:5173` Vite) | One process on `$DATABRICKS_APP_PORT` | New top-level `app.py` mounting `/api` sub-app + `StaticFiles(frontend/dist)` at `/` |
| Routes at `/api/*` | Same | None — already compliant |
| `.env` → `OPENROUTER_API_KEY` | Databricks secret scope + `valueFrom` | Add secret, declare app resource, reference in `app.yaml` |
| `data/conversations/*.json` local | UC Volume **or** Lakebase | Decision needed |
| `api.js` hardcodes `http://localhost:8001` | Same-origin (relative paths) | `API_BASE = ''` |
| CORS to `localhost:5173/3000` | Same-origin in prod | Drop CORS for prod path |
| `pyproject.toml + uv.lock` | Same (or `requirements.txt`) | Decision needed; both work |
| No `app.yaml` | Required | New |
| No `databricks.yml` | Optional but recommended for CI/CD | New |
| `start.sh` | Replaced or kept for local | Decision needed |
| `frontend/` dev server | Vite **build** to `frontend/dist/` | Add to deploy workflow |

#### Open decisions to ask the user
1. **Persistence backend** — UC Volume (file-based, minimal code change) vs Lakebase Postgres (relational, transactions, scales). Recommendation: UC Volume for first cut.
2. **Auth scoping** — workspace-shared conversations (no app changes) vs per-user via `X-Forwarded-User`. Recommendation: workspace-shared first.
3. **Local dev flow** — keep current `start.sh` + Vite dev server, or move to `databricks apps run-local`. Recommendation: keep both.
4. **Python deps** — `requirements.txt` (simplest, widest doc support) vs `pyproject.toml + uv.lock` (already present). Recommendation: keep `pyproject.toml`.

#### Concrete sub-phases (executed after user approval)
- **7a — Backend**
  - New `app.py` at repo root: top-level FastAPI mounting the existing `backend.main:app` at `/api` and `frontend/dist` at `/`.
  - `backend/main.py`: drop the hardcoded host/port `__main__` block (or gate behind env); only enable CORS when running locally.
  - `backend/config.py`: keep `load_dotenv()` (no-op when env already populated); read `OPENROUTER_API_KEY` from env (already does).
  - `backend/storage.py`: read `DATA_DIR` from env so prod can use `/Volumes/.../conversations`.
- **7b — Frontend**
  - `frontend/src/api.js`: `API_BASE = ''`.
  - `frontend/vite.config.js`: add proxy for `/api` to `:8001` during `npm run dev` (so dev mirrors prod routing).
  - Confirm `frontend/dist` is the build output path.
- **7c — Databricks files**
  - `app.yaml` at repo root with uvicorn command, `OPENROUTER_API_KEY` via `valueFrom`, `DATA_DIR` value.
  - `requirements.txt` (or rely on `pyproject.toml`).
  - Updated `.gitignore` to keep `frontend/dist/` deployable (currently git-ignored but that's fine — Databricks sync follows its own ignore rules; `frontend/dist/` must be **present at deploy time**, so the build runs before `databricks sync`).
  - Optional `databricks.yml` for bundle deploys.
  - Optional `Makefile` / build script: `cd frontend && npm install && npm run build && databricks sync ... && databricks apps deploy ...`
- **7d — Docs**
  - Update `README.md` with Databricks deploy steps.
  - Update `CLAUDE.md` to reflect the new architecture.

### Phase 8: Execute approved phases — complete

- 7a — Backend: created `app.py` (top-level wrapper), updated `backend/config.py` (DATA_DIR from env).
- 7b — Frontend: `api.js` → `API_BASE = ''`; Vite proxy added in `vite.config.js`.
- 7c — Databricks files: `app.yaml`, `run_app.py`, `requirements.txt` created at repo root.
- 7d — Docs: README "Deploy to Databricks Apps" section + comparison table; CLAUDE.md "Databricks Apps Deployment" section + config/port notes refreshed.
- Smoke test: `uv run python -c "import app"` ✓ (10 routes registered).

### Phase 9: User-side setup (not code) — pending the user

1. `databricks apps create llm-council` (or use the UI).
2. Add the OpenRouter secret as an app resource with resource key `openrouter_api_key`.
3. Create `/Workspace/Users/bwise@redventures.com/data/conversations/` and grant the app SP `Can Edit`.
4. Run `cd frontend && npm install && npm run build`, then `databricks sync . /Workspace/Users/bwise@redventures.com/llm-council`, then `databricks apps deploy llm-council --source-code-path /Workspace/Users/bwise@redventures.com/llm-council`.

## Out of scope (until user requests)
- Multi-turn UX refactor.
- Per-model error surfacing.
- Switching ranking to structured JSON output.
- Conversation rename / delete.

## Errors Encountered
| Error | Attempt | Resolution |
|-------|---------|------------|
| `Edit` on `task_plan.md` failed after file was `mv`'d into `planning/` | 1 | Re-read the moved file; rewrote with `Write` instead of `Edit`. |
