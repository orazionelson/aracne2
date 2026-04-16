# Named Entity Index

## Overview

The Named Entity Index plugin automatically extracts named entities from TEI XML
documents (persons, places, organisations, or any configurable TEI element) and
stores them in a PostgreSQL index. The index powers:

- **Public entity browser** — visitors can search entities across all public collections
- **Admin entity management** — Admins can normalise canonical forms, link to authority files, merge duplicates, and trigger re-indexing
- **Authority linking** — entities can be linked to VIAF, GeoNames, or any URI-based authority vocabulary

Indexing is triggered automatically when a document is uploaded or saved, and can be
triggered manually via a per-collection reindex endpoint.

---

## Data model

```
named_entities
─────────────────────────────
id                UUID    PK
type              VARCHAR(128)    — TEI local tag name (e.g. "persName")
canonical_form    VARCHAR(1024)   — normalised display form
authority_ref     TEXT | NULL     — external authority URI (VIAF, GeoNames, …)
occurrence_count  INTEGER         — denormalised counter (updated on index/merge)
created_at        TIMESTAMPTZ
updated_at        TIMESTAMPTZ

entity_occurrences
─────────────────────────────
id               UUID    PK
entity_id        UUID    FK → named_entities.id ON DELETE CASCADE
collection_id    UUID    FK → collections.id ON DELETE CASCADE
filename         VARCHAR(512)    — document filename within the collection
raw_form         TEXT            — exact text as it appeared in the source XML
context          TEXT | NULL     — surrounding text snippet (for display)
```

**Files**:
- `backend/app/plugins/_native/named_entities/models.py`

---

## Indexing configuration

The set of TEI tag names to index is stored in system settings as a JSON array:

```
entity_index_tags = '["persName","placeName","orgName"]'   (default)
```

**Configuration API**: `GET` / `PUT /api/v1/entities/admin/tag-config` [EiC+]

Any TEI local element name is valid. The tag name is used directly as the entity `type`
in the database. Examples: `persName`, `placeName`, `orgName`, `objectName`, `geogName`.

After changing the tag configuration, existing index data is **not** automatically
refreshed — trigger a per-collection reindex to apply the new configuration.

**Limits** (enforced by `EntityTagConfig`): max 50 tags; each tag name ≤ 64 characters.

---

## Extraction mechanism

When a document is saved or uploaded, an XQuery script extracts all elements whose
local name matches the configured tag list:

```
backend/app/xqueries/named_entities/extract_document.xq
```

The XQuery receives the tag list as a typed external variable (`$tags`), iterates
over matching elements, and returns a sequence of `(type, raw_form, context)` tuples.
The backend service upserts these into `named_entities` (case-insensitive deduplication
via `func.lower(canonical_form)`) and creates `entity_occurrences` rows.

**XQuery injection note**: the tag list is bound as a typed XQuery external variable,
not interpolated into source — no injection vector exists.

---

## Backend

### Files

| Path | Role |
|---|---|
| `backend/app/plugins/_native/named_entities/models.py` | ORM models |
| `backend/app/plugins/_native/named_entities/schemas.py` | Pydantic schemas |
| `backend/app/plugins/_native/named_entities/router.py` | FastAPI router |
| `backend/app/plugins/_native/named_entities/service.py` | Index logic (upsert, merge, reindex) |
| `backend/app/plugins/_native/named_entities/plugin.py` | Hook listener (auto-index on save/upload) |
| `backend/app/xqueries/named_entities/extract_document.xq` | XQuery extraction script |

### Endpoints

#### Public endpoints [pub] — no authentication required

---

##### `GET /api/v1/entities`

Paginated entity list from published public collections.

**Rate limit**: 60 req/min.

**Query parameters**:

| Parameter | Type | Default | Description |
|---|---|---|---|
| `type` | string | — | Filter by entity type (e.g. `persName`) |
| `q` | string (max 200) | — | Case-insensitive prefix / substring search on `canonical_form` |
| `collection_slug` | string | — | Restrict to one collection |
| `page` | int (≥ 1) | 1 | |
| `per_page` | int (1–100) | 30 | |

**Response `200`**:
```jsonc
{
  "data": [
    {
      "id": "3fa85f64-...",
      "type": "persName",
      "canonical_form": "Alessandro Manzoni",
      "authority_ref": "https://viaf.org/viaf/64013650/",
      "occurrence_count": 47,
      "created_at": "2026-01-10T00:00:00Z",
      "updated_at": "2026-04-01T00:00:00Z"
    }
  ],
  "pagination": { "page": 1, "per_page": 30, "total": 1, "total_pages": 1 }
}
```

---

##### `GET /api/v1/entities/{entity_id}/occurrences`

Paginated occurrences of one entity in published public collections.

**Query parameters**:

| Parameter | Type | Default | Description |
|---|---|---|---|
| `collection` | string | — | Filter by collection slug |
| `page` | int (≥ 1) | 1 | |
| `per_page` | int (1–100) | 20 | |

**Response `200`**:
```jsonc
{
  "data": [
    {
      "id": "...",
      "entity_id": "3fa85f64-...",
      "collection_id": "...",
      "collection_slug": "epistolario-manzoni",
      "collection_title": "Epistolario Manzoni",
      "filename": "lettera-001.xml",
      "raw_form": "Manzoni",
      "context": "…lettera indirizzata a <persName>Manzoni</persName> nel 1821…"
    }
  ],
  "pagination": { ... }
}
```

---

#### Admin endpoints [A] — Admin only

---

##### `GET /api/v1/entities/admin`

Admin entity list across **all** collections (published and unpublished).

Additional query parameter: `unlinked=true` — return only entities without an `authority_ref`.

---

##### `PUT /api/v1/entities/admin/{entity_id}`

Update `canonical_form` and/or `authority_ref` of an entity.

**Request body**:
```jsonc
{
  "canonical_form": "Manzoni, Alessandro",
  "authority_ref": "https://viaf.org/viaf/64013650/"
}
```

Both fields are optional. `canonical_form` cannot be set to blank.

---

##### `DELETE /api/v1/entities/admin/{entity_id}`

Permanently delete an entity and all its occurrences.

---

##### `POST /api/v1/entities/admin/merge`

Merge `source_id` into `target_id`. All occurrences are reassigned to the target;
the source entity is deleted. Useful for deduplicating the index after a name
appears in multiple forms across documents.

**Request body**:
```jsonc
{
  "source_id": "uuid-of-duplicate",
  "target_id": "uuid-of-canonical"
}
```

**Response `200`**: the target entity (with updated `occurrence_count`).

---

##### `POST /api/v1/entities/admin/reindex/{collection_slug}`

Wipe and rebuild the entire entity index for a collection. Reads every document
in the collection from eXist-db, extracts entities according to the current tag
configuration, and repopulates `named_entities` / `entity_occurrences`.

**Response `200`**:
```jsonc
{
  "data": {
    "collection_slug": "epistolario-manzoni",
    "occurrences_indexed": 1283
  }
}
```

---

#### EiC+ endpoints — tag configuration

##### `GET /api/v1/entities/admin/tag-config`

Return the current list of TEI tag names to index.

**Response `200`**: `{ "data": ["persName", "placeName", "orgName"] }`

---

##### `PUT /api/v1/entities/admin/tag-config`

Replace the tag list.

**Request body**: `{ "tags": ["persName", "placeName", "orgName", "objectName"] }`

---

## Authority integrations

Aracne2 provides two proxy endpoints for authority lookup during entity editing:

### GeoNames (`routers/geonames.py`)

```
GET /api/v1/geonames/search?q={query}&maxRows={n}&lang={lang}
```

Proxies to `api.geonames.org/searchJSON`. Requires a GeoNames username configured
in system settings. Rate-limited. Returns place suggestions for `placeName` entities.

### VIAF (`routers/viaf.py`)

```
GET /api/v1/viaf/suggest?q={query}
```

Proxies to `viaf.org/viaf/AutoSuggest`. No API key required. Returns person/corporate
body suggestions for `persName` / `orgName` entities.

Both proxies are authenticated (`[auth]`), rate-limited, and strip unnecessary fields
from the upstream response.

---

## Frontend

### Files

| Path | Role |
|---|---|
| `frontend/src/views/admin/NamedEntitiesView.vue` | Admin entity management page |
| `frontend/src/views/PublicEntitiesView.vue` | Public entity browser |

### Admin entity management

The admin page provides:
- Searchable, filterable entity list (all collections, all states)
- Per-entity editing: canonical form input + authority URI input with VIAF/GeoNames autocomplete
- Merge dialog: select source and target entity with preview of occurrence counts
- Delete with confirmation
- Per-collection "Reindex" trigger
- Tag configuration editor (EiC+ tab)

### Public entity browser

The public view (`/entities`) provides:
- Entity type tabs (persName / placeName / orgName / …)
- Full-text search input
- Collection filter
- Entity card with `canonical_form`, `authority_ref` link, occurrence count
- Occurrence list on entity click (expandable panel)

---

## Security

| Concern | Mitigation |
|---|---|
| Public ACL | `get_public_entities()` always filters `Collection.status == published` AND `Collection.is_public == true` |
| Occurrence ACL | `get_entity_occurrences(public_only=True)` applies the same filter |
| Rate limiting | Public entity list: 60 req/min; occurrence list: global 200 req/min |
| Input bounds | `q` max 200 chars; `per_page` max 100; tag config max 50 tags × 64 chars each |
| XQuery injection | Tag list bound as typed external variable — no injection vector |
| Authority ref validation | `_clean_authority_ref()` rejects internal `#`-prefixed refs; accepts only strings with `:` |
