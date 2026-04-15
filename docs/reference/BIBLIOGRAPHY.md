# Bibliography — Technical Reference

This document covers the full bibliography subsystem in Aracne2: data model,
backend API, Bibliobuilder editorial tool, public exposure on the platform home
page, and integration with the Website system pages.

Read `AI_INTEGRATION.md` for the AI layer (Bibliobuilder prompts, `aiStore`
wiring, streaming).  Read `WEB_SITES.md` for the broader website rendering
pipeline.

---

## Overview

A **bibliography** in Aracne2 is a normalized TEI `<listBibl>` XML document
associated with a collection.  The system supports an arbitrary number of
**versioned snapshots** per collection; at most one version per collection can
be marked **public**.

```
Collection (1) ──── (N) CollectionBibliography (versioned)
                              │
                         is_public = true  ──→  exposed on public pages
```

The standard editorial workflow is:

1. **Bibliobuilder** extracts all raw `<bibl>`/`<biblStruct>` elements scattered
   across the collection's XML documents.
2. The result is fed to the `bibliobuilder` AI prompt, which normalizes and
   deduplicates the entries into a `<listBibl>`.
3. The Editor in Chief reviews and optionally edits the AI output, then saves it
   as a new version.
4. One version is flagged as `is_public`; this version is rendered on the public
   home page and on the Website bibliography page.

---

## File map

```
backend/app/
├── models/collection_bibliography.py     # ORM model
├── schemas/collection_bibliography.py    # Pydantic schemas
├── plugins/_native/collections/router.py # Bibliography endpoints (§ below)
├── services/websites.py                  # _build_bibliography_content,
│                                         # render_dynamic_bibliography
└── xqueries/collections/extract_bibl.xq # XQuery: collect bibl entries

frontend/src/
├── stores/collections.ts                 # CollectionBibliography interface +
│                                         # store methods
├── views/CollectionBibliobuilderview.vue # Bibliobuilder editorial page
├── views/CollectionDetailView.vue        # Saved bibliographies panel (EiC+)
├── views/PublicBibliographyView.vue      # Public bibliography page
└── components/PublicHomeSection.vue      # "Bibliography" button on public home

backend/alembic/versions/
├── 0044_collection_bibliographies.py     # Creates table
└── 0045_bibliography_is_public.py        # Adds is_public column + index
```

---

## Database model

### `collection_bibliographies`

```python
# backend/app/models/collection_bibliography.py
class CollectionBibliography(Base):
    __tablename__ = "collection_bibliographies"
    __table_args__ = (UniqueConstraint("collection_id", "version"),)

    id:             UUID (PK)
    collection_id:  UUID (FK → collections.id, ON DELETE CASCADE, indexed)
    version:        int — auto-incremented per collection (1-based)
    content:        Text — full <listBibl> XML string
    created_at:     datetime (tz-aware)
    created_by_id:  UUID | None (FK → users.id, ON DELETE SET NULL)
    is_public:      bool — default False; at most one True per collection
```

**Version numbering**: assigned by the backend as `COALESCE(MAX(version), 0) + 1`
scoped to the collection.  Deleting a version does not shift remaining version
numbers.

**`is_public` constraint**: enforced at the application level, not by a DB
unique partial index.  When a PATCH sets `is_public=True`, the service issues
a bulk `UPDATE … SET is_public=FALSE WHERE collection_id=… AND version!=…`
before setting the target row.

**Migrations**:
- `0044` — creates the table with all columns except `is_public`
- `0045` — adds `is_public BOOLEAN NOT NULL DEFAULT FALSE` and a composite
  index on `(collection_id, is_public)` to speed public-flag lookups

---

## Backend API

All bibliography endpoints are defined in
`backend/app/plugins/_native/collections/router.py`.

| Method | Path | ACL | Description |
|--------|------|-----|-------------|
| GET | `/{collection_id}/extract-bibl` | EiC+ | Run XQuery, return raw `<entries>` XML |
| POST | `/{collection_id}/bibliographies` | EiC+ | Save new versioned snapshot |
| GET | `/{collection_id}/bibliographies` | EiC+ | List all versions, newest first |
| DELETE | `/{collection_id}/bibliographies/{version}` | EiC+ | Delete a version |
| PATCH | `/{collection_id}/bibliographies/{version}` | EiC+ | Set/unset `is_public` |
| GET | `/{collection_id}/public-bibliography` | public | Return the public version |

`{collection_id}` accepts either the collection UUID or the slug in all
endpoints.

### GET `/{collection_id}/extract-bibl`

Runs `xqueries/collections/extract_bibl.xq` via `ExistDBClient.xquery()`,
passing `$collection_path` as an external variable.  Returns the raw XQuery
result as `application/xml` — not the standard JSON envelope — because the
payload is large structured XML, not a resource representation.

**Response format**:
```xml
<entries>
  <bibl source="doc001.xml" n="1">Rossi, Mario. <title>…</title></bibl>
  <biblStruct source="doc001.xml" n="2">
    <monogr>…</monogr>
  </biblStruct>
  <!-- … -->
</entries>
```

Each entry element:
- carries the TEI element's **local name** (namespace stripped)
- `@source` — originating document filename (`util:document-name`)
- `@n` — 1-based sequence number within that document
- child elements are also namespace-stripped (one level deep)

### POST `/{collection_id}/bibliographies`

Request body: `CollectionBibliographySave { content: str }` — the full
`<listBibl>` XML string.

Response: `201 Created`, `DataResponse[CollectionBibliographyResponse]` with
the assigned `version` number.

Version is computed server-side; the client never sends it.

### PATCH `/{collection_id}/bibliographies/{version}`

Request body: `CollectionBibliographySetPublic { is_public: bool }`

When `is_public=True`:
1. Bulk `UPDATE … SET is_public=FALSE` for all other versions of the collection.
2. Set `is_public=TRUE` on the target row.

When `is_public=False`: only clears the target row's flag.

Response: `DataResponse[CollectionBibliographyResponse]` with the updated row.

### GET `/{collection_id}/public-bibliography`

No authentication required.  Accepts UUID or slug.  Returns 404 if:
- the collection does not exist
- `collection.is_public` is False
- `collection.status != "published"`
- no version has `is_public=True`

This endpoint is called by `PublicBibliographyView.vue` and, on the website
side, by `render_dynamic_bibliography()`.

---

## XQuery — `extract_bibl.xq`

**File**: `backend/app/xqueries/collections/extract_bibl.xq`

```xquery
xquery version "3.1";

declare namespace tei = "http://www.tei-c.org/ns/1.0";
declare variable $collection_path external;

let $col := collection($collection_path)
return
<entries>{
  for $doc in $col
  let $id := util:document-name($doc)
  for $entry at $n in ($doc//tei:bibl | $doc//tei:biblStruct)
  return
    element { local-name($entry) } {
      attribute source { $id },
      attribute n { $n },
      $entry/node() ! (
        if (. instance of element()) then
          element { local-name(.) } { ./(@* except @xmlns), ./node() }
        else .
      )
    }
}</entries>
```

The namespace stripping is intentional: the `bibliobuilder` AI prompt receives
clean XML without TEI namespace prefixes, which reduces token count and avoids
namespace-handling confusion in model output.

---

## Pydantic schemas

```python
# backend/app/schemas/collection_bibliography.py

class CollectionBibliographySave(BaseModel):
    content: str

class CollectionBibliographySetPublic(BaseModel):
    is_public: bool

class CollectionBibliographyResponse(BaseModel):
    id:             UUID
    collection_id:  UUID
    version:        int
    content:        str
    created_at:     datetime
    created_by_id:  UUID | None
    is_public:      bool
    model_config = {"from_attributes": True}
```

`CollectionBibliographyResponse.content` contains the full XML; consumers
are responsible for parsing it.  The `has_public_bibliography: bool = False`
field on `CollectionResponse` (in `schemas/collections.py`) is a computed
flag injected at list time and is never persisted.

---

## Frontend store (`frontend/src/stores/collections.ts`)

### TypeScript interface

```typescript
export interface CollectionBibliography {
  id: string;
  collection_id: string;
  version: number;
  content: string;         // full <listBibl> XML
  created_at: string;
  created_by_id: string | null;
  is_public: boolean;
}
```

`has_public_bibliography?: boolean` on the `Collection` interface is populated
by the `collections_public` endpoint on public listings (see below).

### Store state

```typescript
const bibliographies = ref<CollectionBibliography[]>([]);
```

Loaded on demand; scoped to the currently viewed collection.  Not reset
automatically between collection navigations — callers are responsible for
calling `listBibliographies` when needed.

### Store methods

| Method | HTTP | Notes |
|--------|------|-------|
| `extractBibl(collectionId)` | GET `…/extract-bibl` | Returns raw XML string; bypasses JSON envelope via `axios.get({ responseType: "text" })` |
| `saveBibliography(collectionId, content)` | POST `…/bibliographies` | Returns `CollectionBibliography` with server-assigned version |
| `listBibliographies(collectionId)` | GET `…/bibliographies` | Populates `bibliographies` ref |
| `deleteBibliography(collectionId, version)` | DELETE `…/{version}` | Removes row from `bibliographies` optimistically |
| `setBibliographyPublic(collectionId, version, isPublic)` | PATCH `…/{version}` | When `isPublic=true`, sets all other entries to `is_public:false` locally, mirroring the backend bulk update |
| `fetchPublicBibliography(slug)` | GET `…/public-bibliography` | Returns `CollectionBibliography`; used by public views |

`extractBibl` deliberately uses the raw axios instance instead of `apiClient`
because the endpoint returns `application/xml` rather than the standard
`{"data": …}` JSON envelope.

---

## Bibliobuilder page (`CollectionBibliobuilderview.vue`)

**Route**: `/collections/:slug/bibliobuilder`
**ACL**: EiC+ (`requiresMinRole: "EditorInChief"`)
**Entry point**: Bibliobuilder button in `CollectionDetailView` action bar
(visible to EiC+ only).

### Page layout

```
┌─────────────────────────────────────────────────────┐
│ ← Collection title                  Bibliobuilder   │
├─────────────────────────────────────────────────────┤
│ STEP 1 — EXTRACT                                     │
│  [Extract bibliographies]  spinner while running     │
│  "42 entries extracted"  [Show / Hide raw XML]       │
│  <textarea readonly v-show="showRaw">                │
│  Error alert if XQuery fails                         │
├─────────────────────────────────────────────────────┤
│ STEP 2 — AI  (disabled until step 1 done)           │
│  [Run Bibliobuilder]  /  [Stop] when streaming       │
│  ┌────────────────────────────────────────────────┐ │
│  │  thinking… / streaming <listBibl> / error      │ │
│  │  monospace, auto-scroll, overflow-y-auto       │ │
│  └────────────────────────────────────────────────┘ │
│  Action bar: [Edit] [Cancel edit] [Copy] [Save]      │
│  (action bar visible when lastAssistantResponse ≠ "")│
├─────────────────────────────────────────────────────┤
│ FOLLOW-UP  (visible when chatHistory.length >= 2)   │
│  <textarea placeholder="Send next batch or ask …">  │
│  [Send]  hint: ⌘↵                                   │
└─────────────────────────────────────────────────────┘
```

### Step 1 — Extract

```
doExtract()
  → collectionsStore.extractBibl(collection.id)
      → GET /api/v1/collections/{id}/extract-bibl
      → returns raw <entries> XML
  → rawEntries.value = xml
  → entryCount.value = regex count of <bibl|biblStruct[\s>] matches
  → showRaw.value = true   (auto-expands for inspection)
  → aiStore.resetChat()    (clears any previous AI session)
```

### Step 2 — AI

```
runAi()
  → aiStore.continueChat("bibliobuilder", {}, rawEntries.value)
```

Note: `continueChat` (not `startStream`) is used so the extracted XML is sent
as the **first user message**, not as a context variable substitution.  The
`bibliobuilder` prompt has no `{placeholder}` variables, so `context = {}`.

The backend reconstructs the full message list as:
```
[
  { role: "user", content: "<bibliobuilder prompt template>" },
  { role: "user", content: "<entries>…</entries>" }   ← rawEntries
]
```

If the collection contains more than 80 entries the AI returns `NEXT` at the
end of each batch.  The user sends the next batch (or a refined excerpt) via
the follow-up textarea.

### Follow-up turns

```
sendFollowUp()
  → msg = chatInput.value.trim()
  → aiStore.continueChat("bibliobuilder", {}, msg)
```

`Ctrl+Enter` / `Cmd+Enter` triggers send from the textarea.
Follow-up panel is hidden until `chatHistory.length >= 2`.

### Result — edit and save

After the first AI response, the action bar appears.

**Edit mode** (`isEditing = editableContent !== null`):
- Clicking **Edit** copies `lastAssistantResponse` into `editableContent` and
  renders a `<textarea>`.
- While editing, `effectiveContent = editableContent` (takes precedence over
  the AI output).
- Clicking **Cancel edit** or starting a new AI exchange clears `editableContent`.

**Save** calls `collectionsStore.saveBibliography(collection.id, effectiveContent)`,
receives the server-assigned `version`, shows "Saved v{n}" inline badge, and
exits edit mode.

**Copy** writes `effectiveContent` to the clipboard.

---

## Saved bibliographies panel (`CollectionDetailView.vue`)

Visible to EiC+ users in the collection detail page.  The panel is foldable
(controlled by `biblioOpen`).

### Panel structure

```
┌─ Saved bibliographies ──────────────────────── [▲/▼] ─┐
│ Version │ Date       │ Is public          │ Actions     │
├─────────┼────────────┼────────────────────┼─────────────┤
│  v3     │ 2026-04-15 │ ● (radio, checked) │ Copy Delete │
│  v2     │ 2026-04-10 │ ○                  │ Copy Delete │
│  v1     │ 2026-04-01 │ ○                  │ Copy Delete │
└─────────────────────────────────────────────────────────┘
  [→ View public page]  (shown when any version is public)
```

**Radio button semantics**: each row has a radio input with
`name="bib-public-{collection_id}"`.  Selecting a radio calls
`handleSetPublic(version, true)`, which:
1. Issues PATCH on the backend (bulk un-publish + publish target).
2. Mirrors the result locally: `bibliographies.map(b => b.version === version ? updated : { ...b, is_public: false })`.

The currently public row is highlighted in green.

When no version is public, the "View public page" link is hidden.  When a
version becomes public, the link targets `{ name: 'public-bibliography', params: { slug } }`.

**Load**: `listBibliographies(collection.id)` is called in `onMounted` inside
the EiC+ guard block, so the panel is pre-populated when the page loads.

---

## Public exposure

### Home page button

`CollectionResponse.has_public_bibliography` is computed during the
`collections_public` listing request (`GET /api/v1/collections`):

```python
# One batch query for all collection IDs in the current page:
pub_bib_rows = await db.execute(
    select(CollectionBibliography.collection_id)
    .where(
        CollectionBibliography.collection_id.in_(col_ids),
        CollectionBibliography.is_public.is_(True),
    )
    .distinct()
)
public_bib_set = {row[0] for row in pub_bib_rows}

for r in rows:
    cr = CollectionResponse.model_validate(r)
    if r.id in public_bib_set:
        cr.has_public_bibliography = True
```

In `PublicHomeSection.vue`, when `col.has_public_bibliography` is true, an
amber **Bibliography** `RouterLink` appears on both the "recent collections"
cards and the full list rows, pointing to
`{ name: 'public-bibliography', params: { slug: col.slug } }`.

### Public bibliography page (`PublicBibliographyView.vue`)

**Route**: `/browse/:slug/bibliography` (no auth, public)

This route is registered **before** `/browse/:slug/:filename` in `router/index.ts`
to prevent Vue Router from consuming the literal string `"bibliography"` as a
`:filename` parameter.

On mount: `collectionsStore.fetchPublicBibliography(slug)`.

The `entries` computed property parses `bibliography.content` (XML string) using
the browser's native `DOMParser`:

```typescript
const doc = parser.parseFromString(bibliography.content, "application/xml");
// Try TEI namespace first, then no-namespace fallback:
let nodes = doc.getElementsByTagNameNS("http://www.tei-c.org/ns/1.0", tag);
if (nodes.length === 0) nodes = doc.getElementsByTagName(tag);
```

Each entry is rendered as a numbered `<li>` with the element's plain-text
content (`textContent`).

---

## Website system page — Bibliography

The **Bibliography** system page is available on all websites as the fifth
aracne-nav entry (alongside Home, Browse, Search, Indices).

### Configuration

In `WebsiteEditView.vue`, the "Pages" tab shows the Bibliography system page
with a visibility toggle.  The page is active by default (`is_hidden: false`).
It can be hidden from the nav without deleting it.

In `backend/app/services/websites.py`, `_parse_aracne_nav()` includes:

```python
"bibliography": {"id": "bibliography", "sort_order": 4, "is_hidden": False}
```

### HTML rendering (`_build_bibliography_content`)

```python
# backend/app/services/websites.py

def _build_bibliography_content(content_xml: str | None) -> str:
    # Parses content_xml with defusedxml.ElementTree (mandatory — no xml.etree).
    # Extracts <bibl> and <biblStruct> children.
    # Tries TEI namespace first; falls back to no-namespace.
```

Output structure:
```html
<section class="bibl-section">
  <ul class="bibl-list">
    <li class="bibl-entry">
      <span class="bibl-number">1.</span>
      <span class="bibl-text">Rossi, Mario. …</span>
    </li>
    <!-- … -->
  </ul>
</section>
```

Note: `<ul>` (not `<ol>`) is used deliberately to prevent browser auto-numbering
from stacking with the explicit `bibl-number` span.

Empty states:
- `content_xml` is `None` → `<p class="bibl-empty">No bibliography available.</p>`
- No entries found in XML → `<p class="bibl-empty">No bibliography entries found.</p>`
- XML parse error → `<p class="bibl-empty">Could not render bibliography.</p>`

### Dynamic rendering (`render_dynamic_bibliography`)

```
GET /api/v1/sites/{slug}/bibliography
GET /api/v1/sites/{slug}/bibliography.html
```

Both paths are handled by the same FastAPI endpoint in
`backend/app/routers/websites.py`:

```python
if website.rendering_mode == RenderingMode.STATIC:
    # Serve pre-built bibliography.html from disk.
    path = _resolve_site_file(slug, "bibliography.html")
    return FileResponse(path, media_type="text/html")
html = await svc.render_dynamic_bibliography(db, website)
return _dynamic_html_response(html, svc.compute_etag(website), request)
```

`render_dynamic_bibliography` (Dynamic / Hybrid modes):
1. Checks page cache (`_get_cached_page`).
2. Queries `CollectionBibliography` for `is_public=True` on the linked collection.
3. Calls `_build_bibliography_content(content_xml)`.
4. Calls `_render_page(...)` with `custom_js=website.custom_js` (the un-enhanced
   designer JS — image/note rendering scripts are excluded from this page).
5. Stores the result in the page cache.

### Static / Hybrid build

During `_build_static_site` and `_build_hybrid_site`, the bibliography page is
written as `{site_dir}/bibliography.html`.  It is skipped when
`bibliography_hidden=True` (nav config flag).

```python
base_custom_js = website.custom_js   # save before document-only JS is appended
custom_js = base_custom_js
if _ir_modal: custom_js += "\n" + _IMAGE_MODAL_JS
# … further document-specific JS appended to custom_js …

# bibliography.html uses base_custom_js, not the enhanced custom_js:
bibliography_html = _render_page(
    content=_build_bibliography_content(bib_xml),
    custom_js=base_custom_js,   # ← no document scripts
    …
)
```

`base_custom_js` is intentionally split out so that image-modal and
note-rendering JavaScript (which expect TEI document HTML structure) are not
injected into the bibliography page.

---

## Data flow summary

```
Editor in Chief
  │
  ├─ opens /collections/{slug}/bibliobuilder
  │     │
  │     ├─ [Extract] → GET /extract-bibl → XQuery → <entries> XML
  │     │
  │     └─ [Run Bibliobuilder] → POST /ai/complete (bibliobuilder prompt)
  │              → streaming <listBibl>
  │              → [Edit] (optional manual corrections)
  │              → [Save] → POST /bibliographies → version N created
  │
  ├─ opens Collection detail → Saved bibliographies panel
  │     └─ radio → PATCH /bibliographies/{version} { is_public: true }
  │                → only this version is public
  │
  └─ Public exposure
        ├─ Public home page → "Bibliography" button when has_public_bibliography
        │     └─ /browse/{slug}/bibliography → GET /public-bibliography → parse XML
        │
        └─ Website system page
              ├─ Dynamic: GET /sites/{slug}/bibliography → render_dynamic_bibliography
              ├─ Hybrid:  bibliography.html pre-built + live-served
              └─ Static:  bibliography.html pre-built, served from disk
```

---

## Known constraints and design decisions

- **No namespace in stored XML**: the AI output typically omits the TEI namespace
  declaration. `_build_bibliography_content` tries the TEI namespace first and
  falls back to no-namespace, so both forms are handled correctly.

- **Content is stored as-is**: the backend does not validate or re-parse the
  `content` field on save. The EiC is responsible for reviewing the XML before
  saving. Invalid XML will render as an empty-state message.

- **One public version at a time**: enforced at the application level by the
  PATCH handler and mirrored optimistically on the frontend. There is no DB
  partial unique index; race conditions (two concurrent PATCHes) are unlikely in
  practice but not transactionally impossible.

- **Version numbers are not recycled**: deleting v3 does not renumber v1 and v2.
  The next save will be v4. This preserves referential stability (e.g. if a
  version number appears in external notes).

- **Cache invalidation**: `render_dynamic_bibliography` uses the website's TTL
  cache.  After saving and publishing a new bibliography version, the new content
  will appear on the website after at most one TTL period — or immediately if
  the static/hybrid build is re-triggered.
