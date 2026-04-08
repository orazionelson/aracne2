# Aracne2

A modular, production-ready CMS for managing, editing and publishing collections of structured XML documents. Built with a separate frontend/backend architecture and a plugin system inspired by WordPress modularity.

## Architecture overview

```
Browser ──── REST API + JWT ──── FastAPI backend ──── PostgreSQL  (platform data)
                                                  └─── eXist-db    (XML documents)
```

**Two distinct data layers:**
- **Layer 1 — Platform data**: users, roles, sessions, settings, audit, plugins → PostgreSQL
- **Layer 2 — Document data**: XML file collections → filesystem + eXist-db (native XML database)

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

### Common commands

```bash
make up            # Start all services
make down          # Stop all services
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
│   └── reference/             # API format, DB schema
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
- If the collection has a schema with a validation file, a **Validate** button appears in the toolbar. Validation also runs automatically after each save. Results appear in a panel below the editor (line · column · message). Validation failure is non-blocking: the document is always saved regardless.

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
