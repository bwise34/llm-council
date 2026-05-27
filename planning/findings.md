# Findings: LLM Council Codebase

Investigation snapshot — captured before the user's refactor request.

## 1. Repo Layout

```
llm-council/
├── backend/
│   ├── __init__.py         # empty marker
│   ├── config.py           # models, env vars, paths
│   ├── openrouter.py       # async HTTP client (httpx)
│   ├── council.py          # 3-stage orchestration + ranking parser
│   ├── storage.py          # JSON file persistence
│   └── main.py             # FastAPI app, runs on :8001
├── frontend/
│   ├── index.html
│   ├── vite.config.js      # plain Vite + @vitejs/plugin-react
│   ├── package.json        # React 19, react-markdown 10, Vite 7
│   └── src/
│       ├── main.jsx        # createRoot entry
│       ├── App.jsx         # state container, streaming orchestration
│       ├── api.js          # fetch wrappers + SSE parser
│       ├── index.css       # global + .markdown-content rules
│       ├── App.css
│       └── components/
│           ├── Sidebar.{jsx,css}
│           ├── ChatInterface.{jsx,css}
│           ├── Stage1.{jsx,css}
│           ├── Stage2.{jsx,css}
│           └── Stage3.{jsx,css}
├── data/conversations/     # JSON persistence (gitignored, currently empty)
├── main.py                 # vestigial "Hello from llm-council" stub
├── start.sh                # launches both backend + frontend
├── pyproject.toml          # uv-managed, FastAPI/uvicorn/httpx/pydantic
└── CLAUDE.md               # technical notes
```

`.gitignore` excludes `.env`, `data/`, `.venv`, `frontend/node_modules`, `frontend/dist`. The repo's root `main.py` is unused — it's an `uv init` leftover.

## 2. Backend

### 2.1 `config.py`
- Loads `OPENROUTER_API_KEY` from `.env` via `python-dotenv`.
- `COUNCIL_MODELS` is hard-coded list of OpenRouter IDs. **Current values use future-version IDs** (`openai/gpt-5.4`, `google/gemini-3.1-flash-lite`, `anthropic/claude-sonnet-4.6`, `x-ai/grok-4.3`) — these may or may not resolve at OpenRouter; the README and CLAUDE.md reference older IDs.
- `CHAIRMAN_MODEL = "anthropic/claude-opus-4.7"` — hard-coded separately.
- `OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"`.
- `DATA_DIR = "data/conversations"` (relative to CWD, so backend must be launched from project root).

### 2.2 `openrouter.py`
- `query_model(model, messages, timeout=120)` — async POST to OpenRouter. Returns `{'content', 'reasoning_details'}` or `None` on any exception. Swallows error to `print()`; no structured logging, no retries, no rate-limit handling.
- `query_models_parallel(models, messages)` — `asyncio.gather` fan-out; returns `{model: response | None}`.
- No streaming from OpenRouter — each call is a full request/response. The frontend "stream" is granular at the *stage* level, not token level.

### 2.3 `council.py` — the orchestration core
Six exported functions:

| Function | Role |
|---|---|
| `stage1_collect_responses(query)` | Parallel `query_models_parallel(COUNCIL_MODELS, ...)`. Drops failed models silently. Returns `[{model, response}]`. |
| `stage2_collect_rankings(query, stage1_results)` | Anonymizes Stage 1 outputs as `Response A`, `Response B`, … (max 26 — `chr(65+i)`). Builds long single-shot prompt with strict `FINAL RANKING:` format. Parallel query. Returns `(rankings, label_to_model)`. |
| `stage3_synthesize_final(query, s1, s2)` | Builds chairman prompt with **de-anonymized** Stage 1 (real model names) + Stage 2 ranking text. Single call to `CHAIRMAN_MODEL`. |
| `parse_ranking_from_text(text)` | Regex: tries `\d+\.\s*Response [A-Z]` after the `FINAL RANKING:` marker; falls back to any `Response [A-Z]` matches in order; final fallback to matches across whole text. |
| `calculate_aggregate_rankings(s2, label_to_model)` | Averages position (1-indexed). Sorts ascending. Returns `[{model, average_rank, rankings_count}]`. |
| `generate_conversation_title(query)` | Hard-codes `google/gemini-2.5-flash`, 30s timeout, ≤50 char title with stripping. |
| `run_full_council(query)` | Sequential composition of the three stages; returns `(s1, s2, s3, metadata)` where metadata = `{label_to_model, aggregate_rankings}`. |

### 2.4 `storage.py`
- Pure JSON file per conversation: `data/conversations/{uuid}.json`.
- Conversation shape: `{id, created_at, title, messages: [...]}`.
- User message: `{role: "user", content}`. Assistant message: `{role: "assistant", stage1, stage2, stage3}`. **No metadata persisted** — `label_to_model` and `aggregate_rankings` only live on the live API response. Re-opening a past conversation loses de-anonymization mapping and aggregate ranks.
- `list_conversations()` reads every file on every call (no in-memory cache, no pagination). Returns metadata + `message_count`.
- `datetime.utcnow()` (deprecated in Py 3.12+) used for timestamps.
- No locking. Concurrent writes to the same conversation would race.

### 2.5 `main.py` (FastAPI)
- CORS: `http://localhost:5173` and `http://localhost:3000`.
- Endpoints:
  - `GET /` — health.
  - `GET /api/conversations` — list metadata.
  - `POST /api/conversations` — create (returns new UUID + empty conv).
  - `GET /api/conversations/{id}` — full conversation.
  - `POST /api/conversations/{id}/message` — synchronous, full-blocking, returns `{stage1, stage2, stage3, metadata}`.
  - `POST /api/conversations/{id}/message/stream` — SSE stream emitting `stage1_start/complete`, `stage2_start/complete`, `stage3_start/complete`, `title_complete`, `complete`, `error`.
- Title generation runs as `asyncio.create_task` concurrently with Stage 1+2+3, awaited just before `title_complete`. So if title is slow it can briefly block the `complete` event after Stage 3.
- Listens on `0.0.0.0:8001`.
- **No endpoints for**: delete conversation, rename conversation, list/edit models, retry failed model, edit/regenerate a past message.
- **No auth**, **no rate limiting**.

## 3. Frontend

### 3.1 Entry & state (`main.jsx`, `App.jsx`)
- React 19 + StrictMode.
- All app state lives in `App.jsx`:
  - `conversations` — list metadata.
  - `currentConversationId` / `currentConversation` — selection + full payload.
  - `isLoading` — global lock during a streaming send.
- Effects: load list on mount; load full conversation on selection change.
- `handleSendMessage` is the streaming dispatcher. Optimistically appends user + a stub assistant message, then mutates the stub message in place as SSE events arrive. After `complete`, calls `loadConversations()` to refresh sidebar.

### 3.2 `api.js`
- `API_BASE = 'http://localhost:8001'` — hard-coded (no env var, no vite proxy).
- Provides `listConversations`, `createConversation`, `getConversation`, `sendMessage` (non-stream, unused by current UI), and `sendMessageStream`.
- SSE parsing is naive: splits chunk on `\n`, strips `data: ` prefix, `JSON.parse`. **No buffering for cross-chunk SSE frames** — a frame split mid-chunk would fail (`JSON.parse` catch only logs). Works in practice because frames are small and emitted promptly.

### 3.3 Components

| Component | Notes |
|---|---|
| `Sidebar` | Header with "+ New Conversation". Item list shows `conv.title` and `message_count`. Active-item highlight. No delete/rename. Item insert on creation in `App.jsx` uses placeholder `{id, created_at, message_count: 0}` (no title field) — relies on a `loadConversations()` refresh after `title_complete` to fill it. |
| `ChatInterface` | Renders messages, auto-scrolls. **Input form is only rendered when `conversation.messages.length === 0`** — this enforces a *single-turn* UX. After the first message, the input disappears; you must open a new conversation to ask again. Stage loading spinners controlled by per-message `loading.stageN` booleans. |
| `Stage1` | Tab view over `responses[]`. Tab label = model ID after the `/`. Renders markdown of selected tab. |
| `Stage2` | Tab view over `rankings[]`. De-anonymization is client-side via `String.replace(/Response X/g, '**modelName**')` — order-sensitive on `Object.entries(labelToModel)` and may produce overlap issues if a model name itself contained `Response X` text. Below each tab, an "Extracted Ranking" list shows `parsed_ranking` mapped to model names — gives the user a way to spot parser failures. Bottom: aggregate "Street Cred" board. |
| `Stage3` | Renders chairman's markdown with green-tinted card. |

### 3.4 Styling
- Light theme (`#f5f5f5` background, `#4a90e2` blue accent per CLAUDE.md).
- Global `.markdown-content` class supplies padding + spacing for all ReactMarkdown trees.
- Per-component CSS files (Sidebar.css, etc.) not read in full but exist.

## 4. End-to-end Flow (single message)

```
[User types & Enter]
  └─ ChatInterface.handleSubmit
     └─ App.handleSendMessage
        ├─ Optimistic UI: append {role:user} + assistant stub {loading.*:false}
        └─ api.sendMessageStream(convId, content, onEvent)
            └─ POST /api/conversations/{id}/message/stream
                ├─ storage.add_user_message
                ├─ asyncio.create_task( generate_conversation_title )  [if first msg]
                ├─ SSE: stage1_start
                ├─ stage1_collect_responses → parallel OpenRouter calls
                ├─ SSE: stage1_complete   ── App sets msg.stage1
                ├─ SSE: stage2_start      ── App flips loading.stage2
                ├─ stage2_collect_rankings → parallel OpenRouter w/ anonymized prompt
                ├─ calculate_aggregate_rankings
                ├─ SSE: stage2_complete   ── App sets msg.stage2 + metadata
                ├─ SSE: stage3_start
                ├─ stage3_synthesize_final → single OpenRouter to chairman
                ├─ SSE: stage3_complete   ── App sets msg.stage3
                ├─ await title_task; storage.update_conversation_title
                ├─ SSE: title_complete    ── App calls loadConversations()
                ├─ storage.add_assistant_message  (metadata NOT saved)
                └─ SSE: complete          ── App clears isLoading
```

## 5. Known Constraints & Gotchas

| # | Constraint | Where | Implication for refactors |
|---|---|---|---|
| 1 | Single-turn UX | `ChatInterface.jsx:123` (`messages.length === 0` gates the input form) | Multi-turn chat requires moving / unconditionally rendering the input form. |
| 2 | Metadata is ephemeral | `storage.add_assistant_message` strips metadata | Restored conversations lose de-anon mapping & aggregate ranks. |
| 3 | Ranking parser is regex over free text | `parse_ranking_from_text` | If a model deviates from `FINAL RANKING:` format, fallback may return wrong positions. Consider tool-use / JSON mode. |
| 4 | Hard-coded models in 3 places | `config.py` (council + chairman), `council.py:278` (title model) | UI cannot change models without code edit. |
| 5 | Hard-coded URLs | `api.js:5` (`localhost:8001`), `main.py:20` CORS list | No env-based config; not deployable as-is. |
| 6 | Anonymization tops out at 26 models | `chr(65 + i)` | Not a practical issue, but a wall. |
| 7 | SSE parsing is non-buffered | `api.js:99-112` | Larger / slower payloads could fragment frames. |
| 8 | No retries / per-model error surfacing | `openrouter.py:51-53` | Silent failures — frontend can't tell *which* model died, only that one fewer tab appears. |
| 9 | `list_conversations` is O(N) file reads per call, no cache | `storage.py:81-107` | Fine at <100 convos, gets slow later. |
| 10 | No delete/rename endpoints | `main.py` | Sidebar can grow stale conversations indefinitely. |
| 11 | `datetime.utcnow()` deprecated | `storage.py:35` | Cosmetic but worth replacing with `datetime.now(timezone.utc)` if touched. |
| 12 | Chairman gets de-anonymized Stage 1 (`Model: ...`) | `council.py:132-135` | Chairman knows which model said what, by design. Worth being explicit about if anonymization is tightened. |

## 6. Likely Refactor Seams

Where common asks tend to land:

- **Model config UI** → expose `COUNCIL_MODELS`/`CHAIRMAN_MODEL` via API + `Sidebar` or settings panel. New endpoints + state in `config.py` → persistent settings file or pass-through per-request.
- **Multi-turn chat** → drop the `messages.length === 0` gate; conversation context (history) needs to flow into Stage 1/2/3 prompts. `messages=[{user},{assistant…}]` for OpenRouter requires deciding what counts as the "assistant" content (Stage 3 only? all three?).
- **Streaming tokens within a stage** → switch to OpenRouter `stream:true`; each `query_model` becomes an async generator; SSE event types extend to `stage1_token` per model.
- **Persistent metadata** → add `metadata` field to assistant message in `storage.add_assistant_message` + Conversation pydantic shape + `App.jsx` reload path.
- **Structured rankings** → swap the regex prompt for OpenRouter response-format JSON or tool calls. Replaces `parse_ranking_from_text` with `json.loads`.
- **Per-model error surfacing** → propagate `None` responses through Stage 1/2/3 as `{model, error}` entries; UI gets a "failed" tab.
- **Configurable Chairman / fallback** → if chairman fails, retry with a second model from a fallback list; surface in metadata.
- **Auth / deploy** → factor `API_BASE` into a Vite env var; expand CORS via env list; add token gate.
- **Conversation management** → `DELETE /api/conversations/{id}`, `PATCH /api/conversations/{id}` for rename; sidebar item context menu.

## 7. Discrepancies between CLAUDE.md and current code

Worth flagging so the user knows what the actual state is:

- CLAUDE.md says only `/message` returns metadata. **Both** `/message` and `/message/stream` now return metadata (stream emits it on `stage2_complete`).
- CLAUDE.md doesn't mention SSE / streaming endpoint at all — that's a feature that's been added since the doc was written.
- CLAUDE.md doesn't mention the title-generation flow or `generate_conversation_title`.
- CLAUDE.md's model defaults (`openai/gpt-5.1`, `claude-sonnet-4.5`, `google/gemini-3-pro-preview`) differ from current `config.py` values (`gpt-5.4`, `claude-sonnet-4.6`, `gemini-3.1-flash-lite`, chairman `claude-opus-4.7`).
- CLAUDE.md describes a multiline textarea always present; current UI only renders the input on the empty-conversation state.

Not bugs — just stale documentation.
