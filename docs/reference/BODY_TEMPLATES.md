# Body Templates

## Overview

**Body templates** are XML snippet presets used to scaffold the `<body>` section of a
new TEI document. When an Editor creates a new document in a collection, they can choose
a template from a dropdown — the template's snippet is injected as the initial content
of the `<text><body>` element, giving the editor a pre-structured starting point.

Templates are platform-managed (Admin CRUD) and available to all authenticated users.
Two native templates are seeded automatically on first startup.

---

## Data model

```
body_templates
─────────────────────────────
id          UUID    PK
label       VARCHAR(128)    — unique, human-readable name shown in the dropdown
snippet     TEXT            — XML fragment injected into <text><body>
is_native   BOOLEAN         — true for templates shipped with the platform
created_at  TIMESTAMPTZ
```

**File**: `backend/app/models/body_template.py`

The `label` column has a unique constraint — duplicate names are rejected at the DB level.

---

## Native templates

Two templates are seeded by `seed_body_templates()` in `backend/app/db/seed.py`:

### `generic`

A minimal document structure suitable for any document type:

```xml
<docDate>
  <date>YYYY-MM-DD</date>
</docDate>
<div type="protocollo"/>
<div type="testo"/>
<div type="escatocollo"/>
```

### `epistola`

A full epistolary structure following the classical letter format:

```xml
<docDate>
  <date/>
</docDate>
<div type="inscriptio"/>
<div type="rubrica"/>
<div type="salutatio"/>
<div type="exordium"/>
<div type="narratio"/>
<div type="petitio"/>
<div type="conclusio"/>
```

Native templates (`is_native = true`) are seeded idempotently — they are created on
first run and skipped on subsequent seed calls. They can be edited via PATCH but not
re-seeded over (the seed checks by `label` and skips if the row already exists).

---

## Backend

### Files

| Path | Role |
|---|---|
| `backend/app/models/body_template.py` | SQLAlchemy ORM model |
| `backend/app/schemas/body_templates.py` | Pydantic schemas |
| `backend/app/routers/body_templates.py` | FastAPI router |
| `backend/app/services/body_templates.py` | Business logic (CRUD) |
| `backend/app/db/seed.py` | `seed_body_templates()` — seeds native templates |

### Endpoints

#### `GET /api/v1/body-templates` [auth]

List all available body templates. Available to every authenticated user (including
plain User role) so the editor dropdown can load them.

**Response `200`**:
```jsonc
{
  "data": [
    {
      "id": "3fa85f64-...",
      "label": "generic",
      "snippet": "<docDate>\n  <date>YYYY-MM-DD</date>\n</docDate>\n...",
      "is_native": true,
      "created_at": "2026-01-01T00:00:00Z"
    },
    {
      "id": "4ab12cd3-...",
      "label": "epistola",
      "snippet": "<docDate>\n  <date/>\n</docDate>\n...",
      "is_native": true,
      "created_at": "2026-01-01T00:00:00Z"
    }
  ]
}
```

---

#### `POST /api/v1/body-templates` [A]

Create a custom body template. Admin only.

**Request body**:
```jsonc
{
  "label": "Atto notarile",
  "snippet": "<div type=\"protocollo\"/>\n<div type=\"dispositivo\"/>\n<div type=\"escatocollo\"/>"
}
```

**Validation**: `label` and `snippet` must not be blank.
`label` must be unique (DB constraint — returns `409` on duplicate).

**Response `201`**: created template object.

---

#### `PATCH /api/v1/body-templates/{template_id}` [A]

Partial update. Admin only. Either `label` or `snippet` (or both) can be supplied.

**Response `200`**: updated template object.

---

#### `DELETE /api/v1/body-templates/{template_id}` [A]

Delete a body template. Admin only. Native templates (`is_native = true`) can be
deleted via this endpoint — there is no special protection at the API level.

**Response `204`**: no body.

---

### Pydantic schemas

```python
# backend/app/schemas/body_templates.py

class BodyTemplateCreate(BaseModel):
    label: str    # unique, non-blank
    snippet: str  # non-blank XML fragment

class BodyTemplatePatch(BaseModel):
    label: str | None = None
    snippet: str | None = None

class BodyTemplateResponse(BaseModel):
    id: uuid.UUID
    label: str
    snippet: str
    is_native: bool
    created_at: datetime
```

---

## Frontend

### Files

| Path | Role |
|---|---|
| `frontend/src/stores/body_templates.ts` | Pinia store — template list |
| `frontend/src/views/admin/SettingsView.vue` | Settings → "Template" tab (Admin) |
| `frontend/src/components/editor/NewDocumentDialog.vue` | Template selector in new-document dialog |

### Store (`useBodyTemplatesStore`)

```typescript
const templates = ref<BodyTemplateResponse[]>([])

async function fetchTemplates()
async function createTemplate(payload: { label: string; snippet: string })
async function patchTemplate(id: string, payload: { label?: string; snippet?: string })
async function deleteTemplate(id: string)
```

### New document dialog

When an Editor opens the **"New document"** dialog on a collection:

1. The store loads all templates via `GET /body-templates`
2. A dropdown shows the `label` of each template plus a "Blank document" option
3. On create, the selected `snippet` is sent as the initial body content
4. The new document opens in the TEI editor with the snippet pre-populated inside `<text><body>`

### Settings UI

The **Settings → Template** tab (Admin) shows:
- List of all templates with `is_native` badge
- Create form (label + XML textarea)
- Edit dialog (PATCH)
- Delete button (with confirmation)

---

## Adding a new native template

To add a new template shipped with the platform:

1. Add an entry to `DEFAULT_BODY_TEMPLATES` in `backend/app/db/seed.py`:
   ```python
   DEFAULT_BODY_TEMPLATES: list[tuple[str, str]] = [
       ("generic", "..."),
       ("epistola", "..."),
       ("atto_notarile", "<div type=\"protocollo\"/>..."),  # new
   ]
   ```
2. Run `make seed` — idempotent, only inserts if the label doesn't already exist.

The `is_native` flag is set to `True` for all entries created by `seed_body_templates()`.
