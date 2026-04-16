# Search Engine Embed Widget

## Overview

Each **Search Engine** in Aracne2 can optionally expose a public-facing embed widget —
a self-contained JavaScript search box that any third-party website can embed with a
single `<script>` tag. The widget talks directly to the Aracne2 API via CORS-enabled
endpoints, so no server-side integration is required on the embedding site.

The embed subsystem is mounted on a **separate FastAPI sub-application** (`/api/v1/embed/`)
with its own CORS middleware configured to allow preflight from all origins. Actual origin
enforcement is done inside each route handler using a per-engine allowlist.

---

## Architecture

```
Third-party website
  │
  ├── loads <script src="https://aracne.example.org/api/v1/embed/{slug}/widget.js">
  │       ↓ (GET /embed/{slug}/widget.js — 5 min cache, no auth)
  │   Returns self-contained JS widget (generated from engine's embed_config)
  │
  └── widget makes fetch() calls:
        GET /embed/{slug}/search?q=...           — full-text search
        GET /embed/{slug}/advanced-search?q=...  — structural/attribute search
        (both: origin header checked against allowed_origins whitelist)
```

The widget code is generated **dynamically** from the search engine's `embed_config`
(mode, styles) — it is not a static file.

---

## Enabling embed on a search engine

1. Go to **Admin → Search Engines** and open a search engine
2. Toggle **Embed widget** → enabled
3. Configure **`embed_config`**:
   - `mode`: `"simple"` | `"advanced"` | `"both"`
   - `allowed_origins`: list of permitted request origins (empty = open to all)
4. Copy the embed snippet from the **Embed** tab and paste it into the third-party site

---

## Backend

### Files

| Path | Role |
|---|---|
| `backend/app/routers/embed.py` | FastAPI router — widget.js, search, advanced-search |
| `backend/app/services/embed.py` | Widget JS generation, origin check, search dispatch, log |
| `backend/app/models/search_engine_embed_log.py` | ORM model for embed request logs |
| `backend/app/schemas/search_engines.py` | `EmbedConfig`, `EmbedLogEntry` schemas |
| `backend/app/main.py` | Separate CORS sub-app mount at `/api/v1/embed` |

### Embed sub-app mount

```python
# backend/app/main.py
embed_app = FastAPI()
embed_app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["GET"])
embed_app.include_router(embed_router)
app.mount("/api/v1/embed", embed_app)
```

The outer `app` has a strict CORS policy (only configured origins). The `embed_app`
allows all origins so the browser's preflight passes — origin enforcement is then done
inside each handler.

### Embed config schema

```python
class EmbedConfig(BaseModel):
    mode: Literal["simple", "advanced", "both"] = "simple"
    allowed_origins: list[str] = []  # empty = open embed (all origins allowed)
```

`allowed_origins` entries must start with `http://` or `https://`. Trailing slashes
are normalised before comparison.

---

### Endpoints [pub] — no authentication required

All embed endpoints are public. Origin enforcement is handled inside the service.

---

#### `GET /api/v1/embed/{slug}/widget.js`

Return the self-contained JavaScript widget for the given search engine.

**Response**: `application/javascript`, `Cache-Control: max-age=300, public`

The script auto-detects the API base URL from its own `src` attribute, so no
server URL needs to be hardcoded in the embedding HTML.

**404** if the engine does not exist or `embed_enabled` is false.

---

#### `GET /api/v1/embed/{slug}/search`

Full-text search via the embed widget.

**Query parameters**:

| Parameter | Type | Constraint | Description |
|---|---|---|---|
| `q` | string | required, 1–512 chars | Search query |
| `collections` | string | optional | Comma-separated collection slugs to restrict search |
| `max_results` | int | 1–200, default 50 | Maximum results |

**Response `200`**:
```jsonc
{
  "data": {
    "hits": [
      {
        "doc_url": "https://aracne.example.org/collections/epistolario/documents/lettera-001",
        "collection_slug": "epistolario",
        "filename": "lettera-001.xml",
        "title": "Lettera a Fauriel, 3 maggio 1821",
        "kwic": "…citando il grande <em>Alessandro Manzoni</em>…"
      }
    ],
    "total": 1
  }
}
```

**403** if the request origin is not in the allowed list (still logged).

---

#### `GET /api/v1/embed/{slug}/advanced-search`

Structural/attribute search via the embed widget.

**Query parameters**:

| Parameter | Type | Description |
|---|---|---|
| `q` | string (max 512) | Optional full-text term |
| `element` | string (max 64, NCName pattern) | TEI element to search within (e.g. `persName`) |
| `attr_name` | string (max 64, NCName pattern) | Attribute name filter |
| `attr_value` | string (max 256) | Attribute value filter |
| `collections` | string | Comma-separated collection slugs |
| `max_results` | int (1–200) | Default 50 |

---

### Origin enforcement and logging

Every request to `/embed/{slug}/search` and `/embed/{slug}/advanced-search`:

1. **Checks** the `Origin` request header against `embed_config.allowed_origins`
2. **Logs** the request to `search_engine_embed_logs` regardless of outcome
   (origin, referer, IP, query, mode, allowed flag, timestamp)
3. **Returns 403** if the origin is blocked

```python
# backend/app/services/embed.py
def _check_origin(engine: SearchEngine, origin: str | None) -> bool:
    config = EmbedConfig.model_validate(engine.embed_config or {})
    if not config.allowed_origins:
        return True      # open embed — all origins allowed
    if origin is None:
        return False
    norm = origin.rstrip("/")
    return any(norm == allowed.rstrip("/") for allowed in config.allowed_origins)
```

---

## Frontend

### Files

| Path | Role |
|---|---|
| `frontend/src/stores/search_engines.ts` | Pinia store — includes embed config and log state |
| `frontend/src/views/admin/SearchEnginesView.vue` | Admin search engine management |

### Admin UI — Embed tab

The **Search Engines → Embed** tab shows:
- Enable/disable toggle
- Mode selector (`simple` / `advanced` / `both`)
- Allowed origins manager (add/remove)
- **Embed snippet** — two options:
  - `<script src="widget.js">` (external, CDN-cacheable)
  - Inline `<script>` with the full widget code (for strict CSP environments)
- **Embed logs** table: recent requests with origin, query, mode, allowed flag, timestamp

---

## Widget behaviour

The generated JavaScript widget:

- Derives the API base URL from its own `src` attribute at runtime — no hardcoded URLs
- Targets a `<div>` by `id` (default: `aracne2-{slug}`, or `data-target` attribute)
- Injects its own CSS (scoped via `.arc2w` class prefix) — no external CSS needed
- Renders tabs (if `mode = "both"`), simple search form, and/or advanced search form
- Hits `fetch(/embed/{slug}/search?q=...)` and renders result cards inline
- Result cards link to the document public URL (`doc_url`) in a new tab

### Embedding example

```html
<!-- Target div -->
<div id="aracne2-epistolario"></div>

<!-- Widget script — loads and renders the search box automatically -->
<script
  src="https://aracne.example.org/api/v1/embed/epistolario/widget.js"
  data-target="aracne2-epistolario">
</script>
```

### Inline embedding (strict CSP)

For sites that block external scripts:

```html
<div id="aracne2-epistolario"></div>
<script>
  /* paste the output of build_inline_snippet() here */
</script>
```

---

## Embed log data model

```
search_engine_embed_logs
─────────────────────────────
id                  BIGINT  PK
search_engine_id    UUID    FK → search_engines.id ON DELETE CASCADE
origin              VARCHAR(512) | NULL
referer             VARCHAR(512) | NULL
ip_address          TEXT | NULL
query               VARCHAR(512)
mode                VARCHAR(32)   — "simple" | "advanced"
allowed             BOOLEAN       — false = origin was blocked
requested_at        TIMESTAMPTZ
```

Logs are available to Admin via the search engine detail page (paginated, newest first).

---

## Security

| Concern | Mitigation |
|---|---|
| CORS bypass | Preflight allowed by sub-app; actual origin checked per-engine in handler |
| Open embed | Explicitly opt-in (empty `allowed_origins`); default new engine: embed disabled |
| Query injection | `q` max 512 chars, `element` / `attr_name` validated against NCName pattern |
| Rate limiting | Falls under the global 200 req/min limit; no per-engine limit yet |
| Blocked origin log | Blocked requests are still logged — useful for detecting misconfigured origins |
| IP logging | Client IP stored from `X-Forwarded-For` or `request.client.host` |
