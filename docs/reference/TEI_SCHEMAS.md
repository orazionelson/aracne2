# TEI Schema Management

## Overview

Aracne2 supports attaching a **TEI validation schema** (RNG, DTD, or XSD) to a collection.
When a schema is assigned, editors can validate individual documents or trigger a
collection-wide validation run from the admin UI.

Each schema entry consists of:

1. **Validation schema** (RNG / DTD / XSD) — used by `lxml` to validate TEI XML
2. **CM5 autocomplete schema** (optional) — a custom XML format consumed by the
   CodeMirror 5 `xml-hint` addon to provide element/attribute autocomplete in the editor

Schemas are stored in the filesystem under `SCHEMAS_DIR` (default: `/app/schemas`)
and their metadata is tracked in PostgreSQL.

A bundled **TEI All (P5 v4.11.0)** schema is seeded automatically on first startup.

---

## Data model

```
tei_schemas
─────────────────────────────
id                  UUID    PK
name                VARCHAR(256)
validation_filename VARCHAR(512) | NULL   — original filename (e.g. "tei_all.rng")
validation_format   ENUM(rng, dtd, xsd) | NULL
cm5_filename        VARCHAR(512) | NULL   — "cm5.xml" or "generated-cm5.xml"
created_by          UUID | NULL   FK → users.id ON DELETE SET NULL
created_at          TIMESTAMPTZ
```

**File**: `backend/app/models/tei_schema.py`

### File layout on disk

```
SCHEMAS_DIR/
└── {schema_uuid}/
    ├── validation.rng   (or .dtd / .xsd)
    └── cm5.xml          (optional — uploaded or auto-generated)
```

---

## Supported formats

| Format | Extension | lxml engine |
|---|---|---|
| RelaxNG | `.rng` | `etree.RelaxNG` |
| DTD | `.dtd` | `etree.DTD` |
| XML Schema | `.xsd` | `etree.XMLSchema` |

**RNG is recommended** — it is the format used by the official TEI P5 schema (`tei_all.rng`)
and provides the most precise validation for TEI documents.

---

## Bundled schema

**TEI All (P5 v4.11.0)** is shipped with the application at:

```
backend/app/tei_schemas/tei_all.rng
```

On first startup (via `make seed`), the seed script:
1. Creates a `tei_schemas` DB row named `"TEI All (P5 v4.11.0)"`
2. Copies the bundled `.rng` file to `SCHEMAS_DIR/{uuid}/validation.rng`

The bundled schema is idempotent — it is skipped if a row with the same name already
exists in the database.

---

## Backend

### Files

| Path | Role |
|---|---|
| `backend/app/models/tei_schema.py` | SQLAlchemy ORM model + `SchemaFormat` enum |
| `backend/app/schemas/tei_schemas.py` | Pydantic schemas |
| `backend/app/routers/schemas.py` | FastAPI router |
| `backend/app/services/schemas.py` | Validation, CM5 generation, file management |
| `backend/app/tei_schemas/tei_all.rng` | Bundled TEI All schema |
| `backend/app/db/seed.py` | `seed_tei_schemas()` — seeds bundled schemas |

### CM5 schema generation

`POST /{schema_id}/generate-cm5` parses the stored validation schema and extracts
the element/attribute structure:

- **RNG**: recursively resolves `<ref>` → `<define>` chains, stopping at `<element>`
  boundaries, collecting child elements and attributes
- **XSD**: follows `<xs:group ref>` and `<xs:attributeGroup ref>` chains
- **DTD**: uses lxml's built-in DTD parser (`ElementContent` tree)

The extracted map is serialised as `<cm_tei_schema>` XML and stored as `generated-cm5.xml`.
This file is served directly to the editor via `GET /{schema_id}/cm5-file`.

For the full `tei_all.rng` schema, CM5 generation extracts ~500 elements and their
attributes — the process takes a few seconds and runs synchronously.

---

### Endpoints

#### `GET /api/v1/schemas` [auth]

List all registered schemas (any authenticated user).

**Response `200`**:
```jsonc
{
  "data": [
    {
      "id": "3fa85f64-...",
      "name": "TEI All (P5 v4.11.0)",
      "validation_filename": "tei_all.rng",
      "validation_format": "rng",
      "cm5_filename": null,
      "created_by": null,
      "created_at": "2026-01-01T00:00:00Z"
    }
  ]
}
```

---

#### `POST /api/v1/schemas` [EiC+]

Create an empty schema entry (no files yet).

**Request body**: `{ "name": "My custom schema" }`

**Response `201`**: schema object with `validation_filename: null`.

---

#### `DELETE /api/v1/schemas/{schema_id}` [EiC+]

Delete schema metadata and remove all files from disk.

**Response `204`**: no body.

---

#### `POST /api/v1/schemas/{schema_id}/upload-validation` [EiC+]

Upload a validation schema file (multipart form). Format is auto-detected from
the file extension (`.rng`, `.dtd`, `.xsd`).

**Form field**: `file` — the schema file.

**Response `200`**: updated schema object with `validation_filename` and `validation_format` set.

---

#### `POST /api/v1/schemas/{schema_id}/import-validation` [EiC+]

Import a validation schema from a public URL (SSRF-guarded, max 10 MB).

**Request body**: `{ "url": "https://tei-c.org/release/xml/tei/custom/schema/relaxng/tei_all.rng" }`

**Response `200`**: updated schema object.

SSRF guard: private IP ranges, loopback, and link-local addresses are rejected.

---

#### `POST /api/v1/schemas/{schema_id}/upload-cm5` [EiC+]

Upload a pre-built CM5 autocomplete schema file (XML).

**Form field**: `file`.

---

#### `POST /api/v1/schemas/{schema_id}/import-cm5` [EiC+]

Import a CM5 schema from a public URL.

**Request body**: `{ "url": "https://..." }`

---

#### `POST /api/v1/schemas/{schema_id}/generate-cm5` [EiC+]

Auto-generate a CM5 schema from the stored validation schema. Requires a validation
file to be already uploaded. Writes `generated-cm5.xml` and sets `cm5_filename`.

**Response `200`**: updated schema object.

---

#### `GET /api/v1/schemas/{schema_id}/cm5-file` [auth]

Serve the raw CM5 schema XML to the document editor. Called by the editor on document
open when the collection has a schema with a CM5 file attached.

**Response `200`**: `application/xml` body.

---

## Frontend

### Files

| Path | Role |
|---|---|
| `frontend/src/stores/schemas.ts` | Pinia store — schema catalog and file operations |
| `frontend/src/views/admin/SettingsView.vue` | Settings → "Schemi TEI" tab |
| `frontend/src/components/editor/TeiEditor.vue` | Loads CM5 schema on document open |

### Store (`useSchemasStore`)

```typescript
const schemas = ref<TeiSchemaResponse[]>([])

async function fetchSchemas()
async function createSchema(name: string)
async function deleteSchema(id: string)
async function uploadValidation(id: string, file: File)
async function importValidation(id: string, url: string)
async function uploadCm5(id: string, file: File)
async function importCm5(id: string, url: string)
async function generateCm5(id: string)
```

### Settings UI

The **Settings → Schemi TEI** tab (EiC+) shows:
- Schema list with `validation_format` badge and CM5 status indicator
- Create schema (name only — files are uploaded separately)
- Upload/import validation file dialog
- Upload/import CM5 file dialog
- "Generate CM5" button (available when a validation file is present)
- Delete button (with confirmation)

### Editor integration

When an Editor opens a document from a collection that has an assigned schema with a
CM5 file, the editor:

1. Calls `GET /schemas/{id}/cm5-file`
2. Parses the `<cm_tei_schema>` XML to extract the element/attribute map
3. Registers the map with CodeMirror 5's `xml-hint` addon
4. Autocomplete suggestions are filtered in real time as the editor types

---

## Validation workflow

See `COLLECTIONS.md` for the collection-wide validation UI.

Single-document validation flow:
1. Editor saves a document
2. Frontend calls `POST /collections/{slug}/documents/{filename}/validate`
   with `{ "schema_id": "..." }` (or omits it to use the collection default)
3. Backend reads the document from eXist-db, runs `validate_xml()` from `services/schemas.py`
4. Returns `{ "valid": true, "errors": [] }` or a list of `ValidationError` objects
   with line, column, message, and a resolved element path

---

## Security

| Concern | Mitigation |
|---|---|
| SSRF on URL import | `check_ssrf()` blocks private IPs, loopback, link-local |
| File size | Import capped at 10 MB (`_MAX_IMPORT_BYTES`) |
| XML parsing | Validation and CM5 generation use `lxml` with `resolve_entities=False`, `no_network=True` — no XXE |
| Document validation | User-supplied XML parsed with `_safe_xml_parser` (external entities and network disabled) |
| Access control | Write endpoints require EiC+; CM5 serve requires auth only |
