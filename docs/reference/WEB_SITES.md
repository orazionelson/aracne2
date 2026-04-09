# Websites — Reference Architecture

Design notes, open questions and implementation decisions for the Websites module.
Updated as decisions are taken. For deferred items see `docs/DEFERRED.md`.

---

## Rendering modes

The `Website` model supports three rendering modes (`rendering_mode` field):

| Mode | Description |
|---|---|
| `STATIC` | Full build generates HTML files on disk; served via `FileResponse`. Build is triggered explicitly by the designer. |
| `DYNAMIC` | No files on disk. Every request fetches data live from eXist-db, applies XSLT in real-time and returns HTML. |
| `HYBRID` | `index.html`, `browse.html`, `search.html` and `pages/*.html` are built statically. Individual document pages (`/docs/{filename}`) are rendered dynamically on every request. Best for collections that change frequently without a full rebuild. |

---

## URL structure (all modes share the same routes)

The router detects `website.rendering_mode` at request time and routes accordingly.
No separate URL namespace per mode.

```
GET /api/v1/sites/{slug}/                  → cover / index page
GET /api/v1/sites/{slug}/browse            → document list
GET /api/v1/sites/{slug}/browse.html       → alias (backward-compat with static links)
GET /api/v1/sites/{slug}/search            → search page (or search results)
GET /api/v1/sites/{slug}/docs/{filename}   → single document (XSLT applied)
GET /api/v1/sites/{slug}/pages/{page_slug} → free Markdown pages
```

Static mode also serves arbitrary files (`CSS`, `JS`, `images`) via the existing
catch-all `/{path:path}` handler, which falls through to `FileResponse`.
Dynamic/Hybrid handlers intercept the semantic paths above before the catch-all.

---

## Service layer — render functions (DYNAMIC / HYBRID)

All existing HTML helper functions (`_render_page`, `_style_block`,
`_build_cover_content`, `_build_browse_content`, `_build_search_content`, etc.)
are **pure functions** that do not touch the filesystem. They are reused unchanged
by the dynamic path.

New async wrappers to add in `app/services/websites.py`:

```python
async def render_dynamic_index(db, website)              -> str  # full HTML
async def render_dynamic_browse(db, website)             -> str
async def render_dynamic_search(db, website, q: str)     -> str
async def render_dynamic_doc(db, website, filename: str) -> str
async def render_dynamic_page(db, website, page_slug)    -> str
```

Each wrapper:
1. Loads the linked `Collection` from PostgreSQL (single `db.get()`).
2. Calls eXist-db (XQuery or REST) for the required data.
3. Applies XSLT via `_resolve_transform()` (cached — see below).
4. Calls `_render_page()` and returns the HTML string.

---

## Caching strategy

### a) XSLT transform cache

`_xslt_cache: dict[str, Callable[[bytes], str]]` keyed by `website.slug`.

- Populated on first request (or on build trigger for STATIC/HYBRID).
- Invalidated when `PUT /websites/{slug}` updates `xslt_config`.
- Thread-safe: the dict stores immutable callables compiled once by lxml.

### b) Rendered-page cache (HTML)

`_page_cache: dict[tuple[str, str], tuple[str, datetime]]`
Key: `(slug, path_key)` where `path_key` is e.g. `"index"`, `"browse"`,
`"doc:filename.xml"`, `"page:about"`, `"search:query_string"`.
Value: `(html, computed_at)`.

- TTL: configurable, default **5 minutes**.
  Stored in `website.theme_config["cache_ttl_seconds"]` or globally in
  `system_settings["dynamic_cache_ttl"]`. **Decision pending** (see §Open questions).
- Invalidated explicitly by `POST /websites/{slug}/clear-cache` [D+].
- Also invalidated automatically when `PUT /websites/{slug}` is called
  (any metadata or XSLT change).

### c) HTTP caching — ETag / Last-Modified

ETag computed as `sha256(slug + website.updated_at.isoformat())[:16]`.
Returned as `ETag` response header. If the request carries `If-None-Match`
matching the current ETag, return `304 Not Modified` with empty body.
**Decision: implement from day one** — low effort, significant CDN benefit.

---

## Search — by rendering mode

The search strategy differs fundamentally between STATIC and DYNAMIC/HYBRID,
because the data residency differs.

### STATIC — client-side search on a metadata snapshot

The build step produces `search.json` (title + author of every document) and
`search.html` (JavaScript that downloads the JSON and filters locally in the browser).
The collection data is **copied** into the snapshot for portability: the static site
works without eXist-db at runtime.

### DYNAMIC / HYBRID — eXist-db native full-text search

The collection stays in eXist-db. There is no `search.json` and no client-side JS.

`GET /sites/{slug}/search?q=term` is handled server-side:

1. The backend runs an XQuery using eXist-db's **Lucene full-text index**
   (`ft:query()`) against the entire XML content of every document in the collection
   — not just title and author.
2. The XQuery returns hits with **KWIC snippets** (Key Word In Context) so the
   user sees the matching passage highlighted in context.
3. The backend renders the results as an HTML page via `_render_page()` and returns
   it directly — no client JavaScript needed.

This delivers true full-text search from the first release of DYNAMIC mode, leveraging
the index that eXist-db already maintains for the collection.

**XQuery file**: `app/xqueries/search/fulltext_search.xq` (new — to be written).
The query receives `$collection_path` and `$q` as external variables and returns
an XML result set with `<hit filename="" score="">...<kwic>...</kwic></hit>` elements.

**Prerequisite**: the eXist-db collection must have a Lucene index configured.
For collections without a Lucene index, the query falls back to a `contains()`
scan (slower but always works). The fallback is transparent to the user.

**Empty query (`q` absent or blank)**: render the same document-list page as
`/browse` (no search box with empty results — redirect or render browse instead).

---

## HYBRID mode — precise boundary

- **Built statically** (require explicit build trigger): `index.html`, `browse.html`,
  `search.html`, `pages/*.html`.
- **Always dynamic** (no file on disk, rendered on every request):
  `/docs/{filename}` — regardless of whether a static file exists at that path.

The document handler checks `rendering_mode` first; if `HYBRID` or `DYNAMIC` it
goes to the live render path without looking at the filesystem.

---

## Admin UI changes by mode

| UI element | STATIC | DYNAMIC | HYBRID |
|---|---|---|---|
| "Build" button | ✅ | ❌ hidden | ✅ (builds pages, not docs) |
| Build status badge | ✅ | ❌ | ✅ partial (`pages built`) |
| "Clear cache" button | ❌ | ✅ | ✅ |
| Preview in Document tab | ✅ via endpoint | ✅ via endpoint | ✅ via endpoint |
| Last-build timestamp | ✅ | ❌ | ✅ |

"Clear cache" triggers `POST /api/v1/websites/{slug}/clear-cache` [D+].

---

## New endpoint: `POST /websites/{slug}/clear-cache`

```
POST /api/v1/websites/{slug}/clear-cache   [D+]
→ 200 { "data": { "cleared": true } }
```

Drops all entries from `_page_cache` and `_xslt_cache` for the given slug.
Does **not** trigger a build. Safe to call at any time.

Whether `PUT /websites/{slug}` should also call this automatically:
**yes** — any metadata or XSLT change must invalidate the rendered-page cache
immediately, otherwise stale HTML is served.

---

## Open questions (decisions pending before implementation)

| # | Question | Options | Status |
|---|---|---|---|
| 1 | **Cache TTL storage** | Per-site in `theme_config["cache_ttl_seconds"]` vs. global `system_settings["dynamic_cache_ttl"]` | ❓ Pending |
| 2 | **HYBRID doc boundary** | Always dynamic vs. dynamic only if no static file on disk | ✅ Decided: always dynamic |
| 3 | **Search in DYNAMIC** | Option A (on-demand JSON, metadata only) vs. Option B (eXist-db Lucene FT, full document) | ✅ Decided: Option B — full-text on eXist-db from day one. STATIC retains portable JSON snapshot. |
| 4 | **Cache invalidation on PUT** | Auto-invalidate on every `PUT /websites/{slug}` vs. manual `clear-cache` only | ✅ Decided: auto on PUT + manual endpoint |
| 5 | **ETag** | Implement from day one vs. later optimisation | ✅ Decided: day one |

---

## Implementation order (proposed)

1. `app/xqueries/search/fulltext_search.xq` — XQuery with `ft:query()` + `contains()` fallback.
2. `_page_cache` / `_xslt_cache` data structures + eviction helpers in `app/services/websites.py`.
3. `POST /websites/{slug}/clear-cache` endpoint [D+].
4. `render_dynamic_*` functions in `app/services/websites.py` (index, browse, doc, page, search).
5. Router: update existing `/sites/{slug}/` handlers to branch on `rendering_mode`.
6. HYBRID doc handler (always dynamic regardless of file presence on disk).
7. Admin UI: hide/show Build button, add Clear Cache button, by mode.
8. ETag response headers.

*Created: 2026-04-09 — Search decision revised: full-text eXist-db Lucene for DYNAMIC/HYBRID, portable JSON snapshot for STATIC.*
