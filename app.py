"""Top-level FastAPI entry point for Databricks Apps deployment.

Re-exports the existing `backend.main:app` (which serves all routes under
`/api/*`) and mounts the built React SPA at `/` when `frontend/dist/`
exists. In local-dev (`./start.sh`) this file is unused — `backend.main`
runs standalone on :8001 and Vite serves the SPA on :5173 with a `/api`
proxy.
"""

import os

from fastapi.staticfiles import StaticFiles

from backend.main import app

FRONTEND_DIST = os.environ.get("FRONTEND_DIST", "frontend/dist")

if os.path.isdir(FRONTEND_DIST):
    app.mount(
        "/",
        StaticFiles(directory=FRONTEND_DIST, html=True),
        name="frontend",
    )
