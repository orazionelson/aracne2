# AI Integration — Technical Reference

This document covers the full AI integration in Aracne2: backend plugin, provider
adapters, service layer, frontend store, and UI components. Read this before any
session that touches AI features.

---

## File map

```
backend/app/plugins/_native/ai/
├── __init__.py
├── router.py          # FastAPI router — prompt CRUD + /complete endpoint
├── service.py         # Business logic: rate limiting, template fill, streaming
└── providers/
    ├── base.py        # Abstract BaseAiProvider
    ├── openai.py      # OpenAI Chat Completions adapter
    ├── anthropic.py   # Anthropic Messages adapter
    └── gemini.py      # Google Gemini generateContent adapter

backend/app/
├── models/
│   ├── ai_prompt.py        # ORM: ai_prompts table
│   └── ai_request_log.py   # ORM: ai_request_logs table (rate limiting)
├── schemas/
│   └── ai.py               # Pydantic schemas for all AI endpoints
└── db/seed.py              # Seeds three native prompts on first boot

frontend/src/
├── stores/ai.ts            # Pinia store: streaming state + chat history
└── components/AiPanel.vue  # Reusable panel (single-shot and chat modes)

frontend/src/views/
├── CollectionDetailView.vue        # Uses AiPanel with chat=true (validation context)
├── DocumentEditView.vue            # Uses ai store directly (editor context, no chat)
├── admin/WebsiteEditView.vue       # XSLT editor: custom debug panel + AiPanel discuss mode
└── CollectionBibliobuilderview.vue # Bibliobuilder: custom panel wired to ai store directly
```

---

## Database models

### `ai_prompts`

Stores prompt templates. Native prompts are seeded at boot and cannot be deleted
(only their `template` and `label` can be edited by Admin).

```python
# backend/app/models/ai_prompt.py
class AiPrompt(Base):
    __tablename__ = "ai_prompts"

    id:             UUID (PK)
    slug:           str (unique, max 128) — machine identifier, e.g. "validate_errors_explain"
    label:          str (max 256)         — human label shown in the UI
    description:    str | None            — optional admin note
    template:       str (Text)            — prompt body; {variable_name} placeholders
    context_vars:   list[str] (JSON)      — required placeholder names
    target_context: str | None            — "editor" | "validation" | "xslt" | None
    is_native:      bool                  — True = seeded, not deletable
    created_at:     datetime (tz-aware)
    updated_at:     datetime (tz-aware)
```

### `ai_request_logs`

One row per call to `/api/v1/ai/complete`. Used only for per-user hourly rate limiting.
No conversation state is persisted server-side.

```python
# backend/app/models/ai_request_log.py
class AiRequestLog(Base):
    __tablename__ = "ai_request_logs"

    id:          UUID (PK)
    user_id:     UUID (indexed)
    prompt_slug: str
    provider:    str
    created_at:  datetime (tz-aware, indexed)
```

---

## Pydantic schemas

```python
# backend/app/schemas/ai.py

class AiChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str

class AiCompleteRequest(BaseModel):
    prompt_slug: str
    context: dict[str, str]   # values for {placeholder} substitution
    history: list[AiChatMessage] = []  # empty = first turn; subsequent turns carry the full exchange

class AiPromptResponse(BaseModel):
    id: UUID; slug: str; label: str; description: str | None
    template: str; context_vars: list[str]; target_context: str | None
    is_native: bool; created_at: datetime; updated_at: datetime

class AiPromptCreate(BaseModel):
    slug: str      # validated: ^[a-z0-9_]+$
    label: str
    description: str | None = None
    template: str  # validated: not empty
    context_vars: list[str] = []
    target_context: str | None = None

class AiPromptUpdate(BaseModel):
    label: str | None = None; description: str | None = None
    template: str | None = None; context_vars: list[str] | None = None
    target_context: str | None = None

class AiConfigResponse(BaseModel):
    provider: str; model: str; rate_limit: int; privacy_warning: bool
```

The following schema lives in `backend/app/schemas/collections.py` but is part of
the editor AI validation flow:

```python
class DocumentValidateRequest(BaseModel):
    xml_content: str | None = None
    # When provided, the backend validates this string directly instead of
    # fetching the saved file from eXist-db.  Used by runValidateAi() to
    # validate the current editor buffer without requiring a save first.
```

---

## Backend: router

```
prefix: /api/v1/ai
file:   backend/app/plugins/_native/ai/router.py
```

| Method | Path             | ACL    | Description                              |
|--------|------------------|--------|------------------------------------------|
| GET    | /prompts         | E+     | List templates; optional `?context=` filter |
| POST   | /prompts         | Admin  | Create custom template                   |
| PATCH  | /prompts/{slug}  | Admin  | Update template                          |
| DELETE | /prompts/{slug}  | Admin  | Delete custom template (native: 403)     |
| GET    | /config          | Admin  | Provider name, model, rate limit, privacy flag |
| POST   | /complete        | E+     | Stream a completion (SSE)                |

### POST /complete

Request body: `AiCompleteRequest`
Response: `text/event-stream` (SSE)

```
data: {"chunk": "text fragment"}\n\n   — one or more
data: {"error": "message"}\n\n         — on failure, before [DONE]
data: [DONE]\n\n                       — terminal event always present
```

Headers on the response:
```
X-Accel-Buffering: no
Cache-Control: no-cache
Connection: keep-alive
```

---

## Backend: service layer

```python
# backend/app/plugins/_native/ai/service.py

async def stream_completion(
    db: AsyncSession,
    prompt_slug: str,
    context: dict[str, str],
    user: User,
    history: list[AiChatMessage] | None = None,
) -> AsyncGenerator[str, None]:
```

Execution order:
1. `_check_rate_limit(db, user)` — reads `ai_max_requests_per_hour` setting;
   counts `AiRequestLog` rows for this user in the last hour; raises
   `AiRateLimitError` (503) if exceeded.
2. Fetches `AiPrompt` by slug; raises `NotFoundError` if missing.
3. `_fill_template(template, context)` — `str.format_map(context)`; raises
   `DomainValidationError("AI_MISSING_CONTEXT_VAR", ...)` on missing variable.
4. Builds the messages list:
   ```python
   messages = [{"role": "user", "content": filled}]   # resolved template always first
   if history:
       messages.extend(h.model_dump() for h in history)
   ```
5. Calls `_get_provider(db)` — reads `ai_provider` setting; decrypts the API key
   via `get_decrypted_setting(db, f"ai_{provider_name}_api_key")`; returns the
   correct provider instance.
6. Inserts an `AiRequestLog` row and commits (counts immediately toward rate limit).
7. `async for chunk in provider.stream(messages): yield chunk`
8. On `httpx.HTTPStatusError`: parses `{"error": {"message": "..."}}` from provider
   body; raises `ExternalServiceError`.
9. On `httpx.RequestError`: raises `ExternalServiceError`.

Custom exceptions (mapped to HTTP in `main.py`):
- `AiDisabledError` → 503, code `AI_PROVIDER_DISABLED`
- `AiRateLimitError` → 429, code `AI_RATE_LIMIT_EXCEEDED`

---

## Backend: provider adapters

All providers live in `backend/app/plugins/_native/ai/providers/`.

### Abstract base

```python
# providers/base.py
class BaseAiProvider(ABC):
    @abstractmethod
    async def stream(self, messages: list[dict[str, str]]) -> AsyncGenerator[str, None]:
        ...
```

`messages` is always `[{"role": "user"|"assistant", "content": str}, ...]`.
The first entry is always `role: "user"` (the resolved template).
Multi-turn chat appends alternating assistant/user turns after it.

### OpenAI (`providers/openai.py`)

- URL: `https://api.openai.com/v1/chat/completions`
- Auth: `Authorization: Bearer {api_key}`
- Payload: `{"model": ..., "stream": true, "messages": messages}`
- SSE parsing: lines starting with `data: `; `[DONE]` sentinel;
  extracts `choices[0].delta.content`.

### Anthropic (`providers/anthropic.py`)

- URL: `https://api.anthropic.com/v1/messages`
- Auth: `x-api-key: {api_key}`, `anthropic-version: 2023-06-01`
- Payload: `{"model": ..., "max_tokens": 2048, "stream": true, "messages": messages}`
- SSE parsing: events of type `content_block_delta`; extracts `delta.text`.
- Note: Anthropic's messages format is identical to OpenAI's
  (`{"role": ..., "content": ...}`), no conversion needed.

### Gemini (`providers/gemini.py`)

- URL: `https://generativelanguage.googleapis.com/v1beta/models/{model}:streamGenerateContent`
- Auth: `?key={api_key}&alt=sse` query params
- Payload: `{"contents": [{"role": ..., "parts": [{"text": ...}]}, ...]}`
- Conversion from standard messages format:
  ```python
  contents = [
      {
          "role": "model" if msg["role"] == "assistant" else msg["role"],
          "parts": [{"text": msg["content"]}],
      }
      for msg in messages
  ]
  ```
  Gemini uses `"model"` (not `"assistant"`) for the assistant role.
- SSE parsing: extracts `candidates[0].content.parts[].text`.

### Ollama (`providers/ollama.py`)

- URL: `{ai_ollama_base_url}/api/chat` (default base: `http://ollama:11434`, the
  Compose service under profile `ai-local`; or any host-installed Ollama).
- Auth: none — Ollama does not require an API key. `_get_provider` in
  `service.py` skips the `ai_{provider}_api_key` lookup for `provider_name == "ollama"`.
- Payload: `{"model": ..., "stream": true, "messages": messages}` — same
  `{"role": ..., "content": ...}` shape as OpenAI / Anthropic.
- NDJSON parsing: one JSON object per line; extracts `message.content` deltas;
  stops on `done: true`. `{"error": ...}` payloads are converted to `httpx.HTTPError`
  so the service layer surfaces a consistent error message.
- Generous read timeout (300 s): first-token latency spikes when Ollama has to
  load a large model into memory; subsequent tokens are fast.

See `docs/OPERATIONS.md` § "Local AI (Ollama)" for the operator-facing recipe
(profile activation, pulling models, switching models, host-installed vs
bundled Ollama).

---

## System settings (ai_*)

Stored in `system_settings` table; managed by Admin in the Settings view. The
UI groups them under the AI tab in a collapsible "Provider & API keys" panel.

### Provider selection and credentials

| Key                          | Default               | Notes                                                       |
|------------------------------|-----------------------|-------------------------------------------------------------|
| `ai_provider`                | `"disabled"`          | `"openai"` / `"anthropic"` / `"gemini"` / `"ollama"` / `"disabled"` |
| `ai_openai_model`            | `"gpt-4o"`            |                                                             |
| `ai_anthropic_model`         | `"claude-opus-4-6"`   |                                                             |
| `ai_gemini_model`            | `"gemini-1.5-pro"`    |                                                             |
| `ai_ollama_base_url`         | `"http://ollama:11434"` | Base URL of the Ollama server used for chat AND embeddings |
| `ai_ollama_model`            | `"llama3.1:8b"`       | Pull once: `ollama pull <tag>`                              |
| `ai_openai_api_key`          | —                     | Stored encrypted. Not used by the `ollama` provider         |
| `ai_anthropic_api_key`       | —                     | Stored encrypted                                            |
| `ai_gemini_api_key`          | —                     | Stored encrypted                                            |
| `ai_max_requests_per_hour`   | `20`                  | Per-user rolling window                                     |
| `ai_privacy_warning_enabled` | `"false"`             | Shows banner in AiPanel                                     |

### Retrieval-augmented generation (RAG)

Optional feature that grounds prompts referencing `{rag_context}` on a
pgvector index. Turned off by default; see the dedicated
[RAG](#retrieval-augmented-generation-rag) section below.

| Key                         | Default              | Notes                                                             |
|-----------------------------|----------------------|-------------------------------------------------------------------|
| `ai_rag_enabled`            | `"false"`            | Master switch — when `"true"` and pgvector is configured, prompts containing `{rag_context}` get retrieval-injected context |
| `ai_rag_top_k`              | `5`                  | Number of chunks retrieved per query                              |
| `ai_rag_context_tokens`     | `1500`               | Approximate token budget for the injected context (4 chars ≈ 1 token heuristic) |
| `ai_rag_embedding_model`    | `"bge-m3"`           | Ollama tag used for embeddings. 1024-dim multilingual. Pull once: `ollama pull bge-m3` |

---

## Retrieval-augmented generation (RAG)

Opt-in feature that lets prompts pull context from a semantic index at
inference time. When a prompt template contains `{rag_context}` and RAG is
enabled, the service layer retrieves the top-matching passages and injects
them into the prompt **before** it reaches the LLM. The retrieved block
lives inside the same prompt turn — no extra round-trip.

### Architecture

```
 prompt ── _augment_with_rag ── _fill_template ── provider.stream ──▶ client (SSE)
               │                                         ▲
               │  1. setting "ai_rag_enabled" = true?    │
               │  2. pgvector configured?                │
               │  3. template contains {rag_context}?    │
               ▼                                         │
         embed_text (Ollama /api/embeddings) ─────────┐  │
               │                                      │  │
               ▼                                      ▼  │
          ai_context_chunks (pgvector,           base prompt
           1024-dim vector cosine)               + retrieved chunks
               │
               ▼
          top-K RetrievedChunk
```

Fail-soft at every step: if the master switch is off, pgvector is not
configured, the embedding call fails, or retrieval raises, the service
substitutes `{rag_context}` with an empty string and the base prompt still
reaches the provider. The user never sees an error coming from the RAG
path; a structured-log `warning` records the reason.

### Components

| File                                            | Role                                                       |
|-------------------------------------------------|------------------------------------------------------------|
| `app/db/pgvector.py`                            | Lazy async engine + `PgvectorBase`; `ensure_schema()` at lifespan; `get_session_factory()` for ad-hoc sessions |
| `app/models/ai_context_chunk.py`                | `AiContextChunk` model with `Vector(1024)` + HNSW cosine index |
| `app/plugins/_native/ai/embeddings.py`          | `embed_text(db, text)` against Ollama `/api/embeddings`; wraps errors in `EmbeddingUnavailable` |
| `app/plugins/_native/ai/rag.py`                 | `is_enabled()`, `retrieve()` (cosine top-K + token budget), `format_chunks()` |
| `app/plugins/_native/ai/service.py::_augment_with_rag` | Runs before `_fill_template`; injects `{rag_context}` or `""` |
| `app/scripts/ingest_tei_p5.py`                  | CLI ingestion (walks `--source` for .html/.xml/.txt/.md → chunks → embeds → inserts) |

### Vector store schema

Lives in a **separate Postgres instance** (the `pgvector` Compose service,
under profile `ai-local`). Kept disjoint from the platform DB so:

- vector-only workloads (bulk ingest, ANN) do not contend with editorial traffic;
- the schema can be dropped and rebuilt without touching user data
  (e.g. when switching embedding dimension);
- future embedding providers beyond Ollama do not require platform schema changes.

```sql
CREATE EXTENSION IF NOT EXISTS vector;
CREATE TABLE ai_context_chunks (
    id            UUID PRIMARY KEY,
    source_type   VARCHAR(64) NOT NULL,     -- "tei_p5", "schema", …
    source_id     VARCHAR(512) NOT NULL,    -- relative path or slug
    chunk_index   INTEGER NOT NULL DEFAULT 0,
    text          TEXT NOT NULL,
    embedding     vector(1024) NOT NULL,
    chunk_metadata JSONB NOT NULL DEFAULT '{}',
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ix_ai_context_chunks_embedding_hnsw
    ON ai_context_chunks USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);
CREATE INDEX ix_ai_context_chunks_source
    ON ai_context_chunks (source_type, source_id, chunk_index);
```

The 1024 dimension matches `bge-m3`. Changing the embedding model to a
different dimension requires dropping and recreating the table (see
`OPERATIONS.md` for the procedure).

### Retrieval query

```sql
SELECT text, source_type, source_id, chunk_index,
       1 - (embedding <=> CAST(:qvec AS vector)) AS score
  FROM ai_context_chunks
 ORDER BY embedding <=> CAST(:qvec AS vector)
 LIMIT :top_k;
```

pgvector's `<=>` is cosine distance; score = 1 − distance, higher is better.
The query vector is rendered as a `[x.y,z.w,…]` literal string on the Python
side (`_vec_literal`) and cast to `vector` server-side, so we avoid
registering the pgvector asyncpg codec on the connection — simpler and
keeps the connection plain.

### Token budget

After retrieving `top_k` chunks, `retrieve()` truncates the **list of
chunks** (not individual chunk text) until the cumulative character count
reaches `ai_rag_context_tokens × 4` (rough 4-chars-per-token heuristic).
The first chunk always fits even when oversized — better than mid-chunk
cuts that break structured text.

### Ingestion

Indexing is **out-of-band**: the server never writes to
`ai_context_chunks` during normal request handling. An operator runs
`python -m app.scripts.ingest_tei_p5 --source DIR` from inside the
backend container. The script is format-agnostic (html/xml/txt/md),
chunks by paragraph at ~2000 chars with a 200-char minimum, commits
batches of 50, and exits with a clear error if the embedder is
unreachable. Flags: `--purge` (wipe `source_type` before insert),
`--dry-run` (preview without embeddings/writes), `--source-type`
(defaults to `tei_p5`; override when indexing another corpus).

### What v1 explicitly does not do

- No per-user / per-collection ACL on retrieval (global index in v1).
- No citations in the model output — chunk IDs are in the injected
  context only for operator debugging, not surfaced to the user.
- No user-corpus indexing (TEI P5 only); see `FUTURE_IDEAS.md` for the
  v2 plan (ACL-aware indexing, citations, multi-dim tables).
- No ingestion UI in the admin panel; CLI only.

---

## Native prompt templates

Seeded in `backend/app/db/seed.py`. `is_native=True` — deletable only by directly
editing the DB; editable (label + template) via Admin → Settings → AI.

### `validate_errors_explain` (target_context: `"validation"`)

Context vars: `filename`, `schema`, `errors`

```
You are a TEI P5 XML expert. Analyze the following validation errors
and explain clearly and concisely how to fix each one.

File: {filename}
Schema: {schema}

Validation errors:
{errors}
```

Used in two contexts:

- **`CollectionDetailView`** — "Analyze with AI" button next to each document in the
  collection-wide validation results panel. The errors come from the last validation
  run stored in `useCollectionValidationStore`. Uses `<AiPanel :chat="true">`.
- **`DocumentEditView`** — "Validate with AI" button in the editor AI sidebar.
  Runs a fresh per-document validation against the **current editor buffer** (not the
  saved file) before sending the errors to the AI. Uses the custom inline AI panel
  (not `AiPanel`), single-shot mode.

### `document_edit_suggest` (target_context: `"editor"`)

Context vars: `filename`, `collection_slug`, `selection`

```
You are a TEI P5 XML expert. Review the following XML selection
and suggest improvements to the TEI encoding.
Return ONLY the corrected XML, with no explanations, no markdown,
no code fences, no ``` delimiters — raw XML only.

File: {filename}
Collection: {collection_slug}

Selection:
{selection}
```

Used in: `DocumentEditView` (AI sidebar "Improve XML" button; sends editor selection or full buffer).
Chat mode: **not enabled** (single-shot; the response is raw XML meant to be applied directly).

### `xslt_debug` (target_context: `"xslt"`)

Context vars: `error_msg`, `xslt_source`

```
You are an XSLT 1.0 expert. Analyze the following stylesheet
and the reported error. Explain the cause and suggest a fix.

Error:
{error_msg}

Stylesheet:
{xslt_source}
```

Used in: `WebsiteEditView` — XSLT editor, Debug mode.
The user pastes an error message into a dedicated textarea; clicking "Debug"
calls `aiStore.startStream("xslt_debug", { error_msg, xslt_source })`.
Single-shot (not chat). Does **not** use the `AiPanel` component — the response
is shown in a custom inline panel (see [XSLT editor AI panel](#xslt-editor-ai-panel) below).

### `xslt_discuss` (target_context: `"xslt"`)

Context vars: `xslt_source`

```
You are an XSLT 1.0 expert. The user wants to discuss the following
XSLT stylesheet.
Answer in clear, natural language. You may include corrected XSLT
snippets when helpful, but focus on explaining and guiding.

Stylesheet:
{xslt_source}
```

Used in: `WebsiteEditView` — XSLT editor, Discuss mode.
Clicking "Discuss" switches the side panel to the `AiPanel` component with
`chat=true` and `show-apply=false`. The stylesheet source is captured once
at the moment the button is clicked and passed as `{ xslt_source }` context.

### `tei_bibl_inline` (target_context: `"editor"`)

Context vars: `filename`, `collection_slug`, `selection`

```
You are a TEI P5 expert. Convert the following free-text bibliographic
note into a single valid <biblStruct> element.

ALLOWED STRUCTURE: [minimal biblStruct with analytic / monogr / imprint / idno]
RULES: omit empty elements; ISO dates; xml:id = bib_<surname>_<year>; do not invent.
EXAMPLE: [one worked input→output pair]
Respond with ONLY the <biblStruct> element. No prose, no markdown, no code fences.

{rag_context}

File: {filename}
Collection: {collection_slug}

Selection:
{selection}
```

Used in: `DocumentEditView` (editor AI sidebar). Single-shot; the reply
replaces the editor selection with a `<biblStruct>`. When RAG is enabled,
`{rag_context}` is auto-filled with the top-K passages retrieved from the
TEI P5 index before the template is rendered.

### `tei_extract_entities` (target_context: `"editor"`)

Context vars: `filename`, `collection_slug`, `selection`

```
You are a TEI P5 expert. Wrap every named entity in the following
passage with the appropriate inline element. Do not modify the text
itself — only add markup.

ALLOWED TAGS: <persName>, <placeName>, <orgName>
RULES: preserve exact text; nesting allowed; @cert="medium" for ambiguous; skip pronouns / dates / work titles.
EXAMPLE: [one worked input→output pair]
Respond with ONLY the tagged fragment. No prose, no markdown, no code fences.

{rag_context}

File: {filename}
Collection: {collection_slug}

Selection:
{selection}
```

Used in: `DocumentEditView`. Selection in → selection out with inline
entity tags, ready to paste back into the editor.

### `tei_header_scaffold` (target_context: `"editor"`)

Context vars: `filename`, `collection_slug`, `selection`

```
You are a TEI P5 expert. Produce a minimal <teiHeader> block from the
free-text bibliographic metadata in the selection.

REQUIRED STRUCTURE: [fileDesc with titleStmt / publicationStmt / sourceDesc]
RULES: omit unknown elements; ISO 8601 dates; do not invent titles, authors or dates.
EXAMPLE: [one worked input→output pair]
Respond with ONLY the <teiHeader> block. No prose, no markdown, no code fences.

{rag_context}

File: {filename}
Collection: {collection_slug}

Selection:
{selection}
```

Used in: `DocumentEditView`. Takes free-text metadata lines and emits a
clean `<teiHeader>` scaffold.

### `bibliobuilder` (target_context: `null`)

Context vars: _(none — all content passed as the first user message)_

The prompt instructs the model to normalize raw TEI `<bibl>`/`<biblStruct>`
entries into a deduplicated, sorted `<listBibl>` following a strict TEI P5
structure. Batch size cap: 80 entries per turn.

Used in: `CollectionBibliobuilderview` — dedicated Bibliobuilder page ([see below](#bibliobuilder-flow)).
Does **not** use the `AiPanel` component. Wired to `aiStore` directly.
Multi-turn chat via `continueChat`. The first call passes the extracted XML
as the user message (no context object); follow-up turns pass the user's
free-text questions the same way.

---

## Frontend: Pinia store (`frontend/src/stores/ai.ts`)

### State

```typescript
prompts:     ref<AiPrompt[]>([])          // prompt library
config:      ref<AiConfig | null>(null)   // provider/model/rate_limit/privacy_warning
isStreaming: ref(false)
response:    ref("")                      // live streaming buffer (current turn)
streamError: ref<string | null>(null)
chatHistory: ref<AiChatMessage[]>([])    // finalized turns: [{role, content}, ...]
```

`chatHistory` does NOT include the initial resolved template (that is reconstructed
server-side on every request). It contains only the exchange after the first turn:
alternating `assistant` / `user` / `assistant` ...

### Methods

**`startStream(promptSlug, context)`**
- Clears `response`, `streamError`, `chatHistory` (fresh session).
- POSTs `{ prompt_slug, context, history: [] }` to `/api/v1/ai/complete`.
- Reads SSE stream into `response.value`.
- On completion: pushes `{ role: "assistant", content: response.value }` to `chatHistory`.

**`continueChat(promptSlug, context, userMessage)`**
- Appends `{ role: "user", content: userMessage }` to `chatHistory` immediately.
- Clears `response` and `streamError`.
- POSTs `{ prompt_slug, context, history: chatHistory.value }` — the full history
  (including the just-appended user message) is sent so the backend can reconstruct
  the complete conversation.
- On completion: pushes `{ role: "assistant", content: response.value }` to `chatHistory`.

**`stopStream()`** — aborts the fetch via `AbortController`; sets `isStreaming = false`.

**`clearResponse()`** — clears `response` / `streamError` / `isStreaming`; does NOT
touch `chatHistory`.

**`resetChat()`** — calls `stopStream()` + clears `response`, `streamError`,
`chatHistory`. Used when closing AiPanel or switching to a different document.

**`fetchConfig()`** — GET `/api/v1/ai/config` (Admin ACL server-side, but called from
views that already check `aiEnabled`). Required before AiPanel mounts; typically called
during view setup.

### How the SSE client works

Uses native `fetch()` (not Axios) with `res.body.getReader()` + `TextDecoder`.
Parses `data: {json}` lines; skips malformed lines silently.
`AbortError` on cancel is swallowed (not an error state).
Auth: `Authorization: Bearer {accessToken}` header + `credentials: "include"` (for
the httpOnly refresh cookie).

---

## Frontend: AiPanel component (`frontend/src/components/AiPanel.vue`)

### Props

```typescript
promptSlug: string                   // slug of the template to run
context:    Record<string, string>   // values for {placeholder} substitution
title?:     string                   // panel header label
sidebar?:   boolean                  // fills parent height (vs. fixed card)
chat?:      boolean                  // enables multi-turn chat mode (default: false)
showApply?: boolean                  // when false, hides the Apply button (default: true)
```

### Emits

```typescript
apply: [response: string]   // user clicked "Apply" — passes latest assistant content
close: []                   // user closed the panel
```

### Lifecycle

- On mount: calls `ai.startStream(promptSlug, context)`.
- Watches `context` (deep): calls `ai.resetChat()` then re-runs `startStream`.
  This handles the case where the user switches to a different document while the
  panel is open.
- On unmount: calls `ai.stopStream()`.
- On close: calls `ai.resetChat()` then emits `close`.

### Single-shot mode (`chat` = false, default)

- Shows `ai.response` in a monospace scrollable area.
- "Apply" emits `ai.response`.
- Used by `DocumentEditView` for `document_edit_suggest`.

### Chat mode (`chat` = true)

- Shows `ai.chatHistory` as labeled message bubbles (monospace for assistant,
  plain for user).
- Shows `ai.response` as a live-streaming assistant bubble at the bottom.
- After streaming completes, shows a `<textarea>` + "Send" button.
- Send shortcut: `Ctrl+Enter` / `Cmd+Enter`.
- Auto-scrolls to bottom on every new chunk and on every new history entry
  (via `nextTick` watcher).
- "Apply" emits the content of the last `assistant` entry in `chatHistory`.
- Used by `CollectionDetailView` for `validate_errors_explain`.

---

## Multi-turn chat: full sequence

```
User clicks "Analyze with AI" on a document
  → CollectionDetailView mounts <AiPanel :chat="true" prompt-slug="validate_errors_explain" :context="{filename, schema, errors}">
  → AiPanel.run() → ai.startStream("validate_errors_explain", context)
    → POST /api/v1/ai/complete { prompt_slug, context, history: [] }
    → service: resolves template → messages = [{role:"user", content:resolvedTemplate}]
    → provider.stream(messages) → SSE chunks → ai.response (live)
    → on complete: chatHistory = [{role:"assistant", content:fullResponse}]
  → Panel shows first response; textarea appears

User types "What specifically is wrong with the <tei:name> element?"
  → ai.continueChat("validate_errors_explain", context, "What specifically...")
    → chatHistory.push({role:"user", content:"What specifically..."})
    → POST /api/v1/ai/complete { prompt_slug, context, history: [
          {role:"assistant", content:firstResponse},
          {role:"user",      content:"What specifically..."}
      ]}
    → service: messages = [
          {role:"user",      content:resolvedTemplate},   ← always prepended
          {role:"assistant", content:firstResponse},
          {role:"user",      content:"What specifically..."}
      ]
    → provider.stream(messages) → SSE chunks → ai.response (live)
    → on complete: chatHistory = [
          {role:"assistant", content:firstResponse},
          {role:"user",      content:"What specifically..."},
          {role:"assistant", content:secondResponse}
      ]

User clicks "Apply"
  → emit("apply", lastAssistantMessage.content)
  → CollectionDetailView receives it (currently no handler beyond close;
    validation context does not insert XML)

User clicks ✕
  → ai.resetChat() → clears response, chatHistory, aborts any active stream
  → emit("close") → aiDocFilename = null
```

---

## Editor AI validation flow (`runValidateAi`)

The "Validate with AI" button in `DocumentEditView` is **not** backed by `AiPanel`.
It uses a custom inline panel and wires validation + AI streaming directly.

```
User clicks "Validate with AI"
  → runValidateAi() in DocumentEditView.vue
    → clears validationResult (never uses a cached result)
    → schemaStore.validateDocument(slug, filename, singleCm.getValue())
        → POST /api/v1/collections/{slug}/documents/{filename}/validate
           body: { xml_content: "<current editor buffer>" }
        → backend: skips eXist-db fetch, validates xml_content bytes directly
        → returns ValidationResult { valid, errors[] }
    → if valid (or no result): shows "no errors" message, does NOT call AI
    → if errors: formats errors as "Line X, col Y: message" text
      → aiStore.startStream("validate_errors_explain", { filename, schema, errors })
        → POST /api/v1/ai/complete { prompt_slug, context, history: [] }
        → streams response into the custom AI panel
```

Key detail: `xml_content` is always the live CodeMirror buffer (`singleCm.getValue()`),
not the saved eXist-db version. This means errors introduced without saving are
caught correctly.

The backend validate endpoint is:
```
POST /api/v1/collections/{collection_id}/documents/{filename}/validate
body: DocumentValidateRequest { xml_content?: str }
service: backend/app/services/xmldb.py → validate_document(..., xml_content=...)
```

When `xml_content` is omitted (or `null`), the endpoint fetches from eXist-db as
before — this preserves the behaviour of the regular "Validate" button in the
validation panel, which intentionally validates the saved file.

---

## How to add a new native prompt

1. Add an entry to `DEFAULT_AI_PROMPTS` in `backend/app/db/seed.py`.
2. Define `context_vars` carefully — these are validated at request time.
3. Choose `target_context`: `"editor"` / `"validation"` / `"xslt"` / `None`.
4. Run `seed.py` in the test environment (`docker compose exec backend python -m app.db.seed`),
   or rely on the automatic seed at next container start.
5. On the frontend, call `ai.startStream(slug, context)` or mount `<AiPanel>` with the
   new slug and a matching context object.

No migration needed — seeding is idempotent (skips existing slugs).

## How to add a new provider

1. Create `backend/app/plugins/_native/ai/providers/{name}.py` implementing
   `BaseAiProvider.stream(messages: list[dict[str, str]])`.
2. Add the provider name to the branch in `_get_provider()` in `service.py`.
3. Add a setting entry `ai_{name}_model` with a default value in `seed.py`
   (`DEFAULT_SETTINGS`).
4. For API-key providers, add `ai_{name}_api_key` — it is read via
   `get_decrypted_setting()` so no schema change is needed; the key is
   stored/managed through the Settings UI.
5. For keyless providers (local inference à la Ollama), add a dedicated
   setting for the endpoint URL (e.g. `ai_{name}_base_url`) and branch
   early in `_get_provider()` to skip the API-key lookup — see the
   `provider_name == "ollama"` block for the reference pattern.
6. Update the `SETTING_OPTIONS.ai_provider` select in
   `frontend/src/views/admin/SettingsView.vue` so the new value appears
   in the dropdown.
7. Add i18n hints (`settings.hint_ai_{name}_*`) in `en.json` / `it.json`
   so first-time operators see contextual help under each key.

---

## XSLT editor AI panel

**File**: `frontend/src/views/admin/WebsiteEditView.vue`, tab `xslt_edit`

The XSLT editor tab contains a **resizable side panel** that hosts two distinct AI
modes. The panel is only visible when the XSLT source is set to `custom` (inline
CodeMirror editor active). The AI button is hidden entirely when the AI provider
is `"disabled"`.

### Layout

```
┌────────────────────────────────┬──┬──────────────────────────┐
│                                │  │                          │
│   CodeMirror editor            │▓▓│   AI side panel          │
│   (min-width: 0, flex-1)       │▓▓│   (resizable, 240–720px) │
│                                │  │                          │
└────────────────────────────────┴──┴──────────────────────────┘
                              drag handle
```

The drag handle is a 5px column; dragging leftward expands the AI panel.
State: `xsltAiPanelWidth` (default 384px), `xsltIsDragging`.

### Panel modes

The panel has two mutually exclusive modes controlled by `xsltAiMode`:

| Mode | Value | Prompt | Component |
|------|-------|--------|-----------|
| Debug | `"debug"` | `xslt_debug` | Custom template (no `AiPanel`) |
| Discuss | `"discuss"` | `xslt_discuss` | `<AiPanel :chat="true" :show-apply="false" :sidebar="true">` |

#### Debug mode (default)

Single-shot. The user enters an error message in a `<textarea>` (`xsltDebugError`),
then clicks "Debug":

```
runXsltDebug()
  → xsltAiMode = "debug"
  → aiStore.clearResponse()          // keep chatHistory, clear live buffer only
  → aiStore.startStream("xslt_debug", {
        error_msg:   xsltDebugError.value,     // from textarea
        xslt_source: xsltCm.getValue(),        // current CM5 buffer
    })
```

The response streams into `aiStore.response` and is displayed in a monospace
`<span>` in the response area. No chat follow-up. The user can click "Debug" again
after changing the error text or editing the stylesheet.

#### Discuss mode

Multi-turn chat. The user clicks "Discuss":

```
runXsltDiscuss()
  → aiStore.resetChat()              // clear any previous debug response
  → xsltDiscussContext.value = { xslt_source: xsltCm.getValue() }
  → xsltAiMode = "discuss"
```

This replaces the custom debug panel with the `AiPanel` component (mounted via
`v-if="xsltAiMode === 'discuss' && xsltDiscussContext"`). `AiPanel` auto-starts on
mount, immediately sending the stylesheet as context. The `@close` event calls
`closeXsltAiPanel()`.

`show-apply` is `false` in this context because the output is explanatory text,
not code meant to be applied to the editor.

**Important**: the stylesheet content (`xslt_source`) is captured once, at the
moment "Discuss" is clicked. If the stylesheet changes afterwards, the context is
stale until the user closes and re-opens the panel.

### Panel lifecycle

```
openXsltAiPanel()    → xsltAiOpen=true; default mode = "debug" (if no mode set)
closeXsltAiPanel()   → aiStore.resetChat(); xsltAiOpen=false; xsltAiMode=null;
                        xsltDiscussContext=null
runXsltDiscuss()     → aiStore.resetChat(); capture context; mode="discuss"
runXsltDebug()       → aiStore.clearResponse(); startStream(...)
```

Closing the panel always calls `aiStore.resetChat()` to clear history and abort
any active stream.

---

## Bibliobuilder flow

**File**: `frontend/src/views/CollectionBibliobuilderview.vue`
**Route**: `/collections/:slug/bibliobuilder` (EiC+ only)

The Bibliobuilder page is a two-step tool: extract bibliography entries from the
collection's XML documents, then send them to the AI for normalization.

The page does **not** use the `AiPanel` component. It wires `useAiStore` directly,
following the same pattern as the XSLT debug panel.

### Step 1 — Extract

```
doExtract()
  → collectionsStore.extractBibl(collection.id)
      → GET /api/v1/collections/{id}/extract-bibl
      → backend runs XQuery (xqueries/collections/extract_bibl.xq)
      → returns raw <entries> XML with namespace-stripped <bibl>/<biblStruct>
  → rawEntries.value = xml
  → entryCount.value = count of <bibl>/<biblStruct> tags (regex)
  → showRaw.value = true   (auto-shows extracted XML for inspection)
  → aiStore.resetChat()    (discard any previous AI session)
```

### Step 2 — Run AI

```
runAi()
  → aiStore.continueChat("bibliobuilder", {}, rawEntries.value)
```

Note: `continueChat` is used (not `startStream`) so the extracted XML is passed
as the **first user message**, not as a context variable. The `bibliobuilder`
prompt has no `context_vars`, so `context` is always `{}`.

The response streams into `aiStore.response`, then into `aiStore.chatHistory`.
The response area auto-scrolls on each chunk via a watcher on `aiStore.response`.

### Follow-up turns

After the first response, a follow-up `<textarea>` appears (`v-if hasExchange`).
The user can ask questions or send additional batches:

```
sendFollowUp()
  → msg = chatInput.value.trim()
  → aiStore.continueChat("bibliobuilder", {}, msg)
```

`Ctrl+Enter` / `Cmd+Enter` triggers `sendFollowUp` from the textarea.

### Result actions

After the AI responds, the action bar shows:

| Action | Behaviour |
|--------|-----------|
| Edit | Sets `editableContent` to the last assistant response; replaces the read-only display with a `<textarea>` |
| Cancel edit | Clears `editableContent`; reverts to AI output |
| Copy | `navigator.clipboard.writeText(effectiveContent)` |
| Save | `collectionsStore.saveBibliography(collection.id, effectiveContent)` → auto-increments `version`; shows "Saved v{n}" badge |

`effectiveContent` = edited text (if editing) or last AI response.
A new AI exchange discards any in-progress edit automatically (watcher on
`aiStore.chatHistory.length`).

Saved bibliographies are versioned (one row per version per collection in
`collection_bibliographies`). One version per collection can be marked `is_public`,
which exposes it on the public website at `/browse/{slug}/bibliography`.

---

## Known design constraints

- **No server-side conversation persistence.** History is reconstructed from the
  frontend on every request. If the user closes the panel, the conversation is lost.
  This is intentional — no PII in the DB beyond what is already in `ai_request_logs`.
- **Rate limit is per-request, not per-turn.** Every call to `/complete` (including
  follow-up turns) consumes one slot of `ai_max_requests_per_hour`.
- **`document_edit_suggest` is single-shot by design.** The response is raw XML
  intended to be applied directly to the editor buffer. Chat follow-up could be
  added later by passing `:chat="true"` to the DocumentEditView sidebar panel.
- **The resolved template is never sent to the frontend.** The frontend only stores
  the assistant and user turns that come after the first response. The backend always
  re-resolves the template to reconstruct the full message list. This means
  `context` must be passed unchanged on every `continueChat` call.
