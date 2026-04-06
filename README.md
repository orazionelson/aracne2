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

- Docker and docker-compose
- `make`

### First run

```bash
# 1. Clone and enter the project
git clone <repo-url>
cd aracne2

# 2. Create the environment file
cp .env.example .env
# Edit .env — set JWT_SECRET (min 64 chars) and all passwords

# 3. Start all services
make up

# 4. Run database migrations
make migrate

# 5. Seed initial data (roles, settings, admin user)
make seed

# 6. Verify
curl http://localhost:8000/api/v1/health
```

| Service | URL |
|---------|-----|
| Frontend (dev) | http://localhost:5173 |
| Backend API | http://localhost:8000/api/v1 |
| API docs (dev only) | http://localhost:8000/api/docs |
| eXist-db dashboard | http://localhost:8080/exist/apps/dashboard |
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
├── .claude/                   # Claude Code project configuration
│   ├── settings.json          # hooks, permissions
│   ├── skills/                # /phase, /new-migration, /test-backend
│   ├── hooks/                 # protect-sensitive.sh, autoformat-python.sh
│   └── rules/                 # backend.md, frontend.md
├── docs/
│   ├── phases/                # implementation phase specifications
│   └── reference/             # API format, DB schema
├── docker-compose.yml
├── docker-compose.prod.yml
├── nginx.conf
├── Makefile
└── .env.example
```

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

## Development with Claude Code

This project uses Claude Code with a configured `.claude/` directory.

Custom skills available:

| Skill | Usage |
|-------|-------|
| `/phase` | Implement a development phase: `/phase 02_AUTH` |
| `/new-migration` | Create and verify a migration: `/new-migration add collection_permissions` |
| `/test-backend` | Run tests and auto-fix failures: `/test-backend` |

## License

MIT — see [LICENSE](LICENSE).
