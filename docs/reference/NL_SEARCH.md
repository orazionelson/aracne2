# `nl_search` — natural-language search plugin

## Overview

`nl_search` is a **non-native** plugin that surfaces a public,
chat-style search box on the deployment's own URL. Visitors type a
question in natural language; the plugin's orchestrator runs an LLM
**tool-use loop** against the platform's MCP read tools, and streams
back a synthesised answer with citations to real TEI documents.

Off by default. An Admin must:

1. Activate the plugin from `/admin/plugins`.
2. Configure provider, model, corpus, and (optional) API key from
   **Settings → NL search**.
3. Flip `public_link_nl_search_enabled` from
   **Public Pages → Pagine → Plugin links** to surface the public
   home-page tile (the `/search-nl` route works regardless).

For the user-facing how-to (admin setup + visitor flow) see the
in-app help at **Help → Advanced → Natural-language search**, source
[`backend/help_docs/03-advanced/08-nl-search.md`](../../backend/help_docs/03-advanced/08-nl-search.md).

For the original brainstorm see
[TO_DO.md](../TO_DO.md). For the auto-cabling
primitive that surfaces the link see
[PUBLIC_NAVIGATION.md](PUBLIC_NAVIGATION.md).

---

## Architecture in one paragraph

```
visitor (browser)                                    LLM provider
   │                                                       ▲
   │   POST /api/v1/nl-search/query                        │
   │   { "query": "..." }              tool-use round      │
   ▼                                          ▲           │
endpoint  ─→  pre-flight gates  ─→  orchestrator  ─tools─►MCP dispatch
(SSE)        - rate-limit                 │              (in-process,
              - auth gate                 │               no HTTP loop)
              - budget gate               ▼                   │
              - concurrency        emit SSE events            │
              - cache lookup       (status, chunk, citations,  │
                                     done, error)             │
                                                               │
                                                               ▼
                                                           postgres
                                                       cache + budget
```

Tool calls go through `app.plugins.mcp_server.server.dispatch()`
**as Python function calls**, not over HTTP — the orchestrator
constructs a synthetic `McpAuthContext` from the configured corpus
so the same security boundary as the editor MCP path is preserved.

---

## File map

```
backend/app/plugins/nl_search/
├── __init__.py
├── plugin.py                  # PluginMeta + public_navigation descriptor
├── router.py                  # POST /api/v1/nl-search/query (SSE)
├── service.py                 # auth gate, concurrency, SSE formatter
├── orchestrator.py            # tool-use loop, MCP dispatch, citation enforcement
├── cache.py                   # SHA-256-keyed identical-query cache
├── budget.py                  # per-day spend / queries counter
├── prompts/
│   ├── __init__.py            # load_system_prompt(lang)
│   ├── system_prompt_en.md
│   └── system_prompt_it.md
├── providers/
│   ├── __init__.py
│   ├── base.py                # ToolUseProvider ABC + event types
│   ├── ollama.py              # local provider (default, $0)
│   ├── anthropic.py           # cloud provider (opt-in, billed)
│   └── factory.py             # make_provider(db) reads system_settings
└── tests/
    ├── test_providers.py      # MockTransport-based wire-format tests
    ├── test_orchestrator.py   # fake provider + monkey-patched dispatch
    └── test_endpoint.py       # FastAPI TestClient pre-flight branches

backend/app/models/
├── nl_search_cache.py         # ORM for the cache table
└── nl_search_budget.py        # ORM for the per-day counter

backend/alembic/versions/
├── 0076_nl_search_cache.py
└── 0077_nl_search_budget.py

frontend/src/
├── views/public/NlSearchPublicView.vue   # SSE consumer + UI
├── components/public-pages/registry.ts   # PUBLIC_PAGE_COMPONENTS entry
└── router/index.ts                        # /search-nl route
```

---

## Data model

### `nl_search_cache`

```
nl_search_cache
─────────────────────────────
key             VARCHAR(64) PK   — SHA-256 of (corpus_id, provider, model, normalised_query)
response_json   TEXT             — serialised SSE-event list to replay
expires_at      TIMESTAMPTZ      — created_at + nl_search_cache_ttl_minutes
hits            INT              — bumped on every cache hit
created_at      TIMESTAMPTZ
```

Migration: [`0076_nl_search_cache.py`](../../backend/alembic/versions/0076_nl_search_cache.py).
The cache stores *every* SSE event the endpoint emits so a hit
replays the full timeline (status hints, chunks, citations, done)
verbatim — no LLM round-trip, no MCP dispatch. Expired rows are not
deleted on read; a future cleanup job sweeps them.

### `nl_search_budget_day`

```
nl_search_budget_day
─────────────────────────────
day         DATE PK
eur_spent   NUMERIC(10,4)        — sum of estimated round costs
queries     INT                  — total queries that hit the LLM
```

Migration: [`0077_nl_search_budget.py`](../../backend/alembic/versions/0077_nl_search_budget.py).
Ollama runs always add `0` to `eur_spent` (local, no $ cost) but
still bump `queries` so an operator can chart volume.

---

## System settings

All under the `nl_search_*` prefix. Defaults seeded in
[`backend/app/db/seed.py`](../../backend/app/db/seed.py); modified
through the Admin Settings UI.

| Key | Default | Purpose |
|---|---|---|
| `nl_search_require_login` | `"true"` | Anonymous access is opt-in. Default-on protects the deployment from anonymous LLM consumption. |
| `nl_search_provider` | `"ollama"` | `ollama` \| `anthropic` |
| `nl_search_api_key` | `""` | Cloud provider API key — Fernet-encrypted at rest in `SENSITIVE_KEYS`, masked in API responses |
| `nl_search_model` | `"llama3.1"` | Provider-specific model id; default depends on provider when empty |
| `nl_search_corpus_id` | `""` | UUID of the MCP `corpora` row to expose to the public. Required — empty value emits `CORPUS_NOT_CONFIGURED` |
| `nl_search_daily_budget_eur` | `"2.00"` | Hard daily cap; endpoint short-circuits to 503 when exceeded. `"0"` disables the gate |
| `nl_search_max_concurrent` | `"2"` | In-process semaphore for the orchestrator. Reject-on-full |
| `nl_search_query_timeout_s` | `"30"` | Per-LLM-round wall-clock cap |
| `nl_search_cache_ttl_minutes` | `"60"` | Expiry written into `nl_search_cache.expires_at` |
| `nl_search_max_input_chars` | `"500"` | Soft cap on the request body's `query` field |
| `nl_search_max_tool_rounds` | `"6"` | Maximum tool-use loop iterations before forcing `end_turn` |

`nl_search_api_key` is added to
[`SENSITIVE_KEYS`](../../backend/app/core/encryption.py) so it
never appears in plaintext in API responses or logs.

---

## REST surface

### `POST /api/v1/nl-search/query`

Public — guarded by `nl_search_require_login` rather than the role
ladder. Rate-limited at **3/min, 30/day per IP**.

**Request body** (`NlSearchQuery`):

```jsonc
{
  "query": "What does the corpus say about the father of Charles I?",
  "lang": "en"   // optional; falls back to system default_language → "en"
}
```

**Response**: `text/event-stream`. Events:

| `event:` | `data:` payload | When |
|---|---|---|
| `status` | `{"phase": "thinking"}` | Round starts |
| `status` | `{"phase": "tool_call", "name": "search_entities"}` | Each tool dispatch |
| `status` | `{"phase": "tool_done", "name": "...", "is_error": false}` | After each tool dispatch |
| `chunk`  | `{"text": "..."}` | Incremental answer text |
| `citations` | `{"items": [{"slug": "...", "filename": "...", "excerpt": "..."}]}` | After the final round |
| `error`  | `{"code": "BUDGET_EXCEEDED", "message": "..."}` | Pre-stream failure surfaced inside the stream |
| `done`   | `{}` | Terminal marker |

**HTTP status codes** (errors that need an out-of-stream signal):

| Code | When |
|---|---|
| 401 | `nl_search_require_login=true` and no auth |
| 413 | Query exceeds `nl_search_max_input_chars` |
| 429 | slowapi rate limit hit |
| 503 | Daily budget exhausted |
| 200 + `error` event | Anything that emerges during streaming (corpus not configured, provider misconfigured, provider error, internal error) |

---

## Tool subset

The orchestrator advertises six MCP read tools to the LLM (decision
4 in the §25 brainstorm):

| Tool | Purpose |
|---|---|
| `search_entities` | Search the named-entities index |
| `find_entity_occurrences` | List document occurrences of one entity |
| `get_collection` | Per-slug collection metadata |
| `list_documents` | Document filenames inside a collection |
| `get_document_source` | Raw TEI XML (truncated at 2 MB) |
| `tei_to_text` | Plain-text body without markup |

The schemas come straight from
[`app.plugins.mcp_server.server.TOOLS`](../../backend/app/plugins/mcp_server/server.py)
so the wire format is identical to the editor's MCP path. Tools
outside this list (e.g. `lookup_authority`, write-shaped tools from
hypothetical Phase-2 MCP) are deliberately not exposed — the public
endpoint must never reach beyond the published, indexed corpus.

---

## Citation enforcement

System prompt instructs the LLM to end every answer with a
`## Citations` (or `## Citazioni`) heading followed by one-line
JSON objects:

```json
{"slug": "manzoni", "filename": "letter_001.xml", "excerpt": "..."}
```

The orchestrator:

1. Maintains a **whitelist** of `(slug, filename)` pairs harvested
   from every successful tool result during the conversation.
2. Parses the answer's tail for citation JSON objects.
3. Drops every citation whose `(slug, filename)` is not in the
   whitelist — silently, the user only sees the cleaned list.

A model that hallucinates a slug therefore cannot leak it past the
endpoint. The whitelist scan is recursive: a tool result that nests
document refs inside lists/dicts still contributes its pairs.

---

## Provider adapters

### `ToolUseProvider` ABC

[`providers/base.py`](../../backend/app/plugins/nl_search/providers/base.py)
defines the event-stream contract:

```python
class ToolUseProvider(ABC):
    def run_round(self, *, messages, tools, timeout_s) -> AsyncGenerator[
        TextChunk | ToolCallRequest | Done, None
    ]: ...
```

Implementations yield one or more `TextChunk` / `ToolCallRequest`
events, then exactly one `Done(stop_reason, usage)`. The orchestrator
collects events per round and decides whether to loop.

### `OllamaToolUseProvider`

POST `/api/chat` with the OpenAI-compatible `tools` parameter.
Default at `http://ollama:11434` (override via `OLLAMA_HOST` env
var). Reports zero token counts so the budget table tracks volume
but not cost.

### `AnthropicToolUseProvider`

Anthropic Messages API with structured `content` blocks
(`type: text`, `type: tool_use`, `type: tool_result`). Non-streaming
on each round — streaming the provider's own SSE while interleaving
tool calls is complex and adds latency without obvious UX gain
(the user already sees per-tool status hints from the orchestrator).

### Factory

[`providers/factory.py`](../../backend/app/plugins/nl_search/providers/factory.py)
reads `nl_search_provider` and falls back to Ollama on empty /
unknown values; Anthropic without `nl_search_api_key` raises
`ProviderError`, surfaced to the browser as the
`PROVIDER_MISCONFIGURED` SSE error event.

---

## Budget estimation

[`budget.py:estimate_eur`](../../backend/app/plugins/nl_search/budget.py)
maps `(provider, model)` → `(input_eur_per_mtok, output_eur_per_mtok)`.
Ollama always returns `0`. Cloud models without an explicit entry
fall back to a conservative **(€10 / €50 per million tokens)** so
an unrecognised model can never under-bill. Operators with tighter
cost tracking edit the rate table directly — it is a small static
dict, not a configurable setting.

---

## Caching

[`cache.py:build_key`](../../backend/app/plugins/nl_search/cache.py)
normalises the query (whitespace-trimmed, lowercased) and keys the
SHA-256 over `(corpus_id, provider, model, normalised_query)`.
Trivially-different formulations of the same question therefore hit
the same row.

The cached payload is the **whole SSE-event list**, so a hit
reproduces the original UX (status hints + progressive chunks +
citations) without any LLM round-trip.

---

## Frontend

[`frontend/src/views/public/NlSearchPublicView.vue`](../../frontend/src/views/public/NlSearchPublicView.vue)
opens the SSE stream via `fetch` + `ReadableStream` reader (POST
prevents using `EventSource`), parses events frame-by-frame, and
maintains four reactive bindings:

| Binding | Source | UI |
|---|---|---|
| `answer` | `chunk` events accumulated | Plain-text body (markdown-it not currently in the frontend dep tree) |
| `status` | `status` events | Italic hint above the answer ("Querying tool: search_entities…") |
| `citations` | last `citations` event | Citation strip with `router-link`s to public document pages |
| `errorCode` | `error` event or non-200 HTTP | Localised banner via a code-to-key switch |

The view is registered in
[`PUBLIC_PAGE_COMPONENTS`](../../frontend/src/components/public-pages/registry.ts)
so §24's auto-cabling can surface the link, and a dedicated route at
`/search-nl` is declared under `PublicLayout` so the URL works
regardless of the public-link toggle.

---

## Tests

| Path | Coverage |
|---|---|
| [`tests/test_providers.py`](../../backend/app/plugins/nl_search/tests/test_providers.py) | Wire-format round trips with `httpx.MockTransport` for both providers — plain text, tool_use, mixed, JSON-string arguments quirk, HTTP error mapping |
| [`tests/test_orchestrator.py`](../../backend/app/plugins/nl_search/tests/test_orchestrator.py) | Fake provider + monkey-patched dispatch — single-round end_turn, two-round tool_use, citation hallucination drop, ProviderError propagation, citation-extractor edge cases |
| [`tests/test_endpoint.py`](../../backend/app/plugins/nl_search/tests/test_endpoint.py) | Pre-flight branches against the FastAPI TestClient — 401 anonymous, 503 budget, `CORPUS_NOT_CONFIGURED` event, cache replay path |

---

## Open follow-ups (deferred)

- **Streaming the provider's own SSE** to forward text chunks faster
  than per-round granularity. Re-evaluate after first deployment.
- **Concurrency overflow = queue** (today's mode is reject). Add a
  `nl_search_concurrency_overflow=queue|reject` setting if needed.
- **Captcha gate** before the first query of a session
  (`nl_search_captcha_enabled` is reserved in spec but not wired).
- **Cleanup job** for expired `nl_search_cache` rows.
- **Per-provider fine-grained rate** (default is shared with the
  endpoint's slowapi limit).
- **Admin observability**: a small dashboard reading
  `nl_search_budget_day` to show 30-day spend / queries.
