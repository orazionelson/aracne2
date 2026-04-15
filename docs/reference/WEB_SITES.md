# Websites — Technical Reference

Design decisions, implementation details and architectural notes for the
Websites module.  Read `BIBLIOGRAPHY.md` for the bibliography system page
specifically.

---

## Rendering modes

The `Website` model has a `rendering_mode` field (`RenderingMode` enum):

| Mode | Description |
|---|---|
| `STATIC` | Full build generates HTML files on disk; served via `FileResponse`. Build is triggered explicitly by the Designer. |
| `DYNAMIC` | No files on disk. Every request fetches data live from eXist-db, applies XSLT in real-time and returns HTML. |
| `HYBRID` | `index.html`, `browse.html`, `bibliography.html` and `pages/*.html` are written to disk. Document pages (`/docs/{filename}`) and search are rendered dynamically on every request. Best for collections that change frequently without a full rebuild. |

---

## URL structure

All three modes share the same routes.  The router detects `rendering_mode` at
request time and branches accordingly.

```
GET /api/v1/sites/{slug}/                    → cover / index page
GET /api/v1/sites/{slug}/browse              → document list
GET /api/v1/sites/{slug}/browse.html         → 301 redirect → /browse
GET /api/v1/sites/{slug}/search?q=term       → search page / results
GET /api/v1/sites/{slug}/bibliography        → bibliography page
GET /api/v1/sites/{slug}/bibliography.html   → same (static-link compat)
GET /api/v1/sites/{slug}/docs/{filename}     → single document (XSLT applied)
GET /api/v1/sites/{slug}/pages/{page_slug}   → free Markdown / WYSIWYG page
GET /api/v1/sites/{slug}/indices/            → all indices aggregated page
GET /api/v1/sites/{slug}/index/{label}/      → single index page
GET /api/v1/sites/{slug}/{path:path}         → catch-all for static assets
                                               (CSS, images, media, etc.)
```

Dynamic/Hybrid handlers intercept the semantic paths above.  The catch-all
falls through to `FileResponse` for everything else (static mode).

---

## Admin endpoints

```
GET    /api/v1/websites                                → list all websites [D+]
POST   /api/v1/websites                                → create [D+]
GET    /api/v1/websites/{slug}                         → get [D+]
GET    /api/v1/websites/{slug}/meta-suggestions        → Dublin Core suggestions [D+]
PUT    /api/v1/websites/{slug}                         → update (invalidates cache) [D+]
DELETE /api/v1/websites/{slug}                         → delete [D+]
POST   /api/v1/websites/{slug}/build                   → trigger async build [D+]
GET    /api/v1/websites/{slug}/download                → zip download of built site [D+]
POST   /api/v1/websites/{slug}/clear-cache             → invalidate page+XSLT cache [D+]
POST   /api/v1/websites/{slug}/preview-doc/{filename}  → render one doc live [D+]
POST   /api/v1/websites/{slug}/pages                   → create free page [D+]
PUT    /api/v1/websites/{slug}/pages/{page_slug}       → update free page [D+]
DELETE /api/v1/websites/{slug}/pages/{page_slug}       → delete free page [D+]
GET    /api/v1/websites/{slug}/tags                    → list extracted index tags [D+]
POST   /api/v1/websites/{slug}/tags/refresh            → re-extract tags from eXist-db [D+]
GET    /api/v1/websites/{slug}/indices                 → list indices [D+]
POST   /api/v1/websites/{slug}/indices                 → create index [D+]
PUT    /api/v1/websites/{slug}/indices/{index_id}      → update index [D+]
DELETE /api/v1/websites/{slug}/indices/{index_id}      → delete index [D+]
POST   /api/v1/websites/{slug}/indices/rebuild-all     → rebuild all indices [D+]
POST   /api/v1/websites/{slug}/indices/{index_id}/rebuild → rebuild one index [D+]
```

`[D+]` = Designer or EditorInChief or Admin.

---

## Service layer — render functions

**File**: `backend/app/services/websites.py`

### Dynamic / Hybrid render functions

All render functions follow the same pattern:
1. Check `_page_cache` — return cached HTML if valid.
2. Fetch data from PostgreSQL and/or eXist-db.
3. Build content via a pure `_build_*` helper.
4. Call `_render_page()` and store in cache.

| Function | Path key | Notes |
|---|---|---|
| `render_dynamic_index(db, website)` | `"index"` | Loads collection + doc list |
| `render_dynamic_browse(db, website)` | `"browse"` | Same doc list |
| `render_dynamic_search(db, website, q)` | `"search:{q}"` | Runs XQuery; empty `q` returns search form uncached |
| `render_dynamic_bibliography(db, website)` | `"bibliography"` | Fetches `is_public=True` row from `collection_bibliographies` |
| `render_dynamic_doc(db, website, filename)` | `"doc:{filename}"` | Applies XSLT (transform cached separately) |
| `render_dynamic_page(db, website, page_slug)` | `"page:{page_slug}"` | 404 if page is hidden |

### Build functions

| Function | Called when |
|---|---|
| `_build_static_site(db, website)` | `rendering_mode == STATIC` |
| `_build_hybrid_site(db, website)` | `rendering_mode == HYBRID` |

`run_build(slug)` is a background task (owns its own `AsyncSession`) called
after `trigger_build()` marks the site `BuildStatus.pending`.  DYNAMIC mode
resolves immediately to `BuildStatus.done` without writing any files.

---

## Pages and system navigation

### Aracne system pages

Five fixed system pages are managed via `_parse_aracne_nav(nav_config)`.
The function merges stored `nav_config` entries with defaults, always
returning all five:

| id | Default sort_order | Default is_hidden |
|---|---|---|
| `home` | 0 | False |
| `browse` | 1 | False |
| `search` | 2 | False |
| `indices` | 3 | False |
| `bibliography` | 4 | False |

`nav_config` is stored as a JSONB list on the `Website` model.  Each entry
is `{ "id": "<id>", "sort_order": <int>, "is_hidden": <bool> }`.  Missing
entries fall back to defaults.

Hidden system pages are excluded from the navbar and (for STATIC/HYBRID)
their corresponding HTML file is not generated.

The `indices` link is additionally suppressed when no index has a
`last_built_at` value — i.e. the navbar only shows Indices after at least
one index has been built.

### Free pages

Created via `POST /websites/{slug}/pages`.  Each `WebsitePage` has:
- `slug` — URL segment (`/pages/{slug}`)
- `title` — shown in navbar and as `<h1>`
- `content_md` — body (Tiptap WYSIWYG HTML output, or legacy Markdown)
- `sort_order` — controls position in navbar relative to system pages
- `is_hidden` — excluded from navbar and build when true

`_md_to_html()` detects Tiptap output (starts with `<`) and returns it
as-is; otherwise applies a minimal Markdown → HTML converter.

---

## XSLT pipeline

### XSLT sources

`website.xslt_config` is a JSONB object.  The `source` key selects the
stylesheet:

| `source` | Description |
|---|---|
| `"default"` | Built-in `backend/app/xslt/tei_generic.xsl` (fallback) |
| `"custom"` | Inline XSLT text stored in `xslt_config["content"]` |
| `"url"` | XSLT fetched at build time from `xslt_config["url"]` (SSRF-checked) |
| `"catalog"` | XSLT loaded from the `xslt_templates` table by `xslt_config["catalog_id"]` (UUID) |

Resolution is handled by `_resolve_transform(xslt_config)`.  Any source that
fails to load (empty content, unreachable URL, unknown catalog_id) falls back
silently to the default transform.

`xslt_config["processor"]` selects the engine: `"lxml"` (default) or `"saxon"`
(not yet active).

### XSLT transform cache

`_site_xslt_cache: dict[str, tuple[Callable, datetime]]` — keyed by slug.

Populated lazily on first dynamic request via `_resolve_transform_cached()`.
Invalidated by `invalidate_cache(slug)` (called on `PUT /websites/{slug}` and
`POST /websites/{slug}/clear-cache`).

The cached value is a synchronous callable; it is invoked via
`asyncio.to_thread()` so it never blocks the event loop.

---

## Image rendering

Configured in `xslt_config["image_rendering"]` (JSONB sub-object).

| Key | Values | Effect |
|---|---|---|
| `enabled` | bool | Master switch; all image rendering is off when false |
| `figure.size` | `"small"`, `"medium"`, `"large"` | CSS size class on `<figure>` |
| `figure.layout` | `"inline"`, `"modal"`, `"column-left"`, `"column-right"` | Placement of `<tei:figure>` images |
| `pb.show` | bool | Whether page-break images (`<tei:pb facs="…">`) are rendered |
| `pb.size` | `"small"`, `"medium"`, `"large"` | CSS size class for pb thumbnails |
| `pb.layout` | `"inline"`, `"modal"`, `"column-left"`, `"column-right"`, `"one-to-one"` | Placement of pb images |
| `facsimile_gallery` | bool | Renders a horizontal gallery of all `<tei:graphic>` at the top of the doc |
| `column_connectors` | bool | Draws SVG connecting lines between column images and their text anchors |

CSS and JavaScript helpers generated from this config:

| Helper | When generated | Purpose |
|---|---|---|
| `_build_image_rendering_css(cfg)` | Always | CSS for figure/pb sizes and layouts |
| `_IMAGE_MODAL_JS` | When any layout is `modal`, or gallery/OTO active | Lightbox click-to-expand |
| `_build_image_column_js(cfg)` | When any layout is `column-left` or `column-right` | Positions column images next to their anchors |
| `_build_one_to_one_js(cfg)` | When `pb.layout == "one-to-one"` | Synchronized text/image scroll |
| `_inject_facsimile_gallery(doc_body, xml_bytes)` | When `facsimile_gallery=True` | Prepends gallery HTML to document body |

Image rendering CSS is added to `doc_style` (document pages only) and does
**not** appear on non-document pages (index, browse, bibliography, etc.).

---

## One-to-One viewer

The **One-to-One** (OTO) mode is the most sophisticated document rendering
layout in Aracne2.  It presents a two-column full-viewport page: the
facsimile image is pinned in a sticky dark panel on the left; the transcription
text scrolls on the right.  As the reader scrolls, the panel automatically
advances to the correct facsimile page.  Hovering over a tagged word or line
highlights the corresponding zone rectangle on the image.

### TEI document prerequisites

For OTO to work, the XML document must use standard TEI facsimile linking.

**Minimum requirement** — page-level linking only:

```xml
<TEI>
  <facsimile>
    <surface xml:id="f1">
      <graphic url="/api/v1/collections/{slug}/documents/{file}/media/f1.jpg"/>
    </surface>
    <surface xml:id="f2">
      <graphic url="…/f2.jpg"/>
    </surface>
  </facsimile>

  <text>
    <body>
      <pb facs="#f1" n="1"/>
      <!-- text of page 1 -->
      <pb facs="#f2" n="2"/>
      <!-- text of page 2 -->
    </body>
  </text>
</TEI>
```

Each `<pb facs="#id">` is linked to a `<surface xml:id="id">`.  The XSLT
resolves the reference and emits a `<figure class="tei-pb-facsimile">` with
the image URL from `<surface>/tei:graphic/@url`.

**Full requirement** — word/line zone highlighting (optional):

```xml
<facsimile>
  <surface xml:id="f1">
    <graphic url="…/f1.jpg"/>
    <!-- Zone coordinates are in the image's natural pixel space -->
    <zone xml:id="z1_001" ulx="110" uly="204" lrx="680" lry="248"/>
    <zone xml:id="z1_002" ulx="110" uly="252" lrx="720" lry="296"/>
    <!-- … -->
  </surface>
</facsimile>

<body>
  <pb facs="#f1" n="1"/>
  <p>
    <w facs="#z1_001">Lorem</w>
    <w facs="#z1_002">ipsum</w>
    <!-- or at line level: -->
    <lb facs="#z1_003"/>
  </p>
</body>
```

- `<w facs="#zone_id">` — word-level link (space-granularity alignment)
- `<lb facs="#zone_id">` — line-break anchor (line-level alignment)
- Both require a `#` prefix; plain `facs` values without `#` are ignored

### XSLT output (tei_generic.xsl)

The generic stylesheet handles all OTO-relevant TEI elements:

| TEI element | HTML output | Purpose |
|---|---|---|
| `<pb facs="#id">` | `<figure class="tei-pb-facsimile"><img…></figure>` | Page image placeholder (hidden by CSS, src read by JS) |
| `<pb n="…">` (no facs) | `<span class="tei-pb">[p. N]</span>` | Page marker without image |
| `<w facs="#zone_id">` | `<span class="tei-w" data-facs="zone_id">…</span>` | Hoverable word token |
| `<lb facs="#zone_id">` | `<span class="tei-lb" data-facs="zone_id"></span><br/>` | Hoverable line anchor |
| `<facsimile>` (with zones) | `<script type="application/json" id="tei-facsimile-zones">{…}</script>` | Zone coordinate map |
| `<surface>`, `<zone>` | _(suppressed)_ | Data consumed by XSLT, not rendered directly |

The `tei-facsimile-zones` script block is a flat JSON object:
```json
{ "z1_001": {"ulx": 110, "uly": 204, "lrx": 680, "lry": 248}, … }
```

It is only emitted when at least one `<surface>` has `<zone>` children.
In documents without zones the script block is absent and the viewer
operates in page-flip mode only (no zone highlighting).

### Configuration

In `xslt_config["image_rendering"]`:

```json
{
  "enabled": true,
  "figure": {
    "layout": "modal"
  },
  "pb": {
    "show": true,
    "layout": "one-to-one"
  }
}
```

`pb.layout = "one-to-one"` is the only required change from the defaults.
Setting `figure.layout = "modal"` is recommended so inline figures (not
page-break facsimiles) open in the lightbox overlay rather than sitting in
the text flow.

When `pb.layout == "one-to-one"`, the builder automatically sets
`_ir_modal = True` and `_ir_oto = True`, which causes all three JS blocks
to be injected: `_IMAGE_MODAL_JS`, `_build_image_column_js` (skipped —
no column selectors in OTO), and `_build_one_to_one_js`.

### Layout structure (runtime DOM)

After the JS runs, the page DOM becomes:

```
<main>                          ← max-width cleared to 100 %
  <div class="oto-layout">      ← display:grid; 1fr 1fr
    <div class="oto-panel">     ← sticky, top:3.5rem, height:calc(100vh-3.5rem), dark bg
      <div class="oto-img-wrap">
        <img class="oto-img" object-fit:contain />
        <svg class="oto-zone-svg" />   ← zone highlight overlay
      </div>
      <div class="oto-nav">
        <button class="oto-nav-btn">←</button>
        <span class="oto-nav-counter">1 / N</span>
        <button class="oto-nav-btn">→</button>
      </div>
    </div>
    <div class="tei-body">      ← right column, scrollable
      …transcription text…
      <span data-oto-idx="0" />  ← zero-height anchor (inserted by JS)
      <figure class="tei-pb-facsimile" />   ← hidden by CSS
      …
    </div>
  </div>
</main>
```

`figure.tei-pb-facsimile` elements are never shown in the text column
(`display:none !important`).  The JS extracts their `img.src` before they
are moved, builds the `pages[]` array, then leaves them in place (hidden).

### Scroll synchronisation

Zero-height `<span data-oto-idx="N">` anchors are inserted immediately
before each `figure.tei-pb-facsimile` while still in the normal document
flow (before the layout grid is built).  Because `display:none` elements
have no layout box, these anchors are the only elements that report a
valid `getBoundingClientRect()` position — they are the scroll targets for
the prev/next buttons and the observations targets for `IntersectionObserver`.

```
IntersectionObserver({
  rootMargin: '0px 0px -40% 0px',  // anchor counts as visible only above 60 % of viewport
  threshold: 0
})
```

When the earliest (lowest index) visible anchor changes, `goTo(first)`
is called: the panel image switches to the new page and the counter updates.
Manual prev/next buttons call `anchors[i].scrollIntoView({behavior:'smooth'})`.

`IntersectionObserver` is used with a graceful absence check
(`typeof IntersectionObserver !== 'undefined'`); older browsers get manual
navigation only.

### Zone highlighting

On `mouseover` of `.tei-body`, the handler walks up the DOM from
`event.target` looking for the nearest `[data-facs]` ancestor.  When found:

1. `showZone(zoneId)` looks up the coordinates in `zoneMap`.
2. Computes the rendered size of the image accounting for `object-fit:contain`
   letterboxing and CSS padding:
   ```
   scale_x = rendered_width  / naturalWidth
   scale_y = rendered_height / naturalHeight
   offset_x = (container_width  - rendered_width)  / 2  + padding_left
   offset_y = (container_height - rendered_height) / 2  + padding_top
   ```
3. Draws an SVG `<rect>` on `.oto-zone-svg`:
   - fill: `rgba(99,102,241,.20)` (semi-transparent indigo)
   - stroke: `#6366f1`, stroke-width: `2`, rx: `3`

The SVG coordinate system covers the full `oto-img-wrap` area (same size
as the `<img>`), so the letterbox offset calculation is done in the same
space as the image padding.

When the image has not finished loading when the hover fires,
`naturalWidth / naturalHeight` are 0 and `showZone` returns early.
An `imgEl.load` event listener re-draws the active zone once the image loads.

`mouseleave` on `.tei-body` clears the active zone and the SVG rectangle.

### Responsive behaviour

```css
@media (max-width: 720px) {
  .oto-layout { display: block !important; }      /* single column */
  .oto-panel  { position: static; height: 60vw; } /* image above text */
  .oto-layout > .tei-body { padding: 1rem 1.5rem 2rem; }
}
```

On narrow screens the grid collapses to a single column: image panel on top
(fixed 60vw height), transcription below.  The panel is no longer sticky.

### CSS classes reference

| Class | Element | Description |
|---|---|---|
| `.oto-layout` | `<div>` (wrapper) | Two-column grid, `1fr 1fr`, `min-height:100vh` |
| `.oto-panel` | `<div>` (left column) | Sticky facsimile panel, dark background |
| `.oto-img-wrap` | `<div>` | Flex container for img + SVG, fills panel height |
| `.oto-img` | `<img>` | Facsimile image, `object-fit:contain`, padded |
| `.oto-zone-svg` | `<svg>` | Zone highlight overlay, `pointer-events:none` |
| `.oto-nav` | `<div>` | Navigation bar at the bottom of the panel |
| `.oto-nav-btn` | `<button>` | Prev / next arrow buttons |
| `.oto-nav-counter` | `<span>` | "N / total" monospace counter |
| `.tei-pb-facsimile` | `<figure>` | Page-break image (hidden by CSS in OTO mode) |
| `.tei-w[data-facs]` | `<span>` | Hoverable word token, dotted indigo underline |
| `.tei-lb[data-facs]` | `<span>` | Hoverable line anchor, narrow inline block |

### Interaction with other image rendering options

- **`facsimile_gallery`**: compatible with OTO.  The gallery is prepended
  at the top of the text column and all gallery images are modal-clickable
  (the modal JS is always present in OTO mode).
- **`figure.layout = "modal"`**: recommended.  Inline `<figure>` images open
  in the lightbox.  The `cursor:zoom-in` CSS is applied by the OTO CSS block.
- **`figure.layout = "column-left/right"`**: not recommended with OTO; the
  column JS would conflict with the OTO grid layout.
- **`column_connectors`**: not applicable in OTO mode (there is no sidebar).

---

## Note rendering

Configured in `xslt_config["note_rendering"]` (JSONB sub-object).

| Key | Values | Effect |
|---|---|---|
| `enabled` | bool | Master switch |
| `mode` | `"end-of-text"`, `"tooltip"`, `"frame"` | How `<tei:note>` elements are rendered |

Helpers:

| Helper | Purpose |
|---|---|
| `_build_note_rendering_css(cfg)` | CSS for the chosen note mode |
| `_build_note_rendering_js(cfg)` | JS (tooltip show/hide, frame toggling) |

---

## Document-only JS and the `base_custom_js` split

Image and note rendering scripts require TEI document HTML structure.  They
must not appear on non-document pages (index, browse, search, bibliography,
free pages).

The static builder resolves this by splitting the JS before iterating:

```python
base_custom_js = website.custom_js          # un-enhanced designer JS
custom_js = base_custom_js
if _ir_modal:   custom_js += "\n" + _IMAGE_MODAL_JS
if _ir_column:  custom_js += "\n" + _build_image_column_js(_ir_cfg)
if _ir_oto:     custom_js += "\n" + _build_one_to_one_js(_ir_cfg)
if _nr_js:      custom_js += "\n" + _nr_js
```

- `doc_style` / `custom_js` → used for `docs/*.html`
- `style` / `base_custom_js` → used for `index.html`, `browse.html`,
  `bibliography.html`, `search.html`, `pages/*.html`

The hybrid builder uses the same split.  Dynamic render functions always use
`website.custom_js` directly (no document-specific JS is appended, because
each page has its own render function).

---

## `_render_page` — shared HTML assembler

```python
def _render_page(
    *,
    site_title: str,
    page_title: str,
    content: str,
    style: str,
    navbar: str,
    breadcrumb: str = "",
    footer_note: str = "",
    identifier_url: str = "",
    meta_tags: str = "",
    custom_js: str | None = None,
    include_jquery: bool = False,
) -> str:
```

Produces a complete `<!DOCTYPE html>` page.  Notable details:

- `style` — inserted as a `<style>` block in `<head>`.
- `meta_tags` — raw HTML string of `<meta>` tags (from `_build_meta_tags`).
- `footer_note` — publisher + year string from the linked collection.
- `identifier_url` — persistent identifier (DOI/Handle/URN) shown as a
  footer link; the label (DOI / Handle / URN / ID) is derived from the URL
  prefix by `_identifier_label()`.
- `include_jquery` — injects jQuery 3.7.1 from CDN via a `<script>` tag;
  used when note rendering mode requires it.
- `custom_js` — injected as an inline `<script>` tag.  `</script>` is
  stripped from the content to prevent tag breakage (Designer input is
  trusted but sanitized against this one case).
- `_PREVIEW_PROPAGATOR_SCRIPT` and `_HIGHLIGHT_SCRIPT` are always included
  (syntax highlighting for XML code blocks).

---

## Meta config and Dublin Core

`website.meta_config` is a JSONB dict.  `_build_meta_tags(meta, website_url)`
emits HTML `<meta>` tags from it.

Supported fields: `keywords`, `description`, `subject`, `copyright`,
`author`, `designer`, `url`, `dc_title`, `dc_creator`, `dc_subject`,
`dc_description`, `dc_publisher`, `dc_contributor`, `dc_date`, `dc_type`,
`dc_format`, `dc_identifier`.

Repeatable fields (`subject`, `author`, `designer`, `dc_creator`, etc.)
can be stored as a string or a list of strings — one `<meta>` tag per value.

When at least one `dc_*` field has a value, the Dublin Core namespace
`<link>` is prepended automatically.

`GET /websites/{slug}/meta-suggestions` queries eXist-db and the collection
metadata to suggest pre-filled values for the form fields.

---

## Theme config

`website.theme_config` is a JSONB dict.  Keys used by the service layer:

| Key | Type | Effect |
|---|---|---|
| `logo_url` | string | URL of the logo image in the navbar |
| `hide_header` | bool | Omits the entire `<header>/<nav>` block from every page |
| `cache_ttl_seconds` | int | Per-site page cache TTL (overrides default 300 s) |
| `home_layout` | `"single"`, `"two_left"`, `"two_right"`, `"three"` | Cover page column grid |
| `col_left` | string (HTML/Markdown) | Left column body on the cover page |
| `col_right` | string (HTML/Markdown) | Right column body on the cover page |
| `col_center` | string (HTML/Markdown) | Center column body on the cover page |

Additional theme keys (colours, fonts, etc.) are consumed by `_style_block()`
and emitted as CSS custom properties in the `<style>` block.

---

## Caching strategy

### Page cache

```python
_page_cache: dict[tuple[str, str], tuple[str, datetime]] = {}
# Key: (slug, path_key)
# Value: (html, computed_at)
```

`path_key` examples: `"index"`, `"browse"`, `"doc:file.xml"`,
`"page:about"`, `"search:query_string"`, `"bibliography"`.

TTL precedence (highest first):
1. `website.theme_config["cache_ttl_seconds"]` (per-site override)
2. Hard-coded default: **300 seconds**

`_get_cached_page(slug, path_key, ttl)` returns `None` when the entry is
absent or expired (deletes the stale entry in-place).

Search results (`search:{q}`) are cached.  An empty `q` is never cached
(the search form is rendered fresh every time).

### XSLT transform cache

```python
_site_xslt_cache: dict[str, tuple[Callable, datetime]] = {}
# Key: slug
# Value: (transform_callable, cached_at)
```

Populated lazily by `_resolve_transform_cached()`.  The callable is a closure
over the compiled XSLT text; it takes `xml_bytes: bytes` and returns `str`.

### Cache invalidation

`invalidate_cache(slug)` drops all `_page_cache` entries for the slug and
removes the XSLT transform entry.  Called automatically by:
- `update_website()` — any `PUT /websites/{slug}`
- `POST /websites/{slug}/clear-cache` (explicit Designer action)

### HTTP caching — ETag

`compute_etag(website)` returns `sha256("{slug}|{updated_at.isoformat()}")[:16]`.
Returned as an `ETag` response header on every dynamic page.
If the request carries a matching `If-None-Match`, the handler returns
`304 Not Modified`.

---

## Search

### STATIC — client-side search

The build step produces `search.json.gz` (gzip-compressed JSON, typically
70–80 % smaller than plain JSON, decompressed natively by the browser via
`DecompressionStream`).

Each entry:
```json
{ "filename": "doc001.xml", "title": "…", "author": "…", "url": "docs/doc001.xml.html", "body": "…" }
```

`body` contains the full plain-text of the document (extracted by
`_extract_plain_text(xml_bytes)` via `lxml`), enabling full-text matching
in the browser.

`search.html` delivers the JavaScript search client that fetches
`search.json.gz` and filters locally (AND matching across title, author,
body).  No server component at query time.

### DYNAMIC / HYBRID — eXist-db full-text search

`render_dynamic_search(db, website, q)` runs
`xqueries/search/fulltext_search.xq` via eXist-db.

The XQuery uses `ft:query()` (eXist-db Lucene full-text index) with a
`contains()` fallback for collections without a Lucene index.

External variables: `$collection_path`, `$query`, `$max_results` (default 50).

XQuery result format:
```xml
<results>
  <hit filename="doc001.xml" score="1.0">
    <kwic>…matching passage with context…</kwic>
  </hit>
</results>
```

KWIC highlighting in `_build_dynamic_search_content(hits, q, base)` wraps
matched terms in `<mark>` tags via `_kwic_highlight(text, q)`.

---

## Static build — output structure

Generated by `_build_static_site`:

```
{websites_root}/{slug}/
├── index.html
├── browse.html           (skipped when browse is hidden)
├── bibliography.html     (skipped when bibliography is hidden)
├── search.html           (skipped when search is hidden)
├── search.json.gz        (full-text index)
├── indices.html          (skipped when indices hidden or none built)
├── media/                (copy of documents_media_root/{col_slug}/)
│   └── {doc_filename}/
│       └── {image_file}
├── docs/
│   └── {filename}.html   (one per document, XSLT applied)
└── pages/
    └── {page_slug}.html  (one per visible free page)
```

Media files are copied from `settings.documents_media_root / col.slug` to
`site_dir / "media"` at build time (the destination is wiped before copy).
API URLs in document HTML (`/api/v1/collections/{slug}/documents/{doc}/media/{file}`)
are rewritten to relative paths (`../media/{doc}/{file}`) via a `re.sub`.

---

## Hybrid build — output structure

Generated by `_build_hybrid_site`:

```
{websites_root}/{slug}/
├── index.html
├── browse.html           (skipped when browse is hidden)
├── bibliography.html     (skipped when bibliography is hidden)
└── pages/
    └── {page_slug}.html
```

Not built — always served dynamically:
- `docs/{filename}` (via `render_dynamic_doc`)
- `search` (via `render_dynamic_search`)
- `indices/` and `index/{label}/` (via `render_website_index_html` / `render_all_indices_html`)

All hrefs inside the built pages use absolute paths rooted at
`/api/v1/sites/{slug}/` so that navbar and content links resolve correctly.

---

## Indices

Defined on the `WebsiteIndex` model.  Each index:
- Has a `label` (free text, used as nav slug)
- Contains a `cached_data` JSONB blob populated by `rebuild_website_index()`
- Tracks `last_built_at` and `last_error`

`rebuild_website_index(db, slug, index_id)` runs an XQuery against eXist-db
to collect index occurrences, parses the XML result and stores it in
`cached_data`.

`render_website_index_html(website, index)` and
`render_all_indices_html(website)` generate HTML from `cached_data` — no
live eXist-db call at render time.

For DYNAMIC mode the same `render_*_html` functions are called at request
time (no on-disk copy).  The navbar shows the Indices link only when at
least one index has `last_built_at` set.

Tags (`POST /websites/{slug}/tags/refresh`) extract unique attribute values
from the collection XML and store them in `website.tags` (JSONB array) for
use as index-building aids.

---

## Bibliography system page

See `BIBLIOGRAPHY.md` for the full specification.

Summary of website-side behaviour:
- System page id: `"bibliography"`, default `sort_order: 4`.
- Content: fetched from `collection_bibliographies` where `is_public=True`.
- Rendered by `_build_bibliography_content(content_xml)` → `<ul class="bibl-list">`.
- Dynamic/Hybrid: `render_dynamic_bibliography(db, website)`, cached.
- Static/Hybrid build: `bibliography.html` written to disk using `base_custom_js`
  (not the document-enhanced `custom_js`).

---

## Footer

Every page footer includes:
- **Publisher note**: `{col.publisher}, {col.pub_year}` (both optional).
- **Identifier link**: `col.identifier_url` (DOI, Handle, URN, or any URL).
  `_identifier_label(url)` derives the display label from the URL prefix:
  `doi.org` → "DOI", `hdl.handle.net` → "Handle", `urn:` → "URN",
  otherwise "ID".
- **"Built with Aracne2"** link (always present).

Footer data is computed once per build/render by `_footer_parts(col)`.

---

## `include_jquery` / `custom_js`

`website.include_jquery: bool` injects jQuery 3.7.1 (CDN) into every page.
Required by note rendering modes that use jQuery selectors.

`website.custom_js: str | None` is a Designer-provided JavaScript block
injected inline.  The only sanitization applied is stripping `</script>`
occurrences (to prevent breaking the surrounding tag).  All other content
is trusted Designer input.

---

## Preview endpoint

```
POST /api/v1/websites/{slug}/preview-doc/{filename}
Body: { "xml_content": "<xml>…</xml>" }   (optional)
```

Calls `preview_document(db, website, filename, xml_content)`.
When `xml_content` is provided, it is used directly (live editor buffer).
Otherwise the document is fetched from eXist-db.

Returns rendered HTML as `text/html`.  Never cached.  Used by the
document editor to preview XSLT output without triggering a full build.

---

## Design decisions (recorded)

| # | Decision | Resolution |
|---|---|---|
| 1 | **Cache TTL storage** | Per-site `theme_config["cache_ttl_seconds"]`, default 300 s |
| 2 | **HYBRID doc boundary** | Always dynamic — HYBRID never writes `docs/` to disk |
| 3 | **Search in DYNAMIC** | eXist-db Lucene `ft:query()` with `contains()` fallback; STATIC retains portable `search.json.gz` |
| 4 | **Cache invalidation on PUT** | Auto-invalidate on every `PUT /websites/{slug}` + manual `clear-cache` endpoint |
| 5 | **ETag** | Implemented: `sha256(slug + updated_at)[:16]` |
| 6 | **JS split for non-doc pages** | `base_custom_js` saved before document rendering scripts are appended; non-doc pages (index, browse, bibliography…) receive only `base_custom_js` |
| 7 | **HYBRID bibliography** | `bibliography.html` is built statically (like index/browse) because its content comes from PostgreSQL, not from eXist-db live rendering |
