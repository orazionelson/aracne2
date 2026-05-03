# EVT Viewer Integration

## Overview

Aracne2 integrates [EVT 2](https://github.com/evt-project/evt-viewer) (Edition
Visualization Technology) as an optional public viewer for published collections.
EVT is an AngularJS-based viewer designed for digital scholarly editions encoded
in TEI XML. When the integration is active, a **Leggi in EVT** button appears on
the collection detail page and opens EVT pre-loaded with the collection's documents.

The integration is implemented as a **native plugin** (`evt`) that exposes two
public backend endpoints, and a **Docker Compose profile** (`evt`) that builds
and runs the EVT static application behind its own nginx container.

---

## Architecture

```
Browser
  │
  └── GET /evt/{slug}/
        │
        └── EVT nginx container (:8181)
              │
              ├── /evt/{slug}/                    → serves EVT index.html
              ├── /evt/{slug}/*.js, *.css         → EVT static assets (7-day cache)
              │
              ├── /evt/{slug}/config/config.json  ─── proxy_pass ──►
              │         backend:8000/api/v1/public/collections/{slug}/evt-config
              │         (Cache-Control: public, max-age=60)
              │
              └── /evt/{slug}/data/{filename}.xml ─── proxy_pass ──►
                        backend:8000/api/v1/public/collections/{slug}/documents/{filename}/raw
                        (Cache-Control: public, max-age=300)
```

EVT's static JS/CSS files are served directly by the EVT nginx container.
Dynamic data (collection config, XML documents) is proxied in real time to
the Aracne2 backend. No Aracne2 data is baked into the EVT container image.

---

## Prerequisites

- The collection must be **published** (`status = published`) and **public** (`is_public = true`)
- The `evt_enabled` system setting must be set to `true` (**Settings → General**)
- The `evt` Docker Compose profile must be built and running (see Setup below)

---

## Setup

### Step 1 — Build the EVT Docker image

This is a one-time operation. The Dockerfile clones EVT 2 from GitHub, compiles
it from source (Node.js 14 + node-sass), and packages the built assets into an
nginx Alpine image.

```bash
docker compose --profile evt build evt
```

Build time: ~3–5 minutes (downloads npm dependencies and compiles native bindings).

### Step 2 — Start the EVT container

```bash
docker compose --profile evt up -d evt
```

The container listens on port **8181** and is accessible at `http://localhost:8181`.

### Step 3 — Enable the setting

In **Settings → General**, set `evt_enabled` to `true`. The **Leggi in EVT** button
appears automatically on any collection that is published and public.

---

## EVT container internals

### Dockerfile (`backend/app/plugins/evt/container/Dockerfile`)

Two-stage build:

| Stage | Base image | What it does |
|---|---|---|
| `builder` | `node:14-alpine` | Clones EVT 2, installs deps, runs `npm run build` |
| final | `nginx:alpine` | Copies `dist/` and the custom `nginx.conf` |

A `sed` command strips the `<base href="...">` from `dist/index.html` before copying —
this is required so that EVT's relative URLs (`config/config.json`, `data/*.xml`)
resolve correctly from `/evt/{slug}/` instead of from the site root.

EVT uses hash-based routing, so removing `<base href>` does not break in-app navigation.

### nginx configuration (`backend/app/plugins/evt/container/nginx.conf`)

```nginx
# EVT config.json — generated dynamically by the Aracne2 backend
location ~ ^/evt/(?<slug>[^/]+)/config/config\.json$ {
    proxy_pass http://backend:8000/api/v1/public/collections/$slug/evt-config;
}

# XML data files — proxied from the Aracne2 public API
location ~ ^/evt/(?<slug>[^/]+)/data/(?<filename>[^/]+\.xml)$ {
    proxy_pass http://backend:8000/api/v1/public/collections/$slug/documents/$filename/raw;
}

# EVT static assets — strip the collection slug prefix
location ~ ^/evt/[^/]+/(.+)$ {
    rewrite ^/evt/[^/]+/(.+)$ /$1 break;
    try_files $uri =404;
    expires 7d;
}

# EVT index.html — entry point for any /evt/{slug}/ request
location ~ ^/evt/[^/]+/?$ {
    try_files /index.html =404;
}
```

Docker's embedded DNS resolver (`127.0.0.11`) is configured so that nginx can
resolve the `backend` hostname at request time — required when `proxy_pass`
contains a runtime variable.

---

## Backend plugin

### Files

| Path | Role |
|---|---|
| `backend/app/plugins/evt/plugin.py` | Plugin registration (non-native, opt-in) |
| `backend/app/plugins/evt/router.py` | FastAPI router — two public endpoints |
| `backend/app/plugins/evt/service.py` | `get_evt_config()`, `get_document_xml()` |
| `backend/app/plugins/evt/tests/test_endpoints.py` | HTTP-level test suite |

### Endpoints [pub] — no authentication required

Both endpoints verify that the collection is published **and** public before
serving any data. A non-public or unpublished collection returns `404`.

---

#### `GET /api/v1/public/collections/{slug}/evt-config`

Returns an EVT 2-compatible `config.json` for the collection.

**Response `200`** (`application/json`, `Cache-Control: public, max-age=60`):
```jsonc
{
  "projectName": "Epistolario Manzoni",
  "defaultEdition": "diplomatic",
  "dataUrl": "data/lettera-001.xml"
}
```

**How the config is built** (`service.get_evt_config()`):
- Fetches the collection record from PostgreSQL (published + public check)
- Lists all `.xml` files in the eXist-db collection via `existdb.list_collection(slug)`
- Sorts filenames alphabetically; `dataUrl` points to the first file
- Returns a minimal EVT 2 config dict (properties at root — EVT merges these into
  its defaults via `angular.extend`, so no top-level wrapper key is used)

> **Note on multi-document editions:** EVT 2 is designed for single-document editions.
> `dataUrl` is set to the first file; the user can navigate to other documents
> within EVT using its built-in file selector, which calls `data/{filename}.xml`
> for each document.

---

#### `GET /api/v1/public/collections/{slug}/documents/{filename}/raw`

Returns the raw XML bytes of a document.

**Response `200`** (`application/xml`, `Cache-Control: public, max-age=300`):
Raw TEI XML content as stored in eXist-db.

**Filename validation** (`service._validate_filename()`):
- Must match `^[A-Za-z0-9][A-Za-z0-9._-]*\.xml$`
- Maximum 120 characters
- Rejects path traversal attempts (no `/`, `..`, or non-XML filenames)

---

## Frontend

The **Leggi in EVT** button is rendered in the collection detail view when:

1. `evt_enabled` system setting is `true`
2. The collection `status === 'published'` and `is_public === true`

Clicking the button navigates to `/collections/{slug}/read`, which renders a
full-viewport `<iframe>` pointing to `http://localhost:8181/evt/{slug}/`
(or the configured EVT base URL in production).

---

## Production deployment

In production, the EVT container and the main nginx reverse proxy need additional
configuration so that `/evt/` requests are forwarded to the EVT container:

```nginx
# In the main nginx.conf (production)
location /evt/ {
    proxy_pass http://evt:80/evt/;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
}
```

The EVT container's internal nginx then handles the per-slug routing as described above.

---

## Limitations

| Limitation | Detail |
|---|---|
| Single-document orientation | EVT 2 is designed for single-document editions; multi-document collections work but `dataUrl` points to the first file only |
| No authentication | EVT endpoints are fully public — only published + public collections are served |
| No live reload | Changes to documents in eXist-db are reflected after the cache TTL expires (config: 60 s, documents: 300 s) |
| EVT version | The Dockerfile clones the latest stable EVT 2 branch at build time; no version is pinned |
| Node 14 build | EVT 2 depends on `node-sass@4.x` which requires Node 14; upgrading requires EVT to migrate to `sass` |

---

## Security

| Concern | Mitigation |
|---|---|
| Unpublished data exposure | Both endpoints check `status == published AND is_public == true` before serving |
| Path traversal via `filename` | `_validate_filename()` enforces an allowlist regex and a 120-char length cap |
| SSRF via nginx proxy | The EVT nginx only proxies to `backend:8000` — the target is hardcoded, not user-controlled |
| Cache poisoning | `Cache-Control: public` only set on verified-public responses; 404 responses are not cached |
