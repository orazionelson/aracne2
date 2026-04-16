# XSLT Templates

## Overview

Aracne2 maintains a **XSLT stylesheet catalog** — a database-backed library of XSLT 1.0
(lxml) or XSLT 2.0 (Saxon) stylesheets used to transform TEI XML documents into HTML
for website pages and public document views.

The catalog is managed by users with the **Designer** role (or EditorInChief/Admin).
Websites reference a stylesheet from the catalog to control how their documents are
rendered. A built-in default stylesheet (`tei_generic.xsl`) is always available for
download as a starting point.

---

## Data model

```
xslt_templates
─────────────────────────────
id            UUID    PK
name          VARCHAR(256)     — human-readable label
description   TEXT | NULL
content       TEXT             — full XSLT source
processor     VARCHAR(32)      — "lxml" | "saxon"
tags          JSON             — list[str] for filtering
created_by    UUID | NULL      FK → users.id ON DELETE SET NULL
created_at    TIMESTAMPTZ
updated_at    TIMESTAMPTZ
```

**File**: `backend/app/models/xslt_template.py`

---

## Processors

| Value | Engine | XSLT version |
|---|---|---|
| `lxml` | Python `lxml` (libxslt) | XSLT 1.0 |
| `saxon` | Saxon-HE (via subprocess or py4j) | XSLT 2.0 / 3.0 |

`lxml` is the default and requires no additional setup.
`saxon` requires Saxon-HE to be present in the container path.

---

## Built-in default stylesheet

A generic TEI→HTML stylesheet is bundled with the application at:

```
backend/app/xslt/tei_generic.xsl
```

It is **not** stored in the database — it is served directly from the filesystem.
Designers can download it as a starting point and upload a customised version to the catalog.

---

## Backend

### Files

| Path | Role |
|---|---|
| `backend/app/models/xslt_template.py` | SQLAlchemy ORM model |
| `backend/app/schemas/xslt_templates.py` | Pydantic schemas |
| `backend/app/routers/xslt_templates.py` | FastAPI router |
| `backend/app/services/xslt_templates.py` | Business logic (CRUD) |
| `backend/app/xslt/tei_generic.xsl` | Bundled default stylesheet |

### Access control

All endpoints require `[D+]` — Designer, EditorInChief, or Admin.
The list endpoint is also used internally by the Websites admin tab, which
loads the catalog to let an EiC choose which stylesheet a website uses.

The `[D+]` guard is implemented as a custom dependency in `routers/xslt_templates.py`:

```python
async def _designer_plus(user: User, request: Request) -> User:
    role: str = getattr(request.state, "role", "User")
    if role != "Designer" and ROLE_LEVEL.get(role, 0) < 3:
        raise AuthorizationError()
    return user
```

---

### Endpoints

#### `GET /api/v1/xslt-templates`

List all stylesheets in the catalog (summary — no content body).

**Response `200`**:
```jsonc
{
  "data": [
    {
      "id": "3fa85f64-...",
      "name": "Epistolario layout",
      "description": "Two-column layout with diplomatic transcription",
      "processor": "lxml",
      "tags": ["letters", "diplomatic"],
      "created_at": "2026-03-01T00:00:00Z",
      "updated_at": "2026-04-10T00:00:00Z"
    }
  ]
}
```

The `content` field is omitted for bandwidth efficiency. Use the detail endpoint to get the full stylesheet.

---

#### `GET /api/v1/xslt-templates/default/download`

Download the built-in `tei_generic.xsl` as a file attachment.

**Response `200`**: `application/xml` file download.

---

#### `GET /api/v1/xslt-templates/{template_id}`

Return a single stylesheet including the full `content` field.

**Response `200`**:
```jsonc
{
  "data": {
    "id": "3fa85f64-...",
    "name": "Epistolario layout",
    "description": "...",
    "content": "<?xml version=\"1.0\"?><xsl:stylesheet ...>...</xsl:stylesheet>",
    "processor": "lxml",
    "tags": ["letters"],
    "created_by": "a1b2c3d4-...",
    "created_at": "2026-03-01T00:00:00Z",
    "updated_at": "2026-04-10T00:00:00Z"
  }
}
```

---

#### `POST /api/v1/xslt-templates`

Create a new stylesheet entry.

**Request body**:
```jsonc
{
  "name": "Epistolario layout",
  "description": "Two-column layout for letter collections",
  "content": "<?xml version=\"1.0\"?><xsl:stylesheet ...>...</xsl:stylesheet>",
  "processor": "lxml",
  "tags": ["letters", "diplomatic"]
}
```

**Validation**:
- `name` must not be blank (1–256 chars)
- `content` must be valid XML (validated with `defusedxml.ElementTree.fromstring()`)
- `processor` must be `"lxml"` or `"saxon"`

**Response `201`**: full stylesheet object.

---

#### `PATCH /api/v1/xslt-templates/{template_id}`

Partial update. Any combination of `name`, `description`, `content`, `processor`, `tags`
can be supplied. Omitted fields are not changed.

**Response `200`**: updated full stylesheet object.

---

#### `DELETE /api/v1/xslt-templates/{template_id}`

Delete a stylesheet. Any websites that reference this template will need to be reassigned.

**Response `204`**: no body.

---

### Pydantic schemas

```python
# backend/app/schemas/xslt_templates.py

class XsltTemplateCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=256)
    description: str | None = None
    content: str               # validated as well-formed XML
    processor: str = "lxml"   # "lxml" | "saxon"
    tags: list[str] = []

class XsltTemplatePatch(BaseModel):
    name: str | None = None
    description: str | None = None
    content: str | None = None
    processor: str | None = None
    tags: list[str] | None = None

class XsltTemplateResponse(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None
    content: str
    processor: str
    tags: list[str]
    created_by: uuid.UUID | None
    created_at: datetime
    updated_at: datetime

class XsltTemplateSummary(BaseModel):
    """Lightweight listing — omits content."""
    id: uuid.UUID
    name: str
    description: str | None
    processor: str
    tags: list[str]
    created_at: datetime
    updated_at: datetime
```

---

## Frontend

### Files

| Path | Role |
|---|---|
| `frontend/src/stores/xslt_templates.ts` | Pinia store — template catalog |
| `frontend/src/views/admin/SettingsView.vue` | Settings page — "XSLT" tab |
| `frontend/src/components/admin/XsltTemplateEditor.vue` | Code editor for stylesheet content |

### Store (`useXsltTemplatesStore`)

```typescript
const templates = ref<XsltTemplateSummary[]>([])

async function fetchTemplates()
async function fetchTemplate(id: string): Promise<XsltTemplateResponse>
async function createTemplate(payload: XsltTemplateCreate)
async function patchTemplate(id: string, payload: XsltTemplatePatch)
async function deleteTemplate(id: string)
async function downloadDefault()   // triggers file download of tei_generic.xsl
```

### Settings UI

The **Settings → XSLT** tab (accessible to Designer, EiC, Admin) shows:
- Catalog list with processor badge and tags
- "Download default" button for `tei_generic.xsl`
- Create / edit dialog with a CodeMirror XML editor for the stylesheet content
- Delete button (with confirmation)

The **Website → Document tab** uses the same store to populate the stylesheet
selector dropdown when configuring a website page's rendering.

---

## Workflow example

1. Designer downloads `tei_generic.xsl` (default download endpoint)
2. Customises the stylesheet for a specific collection layout
3. Uploads it via **Settings → XSLT → Create** — it appears in the catalog
4. EiC configures a Website and assigns the new stylesheet to the "Document" page
5. The website rendering engine uses the chosen stylesheet for every document page
