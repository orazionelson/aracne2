# Aracne2 — Quickstart (localhost)

## Prerequisites

- Docker Engine ≥ 24 with the Compose plugin (`docker compose version`)
  - **Do not use Docker via Snap** — it causes socket permission issues. Install from https://get.docker.com
- GNU Make
- Node.js ≥ 18 with npm (needed once to generate `package-lock.json` if missing)

---

## 1. Clone and configure

```bash
git clone <repo-url>
cd aracne2
cp .env.example .env
```

Open `.env` and fill in the mandatory values:

```dotenv
JWT_SECRET=     # minimum 64 characters — generate with the command below
POSTGRES_PASSWORD=changeme_postgres
EXIST_PASSWORD=  # leave empty — eXist-db 6.2.0 ignores this on first boot
```

Generate a JWT secret:

```bash
python3 -c "import secrets; print(secrets.token_hex(64))"
```

> **Important:** `EXIST_PASSWORD` must be left empty for local development.
> eXist-db 6.2.0 ignores this variable on first boot and starts with an empty admin password.
> The backend is already configured to authenticate with an empty password.

---

## 2. Start the stack

```bash
make up
```

This builds and starts four containers: `postgres`, `existdb`, `backend`, `frontend`.
All four must reach `Healthy` status before the stack is usable.

Watch startup progress:

```bash
make logs
```

When you see `Application startup complete` in the backend logs, the stack is ready.

---

## 3. Run migrations

```bash
make migrate
```

Runs `alembic upgrade head` inside the backend container, creating all tables,
triggers, and indexes in PostgreSQL.

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

| Service    | URL                                          | Notes                        |
|------------|----------------------------------------------|------------------------------|
| Frontend   | http://localhost:5173                        | Vue SPA with hot reload      |
| Backend    | http://localhost:8000/api/v1/health          | Should return `status: healthy` |
| API docs   | http://localhost:8000/api/docs               | Swagger UI (dev only)        |
| eXist-db   | http://localhost:8080/exist/apps/dashboard   | Login: admin / (empty password) |
| PostgreSQL | `make shell-db`                              | psql in the container        |

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
    "environment": "development",
    "services": {
      "postgres": { "status": "ok", "detail": null },
      "existdb": { "status": "ok", "detail": null }
    }
  }
}
```

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

**`permission denied while trying to connect to the Docker daemon socket`**
→ Your user is not in the `docker` group, or Docker is installed via Snap.
  Install Docker Engine from https://get.docker.com, then:
  `sudo usermod -aG docker $USER && newgrp docker`

**Backend fails with `error parsing value for field "cors_origins"`**
→ Your `.env` has inline comments (e.g. `CORS_ORIGINS=http://... # comment`).
  Comments must be on their own line — copy `.env.example` again and re-fill values.

**Backend fails with `JWT_SECRET must be at least 64 characters`**
→ Your `.env` has an empty or short `JWT_SECRET`. Generate one:
  `python3 -c "import secrets; print(secrets.token_hex(64))"`

**eXist-db shows `status: error` in health check**
→ Make sure `EXIST_PASSWORD=` is empty in your `.env` (no value after `=`).
  Then do a full reset: `make down && docker volume rm aracne2_existdb_data && make up`

**eXist-db dashboard asks for a password**
→ Leave the password field empty. eXist-db 6.2.0 starts with an empty admin password.

**Port already in use**
→ All ports are bound to `127.0.0.1` only. Check for conflicting local services:
  `sudo lsof -i :5432` / `:8080` / `:8000` / `:5173`
  PostgreSQL running locally? `sudo systemctl stop postgresql`
