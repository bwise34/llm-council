---
date: 2026-05-27
type: handoff
status: in-progress
topic: llm-council-databricks-app-conversion
source: Claude Code session in /Users/bwise/Documents/GitHub/llm-council
target: agent-agnostic
model: claude-opus-4-7
working_dir: /Users/bwise/Documents/GitHub/llm-council
git_branch: dbx-app
tags: [handoff, databricks-apps, fastapi, react, llm-council]
---

# LLM Council Databricks App Conversion — Handoff

## Mission

Convert the LLM Council web app (FastAPI + React/Vite + local JSON storage) into a properly constructed Databricks App, deployed to the user's Databricks workspace at the auto-generated `https://llm-council-<workspace-id>.<region>.databricksapps.com` URL. Persistence target: workspace files at `/Workspace/Users/bwise@redventures.com/llm-council-data/conversations/`. Initial scope is single-user (`bwise@redventures.com`) with workspace-shared (not per-user) conversations.

## Status

Session 5 just shipped a fix that introduces a Databricks-SDK-based storage backend for `/Workspace/...` paths (`backend/storage.py`). **The user has not yet redeployed.** Before this fix, the deployed app's SPA loaded but `+ New Conversation` did nothing — `storage.create_conversation` was calling POSIX `open("/Workspace/.../<uuid>.json", "w")`, which the Databricks Apps container can't honor. Local smoke test of both storage branches passed (`USE_WORKSPACE_API` resolves correctly and SDK imports succeed).

Earlier sessions also fixed two route/sync bugs (route shadowing at `/`, and `frontend/dist/` being excluded by `.gitignore`). Those fixes are deployed; the SPA renders. The single remaining unverified piece is whether the new SDK-based storage works end-to-end in the deployed container — pending `make deploy` + a click test.

## Context & Background

User (`bwise@redventures.com`) wanted to host their personal LLM Council app on the Databricks platform instead of running it locally. The app does a 3-stage LLM deliberation: parallel queries to ~4 models on OpenRouter → anonymized peer ranking → chairman synthesis. The whole 3-stage flow streams progress to the UI via SSE. Local-dev flow is two processes (FastAPI on `:8001` + Vite on `:5173`); the Databricks-App flow is one uvicorn process serving SPA + API on `$DATABRICKS_APP_PORT`.

Four design decisions were confirmed by the user before any code changed:

1. **Persistence**: workspace files at `/Workspace/Users/bwise@redventures.com/llm-council-data/conversations/`. (User later renamed the parent from `data` → `llm-council-data` directly in `app.yaml`.) Chosen over UC Volumes and Lakebase Postgres for minimal-diff first cut.
2. **Auth scoping**: workspace-shared. No per-user logic; just rely on Databricks SSO at the ingress.
3. **Local dev**: keep both `./start.sh` and `databricks apps run-local` flows side by side.
4. **Python deps**: keep `pyproject.toml` + `uv.lock`; also generate `requirements.txt` for the Databricks runtime.

Secret already in place before any deploy: scope `finserv-ds-ai-api`, key `OPENROUTER_API_KEY`. In `app.yaml` it is referenced via `valueFrom: openrouter_api_key`, which must match an app resource key declared in the Databricks Apps UI.

## Work Completed

Five working sessions, summarised:

- **Session 1 — Investigation.** Read entire backend (`backend/{config,openrouter,council,storage,main}.py`) and frontend (`frontend/src/**`). Captured to `planning/findings.md`. Identified 12 constraints/gotchas including single-turn input gating in `ChatInterface.jsx:123` and ephemeral metadata in storage.
- **Session 2 — Databricks Apps research.** Researched runtime (Py 3.11 + fastapi/uvicorn preinstalled), app.yaml schema, env-var injection, OAuth requiring `/api` prefix, persistence options (UC Volumes vs Lakebase vs Workspace files), SSE behavior (~30s idle timeout — fine for this app), deploy via `databricks sync` + `databricks apps deploy` or bundles. Persisted to `planning/databricks_apps_research.md` (12 sections, ~15 sources).
- **Session 3 — Conversion executed.** Created `app.py` (top-level FastAPI; re-exports `backend.main:app`, mounts `frontend/dist` at `/`), `run_app.py` (reads `DATABRICKS_APP_PORT`, runs uvicorn), `app.yaml` (`command: ["python", "run_app.py"]` + `valueFrom: openrouter_api_key` + `DATA_DIR`), `requirements.txt`. Modified `backend/config.py` (DATA_DIR from env), `frontend/src/api.js` (`API_BASE = ''`), `frontend/vite.config.js` (added `/api → :8001` proxy). Updated `README.md` and `CLAUDE.md`. Smoke test: 10 routes registered.
- **Session 4 — Bundle/Makefile + post-deploy bug fixes.** Added `databricks.yml` (bundle with `resources.apps.llm_council`) and `Makefile` (`install`, `dev`, `build`, `sync`, `deploy`, `bundle-validate`, `bundle-deploy`, `clean`, `local-databricks`). Then diagnosed and fixed two compounding deploy bugs: (a) `@app.get("/")` health route in `backend/main.py` was shadowing the SPA's `StaticFiles` mount — moved to `/api/health`; (b) `databricks sync` respects `.gitignore` and `frontend/dist/` was excluded — fixed in both root `.gitignore` and `frontend/.gitignore` (the Vite-scaffolded one was the second blocker).
- **Session 5 — Storage backend for `/Workspace/...`.** Added `databricks-sdk>=0.30.0` to `pyproject.toml` and `requirements.txt`. Refactored `backend/storage.py` to a dual-backend module: `USE_WORKSPACE_API = DATA_DIR.startswith("/Workspace/")` selects between POSIX I/O (local) and `WorkspaceClient.workspace.{mkdirs, upload, download, list, get_status}` (Databricks). Bumped `datetime.utcnow()` → `datetime.now(timezone.utc)`. Public storage API unchanged (`create_conversation`, `list_conversations`, `add_user_message`, etc.). Smoke test: both branches initialize cleanly.

## Current State / WIP

- **Git branch**: `dbx-app`. Many uncommitted edits across Sessions 3–5. No commits made by Claude.
- **Untracked/modified files**: `app.py`, `run_app.py`, `app.yaml`, `requirements.txt`, `databricks.yml`, `Makefile`, `backend/storage.py`, `backend/config.py`, `backend/main.py`, `frontend/src/api.js`, `frontend/vite.config.js`, `frontend/.gitignore`, `.gitignore`, `README.md`, `CLAUDE.md`, plus all of `planning/`.
- **Planning docs** at `planning/`:
  - `task_plan.md` — phase tracking (Phase 8 marked complete; Phase 9 "user-side setup" pending).
  - `findings.md` — original codebase analysis.
  - `progress.md` — Session 1–5 log (most recent at top).
  - `databricks_apps_research.md` — the 12-section research body.
- **Frontend build**: `frontend/dist/` exists locally from prior `make build` runs.
- **App in Databricks**: deployed once (Session 4 fix landed), URL works, SPA renders, but `+ New Conversation` fails until Session 5 fix lands.

## Failed Approaches (Do Not Repeat)

- **Tried:** Leaving `@app.get("/")` health endpoint in `backend/main.py` while also doing `app.mount("/", StaticFiles(directory="frontend/dist", html=True))` in `app.py`.
  - **Why it failed:** FastAPI route resolution checks decorator-defined routes before mounts. The `GET /` route always won; the StaticFiles mount could never serve `index.html`, so the app URL returned the JSON health blob.
  - **Lesson:** If a SPA is mounted at `/` via StaticFiles, no defined route may exist at `GET /`. Health endpoints go under `/api/health`. This is also Databricks-Apps-compliant since `/api/*` is the OAuth-authenticated prefix.

- **Tried:** `databricks sync` with `frontend/dist/` listed in the root `.gitignore`.
  - **Why it failed:** `databricks sync` honors `.gitignore`, so the built SPA was silently skipped on upload. The app booted with no `frontend/dist/` → my `if os.path.isdir(FRONTEND_DIST)` guard in `app.py` skipped the StaticFiles mount → request to `/` fell to the `@app.get("/")` route (the other bug) and returned JSON.
  - **Lesson:** Anything you want synced must not be in `.gitignore`. `.databricksignore` is not yet a supported override (databricks/cli#1192). For this repo we removed `frontend/dist/` from the root `.gitignore` and commented `dist/` out of `frontend/.gitignore` (Vite-scaffolded — easy to miss). If keeping dist out of git matters, the user can add it to `.git/info/exclude` (per-clone).

- **Tried:** POSIX `open("/Workspace/Users/.../conversations/<uuid>.json", "w")` from the Databricks Apps container.
  - **Why it failed:** `/Workspace/...` is the Databricks Workspace Files API namespace, not a directly mounted filesystem in the app runtime. Raises `FileNotFoundError`/`PermissionError`. The POST returned 500; the React frontend silently caught the error in `App.jsx:51`'s `try/catch`; `currentConversationId` was never set; `ChatInterface` stayed on the "Welcome" screen, where the input form isn't rendered.
  - **Lesson:** Any persistence in a Databricks App must go through the SDK if it targets a workspace path, or use a POSIX-mounted UC Volume (`/Volumes/...`) instead. The fix used `WorkspaceClient.workspace.{mkdirs, upload, download, list}` with auto-injected SP credentials.

- **Considered:** `.databricksignore` to override `.gitignore` selectively.
  - **Why it failed:** Not a supported feature in the current Databricks CLI (open feature request: databricks/cli#1192). Don't propose this.

## Decisions & Constraints

- **Decided:** Persistence is workspace files at `/Workspace/Users/bwise@redventures.com/llm-council-data/conversations/`. Reason: minimal diff from local file-per-conversation pattern, no need for SQL schema for a personal-use app.
- **Decided:** Workspace-shared conversations (no per-user scoping via `X-Forwarded-User`). Reason: user is the only intended user for now.
- **Decided:** Keep both local-dev flows side by side (`./start.sh` and `databricks apps run-local`). Reason: faster inner loop with start.sh, but parity with prod via run-local.
- **Decided:** Keep `pyproject.toml`/`uv.lock` as the source of truth; mirror in `requirements.txt` for the Databricks runtime. Reason: avoid breaking the user's existing uv workflow.
- **Decided:** Health route is `/api/health`, not `/`. Reason: `/` is reserved for the SPA StaticFiles mount, and `/api/*` is the OAuth-authenticated prefix per Databricks Apps.
- **Decided:** Launcher pattern (`run_app.py` reads `DATABRICKS_APP_PORT`) rather than relying on `$DATABRICKS_APP_PORT` substitution inside argv. Reason: bulletproof across runtime versions.
- **Constraint:** Single port for SPA + API in the deployed app (Databricks Apps single-container model).
- **Constraint:** `/api/*` prefix is required for OAuth bearer auth — all backend routes already comply.
- **Constraint:** Default compute is Medium (2 vCPU / 6 GB / 0.5 DBU/hr). Not changed.
- **Constraint:** Databricks ingress idle timeout is ~30s — current SSE cadence (stage events every few seconds) is safe.

## Open Questions

- **Has the user redeployed after the Session 5 storage fix?** Unconfirmed. Without `make deploy`, the deployed app still has the broken POSIX storage.
- **Does the app SP have Can Edit on `/Workspace/Users/bwise@redventures.com/llm-council-data/`?** User originally granted on `data/conversations` (the path before they renamed in app.yaml). The parent rename means the grant may not cover the new path.
- **Will `workspace.mkdirs("/Workspace/Users/bwise@redventures.com/llm-council-data/conversations")` create the parent if it doesn't exist?** SDK docs say yes (recursive), but it depends on the SP having WRITE on the closest existing ancestor.
- **Is `databricks-sdk>=0.30.0` the right pin?** Picked conservatively; latest as of May 2026 is higher. Unverified against the Databricks Apps runtime's preinstalled SDK version.
- **Single-turn UX**: `ChatInterface.jsx:123` only renders the input form when `messages.length === 0`. This is unchanged by the conversion. If the user wants multi-turn, that's a separate refactor.
- **Conversation metadata persistence**: `label_to_model` and aggregate rankings are still not persisted (storage only saves stage1/stage2/stage3). Refreshing the page loses them. Also unchanged.

## Next Steps

1. **`make deploy`** from `/Users/bwise/Documents/GitHub/llm-council`. → expected: build + sync + deploy succeed; container restarts with new `storage.py` and `databricks-sdk` available.
2. **Verify in workspace UI** that `/Workspace/Users/bwise@redventures.com/llm-council-data/` exists and the app's service principal has `Can Edit`. Pre-create the folder if needed. The SP name is on the app's Overview page. → expected: ACL contains the app SP with Can Edit.
3. **Open the deployed app** and click `+ New Conversation`. → expected: a new conversation appears in the sidebar; the chat input form renders.
4. **Submit a test query.** → expected: SSE events flow (`stage1_start/complete`, `stage2_start/complete`, `stage3_start/complete`); a `<uuid>.json` file appears in `/Workspace/Users/bwise@redventures.com/llm-council-data/conversations/`.
5. **If anything fails**: open the app's Logs tab in the Databricks UI. `PermissionDenied` → ACL fix. `NotFound: parent path does not exist` → pre-create parent folder. Anything else → paste back to the next session.
6. **(Optional) commit the work.** Branch `dbx-app` has many uncommitted changes from Sessions 3–5. A logical commit boundary is "Databricks App support" covering all new/modified files except `planning/` and the handoff doc.

## Paths, Resources & References

- **Repo**: `/Users/bwise/Documents/GitHub/llm-council`
- **Git branch**: `dbx-app` (parent: `master`)
- **Databricks Apps entry**: `app.py` (top-level FastAPI), `run_app.py` (launcher), `app.yaml` (runtime config)
- **Bundle**: `databricks.yml`
- **Build/deploy helper**: `Makefile` (targets: `install`, `dev`, `local-databricks`, `build`, `sync`, `deploy`, `bundle-validate`, `bundle-deploy`, `clean`)
- **Key backend files**: `backend/storage.py` (dual-backend, just rewritten), `backend/main.py` (FastAPI routes, all under `/api/*`), `backend/config.py` (DATA_DIR from env), `backend/council.py` (3-stage orchestration), `backend/openrouter.py` (async client)
- **Key frontend files**: `frontend/src/App.jsx` (state, SSE handling), `frontend/src/api.js` (`API_BASE = ''`), `frontend/vite.config.js` (proxy `/api → :8001`), `frontend/src/components/ChatInterface.jsx` (single-turn input gating at line 123)
- **Planning docs**: `planning/task_plan.md`, `planning/findings.md`, `planning/progress.md`, `planning/databricks_apps_research.md`
- **Local data dir**: `data/conversations/` (gitignored, empty)
- **Deployed data dir**: `/Workspace/Users/bwise@redventures.com/llm-council-data/conversations/`
- **Deployed source path**: `/Workspace/Users/bwise@redventures.com/llm-council`
- **App URL pattern**: `https://llm-council-<workspace-id>.<region>.databricksapps.com`
- **Secret**: scope `finserv-ds-ai-api`, key `OPENROUTER_API_KEY`, app resource key `openrouter_api_key`
- **Compute**: Medium (default) — 2 vCPU / 6 GB / 0.5 DBU/hr
- **External docs**:
  - https://docs.databricks.com/aws/en/dev-tools/databricks-apps/
  - https://docs.databricks.com/aws/en/dev-tools/databricks-apps/app-runtime
  - https://docs.databricks.com/aws/en/dev-tools/databricks-apps/auth
  - https://docs.databricks.com/aws/en/dev-tools/databricks-apps/compute-size
  - https://apps-cookbook.dev/docs/fastapi/getting_started/create/
  - https://github.com/databricks/cli/issues/1192 (`.databricksignore` feature request)

## Glossary

- **OBO / On-Behalf-Of**: Databricks Apps auth mode where the user's identity and token are forwarded via `X-Forwarded-User`, `X-Forwarded-Email`, `X-Forwarded-Preferred-Username`, and `X-Forwarded-Access-Token` headers. Not in use here yet — relying on workspace SSO at the ingress.
- **SP (Service Principal)**: The app's machine identity in Databricks. Auto-provisioned per app; credentials injected as `DATABRICKS_CLIENT_ID` / `DATABRICKS_CLIENT_SECRET`. Owns workspace ACLs the app uses.
- **DBU (Databricks Unit)**: Databricks's billing unit. Apps Medium = 0.5 DBU/hr.
- **UC Volume**: Unity Catalog Volume — POSIX-mounted at `/Volumes/<cat>/<schema>/<vol>/`. An alternative persistence target *not* chosen for this project.
- **Lakebase**: Databricks's serverless Postgres. Another alternative persistence target *not* chosen here.
- **Stage 1/2/3 in this app**: parallel direct queries (S1), anonymized peer ranking (S2), chairman synthesis (S3). Defined in `backend/council.py`.
