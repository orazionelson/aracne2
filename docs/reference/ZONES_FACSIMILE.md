# Zones & Facsimile — Text-Image Alignment

## Overview

Aracne2 supports **text-image alignment** at word and line level through a TEI `<facsimile>`
block and a set of zone editor endpoints. An Editor draws rectangular zones on a document
image and links them to transcription units (`<lb>`, `<w>`, arbitrary `<seg>`) via the
standard TEI `facs="#zone-id"` attribute.

The feature enables downstream uses such as:

- IIIF manifest generation (each zone maps to a canvas region)
- HTR pipeline output import (ALTO / PAGE XML → zone coordinates)
- EVT viewer alignment (EVT can read `<facsimile>` + `facs` references natively)

---

## TEI model

A TEI document with zones contains a `<facsimile>` element at root level with one or more
`<surface>` children, each `<surface>` carrying `<zone>` elements:

```xml
<TEI>
  <facsimile>
    <surface xml:id="surface-1" facs="media/page1.jpg">
      <zone xml:id="z-line-1" ulx="45" uly="120" lrx="890" lry="155"/>
      <zone xml:id="z-line-2" ulx="45" uly="160" lrx="890" lry="195"/>
    </surface>
  </facsimile>
  <text>
    <body>
      <div>
        <lb facs="#z-line-1"/>First line of text.
        <lb facs="#z-line-2"/>Second line of text.
      </div>
    </body>
  </text>
</TEI>
```

**Coordinate system**: pixel values relative to the full-resolution source image.
`ulx`/`uly` = upper-left corner, `lrx`/`lry` = lower-right corner.

---

## Backend

### Files

| Path | Role |
|---|---|
| `backend/app/routers/zones.py` | FastAPI router — zone CRUD |
| `backend/app/schemas/facsimile.py` | Pydantic v2 schemas (`ZoneIn`, `ZoneOut`, `ZoneUpdateRequest`, `SurfaceZonesResponse`) |
| `backend/app/services/xmldb.py` | `get_surface_zones()`, `update_surface_zones()` — XQuery I/O |
| `backend/app/xqueries/zones/` | XQuery files used by the service |

### Endpoints

All endpoints require `[E+]` (Editor, Designer, EditorInChief, Admin).
The `{slug}` is the collection slug; `{filename}` is the document filename (with `.xml`);
`{surface_id}` is the `xml:id` value of the `<surface>` element (without `#`).

---

#### `GET /api/v1/collections/{slug}/documents/{filename}/facsimile/{surface_id}/zones`

Returns all `<zone>` elements for a surface.

**Response `200`**:
```jsonc
{
  "data": {
    "surface_id": "surface-1",
    "zones": [
      { "xml_id": "z-line-1", "ulx": 45, "uly": 120, "lrx": 890, "lry": 155 },
      { "xml_id": "z-line-2", "ulx": 45, "uly": 160, "lrx": 890, "lry": 195 }
    ]
  }
}
```

Returns `"zones": []` when the document has no `<facsimile>` block — not an error.

---

#### `PUT /api/v1/collections/{slug}/documents/{filename}/facsimile/{surface_id}/zones`

**Atomically replaces** all zones for a surface. Sending an empty list removes all zones.

**Request body**:
```jsonc
{
  "zones": [
    { "xml_id": "z-line-1", "ulx": 45, "uly": 120, "lrx": 890, "lry": 155 }
  ]
}
```

**Validation rules** (enforced by `ZoneIn`):
- `xml_id` must not start with `#` (the `facs` prefix is handled by the backend)
- `lrx > ulx` and `lry > uly` (non-zero area)
- All coordinates `≥ 0`

**Response `200`**: same shape as GET.

---

#### `POST /api/v1/collections/{slug}/documents/{filename}/facsimile/{surface_id}/zones/import`

Reserved for HTR pipeline output. **v1 semantics are identical to PUT** — full replacement.
The separate path exists so future versions can accept ALTO or PAGE XML payloads without
breaking the manual editor path.

**Response `201`**: same shape as GET.

---

### Schemas

```python
# backend/app/schemas/facsimile.py

class ZoneIn(BaseModel):
    xml_id: str          # TEI xml:id without '#' prefix
    ulx: int             # upper-left x  (≥ 0)
    uly: int             # upper-left y  (≥ 0)
    lrx: int             # lower-right x (> ulx)
    lry: int             # lower-right y (> uly)

class ZoneOut(BaseModel):
    xml_id: str
    ulx: int
    uly: int
    lrx: int
    lry: int

class ZoneUpdateRequest(BaseModel):
    zones: list[ZoneIn]  # full replacement — empty list clears all zones

class SurfaceZonesResponse(BaseModel):
    surface_id: str
    zones: list[ZoneOut]
```

---

## Frontend

### Files

| Path | Role |
|---|---|
| `frontend/src/stores/zonesStore.ts` | Pinia store — zone state, API calls |
| `frontend/src/components/editor/ZoneEditor.vue` | Canvas overlay for drawing/editing zones |
| `frontend/src/components/editor/FacsimilePanel.vue` | Right-side panel showing the document image with overlaid zones |

### Store (`zonesStore`)

The store manages zone state for the currently open document surface:

```typescript
// Key state
const zones = ref<Zone[]>([])          // current surface zones
const surfaceId = ref<string | null>(null)
const loading = ref(false)

// Key actions
async function loadZones(slug, filename, surfaceId)   // GET zones
async function saveZones(slug, filename, surfaceId)   // PUT zones
async function importZones(slug, filename, surfaceId) // POST import
```

### Zone editor workflow

1. Editor opens a document in the TEI editor
2. The **Facsimile panel** (right side) renders the surface image from `media/`
3. The **Zone Editor** overlays existing zones as coloured rectangles
4. Editor draws a new zone → rectangle coordinates are added to local state
5. Editor clicks **Save** → `saveZones()` fires `PUT /zones`, backend writes `<zone>` elements to the XML in eXist-db
6. The `facs="#zone-id"` attribute on transcription units is set manually in the XML editor or via a forthcoming inline annotation tool

### HTR import workflow

> **Status — partial.** Today only the HTTP entry point exists. The
> end-to-end "thousand-page corpus → HTR engine → editor reviews
> machine output" workflow described in
> [TO_DO.md](../TO_DO.md) is the upgrade target.

For automated pipelines (e.g. Transkribus, Kraken, eScriptorium):

1. Pipeline produces pixel-level zone coordinates per surface.
2. Client `POST /zones/import` with the zone list — semantics
   identical to PUT in v1, accepts the same JSON shape as the
   manual editor's save.
3. **Not yet implemented**: ALTO / PAGE XML parsing on the import
   endpoint, batch image upload, machine-output review queue,
   confidence-score visualisation, word/line-level alignment.
   See [TO_DO.md](../TO_DO.md) for the design.

---

## Security

| Concern | Mitigation |
|---|---|
| ACL | All zone endpoints require `[E+]` — unauthenticated access is blocked |
| Collection-level access | `get_surface_zones` / `update_surface_zones` check the Editor's collection permissions before reading/writing eXist-db |
| Coordinate bounds | `ZoneIn` validates `ge=0` and `lrx > ulx`, `lry > uly` — malformed rectangles are rejected at the schema layer |
| XML injection | `xml_id` must not start with `#`; the backend sanitises the value before writing it as an XML attribute |
