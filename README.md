# Aracne2

A modular, production-ready CMS for editing and publishing structured
TEI corpora. Built for philologists, historians, archivists and
scholarly editors who want to take a corpus from raw text to a
published, citable digital edition without also becoming sysadmins.

## How we got here

**MaRa** *(2008)* started as a handful of PHP scripts that turned the
Angevine Chancery Papers from typed text into XML and harmonised
their bibliographies. Wrapped in a CodeIgniter web UI, it gave a
workable editorial pipeline to a workflow that until then lived in
one researcher's local files.
*(Cosco, 2018 — [Zenodo](https://zenodo.org/records/1447195),
[Academia.edu](https://www.academia.edu/37523540/))*

**Aracne** *(2016)* tried the platform jump: an editorial framework in
XQuery + HTML5 on top of eXist-db, with an early CodeMirror-based TEI
editor, a sitebuilder and a draft → review → publish flow. The idea
was right; XQuery as the platform language turned out to be a
maintenance and extension dead-end.
*([github.com/orazionelson/aracne](https://github.com/orazionelson/aracne))*

**Aracne2** *(2026)* is a clean rebuild. Backend and admin plane are
Python + FastAPI + PostgreSQL; the frontend is a Vue 3 + TypeScript
SPA; eXist-db goes back to doing what it does best — being a native
XML store. The whole platform ships in Docker, the architecture is
plugin-modular with hot activation, and integration with AI
assistants is a first-class concern.

## What you can do

### Edit and validate TEI

- **Schema-aware TEI editor**: load your TEI ODD, the editor
  autocompletes only the tags and attributes the schema allows.
  Live validation — no nasty surprises at publication time.
- **12 built-in authority lookups**: Wikidata, ORCID, ROR, VIAF,
  GeoNames, GND, CERL Thesaurus, Peripleo, Getty AAT, OpenAlex,
  Trismegistos, CrossRef. Select a name, pick the source, the
  canonical URI lands in the `@ref` attribute.
- **Structured bibliographies**: import from Zotero, resolve DOIs
  via CrossRef, write `<biblStruct>` without memorising the TEI
  grammar.

### Publish

- **Static or dynamic sites** generated from your collections —
  custom theme, free Markdown pages, themed indices, drop-in
  CSS/JS for the brave.
- **Embeddable search engines** scoped to subsets of public
  collections, copy-pasted into any external site with a three-line
  snippet.
- **6 deposit backends**: Zenodo, Internet Archive, Codeberg,
  GitHub, GitLab, Dataverse. Publishing a collection automatically
  pushes it to the depositories you wired up, with persistent DOIs
  and front-end badges.

### Work alongside an AI assistant

AI is a first-class collaborator in the editorial workflow, not a
side panel bolted on. Aracne2 plugs in along three axes:

**In-editor assistance** — the TEI editor ships an AI side panel
that knows the document context. Common turns:

- *Mark up this paragraph as `<persName>` / `<placeName>` / `<orgName>`* —
  the model drafts the markup, the editor reviews and accepts.
- *Why does this fail validation?* — the panel reads the validator's
  errors and explains them in prose, with a fix suggested inline.
- *Draft an XSLT template for the `<msDesc>` block* — Designer-mode
  turn that scaffolds stylesheets the editor refines.
- The **prompt library** is editable per deployment. Each prompt is
  scoped to a surface (TEI editor, bibliography, XSLT debugger, …)
  and the matching toolbar button auto-cables itself based on the
  scope — no per-prompt UI code.

**Bibliography automation** — turn a pile of references into clean
TEI:

- **Bibliobuilder** ingests messy author-supplied references and
  normalises them into `<biblStruct>` with the model's help.
- **CrossRef DOI resolver**: paste a DOI, get back ready-to-use
  TEI bibliographic markup.
- **Zotero import**: pull a group library straight into the
  collection's bibliography without round-trips through CSV.

**External assistant integration via MCP** — expose Aracne2 as a
Model Context Protocol endpoint. An editor working in Claude
Desktop, Cursor or Claude Code can ask *"summarise the tragedies
in this corpus"* or *"in which documents does the placeName 'Naples'
occur?"* and get answers grounded in real TEI documents — not
hallucinations. Tokens are scoped by **corpus**, so heterogeneous
domains hosted on the same instance don't bleed into each other's
analyses. See [MCP_SERVER.md](docs/reference/MCP_SERVER.md).

**Provider choice** — bring your own model:

- Cloud: **OpenAI**, **Anthropic Claude**, **Google Gemini** — paste
  the API key in `Settings → AI`, encrypted at rest.
- Local: **Ollama** profile bundled in the compose file — runs the
  model on your own hardware, no key needed, traffic stays on
  the host.

**Optional retrieval grounding (RAG)** — for deployments that turn
on the local-AI profile, an opt-in `pgvector` store + an Ollama
embeddings model let the editor's prompts retrieve from the
ingested **TEI P5 Guidelines** (or your own corpus). The platform
ships an ingestion script and a per-prompt RAG toggle; the
retrieval surface degrades silently to "no augmentation" if the
infra isn't reachable.

## Who it's for

Aracne2 fits **editorial teams** working on structured
corpora — university projects, critical editions, diplomatic-papers
archives, funded research groups. It is opt-in for plugins and
external services, so a deployment can stay minimal or grow into a
full publishing platform as the project does.

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
| **Websites** | Static / dynamic / hybrid website generator with XSLT rendering per collection |
| **Search Engines** | Configurable multi-collection search portals: buildable static HTML page, public API, and embeddable JS widget with per-origin access control |
| **XSLT templates** | Designer-managed catalog of XSLT stylesheets used by the website generator |
| **TEI schemas** | Schema catalog (upload / URL import / auto-generated CM5); bundled TEI All P5 schema |
| **AI integration** | OpenAI, Anthropic, Gemini **and Ollama (local, no-key)** adapters; native prompt library with TEI-specific templates; optional RAG over pgvector with Ollama embeddings; streaming completion in editor and XSLT debugger |
| **Linked Open Data** | Wikidata entity linking in the TEI editor (@ref on persName/placeName/orgName); schema.org JSON-LD on public pages; content-negotiated RDF export (Turtle / RDF-XML / JSON-LD) on public collection and document endpoints |
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
| Databases | PostgreSQL 15 · eXist-db 6.x · pgvector (optional, RAG) |
| XML | defusedxml (XXE prevention) · XQuery 3.1 |
| Frontend | Vue 3 · Vite 5 · Pinia · Vue Router 4 · vue-i18n 9 · Tailwind CSS 3 |
| Testing | pytest-asyncio · SQLite in-memory · Vitest |
| Infrastructure | Docker · docker-compose · nginx |

## Quick start

The full, dummy-friendly walk-through — prerequisites, first-time
configuration, default credentials, daily-workflow targets, and a
troubleshooting section — lives in [quickstart.md](quickstart.md).

The bare-minimum sequence, for the impatient:

```bash
git clone <repo-url> && cd aracne2
cp .env.example .env       # then fill JWT_SECRET, POSTGRES_PASSWORD; leave EXIST_PASSWORD empty
make up
make migrate
make seed
```

Frontend at http://localhost:5173 — login `admin` / `changeme_admin`
(unless you changed `ADMIN_PASSWORD` in `.env`).

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

## API conventions

The full normative spec lives in
[docs/reference/API_FORMAT.md](docs/reference/API_FORMAT.md) — this
section is the orientation tour.

### URL layout and versioning

- All routes live under `/api/v1/`. The `v1` prefix is permanent for
  the lifetime of the major version; a future breaking change
  branches off as `/api/v2/` rather than mutating `v1`.
- Public, unauthenticated routes (collection landing pages, search
  widget feed, sitemap, OAI-PMH) are bundled under
  `/api/v1/public/...`.
- Plugin routes mount under `/api/v1/plugins/<plugin_name>/...` for
  plugin-management and under whatever prefix the plugin declares
  for its own surface (e.g. `/api/v1/mcp` for the MCP server).

### Response envelope

All JSON responses use one of three consistent shapes:

```jsonc
// Single resource
{ "data": { ... } }

// Paginated list
{
  "data": [...],
  "pagination": {
    "page": 1,
    "per_page": 10,
    "total": 142,
    "total_pages": 15
  }
}

// Error — codes are SCREAMING_SNAKE_CASE
{
  "error": {
    "code": "RESOURCE_NOT_FOUND",
    "message": "User not found",
    "details": { ... }   // optional, only populated in development
  }
}
```

**Why an envelope, instead of returning the resource directly.** Two
reasons: it keeps every response self-describing for clients that
generate types from the OpenAPI spec, and the same outer shape covers
single-resource, paginated, and error cases — so an SPA-side helper
can branch on `data` vs. `error` without sniffing status codes.

### HTTP status codes

| Code | When the API returns it |
|---|---|
| `200 OK` | Successful read or update |
| `201 Created` | New resource created |
| `204 No Content` | Successful delete or void mutation |
| `400 Bad Request` | Malformed JSON / missing required field |
| `401 Unauthorized` | Missing or expired access token |
| `403 Forbidden` | Authenticated, but role lacks permission |
| `404 Not Found` | Resource doesn't exist or is invisible to the caller |
| `409 Conflict` | Domain conflict (e.g. duplicate slug) |
| `422 Unprocessable Entity` | Pydantic validation failure or `DomainValidationError` |
| `429 Too Many Requests` | Rate limit exceeded |
| `500 Internal Server Error` | Uncaught exception (should never reach in dev) |

### Authentication

- **Access token** (short-lived JWT, 60 min default) sent as
  `Authorization: Bearer <jwt>`. Stored in Pinia memory on the SPA
  side — never in localStorage.
- **Refresh token** (long-lived, 30 days default) sent as an
  `httpOnly; SameSite=Strict; Secure` cookie. The SPA never reads it
  directly — `POST /api/v1/auth/refresh` returns a fresh access
  token using the cookie.
- The SPA's axios instance has `withCredentials: true` so the refresh
  cookie travels automatically with `/auth/refresh` calls.

### Pagination

Paginated endpoints accept `page` (1-based) and `per_page` (default
20, capped at 100 — sometimes lower depending on the resource). The
response embeds the `pagination` block with the canonical totals.

```bash
GET /api/v1/collections?page=2&per_page=50
```

### Rate limiting

Two named bucket levels (`slowapi`):

| Bucket | Default | Applied to |
|---|---|---|
| `STRICT` | 10 req / minute / IP | Login, register, password change, MCP endpoint |
| `GLOBAL` | 200 req / minute / IP | Everything else |

A few authority-lookup routes carry their own intermediate limit
(30 req/min) tuned to the upstream's published quota.

### Error codes

Domain errors carry a typed code (in `error.code`) so the SPA can
branch on the kind of failure without parsing the message string.
Examples actually emitted by the platform:

- `RESOURCE_NOT_FOUND`, `INVALID_FILENAME`, `FILE_TOO_LARGE`
- `INVALID_TOKEN`, `EXPIRED_TOKEN`, `INSUFFICIENT_ROLE`
- `DUPLICATE_SLUG`, `DUPLICATE_NAME`, `UNKNOWN_COLLECTION`
- `WORKFLOW_TRANSITION_INVALID`, `COLLECTION_NOT_PUBLISHED`

A complete list is enforced by code rather than enumerated here —
new domain errors land alongside the feature that needs them.

### File downloads

Binary endpoints (TEI source, media, ZIP exports, etc.) return the
body directly with `Content-Disposition: attachment; filename="..."`
and the appropriate `Content-Type`. The envelope is **not** wrapped
around binary bodies. Filenames in the header are validated upstream
to prevent header-injection.

### Discoverability

In development mode (`ENVIRONMENT=development`), the full Swagger
UI is at `http://localhost:8000/api/docs` and the raw OpenAPI JSON
at `/api/openapi.json`. Both are disabled in production.

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
- Restrict `.env` permissions so only the deploy user can read it:
  ```bash
  chmod 600 .env
  chown <deploy-user>:<deploy-user> .env
  ```
  `.env` is already excluded from git via `.gitignore`. The `chmod 600` ensures
  that other OS users on the same server cannot read the file in plain text.
  `docker compose` reads it correctly regardless of these permissions as long as
  it runs as the same user.

## Reference documentation

For a server-side install (test/dev or production) see
[docs/INSTALL_LINUX_SERVER.md](docs/INSTALL_LINUX_SERVER.md).

For day-to-day operations (applying `.env` changes, rotating credentials,
troubleshooting port/DNS/bootstrap issues, backup) see
[docs/OPERATIONS.md](docs/OPERATIONS.md).

Technical reference documents are in [`docs/reference/`](docs/reference/).

| Document | Topic |
|---|---|
| [API_FORMAT.md](docs/reference/API_FORMAT.md) | Standard JSON envelope, pagination, error format |
| [DB_SCHEMA.md](docs/reference/DB_SCHEMA.md) | PostgreSQL platform schema (Layer 1) |
| [SYSTEM_SETTINGS.md](docs/reference/SYSTEM_SETTINGS.md) | All system_settings keys, types, and defaults |
| [COLLECTIONS.md](docs/reference/COLLECTIONS.md) | Collections & TEI editor — data model and endpoints |
| [SEARCH_ENGINES.md](docs/reference/SEARCH_ENGINES.md) | Search Engine portals — data model, build, API, caching |
| [EMBED_WIDGET.md](docs/reference/EMBED_WIDGET.md) | Embeddable JS search widget — CORS, origin enforcement, snippet |
| [WEB_SITES.md](docs/reference/WEB_SITES.md) | Website generator — static / dynamic / hybrid modes |
| [XSLT_TEMPLATES.md](docs/reference/XSLT_TEMPLATES.md) | XSLT template catalog |
| [TEI_SCHEMAS.md](docs/reference/TEI_SCHEMAS.md) | Schema catalog (RNG / DTD / XSD / CM5) |
| [ZONES_FACSIMILE.md](docs/reference/ZONES_FACSIMILE.md) | Text-image alignment via TEI `<zone>` / `facs` |
| [NAMED_ENTITIES.md](docs/reference/NAMED_ENTITIES.md) | Named entity index — extraction, normalisation, VIAF/GeoNames |
| [BIBLIOGRAPHY.md](docs/reference/BIBLIOGRAPHY.md) | Bibliographic entries (BibTeX / CSL-JSON import, Bibliobuilder) |
| [BODY_TEMPLATES.md](docs/reference/BODY_TEMPLATES.md) | Body templates for document creation |
| [PLUGINS.md](docs/reference/PLUGINS.md) | Plugin architecture — native and third-party plugins |
| [AI_INTEGRATION.md](docs/reference/AI_INTEGRATION.md) | AI provider adapters, prompt library, streaming |
| [MCP_SERVER.md](docs/reference/MCP_SERVER.md) | Built-in MCP server — protocol, corpora, token model, tool registry |
| [LOD_INTEGRATION.md](docs/reference/LOD_INTEGRATION.md) | Linked Open Data — Wikidata entity linking, JSON-LD, RDF content negotiation |
| [BRAND.md](docs/reference/BRAND.md) | Aracne icon set — sigla → path mapping and usage policy |
| [WEBHOOKS.md](docs/reference/WEBHOOKS.md) | Webhook dispatcher — events, signing, retries |
| [NOTIFICATIONS.md](docs/reference/NOTIFICATIONS.md) | In-app notification system |
| [OAI_PMH_PROVIDER.md](docs/reference/OAI_PMH_PROVIDER.md) | OAI-PMH 2.0 metadata provider |
| [EVT_INTEGRATION.md](docs/reference/EVT_INTEGRATION.md) | EVT 2 viewer integration |
| [PUBLIC_PAGES.md](docs/reference/PUBLIC_PAGES.md) | CSS classes for the public pages (homepage, collection, document, entities, bibliography) |
| [HEALTH_CHECK.md](docs/reference/HEALTH_CHECK.md) | Health check endpoint |
| [EXISTDB_SETUP.md](docs/reference/EXISTDB_SETUP.md) | eXist-db user model, bootstrap, collection namespace, environment variables |

## License

MIT — see [LICENSE](LICENSE).
