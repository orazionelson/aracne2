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
├── CollectionDetailView.vue  # Uses AiPanel with chat=true (validation context)
└── DocumentEditView.vue      # Uses ai store directly (editor context, no chat)
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

---

## System settings (ai_*)

Stored in `system_settings` table; managed by Admin in the Settings view.

| Key                          | Default            | Notes                            |
|------------------------------|--------------------|----------------------------------|
| `ai_provider`                | `"disabled"`       | `"openai"` / `"anthropic"` / `"gemini"` / `"disabled"` |
| `ai_openai_model`            | `"gpt-4o"`         |                                  |
| `ai_anthropic_model`         | `"claude-opus-4-6"`|                                  |
| `ai_gemini_model`            | `"gemini-1.5-pro"` |                                  |
| `ai_openai_api_key`          | —                  | Stored encrypted                 |
| `ai_anthropic_api_key`       | —                  | Stored encrypted                 |
| `ai_gemini_api_key`          | —                  | Stored encrypted                 |
| `ai_max_requests_per_hour`   | `20`               | Per-user rolling window          |
| `ai_privacy_warning_enabled` | `"false"`          | Shows banner in AiPanel          |

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

Used in: XSLT editor (not yet wired to AiPanel as of this writing — see DEFERRED.md).
Chat mode: not yet determined.

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
2. Add the provider name to the `if/elif` chain in `_get_provider()` in `service.py`.
3. Add a setting entry `ai_{name}_model` with a default value in `seed.py`
   (`DEFAULT_SETTINGS`).
4. Add `ai_{name}_api_key` handling — it is read via `get_decrypted_setting()` so no
   schema change is needed; the key is stored/managed through the Settings UI.
5. Update the `ai_provider` validation in the Settings view frontend if there is a
   closed enum there.

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
