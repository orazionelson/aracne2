# Aracne2

A modular, production-ready CMS for managing, editing and publishing collections of structured XML documents. Built with a separate frontend/backend architecture and a hook-based plugin system designed to be modular and extensible.

## Goals

Aracne2 is designed around three core targets:

- **A structured editing environment for TEI XML documents** — providing a schema-aware code editor with tag and attribute autocomplete, validation against RNG / DTD / XSD schemas, text-image alignment (facsimile zones), bibliography management, and AI-assisted encoding, correction, and annotation.

- **An academic publication platform for TEI corpora** — transforming validated collections into navigable web publications via configurable XSLT rendering, with full-text and structural search, named entity browsing, public bibliography, OAI-PMH metadata exposure, and an embeddable search widget for integration into third-party sites.

- **An end-to-end editorial workflow framework** — supporting the full lifecycle of a scholarly edition, from collection creation and document ingestion through role-based review (Editor, EditorInChief, Designer, Admin) to controlled publication, with notifications, audit logging, and webhook integration for external systems.

## Architecture overview

```
┌─────────────────────────────────────────────────────────────────┐
│  Browser                                                        │
│  Vue 3 SPA · Pinia · Vue Router · Tailwind CSS                  │
└───────────────────────┬─────────────────────────────────────────┘
                        │  REST API · JSON · JWT Bearer
                        │  (httpOnly cookie for refresh token)
┌───────────────────────▼─────────────────────────────────────────┐
│  FastAPI backend  (Python 3.12 · async · Pydantic v2)           │
│                                                                 │
│  ┌─────────────┐  ┌──────────────┐  ┌────────────────────────┐ │
│  │   Routers   │  │   Services   │  │  Plugin system         │ │
│  │  + ACL/JWT  │→ │ + XQuery I/O │  │  hooks · native plugins│ │
│  └─────────────┘  └──────┬───────┘  └────────────────────────┘ │
└─────────────────────────┬┴────────────────────────────────────-─┘
              ┌───────────┴────────────┐
              │                        │
┌─────────────▼──────────┐  ┌──────────▼─────────────────────────┐
│  PostgreSQL 15          │  │  eXist-db 6.x                      │
│  Layer 1 — platform     │  │  Layer 2 — document data           │
│  users · roles          │  │  TEI XML collections               │
│  sessions · settings    │  │  queried via XQuery 3.1            │
│  audit · plugins        │  │  (REST API + .xq files)            │
│  named entities         │  │                                    │
│  schemas · websites     │  │                                    │
└─────────────────────────┘  └────────────────────────────────────┘
```

**Two distinct data layers:**

- **Layer 1 — Platform data** (PostgreSQL): users, roles, sessions, system settings, audit log, plugin registry, named entity index, TEI schemas, XSLT templates, websites, search engines, notifications, webhooks.
- **Layer 2 — Document data** (eXist-db): TEI XML documents stored natively in per-collection XML databases, queried and transformed via XQuery 3.1 files — never via inline query strings.

**Key architectural principles:**

- Frontend and backend communicate **exclusively via REST API + JSON + JWT** — the frontend never accesses any database directly.
- All XQuery is loaded from `.xq` / `.xqm` files on the filesystem — no inline query construction in Python code.
- The plugin system is **hook-based**: plugins register listeners on named events (`document.uploaded`, `collection.published`, …) rather than modifying core code.
- **Rate limiting** (slowapi) is applied at the router level; XML parsing always uses `defusedxml` to prevent XXE attacks.

## Features

| Area | Feature |
|---|---|
| **Editorial** | Collection-based TEI XML document management with full workflow (draft → review → published) |
| **Editor** | CodeMirror 5 TEI editor with XML autocomplete (CM5 schema), AI assistance, and inline validation |
| **Facsimile** | Text-image alignment via TEI `<zone>` / `facs` — manual editor and HTR pipeline import |
| **Validation** | Per-document and collection-wide TEI validation against RNG / DTD / XSD schemas |
| **Bibliography** | Bibliographic entry management with BibTeX/CSL-JSON import and a bibliography normalizer (AI) |
| **Named entities** | Automatic entity extraction (persName, placeName, orgName, …), admin normalisation, VIAF/GeoNames linking |
| **Websites** | Static / dynamic / hybrid website generator with XSLT rendering, search engines, and embed widget |
| **XSLT templates** | Designer-managed catalog of XSLT stylesheets used by the website generator |
| **TEI schemas** | Schema catalog (upload / URL import / auto-generated CM5); bundled TEI All P5 schema |
| **AI integration** | OpenAI, Anthropic, Gemini adapters; prompt library; streaming completion in editor and XSLT debugger |
| **OAI-PMH** | OAI-PMH 2.0 provider for metadata harvesting |
| **EVT viewer** | Optional EVT 2 integration for public reading of published collections |
| **Notifications** | In-app notification inbox; event-driven dispatch via plugin hooks |
| **Webhooks** | Admin-managed HTTP webhooks subscribed to platform events |
| **Plugins** | Hook-based plugin architecture; native plugins for audit, notifications, webhooks, AI, OAI-PMH, EVT |
| **Public site** | Public homepage with customisable CSS, collection browser, entity browser, bibliography, and search |

## Technology stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.12 · FastAPI · SQLAlchemy 2 async · Alembic · Pydantic v2 |
| Auth | python-jose (JWT) · passlib bcrypt · httpOnly refresh cookie |
| Databases | PostgreSQL 15 · eXist-db 6.x |
| XML | defusedxml (XXE prevention) · XQuery 3.1 |
| Frontend | Vue 3 · Vite 5 · Pinia · Vue Router 4 · vue-i18n 9 · Tailwind CSS 3 |
| Testing | pytest-asyncio · SQLite in-memory · Vitest |
| Infrastructure | Docker · docker-compose · nginx |

## Quick start

### Prerequisites

- Docker Engine ≥ 24 with Compose plugin (install from https://get.docker.com — do not use the Snap version)
- `make`

### First run

```bash
# 1. Clone and enter the project
git clone <repo-url>
cd aracne2

# 2. Create the environment file
cp .env.example .env
# Edit .env: set JWT_SECRET (min 64 chars), POSTGRES_PASSWORD, leave EXIST_PASSWORD empty

# 3. Start all services
make up

# 4. Run database migrations
make migrate

# 5. Seed initial data (roles, settings, admin user)
make seed

# 6. Verify
curl -s http://localhost:8000/api/v1/health | python3 -m json.tool
```

> **Note on `EXIST_PASSWORD`:** eXist-db 6.2.0 ignores this variable on first boot
> and starts with an empty admin password. Leave `EXIST_PASSWORD=` empty in `.env`.

> **Full step-by-step guide** (including troubleshooting): see [quickstart.md](quickstart.md).

| Service | URL |
|---------|-----|
| Frontend (dev) | http://localhost:5173 |
| Backend API | http://localhost:8000/api/v1 |
| API docs (dev only) | http://localhost:8000/api/docs |
| eXist-db dashboard | http://localhost:8080/exist/apps/dashboard (login: admin / empty password) |
| PostgreSQL | localhost:5432 (127.0.0.1 only) |

### Stopping and restarting

Always shut down cleanly before rebooting the machine:

```bash
make down   # stops containers and removes the Docker network
# reboot
make up     # recreates the network and starts all services in order
```

If you reboot without running `make down` first, Docker may leave the internal
network in a broken state. Symptom: the backend starts but cannot reach
PostgreSQL (`ConnectionRefusedError`). Fix: `docker compose down && make up`.

### Common commands

```bash
make up            # Start all services
make down          # Stop all services (always run before rebooting)
make logs          # Follow all logs
make logs-be       # Backend logs only

make migrate       # Run pending migrations
make migrate-new MSG="add collection_permissions table"
make migrate-down  # Rollback last migration

make seed          # Seed roles, settings, admin user (idempotent)

make test          # Run backend tests with coverage
make test-v        # Verbose test output
make lint          # ruff check + mypy
make format        # ruff format

make shell-be      # bash inside backend container
make shell-db      # psql inside postgres container
make help          # Full command reference
```

## Project structure

```
/
├── backend/
│   ├── app/
│   │   ├── main.py            # FastAPI entrypoint + lifespan
│   │   ├── config.py          # Pydantic Settings
│   │   ├── core/              # exceptions, hooks, logging, plugins
│   │   ├── db/                # postgres, existdb, seed
│   │   ├── middleware/        # ACL, CORS, rate limiter, request logger
│   │   ├── models/            # SQLAlchemy ORM models
│   │   ├── routers/           # FastAPI routers (one per domain)
│   │   ├── schemas/           # Pydantic schemas
│   │   ├── services/          # business logic
│   │   ├── xqueries/          # XQuery files (never inline)
│   │   └── tests/
│   ├── alembic/               # migrations
│   └── requirements.txt
├── frontend/
│   └── src/
│       ├── services/api.ts    # axios + token refresh interceptor
│       ├── stores/            # Pinia stores (auth, ui)
│       ├── router/            # Vue Router + navigation guards
│       ├── views/             # page components
│       ├── components/        # reusable components
│       └── locales/           # i18n (en, it)
├── docs/
│   ├── phases/                # implementation phase specifications
│   └── reference/             # API format, DB schema, feature reference guides
├── docker-compose.yml
├── docker-compose.prod.yml
├── nginx.conf
├── Makefile
└── .env.example
```

## TEI schema management

Aracne2 supports per-collection TEI schemas for XML validation and CodeMirror 5 autocomplete.

### Registering a schema

Go to **Settings → Schemas** and create a new schema entry (name only). Then attach the files:

- **Validation schema** (.rng / .dtd / .xsd) — used to validate documents on demand and at workflow transitions. Upload a file or import from a public URL.
- **CM5 schema** (custom XML format, `<cm_tei_schema>` root) — used by the CodeMirror editor for tag/attribute autocomplete. Upload a file or import from a public URL.

Both files are optional and independent. A schema with only a CM5 file enables autocomplete without validation, and vice versa.

URL import uses an SSRF guard: only public IP addresses are accepted. Private, loopback, link-local, multicast and reserved ranges are blocked.

### Linking a schema to a collection

1. Open the collection detail page (`/collections/{slug}`).
2. Click **Edit** (top right).
3. Select the desired schema from the **TEI Schema** dropdown.
4. Click **Save**.

### Full-collection validation

EditorInChief and Admin can validate every document in a collection at once using
the **Validate collection** button on the collection detail page.  The run executes
in the background — the page polls for live progress and shows a per-document report
when done.

> **Performance note (development / local setups)**
>
> Each document is validated synchronously inside a Python background task that
> shares the same asyncio event loop as the FastAPI server.  On large collections
> (hundreds of documents) or with heavy schemas (RelaxNG TEI All) this will
> noticeably slow down all other requests for the duration of the run.  The
> **Stop validation** button cancels the run cooperatively: the task halts after
> finishing the current document.
>
> For production deployments with large collections, see `docs/DEFERRED.md`
> (item 12) for the planned optimisation path.

### Using the schema in the editor

When editing a document (`/collections/{slug}/document/{filename}/edit`):

- If the collection has a schema with a CM5 file, the editor loads it automatically and shows a green **TEI P5** badge in the toolbar.
- If no collection-specific CM5 file is found, the editor falls back to the global `/cmschemas/tei-p5.xml` static file (place it in `frontend/public/cmschemas/`).
- If the collection has a schema with a validation file, the **Save** button becomes **Save & Validate**. Clicking it saves the document first; if the save succeeds the schema validator runs automatically on the saved content.

#### Validation and error panel

Results are shown in a resizable side panel that opens automatically whenever an error is detected:

| Trigger | What appears in the panel |
|---|---|
| Save fails (malformed XML) | Save error — full message from the server |
| Save succeeds, schema errors found | Schema validation errors — one row per error with `line:col`, message, XPath, and a "Search on Google" link |
| Save succeeds, document valid | Green "Document is valid" confirmation |

The panel can be closed with the **✕** button. If schema errors were found, a red badge showing the error count appears next to the **Save & Validate** button; clicking the badge reopens the panel without re-saving.

Validation failure is non-blocking: the document is saved to eXist-db regardless of schema errors. The panel contains a **Save & Validate** shortcut to re-run save and validation without leaving the panel.

## EVT viewer

Aracne2 integrates [EVT 2](https://github.com/evt-project/evt-viewer) as an optional public viewer for published collections. When active, a **Leggi in EVT** button appears on the collection detail page and opens a full-viewport iframe at `/collections/{slug}/read`.

### Prerequisites

- The collection must be **published** and **public** (`is_public = true`).
- The `evt_enabled` setting must be set to `true` in **Settings → General**.

### Activating the viewer

**Step 1 — Build the EVT Docker image** (one-time, downloads and compiles EVT from source):

```bash
docker compose --profile evt build evt
```

**Step 2 — Start the EVT container:**

```bash
docker compose --profile evt up -d evt
```

The EVT nginx container runs on port **8181** and proxies config and XML requests to the Aracne2 backend.

**Step 3 — Enable the setting:**

In **Settings → General**, set `evt_enabled` to `true`. The button will appear automatically on any collection that is published and public.

### How it works

```
Browser (iframe)
  └── EVT nginx :8181
        ├── /evt/{slug}/config/config.json  → proxy → backend /public/collections/{slug}/evt-config
        ├── /evt/{slug}/data/{file}.xml     → proxy → backend /public/collections/{slug}/documents/{file}/raw
        └── /evt/{slug}/*                   → EVT static assets (JS/CSS built from source)
```

The backend endpoints are public (no authentication required). They verify that the collection is published and public before serving any data.

## API conventions

All responses use a consistent envelope:

```jsonc
// Single resource
{ "data": { ... } }

// Paginated list
{ "data": [...], "pagination": { "page": 1, "per_page": 10, "total": 142, "total_pages": 15 } }

// Error
{ "error": { "code": "RESOURCE_NOT_FOUND", "message": "User not found", "details": {} } }
```

## Role hierarchy

Editor and Designer are **lateral roles** at the same level — orthogonal domains, same person or different people.

```
                Admin
                  │
            EditorInChief
             ╱          ╲
        Editor          Designer
             ╲          ╱
                User
```

| Role | Level | Domain |
|------|-------|--------|
| User | 1 | Read-only access to published content |
| Editor | 2 | Creates and edits documents |
| Designer | 2 | Manages XSLT templates and CSS themes |
| EditorInChief | 3 | Manages collections and publication workflow |
| Admin | 4 | Full platform access |

## Security

- `access_token`: stored in Pinia memory only — never in localStorage
- `refresh_token`: httpOnly + SameSite=Strict cookie — JS never reads it
- Silent refresh on SPA boot via `POST /auth/refresh`
- Rate limiting: 10 req/min on auth endpoints, 200 req/min global
- XML parsing via `defusedxml` (XXE prevention)
- CSP, X-Frame-Options, and security headers configured in nginx

## Production deployment

```bash
# Build production images
make build-prod

# Start production stack (nginx serves the built SPA, 4 uvicorn workers)
make up-prod
```

Before going to production:
- Set `ENVIRONMENT=production` in `.env`
- Generate a strong `JWT_SECRET` (`python -c "import secrets; print(secrets.token_hex(64))"`)
- Uncomment the HSTS header in `nginx.conf` once HTTPS is active
- Change all default passwords in `.env`

## License

MIT — see [LICENSE](LICENSE).
