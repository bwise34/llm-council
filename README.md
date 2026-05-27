# LLM Council

![llmcouncil](header.jpg)

The idea of this repo is that instead of asking a question to your favorite LLM provider (e.g. OpenAI GPT 5.1, Google Gemini 3.0 Pro, Anthropic Claude Sonnet 4.5, xAI Grok 4, eg.c), you can group them into your "LLM Council". This repo is a simple, local web app that essentially looks like ChatGPT except it uses OpenRouter to send your query to multiple LLMs, it then asks them to review and rank each other's work, and finally a Chairman LLM produces the final response.

In a bit more detail, here is what happens when you submit a query:

1. **Stage 1: First opinions**. The user query is given to all LLMs individually, and the responses are collected. The individual responses are shown in a "tab view", so that the user can inspect them all one by one.
2. **Stage 2: Review**. Each individual LLM is given the responses of the other LLMs. Under the hood, the LLM identities are anonymized so that the LLM can't play favorites when judging their outputs. The LLM is asked to rank them in accuracy and insight.
3. **Stage 3: Final response**. The designated Chairman of the LLM Council takes all of the model's responses and compiles them into a single final answer that is presented to the user.

## Vibe Code Alert

This project was 99% vibe coded as a fun Saturday hack because I wanted to explore and evaluate a number of LLMs side by side in the process of [reading books together with LLMs](https://x.com/karpathy/status/1990577951671509438). It's nice and useful to see multiple responses side by side, and also the cross-opinions of all LLMs on each other's outputs. I'm not going to support it in any way, it's provided here as is for other people's inspiration and I don't intend to improve it. Code is ephemeral now and libraries are over, ask your LLM to change it in whatever way you like.

## Setup

### 1. Install Dependencies

The project uses [uv](https://docs.astral.sh/uv/) for project management.

**Backend:**
```bash
uv sync
```

**Frontend:**
```bash
cd frontend
npm install
cd ..
```

### 2. Configure API Key

Create a `.env` file in the project root:

```bash
OPENROUTER_API_KEY=sk-or-v1-...
```

Get your API key at [openrouter.ai](https://openrouter.ai/). Make sure to purchase the credits you need, or sign up for automatic top up.

### 3. Configure Models (Optional)

Edit `backend/config.py` to customize the council:

```python
COUNCIL_MODELS = [
    "openai/gpt-5.1",
    "google/gemini-3-pro-preview",
    "anthropic/claude-sonnet-4.5",
    "x-ai/grok-4",
]

CHAIRMAN_MODEL = "google/gemini-3-pro-preview"
```

## Running the Application

**Option 1: Use the start script**
```bash
./start.sh
```

**Option 2: Run manually**

Terminal 1 (Backend):
```bash
uv run python -m backend.main
```

Terminal 2 (Frontend):
```bash
cd frontend
npm run dev
```

Then open http://localhost:5173 in your browser.

## Deploy to Databricks Apps

This app can also be deployed as a [Databricks App](https://docs.databricks.com/aws/en/dev-tools/databricks-apps/) — a serverless, workspace-authenticated web service. The same FastAPI backend serves both the React SPA (built to static assets) and the `/api/*` routes on a single port.

### One-time setup (in Databricks)

1. **Create a secret** with your OpenRouter key (skip if already done):
   ```bash
   databricks secrets create-scope finserv-ds-ai-api    # only if scope doesn't exist
   databricks secrets put-secret finserv-ds-ai-api OPENROUTER_API_KEY
   ```
2. **Create the app** in the workspace UI (`Apps` → `+ Create app` → `Custom`) or via CLI:
   ```bash
   databricks apps create llm-council
   ```
3. **Add the OpenRouter secret as an app resource** so `app.yaml`'s `valueFrom` can reference it. In the app's `Resources` section: `+ Add resource → Secret`, set scope `finserv-ds-ai-api`, key `OPENROUTER_API_KEY`, and **resource key `openrouter_api_key`** (this name must match `app.yaml`).
4. **Create the conversations folder** (only the first time):
   - In the workspace UI, create `data/conversations/` under your user folder.
   - Right-click → Permissions → grant the app's service principal `Can Edit`. The service principal is shown on the app's Overview page; its name is the app's client ID.

### Deploy

```bash
# 1. Build the React frontend so frontend/dist/ exists locally
cd frontend && npm install && npm run build && cd ..

# 2. Sync your project to the workspace (creates the folder if missing)
databricks sync . /Workspace/Users/bwise@redventures.com/llm-council

# 3. Deploy (starts or updates the running app)
databricks apps deploy llm-council \
  --source-code-path /Workspace/Users/bwise@redventures.com/llm-council
```

The app URL is shown on the app's Overview page (`https://llm-council-<workspace-id>.<region>.databricksapps.com`).

### How the Databricks deployment differs from local

| | Local (`./start.sh`) | Databricks App |
|---|---|---|
| Processes | 2 (FastAPI :8001 + Vite :5173) | 1 (uvicorn on `$DATABRICKS_APP_PORT`) |
| Frontend served by | Vite dev server | FastAPI `StaticFiles` from `frontend/dist/` |
| `/api` requests | Vite proxy → :8001 | Same-origin to the same FastAPI process |
| `OPENROUTER_API_KEY` | `.env` (loaded by `python-dotenv`) | Databricks secret via `valueFrom` |
| `DATA_DIR` | `./data/conversations` | `/Workspace/Users/.../data/conversations` |
| Auth | none | Workspace SSO at the ingress |

The relevant files for Databricks deployment are `app.py`, `run_app.py`, `app.yaml`, and `requirements.txt` at the repo root.

## Tech Stack

- **Backend:** FastAPI (Python 3.10+), async httpx, OpenRouter API
- **Frontend:** React + Vite, react-markdown for rendering
- **Storage:** JSON files — local `data/conversations/` or a workspace path on Databricks
- **Package Management:** uv for Python, npm for JavaScript
- **Hosting:** Local dev or Databricks Apps (serverless)
