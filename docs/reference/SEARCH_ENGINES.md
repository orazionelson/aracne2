# Search Engines

## Overview

A **Search Engine** in Aracne2 is a configurable, standalone search interface
that allows end users to perform full-text and structural searches across one or
more published collections. Each Search Engine is independently deployable: it
can be built into a static HTML page served directly by Aracne2, called via API,
or embedded as a JavaScript widget inside any third-party website.

Search Engines are managed by **Designer+** users (Designer, EditorInChief, or
Admin). The public search endpoints require no authentication.

---

## What a Search Engine is

A Search Engine is a named entity with:

- **A slug** — unique URL identifier (e.g. `epistolario-search`)
- **A title** — displayed in the built HTML page header
- **A set of linked collections** — only published + public collections can be
  assigned; multiple collections can be searched simultaneously
- **Appearance settings** — background colour, header colour, custom CSS/JS,
  optional jQuery inclusion, optional footer text
- **Cache configuration** — server-side query result caching (TTL in minutes;
  0 = disabled)
- **Advanced search configuration** — list of TEI element names and attribute
  names that users can search structurally
- **An embed widget** — optional JS widget embeddable on external sites with
  per-origin access control (see [EMBED_WIDGET.md](./EMBED_WIDGET.md))

---

## Data model

### `search_engines`

| Column | Type | Description |
|---|---|---|
| `id` | UUID | Primary key |
| `slug` | VARCHAR(200) unique | URL slug |
| `title` | TEXT | Display title |
| `build_status` | Enum | `idle` / `pending` / `building` / `done` / `failed` |
| `last_build_at` | TIMESTAMPTZ | Timestamp of last successful HTML build |
| `build_error` | TEXT | Error message from last failed build |
| `cache_ttl_minutes` | INT (0–10 080) | Query cache TTL; 0 disables caching |
| `page_bg_color` | VARCHAR(32) | Page background hex colour |
| `header_bg_color` | VARCHAR(32) | Header background hex colour |
| `header_hidden` | BOOL | Hide the header band |
| `footer_text` | TEXT | Footer content (attribution, credits) |
| `footer_hidden` | BOOL | Hide the footer band |
| `custom_css` | TEXT | Injected `<style>` block |
| `custom_js` | TEXT | Injected `<script>` before `</body>` |
| `include_jquery` | BOOL | Load jQuery 3.7 from CDN before `custom_js` |
| `advanced_search_enabled` | BOOL | Enable the `/advanced/` page and form |
| `advanced_search_config` | JSONB | `{named_tags, attribute_filters}` — see below |
| `embed_enabled` | BOOL | Enable the embed widget endpoints |
| `embed_config` | JSONB | `{mode, allowed_origins}` — see EMBED_WIDGET.md |
| `xslt_template_id` | UUID FK | Reserved for XSLT result transformation (future) |
| `created_by` | UUID FK | User who created the engine |
| `created_at` | TIMESTAMPTZ | |
| `updated_at` | TIMESTAMPTZ | |

### `search_engine_collections` (junction)

| Column | Type |
|---|---|
| `search_engine_id` | UUID FK → `search_engines.id` CASCADE |
| `collection_id` | UUID FK → `collections.id` CASCADE |

Composite primary key. Only published + public collections appear in the
picker; the constraint is enforced in the service layer.

### `search_engine_query_cache`

| Column | Type | Description |
|---|---|---|
| `id` | UUID | Primary key |
| `search_engine_id` | UUID FK | |
| `query_hash` | VARCHAR(64) | SHA-256 of normalised query + collection slugs |
| `query_text` | TEXT | Original query string |
| `collections_key` | TEXT | Sorted comma-separated slugs used in the hash |
| `hits` | JSONB | Serialised array of `SearchHit` objects |
| `total` | INT | Total hit count |
| `created_at` | TIMESTAMPTZ | |
| `expires_at` | TIMESTAMPTZ | Computed from `created_at + cache_ttl_minutes` |

The cache is keyed on `SHA-256(normalised_query + '\0' + sorted_slugs)`.
Expired entries are purged by the hourly APScheduler job `purge_search_engine_cache`.

---

## Search behaviour

### Full-text search

1. Client sends `GET /api/v1/search-engines/{slug}/search?q=...`
2. Service normalises the query and builds the cache key
3. **Cache hit**: return stored results immediately; set
   `Cache-Control: public, max-age={ttl_seconds}`
4. **Cache miss**: execute `search/search_engine_search.xq` against the target
   eXist-db collections
5. Parse XML response; build `SearchHit` objects:
   - `doc_url`: `/browse/{slug}/{filename}?highlight={query}`
   - `collection_slug`, `filename`, `title`
   - `kwic`: keyword-in-context snippet with `<em>` highlights
   - `score`, `mode` (fulltext vs structural)
6. Write results to cache (if TTL > 0)
7. Return `{query, total, hits[], cached}` with `Cache-Control` header

### Advanced search

Endpoint: `GET /api/v1/search-engines/{slug}/advanced-search`

Optional parameters: `q` (text), `element` (TEI element name), `attr_name`,
`attr_value`, `collections`.

Advanced queries are **not cached** — they are assumed to be infrequent and
highly parameterised. The XQuery `search/search_engine_advanced.xq` is
executed on every request.

### Query parameters (both endpoints)

| Parameter | Type | Constraint | Description |
|---|---|---|---|
| `q` | string | max 512 chars | Full-text query |
| `collections` | string | optional | Comma-separated slugs to restrict search |
| `max_results` | int | 1–200, default 50 | Result cap |
| `element` | string | max 64, NCName | Advanced only — TEI element to search |
| `attr_name` | string | max 64, NCName | Advanced only — attribute name filter |
| `attr_value` | string | max 256 | Advanced only — attribute value filter |

---

## Advanced search configuration

The `advanced_search_config` JSONB column stores two arrays:

```jsonc
{
  "named_tags": [
    { "label": "Person",       "element": "persName" },
    { "label": "Place",        "element": "placeName" },
    { "label": "Organisation", "element": "orgName" }
  ],
  "attribute_filters": [
    { "label": "Role",    "attribute": "role" },
    { "label": "Subtype", "attribute": "subtype" }
  ]
}
```

The Admin UI auto-populates available `element` / `attribute` names by
querying `GET /search-engines/{slug}/available-tags` (XQuery scan over the
linked collections).

---

## Build process

Triggering a build (`POST /search-engines/{slug}/build`) starts an async
background task that:

1. Sets `build_status = pending → building`
2. Generates `index.html` (simple search page) and, if
   `advanced_search_enabled`, `advanced/index.html`
3. Writes files to `{settings.search_engines_root}/{slug}/`
4. Sets `build_status = done` + `last_build_at = now`

On failure, sets `build_status = failed` + records the error message.

### Built page structure

Each generated HTML page is **self-contained**:
- All CSS inline (colour variables resolved from engine config)
- Search JS inline (no framework dependencies, unless `include_jquery = true`)
- JS fetches results from `GET /api/v1/search-engines/{slug}/search` at runtime
- Includes a session-level in-page cache (JavaScript `Map`) to avoid re-querying
  the same term within a single page load

Built pages are served via nginx:
```
location /search-pages/ { alias /app/search-pages/; }
```
Public URL: `https://example.org/search-pages/{slug}/`

---

## API endpoints

All management endpoints require **Designer+ role**.

### Management

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/v1/search-engines` | List all search engines |
| `POST` | `/api/v1/search-engines` | Create a new search engine |
| `GET` | `/api/v1/search-engines/{slug}` | Get a single search engine |
| `PUT` | `/api/v1/search-engines/{slug}` | Update configuration |
| `DELETE` | `/api/v1/search-engines/{slug}` | Delete engine + built pages + cache |
| `GET` | `/api/v1/search-engines/public-collections` | List assignable (published+public) collections |
| `POST` | `/api/v1/search-engines/{slug}/build` | Trigger async HTML build |
| `POST` | `/api/v1/search-engines/{slug}/cache/clear` | Flush all cached query results |
| `GET` | `/api/v1/search-engines/{slug}/available-tags` | Get element → attributes map from linked collections |
| `GET` | `/api/v1/search-engines/{slug}/embed-logs` | Paginated embed request log |

### Public search `[pub]`

Rate-limited to **60 requests / minute** per IP.

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/v1/search-engines/{slug}/search` | Full-text search |
| `GET` | `/api/v1/search-engines/{slug}/advanced-search` | Structural / attribute search |

### Embed widget `[pub]` — separate CORS sub-app

See [EMBED_WIDGET.md](./EMBED_WIDGET.md) for full documentation.

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/v1/embed/{slug}/widget.js` | Self-contained JS widget (5-min cache) |
| `GET` | `/api/v1/embed/{slug}/search` | Full-text search (origin-checked) |
| `GET` | `/api/v1/embed/{slug}/advanced-search` | Structural search (origin-checked) |

---

## Response format

`GET /api/v1/search-engines/{slug}/search` — success:

```jsonc
{
  "data": {
    "query": "Alessandro Manzoni",
    "total": 14,
    "cached": false,
    "hits": [
      {
        "doc_url": "/browse/epistolario/lettera-001.xml?highlight=Alessandro+Manzoni",
        "collection_slug": "epistolario",
        "filename": "lettera-001.xml",
        "title": "Lettera a Fauriel, 3 maggio 1821",
        "kwic": "…citando il grande <em>Alessandro Manzoni</em>…",
        "score": 0.92,
        "mode": "fulltext"
      }
    ]
  }
}
```

Cache hit: same structure with `"cached": true` and `Cache-Control: public, max-age=3600`.

---

## Backend files

| Path | Role |
|---|---|
| `backend/app/routers/search_engines.py` | Management + public search endpoints |
| `backend/app/routers/embed.py` | Embed widget endpoints (sub-app) |
| `backend/app/services/search_engines.py` | Build, search, cache, available-tags logic |
| `backend/app/services/embed.py` | Widget JS generation, origin check, log |
| `backend/app/models/search_engine.py` | ORM models (SearchEngine, SearchEngineCollection, SearchEngineQueryCache) |
| `backend/app/models/search_engine_embed_log.py` | ORM model for embed request logs |
| `backend/app/schemas/search_engines.py` | Pydantic schemas |
| `backend/app/xqueries/search/` | XQuery files for full-text and advanced search |
| `backend/app/core/scheduler.py` | `purge_search_engine_cache` hourly job |

---

## Frontend files

| Path | Role |
|---|---|
| `frontend/src/stores/search_engines.ts` | Pinia store — state, fetch, build, cache, embed |
| `frontend/src/views/admin/SearchEnginesView.vue` | Admin management UI (list + forms + embed modal) |

---

## Security

| Concern | Mitigation |
|---|---|
| XSS via custom CSS/JS | Injected content is controlled by Designer+ users only; not exposed to unauthenticated requests |
| Query injection in XQuery | `q` max 512 chars; `element` / `attr_name` validated against NCName pattern; values inlined via `_inline_prolog_variables` (single-quote doubling) |
| Open embed | Opt-in per engine; new engines default to `embed_enabled = false` |
| CORS bypass | Preflight allowed by sub-app middleware; per-engine origin whitelist enforced in handler |
| Rate limiting | Public search: 60 req/min per IP |
| IP logging in embed | Stored from `X-Forwarded-For`; covered by GDPR retention policy |
