# CLAUDE.md - Technical Notes for LLM Council

This file contains technical details, architectural decisions, and important implementation notes for future development sessions.

## Project Overview

LLM Council is a 3-stage deliberation system where multiple LLMs collaboratively answer user questions. The key innovation is anonymized peer review in Stage 2, preventing models from playing favorites.

## Architecture

### Backend Structure (`backend/`)

**`config.py`**
- Contains `COUNCIL_MODELS` (list of OpenRouter model identifiers)
- Contains `CHAIRMAN_MODEL` (model that synthesizes final answer)
- Reads `OPENROUTER_API_KEY` from env (loaded from `.env` locally, injected via Databricks secret in prod)
- Reads `DATA_DIR` from env, defaults to `data/conversations`
- In local dev the backend runs on **port 8001**; in Databricks Apps the port comes from `DATABRICKS_APP_PORT`

**`openrouter.py`**
- `query_model()`: Single async model query
- `query_models_parallel()`: Parallel queries using `asyncio.gather()`
- Returns dict with 'content' and optional 'reasoning_details'
- Graceful degradation: returns None on failure, continues with successful responses

**`council.py`** - The Core Logic
- `stage1_collect_responses()`: Parallel queries to all council models
- `stage2_collect_rankings()`:
  - Anonymizes responses as "Response A, B, C, etc."
  - Creates `label_to_model` mapping for de-anonymization
  - Prompts models to evaluate and rank (with strict format requirements)
  - Returns tuple: (rankings_list, label_to_model_dict)
  - Each ranking includes both raw text and `parsed_ranking` list
- `stage3_synthesize_final()`: Chairman synthesizes from all responses + rankings
- `parse_ranking_from_text()`: Extracts "FINAL RANKING:" section, handles both numbered lists and plain format
- `calculate_aggregate_rankings()`: Computes average rank position across all peer evaluations

**`storage.py`**
- JSON-based conversation storage in `data/conversations/`
- Each conversation: `{id, created_at, messages[]}`
- Assistant messages contain: `{role, stage1, stage2, stage3}`
- Note: metadata (label_to_model, aggregate_rankings) is NOT persisted to storage, only returned via API

**`main.py`**
- FastAPI app. CORS allows `localhost:5173`/`localhost:3000` — harmless in prod (same-origin) and useful for legacy local-dev where the React app talks to a separate origin
- Both `/api/conversations/{id}/message` (blocking) and `/api/conversations/{id}/message/stream` (SSE) return metadata
- Stream events: `stage1_start/complete`, `stage2_start/complete`, `stage3_start/complete`, `title_complete`, `complete`, `error`
- Metadata includes: label_to_model mapping and aggregate_rankings (not persisted to disk — only on live API responses)

### Frontend Structure (`frontend/src/`)

**`App.jsx`**
- Main orchestration: manages conversations list and current conversation
- Handles message sending and metadata storage
- Important: metadata is stored in the UI state for display but not persisted to backend JSON

**`components/ChatInterface.jsx`**
- Multiline textarea (3 rows, resizable)
- Enter to send, Shift+Enter for new line
- User messages wrapped in markdown-content class for padding

**`components/Stage1.jsx`**
- Tab view of individual model responses
- ReactMarkdown rendering with markdown-content wrapper

**`components/Stage2.jsx`**
- **Critical Feature**: Tab view showing RAW evaluation text from each model
- De-anonymization happens CLIENT-SIDE for display (models receive anonymous labels)
- Shows "Extracted Ranking" below each evaluation so users can validate parsing
- Aggregate rankings shown with average position and vote count
- Explanatory text clarifies that boldface model names are for readability only

**`components/Stage3.jsx`**
- Final synthesized answer from chairman
- Green-tinted background (#f0fff0) to highlight conclusion

**Styling (`*.css`)**
- Light mode theme (not dark mode)
- Primary color: #4a90e2 (blue)
- Global markdown styling in `index.css` with `.markdown-content` class
- 12px padding on all markdown content to prevent cluttered appearance

## Key Design Decisions

### Stage 2 Prompt Format
The Stage 2 prompt is very specific to ensure parseable output:
```
1. Evaluate each response individually first
2. Provide "FINAL RANKING:" header
3. Numbered list format: "1. Response C", "2. Response A", etc.
4. No additional text after ranking section
```

This strict format allows reliable parsing while still getting thoughtful evaluations.

### De-anonymization Strategy
- Models receive: "Response A", "Response B", etc.
- Backend creates mapping: `{"Response A": "openai/gpt-5.1", ...}`
- Frontend displays model names in **bold** for readability
- Users see explanation that original evaluation used anonymous labels
- This prevents bias while maintaining transparency

### Error Handling Philosophy
- Continue with successful responses if some models fail (graceful degradation)
- Never fail the entire request due to single model failure
- Log errors but don't expose to user unless all models fail

### UI/UX Transparency
- All raw outputs are inspectable via tabs
- Parsed rankings shown below raw text for validation
- Users can verify system's interpretation of model outputs
- This builds trust and allows debugging of edge cases

## Important Implementation Details

### Relative Imports
All backend modules use relative imports (e.g., `from .config import ...`) not absolute imports. This is critical for Python's module system to work correctly when running as `python -m backend.main`.

### Port Configuration
- Local backend: 8001 (changed from 8000 to avoid conflict on the maintainer's machine)
- Local frontend: 5173 (Vite default); Vite proxies `/api/*` to `:8001`
- Databricks Apps: `run_app.py` reads `DATABRICKS_APP_PORT` and starts uvicorn on it
- `frontend/src/api.js` uses `API_BASE = ''` (relative paths) in both environments

### Markdown Rendering
All ReactMarkdown components must be wrapped in `<div className="markdown-content">` for proper spacing. This class is defined globally in `index.css`.

### Model Configuration
Models are hardcoded in `backend/config.py`. Chairman can be same or different from council members. The current default is Gemini as chairman per user preference.

## Common Gotchas

1. **Module Import Errors**: Always run backend as `python -m backend.main` from project root, not from backend directory
2. **CORS Issues**: Frontend must match allowed origins in `main.py` CORS middleware
3. **Ranking Parse Failures**: If models don't follow format, fallback regex extracts any "Response X" patterns in order
4. **Missing Metadata**: Metadata is ephemeral (not persisted), only available in API responses

## Future Enhancement Ideas

- Configurable council/chairman via UI instead of config file
- Streaming responses instead of batch loading
- Export conversations to markdown/PDF
- Model performance analytics over time
- Custom ranking criteria (not just accuracy/insight)
- Support for reasoning models (o1, etc.) with special handling

## Testing Notes

Use `test_openrouter.py` to verify API connectivity and test different model identifiers before adding to council. The script tests both streaming and non-streaming modes.

## Databricks Apps Deployment

The repo doubles as a Databricks App. Four files at the repo root drive this:

- **`app.py`** — top-level FastAPI entry. Re-exports `backend.main:app` and (if `frontend/dist/` exists) mounts it at `/` as `StaticFiles(html=True)`. Routes resolve `/api/*` to the FastAPI routes first; everything else falls through to the SPA's `index.html` for client-side routing.
- **`run_app.py`** — launcher used by Databricks. Reads `DATABRICKS_APP_PORT` and calls `uvicorn.run("app:app", host="0.0.0.0", port=port)`. The launcher pattern avoids relying on argv substitution rules in `app.yaml`.
- **`app.yaml`** — Databricks Apps execution config. `command: ["python", "run_app.py"]`. Declares `OPENROUTER_API_KEY` via `valueFrom: openrouter_api_key` (must match a resource declared on the app) and `DATA_DIR` as a workspace path.
- **`requirements.txt`** — explicit Python deps for the Databricks Apps runtime (mirrors `pyproject.toml`).

### How the two environments coexist
- **Local (`./start.sh`):** unchanged two-process flow. Backend module entrypoint `backend/main.py` runs on `:8001`. Vite runs on `:5173` and proxies `/api/*` to `:8001` via `vite.config.js`. `app.py` and `run_app.py` are unused.
- **Databricks Apps:** single uvicorn process, both API and SPA on one origin/port. Auth handled by the Databricks ingress (workspace SSO); identity headers like `X-Forwarded-Email` are forwarded but unused today. Conversations persist at `/Workspace/Users/bwise@redventures.com/data/conversations/` via standard POSIX I/O against the workspace files mount — the app's service principal must have `Can Edit` on that folder.

### Constraints worth remembering
- All routes must remain under `/api/*` (a Databricks Apps requirement for OAuth bearer auth). Don't add public routes outside `/api`; put SPA assets under `/` via StaticFiles only.
- Never inline secrets in `app.yaml`'s `value` field — always `valueFrom` against an app resource.
- `frontend/dist/` must exist at deploy time (run `npm run build` before `databricks sync`). It's gitignored locally; that's fine.

## Data Flow Summary

```
User Query
    ↓
Stage 1: Parallel queries → [individual responses]
    ↓
Stage 2: Anonymize → Parallel ranking queries → [evaluations + parsed rankings]
    ↓
Aggregate Rankings Calculation → [sorted by avg position]
    ↓
Stage 3: Chairman synthesis with full context
    ↓
Return: {stage1, stage2, stage3, metadata}
    ↓
Frontend: Display with tabs + validation UI
```

The entire flow is async/parallel where possible to minimize latency.
