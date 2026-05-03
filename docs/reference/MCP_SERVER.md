# MCP Server — Technical Reference

The **Model Context Protocol** (MCP) integration exposes Aracne2 to
LLM clients (Claude Desktop, Cursor, Claude Code) as a standardised
read-only data source. This document covers the wire protocol,
authentication model, tool / resource registry, and the contract
for adding new tools.

For end-user setup (how an Admin issues tokens, how an editor pastes
the snippet into Claude Desktop) see the in-app help page at
**Help → Advanced → MCP server**, source
[`backend/help_docs/03-advanced/07-mcp-server.md`](../../backend/help_docs/03-advanced/07-mcp-server.md).

For the future-roadmap shape (write tools, personal tokens, audit
log) see [TO_DO.md](../TO_DO.md).

---

## File map

```
backend/app/plugins/mcp_server/
├── __init__.py
├── plugin.py              # PluginMeta + router mount (non-native)
├── router.py              # POST /api/v1/mcp — JSON-RPC entrypoint
├── server.py              # JSON-RPC dispatcher + ToolSpec registry
├── auth.py                # Bearer token → McpAuthContext resolver
├── tools/
│   ├── __init__.py
│   ├── collections.py     # list_collections, get_collection, list_documents,
│   │                      # get_document_source, tei_to_text
│   └── entities.py        # search_entities, find_entity_occurrences,
│                          # lookup_authority
├── resources/
│   └── __init__.py        # corpus://, collection://, document://, entity://
└── tests/__init__.py

backend/app/
├── models/corpus.py       # ORM: corpora, corpus_collections, mcp_tokens
├── schemas/corpora.py     # Pydantic for corpus / token CRUD + reveal
├── services/corpora.py    # CRUD + token issuance / revocation / resolution
├── routers/corpora.py     # /api/v1/corpora — Admin-only CRUD + tokens
└── tests/test_corpora.py  # Corpus REST API + MCP auth/tools end-to-end

frontend/src/
├── stores/corpora.ts      # Pinia store
└── views/admin/CorporaView.vue   # /admin/corpora panel
```

---

## Why a non-native plugin

MCP is opt-in: a deployment that doesn't intend to expose the
endpoint should never see the route. The plugin sits at
`backend/app/plugins/mcp_server/` (no `_native` prefix), starts
**inactive**, and the route mounts only after an Admin activates it
from `/admin/plugins`. The activate / deactivate hot-mount path
already shipped in commit
[`6950645`](https://github.com/orazionelson/aracne2/commit/6950645)
applies — no backend restart required.

The plugin advertises **no capability** (no `inline_authority`, no
`collection_deposit`, no `website_deposit`). Its UI surface is
`/admin/corpora`, a dedicated page rather than an auto-cabled tab.

---

## Wire protocol

### Transport: MCP Streamable HTTP

A single endpoint at `POST /api/v1/mcp`. Each request body is a
**JSON-RPC 2.0** envelope; each response is the matching JSON-RPC
response object. Both single-request and batched-array forms are
supported.

```http
POST /api/v1/mcp HTTP/1.1
Host: aracne2.example
Authorization: Bearer aracne2_mcp_<urlsafe-32-bytes>
Content-Type: application/json

{ "jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {} }
```

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "result": {
    "tools": [
      {
        "name": "list_collections",
        "description": "...",
        "inputSchema": { "type": "object", "properties": { ... } }
      },
      ...
    ]
  }
}
```

The transport choice is the modern MCP "Streamable HTTP", not SSE.
Streamable HTTP is simpler to wire under FastAPI (no long-lived
connection state) and is supported by Claude Desktop, Cursor, and
Claude Code as of late 2025.

### Methods implemented

| Method | What it does |
|---|---|
| `initialize` | Handshake — returns server name, version, protocol version, capability flags |
| `ping` | Empty round-trip the client uses to check liveness |
| `notifications/initialized` | Notification (no response) — accepted and dropped |
| `tools/list` | Lists every registered tool with its JSON-Schema |
| `tools/call` | Dispatches to a tool by name |
| `resources/list` | Lists URI templates + a concrete `corpus://` for the bearer's own corpus |
| `resources/read` | Resolves a URI through the resources resolver |

Anything else maps to JSON-RPC error `-32601 Method not found`.

### Result envelope

Tool results are always wrapped in MCP's `content` envelope:

```json
{
  "result": {
    "content": [
      { "type": "text", "text": "<JSON-encoded payload>" }
    ],
    "isError": false
  }
}
```

The dispatcher always JSON-encodes the tool's Python return value
into a single text block — the LLM unfolds it transparently. On
domain errors the same envelope flips `isError: true` and carries an
error description in the text block:

```json
{
  "result": {
    "content": [
      { "type": "text", "text": "{\"error\": \"Collection 'xyz' not found in this corpus.\"}" }
    ],
    "isError": true
  }
}
```

### Error codes

| JSON-RPC code | Meaning | When |
|---|---|---|
| `-32001` | Unauthorized | Missing / malformed / unknown / revoked bearer token |
| `-32600` | Invalid Request | Body is not a valid JSON-RPC object/array |
| `-32601` | Method not found | Unknown JSON-RPC method |
| `-32602` | Invalid params | Missing required argument or unknown tool name |
| `-32700` | Parse error | Body is not valid JSON |

`401` is returned at the HTTP layer for `-32001` (unauthenticated
client should not see internal protocol details). All other JSON-RPC
errors are returned with HTTP `200` per spec.

---

## Authentication model

### Three primitives

```
                  ┌──────────────────────┐
                  │   Admin              │
                  │   /admin/corpora     │
                  └─────┬──────────┬─────┘
                        │ creates  │ issues
                        ▼          ▼
            ┌─────────────────┐ ┌────────────────┐
            │     Corpus      │ │   MCP token    │
            │ name + descr.   │ │ corpus_id +    │
            │ collections[]   │ │ bcrypt(plain)  │
            └────────┬────────┘ └────────┬───────┘
                     │ scopes            │ resolves
                     ▼                   ▼
            ┌──────────────────────────────────┐
            │           McpAuthContext         │
            │ token, corpus, collection_ids[]  │
            └──────────────────────────────────┘
```

- **Corpus** — thematic grouping of public collections. Many-to-many
  with `collections` via `corpus_collections`. Multiple corpora can
  share a collection.
- **MCP token** — bearer string issued for one corpus. Stored as
  bcrypt hash in `mcp_tokens.hashed_token`; the plaintext is shown
  to the Admin **once** at creation, alongside a Claude Desktop
  snippet pre-filled with the instance URL.
- **`McpAuthContext`** — frozen dataclass built per request from
  the resolved (token, corpus). Tools and resources read it freely
  but cannot mutate it.

### Plaintext token format

```
aracne2_mcp_<43 chars urlsafe-base64 of 32 random bytes>
```

The `aracne2_mcp_` prefix lets `resolve_token` reject obviously
unrelated bearers (random web crawlers, leaked tokens from other
services) without touching the database. Behind the prefix sits 32
bytes of `secrets.token_urlsafe(32)` randomness.

### Token resolution

`app/services/corpora.py:resolve_token(plaintext)`:

1. Reject if missing the `aracne2_mcp_` prefix.
2. Load every non-revoked row from `mcp_tokens` (the per-deployment
   row count is small — a handful per corpus).
3. `bcrypt.verify(plaintext, row.hashed_token)` against each.
4. On match, set `last_used_at = now()` and return the row + corpus.

The linear scan is acceptable because the threat model is "bcrypt
verification per request" — not a sub-millisecond hot path. A
deployment with 50+ tokens that wants to optimise can add a
short-lived in-memory hash → token cache; out of scope today.

### Database schema

Three tables introduced by Alembic `0070_corpora_and_mcp_tokens.py`:

- **`corpora`** — `id, name (unique), description, created_at, updated_at`
- **`corpus_collections`** — `(corpus_id, collection_id)` PK,
  `ON DELETE CASCADE` from both sides.
- **`mcp_tokens`** — `id, corpus_id (FK CASCADE), label, hashed_token,
  created_at, last_used_at, revoked_at, created_by (FK SET NULL)`.

Cascade rules:

- Deleting a corpus revokes (drops) every token issued for it.
- Deleting a collection removes the membership row but the corpus
  survives.
- Deleting the user that issued a token sets `created_by = NULL`
  but preserves the token (it stays usable; the corpora panel just
  shows "issued by: deleted user").

### Per-tool corpus scoping

Every tool intersects its query with two filters:

1. `Collection.is_public = true AND Collection.status = 'published'`
   — same gate as the public website.
2. `Collection.id IN (ctx.collection_ids)` — the token's corpus
   membership.

A token whose corpus is empty therefore sees an empty result set
everywhere; no error, no leak. The `_publishable_filter()` helper
in `tools/collections.py` centralises the join so a future tool
author cannot forget either filter.

---

## Tools registry

The `TOOLS` list in `server.py` is the source of truth — adding a
tool is one entry.

### Current catalogue (Phase 1 + 1.5)

| Tool | Args | Returns | Service called |
|---|---|---|---|
| `list_collections` | `limit`, `offset` | array of `{slug, title, description, published_at}` | direct SQLAlchemy query |
| `get_collection` | `slug` | `{slug, title, description, license_id, schema_id, published_at, target_date, document_count, editor_display_name}` | + `existdb_client.list_collection` for doc count |
| `list_documents` | `collection_slug`, `limit`, `offset` | array of `{filename}` | `existdb_client.list_collection` |
| `get_document_source` | `collection_slug`, `filename` | `{slug, filename, truncated, size_bytes, content}` (≤ 2 MB) | `existdb_client.get_document` |
| `tei_to_text` | `collection_slug`, `filename` | `{slug, filename, truncated, char_count, text}` | `existdb_client.get_document` + `defusedxml.itertext()` |
| `search_entities` | `q`, `type?`, `collection_slug?`, `limit` | array of `{id, canonical_form, type, authority_uri, occurrence_count}` | `app.plugins._native.named_entities.service.get_public_entities` |
| `find_entity_occurrences` | `entity_id`, `limit` | array of `{collection_slug, document_filename, raw_form, context}` | `app.plugins._native.named_entities.service.get_entity_occurrences` |
| `lookup_authority` | `service` ∈ {`wikidata`, `orcid`, `ror`, `viaf`}, `q`, `limit` | `{service, query, hits[]}` with `{id, label, description?, uri}` per hit | per-plugin `service.search()` |

### `ToolSpec` shape

Defined in `server.py`:

```python
@dataclass(frozen=True)
class ToolSpec:
    name: str                  # camelCase or snake_case — keep snake_case
    description: str           # full sentence; advertised verbatim to the LLM
    schema: dict[str, Any]     # JSON-Schema object for inputSchema
    handler: ToolHandler       # async (db, ctx, args) -> Any
```

`ToolHandler = Callable[[AsyncSession, McpAuthContext, dict[str, Any]], Awaitable[Any]]`

### Adding a tool — minimal example

Suppose we want to expose `count_published_collections`. Two edits:

```python
# tools/collections.py
COUNT_PUBLISHED_COLLECTIONS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {},
    "additionalProperties": False,
}

async def count_published_collections(
    db: AsyncSession, ctx: McpAuthContext, args: dict[str, Any],
) -> dict[str, int]:
    n = await db.scalar(
        _publishable_filter(
            select(func.count(Collection.id)),
            ctx.collection_ids,
        )
    )
    return {"count": int(n or 0)}
```

```python
# server.py — TOOLS list
ToolSpec(
    name="count_published_collections",
    description="Return the number of published collections visible to this token.",
    schema=COUNT_PUBLISHED_COLLECTIONS_SCHEMA,
    handler=count_published_collections,
),
```

Ship a test in `app/tests/test_corpora.py` patterned after
`test_mcp_initialize_and_tools_list`. `tools/list` and `tools/call`
pick up the new tool automatically — no other wiring.

### Read-only invariant

Every tool today is read-only: no DB writes, no eXist writes, no
external mutations. Phase 2 (write tools) will add an explicit
`mcp_allow_writes` flag on `mcp_tokens` and a separate registry for
write handlers — see [TO_DO.md](../TO_DO.md). Do
**not** smuggle a write into the existing registry: the read-only
guarantee is part of the security argument for issuing bearer tokens
without per-call admin consent.

---

## Resources registry

Three URI templates + one concrete URI per request:

| Scheme | What it returns | Resolver |
|---|---|---|
| `corpus://<name>` | Markdown manifest of the bearer's own corpus (informational `<name>` segment, real corpus comes from `ctx`) | `_read_corpus(ctx)` |
| `collection://<slug>` | Markdown summary of one collection | `_read_collection(...)` |
| `document://<slug>/<filename>` | Raw TEI XML, capped at 2 MB with truncation marker | `_read_document(...)` |
| `entity://<uuid>` | Markdown card for one named entity | `_read_entity(...)` |

`resources/list` returns the four templates plus a concrete
`corpus://<bearer-corpus-name>` so the LLM client discovers the
bearer's own corpus without a tool call.

The corpus URI's `<name>` segment is **informational only**: the
resolver always reads `ctx.corpus`, so a bearer can't peek at
another corpus by guessing names.

---

## HTTP layer

### Endpoint

`POST /api/v1/mcp` — single Streamable-HTTP entrypoint.

A `GET /api/v1/mcp` handshake handler returns `200 {}` so clients
that probe with GET before POST consider the endpoint reachable.
The real work happens via POST.

### Rate limiting

`@limiter.limit("60/minute")` per IP, applied at the router. The
60-req cap is generous enough for interactive chat (a typical
session is a handful of tool calls per turn) but tight enough to
make abusive scrapers visible in `last_used_at` analytics.

### CORS

None. MCP doesn't run from a browser — clients are Claude Desktop,
Cursor, or Claude Code, which are native applications hitting the
URL directly. The endpoint is intentionally not allowed from any
web origin.

### Body size

Inherits the global nginx 50 MB cap. JSON-RPC payloads are tiny in
practice; the cap exists for sanity, not as a real constraint.

---

## Frontend

### `/admin/corpora`

Two-column layout in
[`frontend/src/views/admin/CorporaView.vue`](../../frontend/src/views/admin/CorporaView.vue):

- **Left**: list of corpora with `{n collections, t active tokens}`
  metadata.
- **Right**: detail card for the selected (or new) corpus —
  editable name + description + multi-select of eligible collections
  + table of issued tokens with issue / revoke buttons + freshness
  badges (`stale` after 90 days idle, `never used` for tokens older
  than 14 days never called).

### Token reveal modal

`POST /corpora/{id}/tokens` returns `McpTokenCreated` carrying both
`plaintext` and `claude_desktop_snippet`. The SPA shows them in a
**one-shot modal** that the Admin must dismiss explicitly. After
dismissal the plaintext is unrecoverable; only revocation +
re-issuance gets a new value.

### Pinia store

[`frontend/src/stores/corpora.ts`](../../frontend/src/stores/corpora.ts)
mirrors the REST API. The `tokensByCorpus` cache lets the admin
panel switch corpus selection without re-fetching every list.

---

## Operational notes

### Activating

1. Admin → `/admin/plugins` → activate **MCP Server**. This
   hot-mounts `POST /api/v1/mcp` on the running ASGI app.
2. Admin → `/admin/corpora` → create the first corpus, tick its
   collections, save.
3. Inside the corpus, click **Issue token**, give it a label, copy
   the plaintext + Claude Desktop snippet from the modal.
4. Hand both to the editor through a secure channel.

### Deactivating

`/admin/plugins` → deactivate **MCP Server**. The route unmounts
and every active bearer starts getting `404` on `/api/v1/mcp`.
Tokens stay in the database (with their `revoked_at = NULL`) so
re-activating restores access without re-issuing.

### Rotating a token

Admin → corpus → revoke the token → issue a fresh one with the
same label. The editor pastes the new value in
`claude_desktop_config.json` and restarts Claude Desktop.

### Audit attribution

Every token row stores `created_by` (the admin who issued it). The
column survives a hard delete of the user via `ON DELETE SET NULL`,
so the audit trail only loses the username, not the token row's
existence. Phase 3 plans a per-call audit log; today the platform
records issuance / revocation in the central `audit_log` and
relies on `last_used_at` for activity tracking.

### Health

The MCP endpoint reuses the platform's standard request logging
and structlog pipeline — no dedicated health surface. To probe a
running instance:

```bash
curl -s -X POST https://aracne2.example/api/v1/mcp \
  -H "Authorization: Bearer aracne2_mcp_..." \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"ping","params":{}}'
```

A healthy server returns `{"jsonrpc":"2.0","id":1,"result":{}}`.

---

## Security model summary

The threat surface is intentionally narrow:

- **No write paths.** Every tool is read-only. The MCP endpoint
  cannot publish, edit, or delete anything.
- **Public-data only.** Every read is gated by
  `is_public AND status='published'` — the same filter as the
  public website. A token can never see drafts, private
  collections, or staging content.
- **Corpus-scoped.** Tokens are bound to a corpus at issuance
  time; cross-corpus reads are impossible without the issuing
  Admin's involvement.
- **Bcrypt-hashed at rest.** Plaintext tokens never persist in the
  DB; they're shown to the Admin once, then disappear.
- **Self-identifying prefix.** `aracne2_mcp_` lets a leaked token
  be recognised in logs / scanners without ambiguity.
- **Revocable in one click.** Revocation is instantaneous and
  takes effect on the next request; no cache to invalidate.

What the model **doesn't** protect against:

- A compromised Admin account can issue a token to an attacker.
  Mitigation lives outside MCP — protect the admin account.
- A compromised editor laptop leaks the token to whoever reads
  `claude_desktop_config.json`. Mitigation: short-lived tokens
  (rotate every 90 days; the admin panel surfaces stale tokens),
  full-disk encryption on editor laptops.
- A token reads the same data the public website serves — there's
  no in-platform leak, but if a publication should not be discoverable
  via API, it should not be published at all.

---

## See also

- In-app help: **Help → Advanced → MCP server**
  ([backend/help_docs/03-advanced/07-mcp-server.md](../../backend/help_docs/03-advanced/07-mcp-server.md))
- [PLUGINS.md](PLUGINS.md) — plugin architecture, hot mount/unmount
- [NON_NATIVE_PLUGINS.md](NON_NATIVE_PLUGINS.md) — sibling non-native plugins
- [API_FORMAT.md](API_FORMAT.md) — REST envelope (the `/corpora` admin endpoints conform to it; the `/mcp` endpoint speaks JSON-RPC, not the platform envelope)
- [TO_DO.md](../TO_DO.md) — backlog entries for Phase 2 (write tools) and Phase 3 (personal tokens, members, audit)
