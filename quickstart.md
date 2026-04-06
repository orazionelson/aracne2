# Aracne2 — Quickstart (localhost)

## Prerequisites

- Docker ≥ 24 with the Compose plugin (`docker compose version`)
- GNU Make
- Python 3.12 (only to generate the JWT secret — no local install needed if you use the Docker method below)

---

## 1. Clone and configure

```bash
git clone <repo-url>
cd aracne2
cp .env.example .env
```

Open `.env` and fill in the three mandatory values:

```dotenv
JWT_SECRET=          # minimum 64 characters — see below
POSTGRES_PASSWORD=   # any strong password
EXIST_PASSWORD=      # any strong password
```

Generate a JWT secret:

```bash
python3 -c "import secrets; print(secrets.token_hex(64))"
```

Everything else in `.env` can stay at its default value for local development.

---

## 2. Start the stack

```bash
make up
```

This builds and starts four containers: `postgres`, `existdb`, `backend`, `frontend`.

> **Note:** eXist-db takes ~30 seconds to become healthy. The backend and frontend
> wait for their dependencies automatically before starting.

Watch startup progress:

```bash
make logs
```

When you see the backend log `Application startup complete`, the stack is ready.

---

## 3. Run migrations

```bash
make migrate
```

This runs `alembic upgrade head` inside the backend container, creating all tables,
triggers, and indexes.

---

## 4. Seed initial data

```bash
make seed
```

Creates the five default roles (`Admin`, `EditorInChief`, `Designer`, `Editor`, `User`)
and the admin user defined in `.env` (`ADMIN_USERNAME`, `ADMIN_EMAIL`, `ADMIN_PASSWORD`).

The seed is **idempotent** — safe to run multiple times.

---

## 5. Verify everything is running

| Service   | URL                                        | Notes                        |
|-----------|--------------------------------------------|------------------------------|
| Frontend  | http://localhost:5173                      | Vue SPA with hot reload      |
| Backend   | http://localhost:8000/api/v1/health        | Should return `{"data": ...}` |
| API docs  | http://localhost:8000/docs                 | Swagger UI (dev only)        |
| eXist-db  | http://localhost:8080/exist/apps/dashboard | Admin password = EXIST_PASSWORD |
| PostgreSQL| `make shell-db`                            | psql in the container        |

Quick health check:

```bash
curl -s http://localhost:8000/api/v1/health | python3 -m json.tool
```

Expected response:

```json
{
  "data": {
    "status": "healthy",
    "version": "1.0.0",
    "postgres": "ok",
    "existdb": "ok"
  }
}
```

`status` can be `"degraded"` if eXist-db is still warming up — wait a few seconds
and retry.

---

## 6. Run the test suite

Tests run inside the backend container against a SQLite in-memory database —
no external services needed.

```bash
make test          # with coverage report
make test-v        # verbose output + short tracebacks
```

Run a single test file:

```bash
make test-file FILE=app/tests/test_scaffolding.py
```

---

## 7. Daily workflow

```bash
make up            # start (skips build if images are current)
make down          # stop (volumes are preserved)
make restart       # down + up

make logs-be       # backend logs only
make logs-db       # postgres logs only
make logs-xml      # existdb logs only

make lint          # ruff + mypy
make format        # ruff format
make typecheck     # mypy --strict
```

---

## 8. Reset everything

To wipe all data and start from scratch:

```bash
make down
docker volume rm aracne2_postgres_data aracne2_existdb_data
make up
make migrate
make seed
```

---

## Troubleshooting

**Backend fails to start with `JWT_SECRET must be at least 64 characters`**
→ Your `.env` has an empty or short `JWT_SECRET`. Generate one with the command in step 1.

**`make migrate` fails with `connection refused`**
→ The stack is not up. Run `make up` first.

**eXist-db dashboard shows `401 Unauthorized`**
→ Use username `admin` and the `EXIST_PASSWORD` value from your `.env`.

**Port already in use**
→ All ports are bound to `127.0.0.1` only. Check for conflicting local services:
`sudo lsof -i :5432` / `:8080` / `:8000` / `:5173`.
