"""Launcher for Databricks Apps.

Reads the runtime-injected `DATABRICKS_APP_PORT` and starts uvicorn against
the top-level `app:app`. The launcher pattern avoids depending on argv
substitution rules inside `app.yaml`.
"""

import os

import uvicorn

if __name__ == "__main__":
    port = int(os.environ.get("DATABRICKS_APP_PORT", "8000"))
    uvicorn.run("app:app", host="0.0.0.0", port=port)
