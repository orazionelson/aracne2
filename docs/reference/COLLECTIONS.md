# Collections & TEI Editor — Technical Reference

This document covers the core editorial workflow of Aracne2: how XML document
collections are organized, managed, and published, and how individual TEI
documents are edited through the browser-based editor with its surrounding
tools.

---

## Table of contents

1. [What is a collection](#1-what-is-a-collection)
2. [Data model](#2-data-model)
3. [ACL and visibility](#3-acl-and-visibility)
4. [Collection lifecycle (workflow)](#4-collection-lifecycle-workflow)
5. [Document storage — eXist-db](#5-document-storage--exist-db)
6. [XQuery operations on collections](#6-xquery-operations-on-collections)
7. [Backend API endpoints](#7-backend-api-endpoints)
8. [Collection detail view (frontend)](#8-collection-detail-view-frontend)
9. [Collection metadata — the edit form](#9-collection-metadata--the-edit-form)
10. [Document management in the detail view](#10-document-management-in-the-detail-view)
11. [Collection-wide validation](#11-collection-wide-validation)
12. [Saved bibliographies panel](#12-saved-bibliographies-panel)
13. [TEI editor — architecture](#13-tei-editor--architecture)
14. [useCodeMirror composable](#14-usecodemirror-composable)
15. [Facsimile & media management](#15-facsimile--media-management)
16. [Note system](#16-note-system)
17. [Right-side panel system](#17-right-side-panel-system)
18. [AI integration in the editor](#18-ai-integration-in-the-editor)
19. [Save flow and validation](#19-save-flow-and-validation)
20. [Frontend stores](#20-frontend-stores)
21. [File map](#21-file-map)

---

## 1. What is a collection

A collection is the primary organizational unit in Aracne2. It represents a
set of XML documents (typically a scholarly edition or a corpus) that share
metadata, a validation schema, and a publication destination.

Every collection:

- maps to exactly one **eXist-db collection** (a folder in the XML database)
- has a **slug** (URL-safe identifier, immutable after creation) used both as
  the eXist-db path segment and as the public-facing URL identifier
- has a **status** that drives the editorial workflow (see §4)
- holds metadata that is injected into new documents (publisher, author,
  license, responsibility statements, etc.)
- optionally carries a **TeiSchema** for validation and CodeMirror autocomplete
- can be assigned to an **Editor** (one at a time) while remaining visible to
  all EditorInChief/Admin users

Collections are distinct from eXist-db indices and websites: a collection is
the authoritative source of documents; indices and websites consume it.

---

## 2. Data model

### `Collection` (PostgreSQL)

| Column | Type | Notes |
|--------|------|-------|
| `id` | `UUID` | PK |
| `slug` | `str UNIQUE` | URL-safe; kebab-case; immutable |
| `title` | `str` | Human-readable title |
| `description` | `str \| None` | Free-text |
| `status` | `enum` | `draft`, `assigned`, `review`, `published` |
| `is_public` | `bool` | Whether visible without auth (published only) |
| `owner_id` | `UUID FK → User` | SET NULL on delete |
| `editor_id` | `UUID FK → User` | Currently assigned editor; SET NULL on delete |
| `assigned_at` | `datetime \| None` | Set when moved to `assigned` |
| `submitted_at` | `datetime \| None` | Set when moved to `review` |
| `published_at` | `datetime \| None` | Set when published |
| `schema_id` | `UUID FK → TeiSchema \| None` | Validation + CM5 schema |
| `body_template_id` | `UUID FK → BodyTemplate \| None` | `<body>` snippet for new docs |
| `publisher` | `str \| None` | Publication metadata |
| `pub_place` | `str \| None` | Publication place (Geonames-autocompleted) |
| `pub_year` | `int \| None` | |
| `license_id` | `UUID FK → License \| None` | |
| `author` | `str \| None` | Collection-level single author (VIAF-autocompleted) |
| `resp_stmts` | `JSONB \| None` | `[{resp, name}]` responsibility statements |
| `listbibl_bibl_main` | `str \| None` | Primary source citation |
| `msidentifier_idno` | `str \| None` | Manuscript identifier |
| `objectdesc_form` | `str \| None` | Physical form: `codex`, `leaf`, `roll`, `tablet`, `sheet`, `fascicle`, `fragment`, `other` |
| `identifier_url` | `str \| None` | DOI / Handle / URN |
| `doc_count` | `int` | Denormalized document count; updated after uploads/deletes |
| `evt_enabled` | `bool` | Per-collection EVT viewer opt-in |
| `created_at`, `updated_at` | `datetime` | Timezone-aware |

### `CollectionPermission`

Grants explicit read access to a specific user for a specific collection,
independently of the assignment workflow. An Editor who is not the assigned
editor can still see a collection if a permission row exists.

| Column | Type | Notes |
|--------|------|-------|
| `collection_id` | `UUID PK, FK cascade` | |
| `user_id` | `UUID PK, FK cascade` | |
| `granted_by_id` | `UUID FK → User` | SET NULL on delete |
| `granted_at` | `datetime` | |

### `TeiSchema`

| Column | Type | Notes |
|--------|------|-------|
| `id` | `UUID` | PK |
| `name` | `str` | Display name |
| `validation_filename` | `str \| None` | RNG / DTD / XSD file on disk |
| `validation_format` | `enum \| None` | `rng`, `dtd`, `xsd` |
| `cm5_filename` | `str \| None` | CodeMirror XML schema (custom format) |
| `created_by` | `UUID FK → User` | |

When `validation_format` is set, the editor automatically validates each save.
When `cm5_filename` is set, the editor loads schema-aware tag and attribute
autocomplete.

### `CollectionBibliography`

See [BIBLIOGRAPHY.md](BIBLIOGRAPHY.md) for full details.

```
id, collection_id, version (per-collection int), content (XML text),
created_at, created_by_id, is_public (mutual exclusion enforced in app)
```

---

## 3. ACL and visibility

### Role hierarchy (relevant levels)

```
Admin (4) → EditorInChief (3) → Editor (2) / Designer (2) → User (1)
```

### Read access

A user may read a collection if **any** of the following is true:

| Condition | Who |
|-----------|-----|
| Role ≥ EditorInChief | always |
| Collection status = `published` | any authenticated user |
| `editor_id` = current user | regardless of status |
| `CollectionPermission` row exists | explicit grant by EiC+ |

Enforced in `_assert_read_access()` in the service layer.

### Write access (document operations)

Write access requires read access **and**:

- Collection must **not** be in `published` status (published collections are
  frozen — no document edits)
- Actor is EiC/Admin, **or** is the assigned editor when status = `assigned`

### List visibility (collections list endpoint)

| Role | Sees |
|------|------|
| EditorInChief / Admin | all collections |
| Editor | assigned collections + permission grants |
| User / Designer | published collections + permission grants |

### Endpoint-level guards

```
[pub]   = no auth required
[auth]  = any authenticated user
[E+]    = Editor or above (level ≥ 2)
[EiC+]  = EditorInChief or above (level ≥ 3)
[A]     = Admin only
```

---

## 4. Collection lifecycle (workflow)

```
draft ──assign──► assigned ──submit──► review ──publish──► published
         (EiC+)  (editor)            (EiC+)   (EiC+)
                     ◄──reject──── (EiC+)
published ──unpublish──► draft  (Admin only)

Any state ──direct-publish──► published  (EiC+, bypasses workflow)
```

### State transitions

| Transition | Endpoint | Actor | Notes |
|------------|----------|-------|-------|
| `draft` → `assigned` | `POST /{id}/assign` | EiC+ | Sets `editor_id`, `assigned_at`; notifies new editor |
| `assigned` → `assigned` (reassign) | `POST /{id}/assign` | EiC+ | Also notifies old editor |
| `assigned` → `review` | `POST /{id}/submit` | Assigned editor only | Sets `submitted_at`; notifies all EiC/Admin |
| `review` → `assigned` | `POST /{id}/reject` | EiC+ | Requires `note`; clears `submitted_at`; notifies assigned editor |
| `review` → `published` | `POST /{id}/publish` | EiC+ | Sets `published_at`; emits `ON_COLLECTION_PUBLISHED` hook; notifies assigned editor |
| `any` → `published` | `POST /{id}/direct-publish` | EiC+ | Bypasses workflow; used for batch imports |
| `published` → `draft` | `POST /{id}/unpublish` | Admin only | Destructive — removes public access |

All workflow transitions accept an optional `note` string (persisted in the
notification payload and audit log).

### Published collection freeze

Once a collection reaches `published` status, its documents are **read-only**.
Service layer `_assert_write_access()` raises `CollectionFrozenError` on any
document mutation, regardless of the requesting user's role.

To edit a published collection, an Admin must first unpublish it.

---

## 5. Document storage — eXist-db

Each collection maps to an eXist-db collection at:

```
/db/aracne2/collections/{slug}/
```

Documents are stored as raw UTF-8 XML files. All queries run directly against
this path via `ExistDBClient.xquery()`.

### Filename validation

Accepted filenames: `^[a-zA-Z0-9][a-zA-Z0-9._\-]*\.xml$`, max 128 chars.

This prevents path traversal, ensures an `.xml` extension, and guarantees
natural sort stability across all XQuery list operations.

### ZIP batch upload

The `POST /{id}/documents/batch` endpoint accepts a `.zip` archive:

- Root-level `.xml` files are extracted; files inside subdirectories are
  skipped
- Bomb-guard: configurable limits via system settings
  (`zip_max_size_mb`, `zip_max_extracted_mb`, `zip_max_files`)
- Returns a `ZipUploadResult` with counts of uploaded, skipped, and failed
  files
- `doc_count` is updated atomically after all uploads

### XML parsing security

All XML received from clients is parsed with `defusedxml.ElementTree` before
being written to eXist-db. This prevents XXE injection attacks regardless of
the content.

---

## 6. XQuery operations on collections

XQuery files live in `backend/app/xqueries/collections/`. They are loaded from
disk at runtime via `ExistDBClient.xquery()` — never inlined in Python code.

### `list.xq`

Returns the filenames of all XML documents in the collection, one per line.

```
External: $path  (e.g. /db/aracne2/collections/dante)
Returns:  newline-separated filenames
```

### `list_with_titles.xq`

Extracts `<title>` and `<author>` from each document's `<titleStmt>` using
`local-name()` matching — works regardless of whether a default TEI namespace
is declared.

```
External: $collection_path
Returns:  <docs><doc><filename/><title/><author/></doc>…</docs>
```

### `stats.xq`

Document count and total size for dashboard display.

```
External: $path
Returns:  "count={n} size={bytes}"
```

### `extract_bibl.xq`

Extracts all `<bibl>` and `<biblStruct>` elements from the collection,
stripping the TEI namespace so the result can be passed directly to the
Bibliobuilder AI prompt.

```
External: $collection_path
Returns:  <entries>
            <bibl source="filename.xml" n="1">…</bibl>
            <biblStruct source="filename.xml" n="1">…</biblStruct>
            …
          </entries>
```

Used by `GET /{id}/extract-bibl` (EiC+). See [BIBLIOGRAPHY.md](BIBLIOGRAPHY.md).

### `distinct_tags.xq`

Scans all documents and returns a JSON object mapping element local-names to
the list of attribute local-names found on them.

```
External: $path
Returns:  {"persName":["key","role"],"placeName":["ref"]}
```

Used by the website index/search subsystem to discover which tags and
attributes carry interesting values.

### `index_occurrences.xq`

Collects all occurrences of a named tag from the collection for index building.
Returns pipe-delimited records: `key ||| subkey ||| text ||| filename`.

```
External: $path, $tag, $key_attr, $subkey_attr
Returns:  newline-separated records
```

Used by the website static build to produce per-tag indices (e.g. persons,
places, dates).

### `documents/get_metadata.xq`

Generic XML document metadata: root element name, namespace URI, character
count, and direct child count.

```
External: $doc_path
Returns:  <metadata>
            <root-element/>
            <namespace/>
            <size/>
            <child-count/>
          </metadata>
```

---

## 7. Backend API endpoints

Router: `backend/app/plugins/_native/collections/router.py`
Service: `backend/app/services/xmldb.py` (high-level wrappers around
`ExistDBClient`)

### ACL aliases

```python
_auth = Depends(get_current_user)          # any authenticated user
_eic  = Depends(require_role("EditorInChief"))  # EiC+
_adm  = Depends(require_role("Admin"))     # Admin only
```

### Collection CRUD

| Method | Path | ACL | Body / Params | Returns |
|--------|------|-----|---------------|---------|
| `GET` | `/collections` | `[auth]` | `page`, `per_page`, `status?`, `search?` | `PaginatedResponse[CollectionResponse]` |
| `POST` | `/collections` | `[EiC+]` | `CollectionCreate` | `DataResponse[CollectionResponse]` 201 |
| `GET` | `/collections/{id}` | `[auth]` | — | `DataResponse[CollectionResponse]` |
| `PATCH` | `/collections/{id}` | `[EiC+]` | `CollectionUpdate` | `DataResponse[CollectionResponse]` |
| `DELETE` | `/collections/{id}` | `[A]` | — | 204 |
| `GET` | `/collections/public` | `[pub]` | `page`, `per_page`, `search?` | `PaginatedResponse[CollectionResponse]` |
| `GET` | `/collections/public/search` | `[pub]` | `q` (1–256 chars), `max_doc_hits` (1–10) | `DataResponse[list[PublicCollectionSearchResult]]` |

### Workflow transitions

| Method | Path | ACL | Body | Notes |
|--------|------|-----|------|-------|
| `POST` | `/{id}/assign` | `[EiC+]` | `AssignAction(user_id, note?)` | draft/assigned → assigned |
| `POST` | `/{id}/submit` | `[auth]` | `WorkflowAction(note?)` | assigned → review (assigned editor only) |
| `POST` | `/{id}/reject` | `[EiC+]` | `RejectAction(note)` | review → assigned |
| `POST` | `/{id}/publish` | `[EiC+]` | `WorkflowAction(note?)` | review → published |
| `POST` | `/{id}/direct-publish` | `[EiC+]` | `WorkflowAction(note?)` | any → published |
| `POST` | `/{id}/unpublish` | `[A]` | `WorkflowAction(note?)` | published → draft |

### Document management

| Method | Path | ACL | Notes |
|--------|------|-----|-------|
| `GET` | `/{id}/documents` | `[auth]` | Natural sort; returns `list[DocumentInfo]` |
| `POST` | `/{id}/documents` | `[auth]` | Multipart upload; filename validated |
| `POST` | `/{id}/documents/batch` | `[auth]` | ZIP batch; bomb-guard applied |
| `GET` | `/{id}/documents/{filename}` | `[auth]` | Raw XML download (attachment) |
| `PUT` | `/{id}/documents/{filename}` | `[auth]` | Replace XML; `Content-Type: application/xml` |
| `DELETE` | `/{id}/documents/{filename}` | `[auth]` | Updates `doc_count` |
| `GET` | `/{id}/documents/{filename}/metadata` | `[auth]` | `DocumentMeta` from XQuery |
| `POST` | `/{id}/documents/{filename}/validate` | `[auth]` | `DocumentValidateRequest(xml_content?)` |

Write endpoints (POST/PUT/DELETE on documents) honour the published-collection
freeze enforced in the service layer.

### Search

| Method | Path | ACL | Notes |
|--------|------|-----|-------|
| `GET` | `/{id}/search` | `[auth]` | `q` param; full-text via eXist-db; max 200 results |
| `GET` | `/public/search` | `[pub]` | Cross-collection; metadata + full-text hits |

### Collection-wide validation

| Method | Path | ACL | Notes |
|--------|------|-----|-------|
| `POST` | `/{id}/validate-all` | `[EiC+]` | Start async background run |
| `GET` | `/{id}/validate-all/latest` | `[EiC+]` | Fetch most recent run |
| `GET` | `/{id}/validate-all/{run_id}` | `[EiC+]` | Fetch specific run |
| `POST` | `/{id}/validate-all/{run_id}/cancel` | `[EiC+]` | Cancel pending/running run |

### Permission management

| Method | Path | ACL | Notes |
|--------|------|-----|-------|
| `GET` | `/{id}/permissions` | `[EiC+]` | List all explicit read grants |
| `POST` | `/{id}/permissions` | `[EiC+]` | Grant user read access (idempotent) |
| `DELETE` | `/{id}/permissions/{user_id}` | `[EiC+]` | Revoke grant; 204 |

### Bibliography endpoints

| Method | Path | ACL | Notes |
|--------|------|-----|-------|
| `GET` | `/{id}/bibliographies` | `[EiC+]` | All versions, newest first |
| `POST` | `/{id}/bibliographies` | `[EiC+]` | Save new version (auto-increment) |
| `PATCH` | `/{id}/bibliographies/{version}` | `[EiC+]` | Set `is_public` (mutual exclusion) |
| `DELETE` | `/{id}/bibliographies/{version}` | `[EiC+]` | 204 |
| `GET` | `/{id}/public-bibliography` | `[pub]` | Public version (no auth) |
| `GET` | `/{id}/extract-bibl` | `[EiC+]` | Raw `<entries>` XML for Bibliobuilder |

---

## 8. Collection detail view (frontend)

**File**: `frontend/src/views/CollectionDetailView.vue` (~1 860 lines)
**Route**: `/collections/:slug` (`name: collection-detail`)
**ACL**: any authenticated user (read); EiC+ for write actions

### Stores used

- `useCollectionStore` — collection data, documents, bibliographies
- `useSchemaStore` — available TeiSchema records
- `useLicenseStore` — license options
- `useBodyTemplateStore` — body template options
- `useCollectionValidationStore` — async validation run state
- `useAiStore` — validation AI assistance
- `useAuthStore` — role checks (`hasMinRole`, `hasRole`)
- `useSettingStore` — global settings (`evt_enabled`)

### On mount

```
1. fetchCollection(slug)
2. fetchDocuments(collectionId)
3. fetchSchemas(), fetchLicenses(), fetchBodyTemplates() — parallel, non-fatal
4. fetchEditors() — for assign dropdown (EiC+ only)
5. listBibliographies(collectionId) — EiC+ only
6. fetchConfig() (AI) — non-fatal
7. validationStore.fetchLatestRun(slug) — EiC+ only
```

### Header section

- Collection title + slug badge
- Status badge with color coding: draft (gray) / assigned (yellow) /
  review (blue) / published (green)
- Public indicator (shown when `is_public = true`)
- Assigned editor display name (shown when `editor_id` is set)
- Edit button (EiC+)

---

## 9. Collection metadata — the edit form

The edit form appears inline (no modal) when the EiC+ clicks "Edit". It
populates from `store.current` and submits via `PATCH /{id}`.

### Fields

| Field | UI control | Notes |
|-------|-----------|-------|
| Title | text input | Required |
| Description | textarea | Optional |
| Is public | checkbox | Whether to expose to unauthenticated users |
| EVT enabled | checkbox | Per-collection EVT viewer opt-in |
| Schema | dropdown | From `schemaStore.schemas` |
| Body template | dropdown | `body_template_id`; snippet for new documents |
| Single author | toggle + text input | VIAF autocomplete via `useViafAutocomplete()` |
| Publication place | text input | Geonames autocomplete via `useGeonamesAutocomplete()` |
| Publisher | text input | |
| Publication year | number input | |
| License | dropdown | From `licenseStore.licenses` |
| Responsibility statements | repeating list of {resp, name} | Person name autocompleted from editor list |
| Main source | toggle + text input | `listbibl_bibl_main` |
| Manuscript identifier | toggle + text input | `msidentifier_idno` |
| Object description form | toggle + select | One of: codex, leaf, roll, tablet, sheet, fascicle, fragment, other |
| Identifier URL | text input | DOI / Handle / URN |

### VIAF autocomplete

`useViafAutocomplete()` composable queries the VIAF API as the user types in
the author field. Results appear in a dropdown; selecting a name fills
`editAuthor` and closes the dropdown. The blur handler uses a 150 ms delay so
a click on a dropdown item fires before the list disappears.

### Geonames autocomplete

`useGeonamesAutocomplete()` works the same way for publication place.

### Responsibility statements

An arbitrary list of `{resp: string, name: string}` pairs. `resp` is a free
text responsibility label (e.g. "edited by"); `name` is autocompleted from the
list of platform editors. Any pair with both fields empty is stripped before
saving.

---

## 10. Document management in the detail view

### Document list

- Paginated with configurable page size: 10 / 25 / 50 / 100
- Shows filename, title (from `<titleStmt>` via XQuery), author, size
- Multi-select with "select all on page" checkbox
- Bulk delete with confirmation dialog

### Creating a new document

1. User enters a filename (extension `.xml` appended automatically if absent)
2. `_buildSkeleton(meta)` generates a full TEI XML skeleton populated with
   collection metadata:
   - `<teiHeader>` with `<titleStmt>`, `<publicationStmt>`, `<respStmt>`,
     `<listBibl>`, `<msDesc>`, `<objectDesc>`, `<idno>`
   - `<body>` section from `body_template_id` snippet (or default placeholder)
   - HTML entities escaped; TEI namespace declared
3. Skeleton uploaded via `POST /{id}/documents`
4. Router navigates to `DocumentEditView` for immediate editing

### Uploading documents

- **Single file**: multipart POST via file input; filename taken from
  `file.name`
- **ZIP batch**: multipart POST; returns `ZipUploadResult` with counts of
  uploaded / skipped / failed; doc list refreshed after upload

### Search

Full-text search across all documents in the collection via eXist-db. Results
show filename + matching context snippet. Clicking a result navigates to the
document editor.

### EVT button

Shown only when all conditions are met:
1. Global setting `evt_enabled = true`
2. Collection `evt_enabled = true`
3. Collection status = `published`
4. Collection `is_public = true`
5. Collection has exactly one document (EVT is designed for single-document
   editions)

Opens the EVT viewer for that document in a new tab.

### Bibliobuilder button (EiC+)

Navigates to `CollectionBibliobuilderview` (`/collections/:slug/bibliobuilder`).
See [BIBLIOGRAPHY.md](BIBLIOGRAPHY.md).

---

## 11. Collection-wide validation

**Store**: `frontend/src/stores/collection_validation.ts`

### Background run lifecycle

```
POST /{id}/validate-all     → run.status = "running"
                              backend: validates every document asynchronously
GET  /{id}/validate-all/latest  → polling; run.status ∈ running|completed|failed|cancelled
POST /{id}/validate-all/{run_id}/cancel → run.status = "cancelled"
```

### Run result structure

```typescript
interface CollectionValidationRun {
  id: string;
  status: 'running' | 'completed' | 'failed' | 'cancelled';
  started_at: string;
  completed_at: string | null;
  results: {
    total: number;
    valid: number;
    invalid: number;
    documents: {
      filename: string;
      valid: boolean;
      errors: { line: number; col: number; message: string }[];
    }[];
  } | null;
}
```

### UI

The validation report in the detail view shows:

- Summary bar: N/total valid
- Per-document rows: filename + error count badge
- Expandable error list per document (click to toggle)
- AI assistance: "Explain errors" button (one per document) opens `AiPanel`
  with `validate_errors_explain` prompt and the document's error list as context

The AI panel in the detail view is instantiated with `show-apply="false"` since
validation explanations are informational, not applicable XML.

---

## 12. Saved bibliographies panel

The saved bibliographies panel (EiC+ only) is a collapsible section in the
detail view showing all saved bibliography versions.

| Action | What it does |
|--------|-------------|
| Toggle row | Expand/collapse the XML content in a read-only CM5 viewer |
| Set public | PATCH version with `is_public=true`; un-publishes all other versions |
| Unset public | PATCH version with `is_public=false` |
| Delete | DELETE version (with confirmation) |
| Copy to clipboard | Copies the `content` XML string |

See [BIBLIOGRAPHY.md](BIBLIOGRAPHY.md) for the Bibliobuilder creation flow.

---

## 13. TEI editor — architecture

**File**: `frontend/src/views/DocumentEditView.vue` (~1 260 lines)
**Route**: `/collections/:slug/documents/:filename` (`name: document-edit`)
**ACL**: any user with read + write access to the collection

The editor is a two-column layout:

```
┌──────────────────────────────┬──────────────────────────────────┐
│                              │                                  │
│  CodeMirror 5 editor area    │  Right-side panel                │
│  (flex-1, min-w-0)           │  (resizable, 240–720 px)         │
│                              │  TEI Help | Media | Zone |       │
│                              │  Validation | AI                 │
│                              │                                  │
└──────────────────────────────┴──────────────────────────────────┘
```

The panel width is adjustable by dragging the divider. Initial width: 384 px
(Tailwind `w-96`). Minimum: 240 px, Maximum: 720 px.

### On mount

```
1. store.fetchCollection(slug)           ─┐ parallel
   store.fetchDocumentRaw(slug, filename) ─┘

2. schemaStore.fetchSchemas() — if cache empty

3. _extractFacsimileFromXml(xml) — populate facsimileXml ref

4. loadCm5Schema(schemaId) — async; sets schema ref
   → tries collection's cm5_filename first
   → falls back to built-in /cmschemas/tei-p5.xml

5. isLoading.value = false  → mounts CM5 editor containers
                              (v-if guard ensures CM5 initialises
                               on a visible, sized element)

6. aiStore.fetchConfig() — non-fatal; controls AI button visibility
```

### Source of truth

The CM5 editor is always the single source of truth for the document content.
The `facsimileXml` ref is a synchronized mirror of the `<facsimile>` block
only — it is updated by `addSurface`, `deleteSurface`, and `handleZonesSaved`,
all of which also patch the editor's own content via `singleCm.setValue()`.

---

## 14. useCodeMirror composable

**File**: `frontend/src/composables/useCodeMirror.ts`

Wraps CodeMirror 5. The parent component never touches the CM5 API directly.

### Options

```typescript
interface UseCodeMirrorOptions {
  initialValue?: string;       // XML loaded on init
  schema?: CM5Schema;          // TEI schema for autocomplete
  readOnly?: boolean;
  onChange?: (value: string) => void;
  onRefClick?: (noteId: string, noteType: 'alpha' | 'numeric', content: string) => void;
}
```

### Exported API

| Method | Description |
|--------|-------------|
| `getValue()` | Returns full editor content |
| `setValue(content)` | Replaces document; resets cursor, scroll, markers |
| `toggleFullscreen()` | F11 toggle |
| `prettyPrint()` | Format XML with indentation |
| `foldAll()` | Collapse all foldable regions |
| `refresh()` | Force CM5 repaint (after `v-show` changes) |
| `insertNote(type, noteId, content)` | Insert `<ref>` + `<note>` atomically |
| `editNote(noteId, newContent)` | Update note text in-place |
| `deleteNote(noteId)` | Remove ref + note; clean up empty `<span type="notes">` |
| `insertPageBreak(surfaceId)` | Insert `<pb facs="#id"/>` at cursor |
| `insertFigure(url)` | Insert `<figure><graphic url="…"/></figure>` at cursor |
| `insertFacsRef(zoneId)` | Append/create `facs="#zoneId"` on nearest opening tag |
| `isFullscreen` | Reactive `Ref<boolean>` |
| `editorInstance` | Reactive `Ref<Editor \| null>` (raw CM5 instance, for escape hatches) |

### Addons loaded

```
mode/xml, fold/xml-fold, fold/foldgutter, edit/closetag, edit/matchtags,
selection/active-line, search/search, search/searchcursor,
search/jump-to-line, dialog/dialog, hint/show-hint, hint/xml-hint,
display/fullscreen, display/autorefresh, scroll/annotatescrollbar,
comment/comment
```

### Schema-aware autocomplete

When `schema` is set, four keys trigger the CM5 xml-hint:

| Trigger | Completes |
|---------|-----------|
| `<` | Element names valid at current position |
| `/` after `<` | Closing tag names |
| space inside tag | Attribute names |
| `=` after attribute | Attribute values |

The schema is loaded from the collection's `cm5_filename` field, or from the
built-in `/cmschemas/tei-p5.xml` fallback. Loading is done via
`loadTeiSchema()` from `@/utils/teiSchema`.

### Keyboard shortcuts

| Shortcut | Action |
|----------|--------|
| `Ctrl+Space` | Toggle autocomplete |
| `Ctrl+J` | Jump to matching tag |
| `Ctrl+/` | Toggle comment |
| `F11` | Toggle fullscreen |
| `Esc` | Exit fullscreen |

### `<ref>` marker protection

On init and after each `setValue()`, `markRefTagsOnInstance()` scans the
document for `<ref target="#…" type="…"/>` elements and applies a read-only
`TextMarker` with CSS class `cm-note-ref`. A `beforeChange` event handler
rejects any edit that overlaps an existing marker (unless the edit originates
from the composable itself, indicated by a programmatic origin key).

This prevents users from accidentally corrupting note references by typing
inside them.

---

## 15. Facsimile & media management

### `<facsimile>` block lifecycle

The `<facsimile>` block inside the TEI document is kept in sync with the editor
through a mirror ref (`facsimileXml`). The block is never parsed server-side
for display purposes — the `surfaces` computed property parses it with regex on
the client.

```typescript
const surfaces = computed((): FacsimileSurface[] => {
  // Parse <surface xml:id="…"> / <graphic url="…"/> pairs from facsimileXml
});
```

### Adding a surface (`addSurface`)

1. Check if the URL is already registered (idempotent)
2. Generate next id: `s${surfaces.length + 1}`
3. If no `<facsimile>` block exists: create one and insert it after
   `</teiHeader>` in the editor
4. Otherwise: append `<surface>` before `</facsimile>`
5. Patch editor content via `singleCm.setValue()`
6. Return the surface id (used immediately by `insertPageBreak`)

### Removing a surface (`deleteSurface`)

1. Remove the `<surface xml:id="id">` element from the facsimile block
2. Strip all `facs="#id"` attributes from `<pb>` elements in the body
3. If the facsimile block becomes empty, remove it entirely
4. Apply both changes in a single `singleCm.setValue()` call

### Reordering surfaces (`handleMoveSurface`)

Swaps two adjacent `<surface>` blocks inside `<facsimile>`. The whitespace
indentation slots stay in place — only the XML content of the two blocks is
swapped.

### Cleaning up media refs (`handleCleanupMediaRefs`)

Called when a media file is deleted from storage:

1. If the URL is linked to a surface, `deleteSurface` is called
2. All `<graphic url="mediaUrl"/>` elements in the document body are also
   stripped

### Media panel component

`MediaPanel.vue` receives `surfaces` and emits:

| Event | Handler | Action |
|-------|---------|--------|
| `insert-figure` | `handleInsertFigure(url)` | `singleCm.insertFigure(url)` |
| `insert-as-card` | `handleInsertAsCard(url)` | `addSurface(url)` + `singleCm.insertPageBreak(surfaceId)` |
| `move-surface` | `handleMoveSurface(id, dir)` | Reorder in facsimile |
| `delete-surface` | `deleteSurface(id)` | Remove from facsimile + strip pb refs |
| `delete-media` | `handleCleanupMediaRefs(url)` | Remove surface + inline graphics |
| `open-zones` | `openZoneEditor(surface)` | Open ZoneEditor panel |

### Zone editor panel

`ZoneEditor.vue` receives a `FacsimileSurface` and exposes:

- Canvas-based zone drawing on the surface image
- Saves zones to eXist-db zones API directly (writes bypass the document editor)
- Emits `zones-saved` → `handleZonesSaved()` callback re-fetches the document,
  extracts the updated `<facsimile>` block, and patches only that portion of the
  editor so unsaved edits outside `<facsimile>` are preserved

The `ZoneEditor` also has an `onAssociate(zoneId)` prop that calls
`singleCm.insertFacsRef(zoneId)` to link a zone to the nearest element at the
current cursor position.

---

## 16. Note system

Notes in Aracne2 follow a specific TEI encoding:

```xml
<!-- Inline reference (cursor position) -->
<ref target="#N1a2b3c4d" type="alpha"/>

<!-- Note content collected at container level -->
<span type="notes">
  <note xml:id="N1a2b3c4d" type="alpha">Note text here</note>
</span>
```

Two note types are supported:

| Type | Display | ID format |
|------|---------|-----------|
| `alpha` | Alphabetic (a, b, c…) | `N` + 9 base-36 chars |
| `numeric` | Numeric (1, 2, 3…) | Same |

### Inserting a note

1. User clicks "Add Note (alpha)" or "Add Note (numeric)" in the toolbar
2. `NoteModal.vue` opens for content entry
3. On confirm: `generateNoteId()` → `singleCm.insertNote(type, noteId, content)`
4. Composable inserts `<ref target="#id" type="…"/>` at cursor
5. Finds nearest container element (div/summary)
6. Finds or creates a `<span type="notes">` child
7. Appends `<note xml:id="id" type="…">content</note>`
8. Marks the ref with a read-only `TextMarker`

### Editing a note

Clicking a `cm-note-ref` marker triggers `onRefClick(noteId, type, content)`.
The modal opens pre-populated; on confirm, `singleCm.editNote(noteId, newContent)`
replaces the note text.

### Deleting a note

Via the modal "Delete" button: `singleCm.deleteNote(noteId)` removes both the
`<ref>` element and the `<note>` element. If the `<span type="notes">` parent
becomes empty, it is removed too.

---

## 17. Right-side panel system

The right-side panel hosts five mutually exclusive panels. Opening any panel
closes the others (explicit `showXPanel.value = false` guards in each open
function).

### Panel width

```typescript
const PANEL_MIN_PX = 240;
const PANEL_MAX_PX = 720;
const panelWidth    = ref(384);   // initial width (Tailwind w-96)
```

A drag handle between the editor and panel fires `mousemove` / `mouseup`
listeners on `document`. Dragging left (negative delta) widens the panel.

### TEI Help panel

- Text input filters element names from the loaded schema (up to 30 matches)
- Selecting an element name shows a link to the TEI P5 documentation:
  `https://tei-c.org/release/doc/tei-p5-doc/en/html/ref-{TAG}.html`
- Works only when a CM5 schema is loaded; the schema provides the element list
  via `Object.keys(schema).filter(k => k !== '!top')`

### Media panel

See §15.

### Zone editor panel

See §15.

### Validation panel

Displays the result of the last validation run:

- Green "Valid" indicator when `validationResult.valid = true`
- List of `{line, col, message}` errors otherwise
- Save error messages also appear here (editor redirects to this panel on
  save failure)

Validation can be triggered explicitly ("Validate" toolbar button) or runs
automatically after each save when the collection has a `validation_format`
schema attached.

### AI panel

See §18.

---

## 18. AI integration in the editor

**Store**: `useAiStore`
**Component**: `AiPanel.vue`

Three AI modes are available in the editor. Each is a separate button in the
AI panel header:

### Mode 1 — Validate (`validate_errors_explain`)

**Purpose**: Explain validation errors in plain language.

**Flow**:

1. User clicks "Validate" AI button
2. `runValidateAi()` is called:
   - Validates the **current editor buffer** (not the saved file, so unsaved
     changes are caught)
   - If valid: displays "No errors found" message; AI stream not started
   - If invalid: collects errors as `Line N, col C: message` text
3. `aiStore.startStream('validate_errors_explain', { filename, schema, errors })`
4. Streamed explanation appears in AiPanel
5. No "Apply" button (explanatory output)

### Mode 2 — Improve (`document_edit_suggest`)

**Purpose**: Suggest XML improvements for the current selection or full document.

**Flow**:

1. User clicks "Improve" button
2. `runImproveAi()`:
   - Captures `activeEditor.getSelection()` (or full document if no selection)
3. `aiStore.startStream('document_edit_suggest', { filename, collection_slug, selection })`
4. Streamed XML appears in a **read-only CM5 viewer** (syntax-highlighted XML,
   `readOnly: true`, height auto)
5. Markdown code fences are stripped from the response via regex before display
6. "Apply" button: replaces the selection (or full document) with the cleaned
   AI response, then closes the panel

### Mode 3 — Discuss (`document_discuss`)

**Purpose**: Free-form conversation about the document.

**Flow**:

1. User clicks "Discuss" button
2. `runDiscussAi()` captures a **snapshot** of `{ filename, collection_slug, selection }`
   into `discussContext` — a stable object that does not update on every
   keystroke (avoids restarting the stream on edits)
3. `AiPanel` uses `continueChat` for follow-up messages
4. No "Apply" button (`showApply="false"`)

### AI button visibility

The AI panel button is shown only when `aiStore.config !== null && config.provider !== 'disabled'`.
The config is fetched on mount (non-fatal — if the fetch fails, the button is
simply not shown).

---

## 19. Save flow and validation

### Manual save

```
handleSave()
  ├── store.updateDocument(slug, filename, singleCm.getValue())
  │     PUT /collections/{id}/documents/{filename}
  │     Content-Type: application/xml
  │     (service: defusedxml parse + write to eXist-db)
  ├── On success:
  │     saved.value = true
  │     if hasValidationSchema → runValidation()
  └── On error:
        saveError displayed in validation panel
        validation panel auto-opened
```

### Auto-validation on save

When the collection has a `validation_format` schema attached
(`hasValidationSchema.value = true`), every successful save triggers
`runValidation()` automatically. Validation errors auto-open the validation panel.

### Validation endpoint

`POST /collections/{id}/documents/{filename}/validate`

Accepts an optional `xml_content` field. When omitted, the backend re-reads the
document from eXist-db. When supplied (as in `runValidateAi()`), the buffer
content is validated without saving — useful for catching errors in unsaved
edits before they are persisted.

Returns `ValidationResult`:

```typescript
interface ValidationResult {
  valid: boolean;
  errors: { line: number; col: number; message: string }[];
}
```

---

## 20. Frontend stores

### `useCollectionStore` (`frontend/src/stores/collections.ts`)

#### State

```typescript
collections: Collection[]
current: Collection | null
documents: DocumentInfo[]
editors: EditorOption[]
bibliographies: CollectionBibliography[]
pagination: PaginationMeta | null
isLoading: boolean
```

#### Collection actions

| Action | API call | Notes |
|--------|---------|-------|
| `fetchCollections(page, status?, search?)` | GET /collections | Paginated |
| `fetchCollection(slug)` | GET /collections/{id} | Sets `current` |
| `fetchEditors()` | GET /users | For assign dropdowns |
| `createCollection(body)` | POST /collections | |
| `updateCollection(id, body)` | PATCH /collections/{id} | Updates `current` |
| `deleteCollection(id)` | DELETE /collections/{id} | |

#### Workflow actions

| Action | API call |
|--------|---------|
| `assignCollection(id, userId, note?)` | POST /{id}/assign |
| `submitCollection(id, note?)` | POST /{id}/submit |
| `rejectCollection(id, note)` | POST /{id}/reject |
| `publishCollection(id, note?)` | POST /{id}/publish |
| `unpublishCollection(id, note?)` | POST /{id}/unpublish |
| `directPublishCollection(id, note?)` | POST /{id}/direct-publish |

#### Document actions

| Action | API call | Notes |
|--------|---------|-------|
| `fetchDocuments(collectionId)` | GET /{id}/documents | Sets `documents` |
| `fetchDocumentRaw(slug, filename)` | GET /{id}/documents/{f} | Returns XML string |
| `createDocument(collectionId, filename, meta?)` | POST /{id}/documents | Builds TEI skeleton |
| `uploadDocument(collectionId, file)` | POST /{id}/documents | Multipart |
| `uploadZip(collectionId, file)` | POST /{id}/documents/batch | Returns `ZipUploadResult` |
| `updateDocument(slug, filename, content)` | PUT /{id}/documents/{f} | Raw XML body |
| `deleteDocument(collectionId, filename)` | DELETE /{id}/documents/{f} | |
| `downloadDocument(collectionId, filename)` | GET /{id}/documents/{f} | Triggers browser download |
| `searchDocuments(collectionId, q, maxResults?)` | GET /{id}/search | |

#### Bibliography actions

| Action | API call |
|--------|---------|
| `listBibliographies(collectionId)` | GET /{id}/bibliographies |
| `saveBibliography(collectionId, content)` | POST /{id}/bibliographies |
| `deleteBibliography(collectionId, version)` | DELETE /{id}/bibliographies/{v} |
| `setBibliographyPublic(collectionId, version, isPublic)` | PATCH /{id}/bibliographies/{v} |
| `extractBibl(collectionId)` | GET /{id}/extract-bibl | Returns raw XML string |
| `fetchPublicBibliography(slug)` | GET /{id}/public-bibliography | No auth |

#### TEI skeleton helper (`_buildSkeleton`)

Private helper called by `createDocument`. Generates a complete TEI XML
skeleton from the collection's current metadata:

- `<teiHeader>` with filled `<titleStmt>`, `<publicationStmt>`, `<respStmt>`
  for each responsibility statement, `<listBibl>` with main source, `<msDesc>`
  with identifier and object description, license info, identifier URL
- `<body>` section using the body template snippet (or a default empty `<div>`)
- All user-supplied strings are HTML-entity escaped
- TEI namespace `http://www.tei-c.org/ns/1.0` is declared on the root element

### `useCollectionValidationStore` (`frontend/src/stores/collection_validation.ts`)

```typescript
currentRun: CollectionValidationRun | null
isStarting: boolean
isFetching: boolean
```

Actions: `startRun(slug)`, `fetchLatestRun(slug)`, `fetchRun(slug, runId)`,
`cancelRun(slug, runId)`, `reset()`.

---

## 21. File map

| Path | Role |
|------|------|
| `backend/app/plugins/_native/collections/router.py` | All collection & document endpoints |
| `backend/app/services/xmldb.py` | High-level service layer (business logic + eXist-db ops) |
| `backend/app/models/collection.py` | `Collection`, `CollectionPermission` ORM models |
| `backend/app/models/tei_schema.py` | `TeiSchema` ORM model |
| `backend/app/models/collection_bibliography.py` | `CollectionBibliography` ORM model |
| `backend/app/schemas/collections.py` | Pydantic v2 request/response schemas |
| `backend/app/xqueries/collections/list.xq` | List filenames in collection |
| `backend/app/xqueries/collections/list_with_titles.xq` | Filenames + TEI title/author |
| `backend/app/xqueries/collections/stats.xq` | Document count + total size |
| `backend/app/xqueries/collections/extract_bibl.xq` | Bibliography extraction |
| `backend/app/xqueries/collections/distinct_tags.xq` | Tag/attribute map for indices |
| `backend/app/xqueries/collections/index_occurrences.xq` | Index value harvesting |
| `backend/app/xqueries/documents/get_metadata.xq` | XML document metadata |
| `frontend/src/views/CollectionDetailView.vue` | Collection detail & management page |
| `frontend/src/views/DocumentEditView.vue` | TEI editor |
| `frontend/src/views/CollectionsView.vue` | Collections list |
| `frontend/src/views/CollectionReadView.vue` | Read-only collection view (for Editor role) |
| `frontend/src/stores/collections.ts` | All collection & document state and API calls |
| `frontend/src/stores/collection_validation.ts` | Async validation run state |
| `frontend/src/composables/useCodeMirror.ts` | CodeMirror 5 integration composable |
| `frontend/src/composables/useViafAutocomplete.ts` | VIAF author autocomplete |
| `frontend/src/composables/useGeonamesAutocomplete.ts` | Geonames place autocomplete |
| `frontend/src/utils/teiSchema.ts` | CM5 schema loader (`loadTeiSchema`) |
| `frontend/src/components/ui/NoteModal.vue` | Note insert/edit dialog |
| `frontend/src/components/ui/MediaPanel.vue` | Facsimile surface list |
| `frontend/src/components/ui/ZoneEditor.vue` | Zone drawing on facsimile |
| `frontend/src/components/AiPanel.vue` | Streaming AI panel (shared) |
