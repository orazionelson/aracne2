# Aracne2 — Quickstart (localhost)

A step-by-step guide to bring Aracne2 up on your laptop. Assumes you
have never run the project before. Allow ~10 minutes the first time
(most of it is Docker pulling images).

## Prerequisites

- **Docker Engine ≥ 24** with the Compose plugin. Test with
  `docker compose version` — it must print a version, not an error.
  - **Do not use Docker via Snap** — it causes socket-permission
    issues. Install Docker Engine from https://get.docker.com.
- **GNU Make** (already on macOS and most Linux distros; on Debian /
  Ubuntu: `sudo apt install make`).

That's it. You do **not** need Python, Node.js, or PostgreSQL on the
host — every dependency runs inside Docker.

---

## 1. Clone and configure

```bash
git clone <repo-url>
cd aracne2
cp .env.example .env
```

Open `.env` in any editor and fill in the three mandatory values:

```dotenv
JWT_SECRET=         # minimum 64 characters — generate with the command below
POSTGRES_PASSWORD=changeme_postgres
EXIST_PASSWORD=     # leave EMPTY (no value after the =) — see note below
```

Generate a JWT secret (paste the output of this command into
`JWT_SECRET=`):

```bash
python3 -c "import secrets; print(secrets.token_hex(64))"
```

> **Important:** `EXIST_PASSWORD` must be left empty for local
> development. eXist-db 6.4.1 ignores this variable on first boot and
> starts with an empty admin password. The backend is already
> configured to authenticate with an empty password.

> **Important:** comments in `.env` must be on their **own line**.
> Inline comments (e.g. `JWT_SECRET=abc... # my secret`) make Pydantic
> reject the file at boot.

The default admin account that gets created in step 4 is defined by
three more variables, already filled in for you:

```dotenv
ADMIN_USERNAME=admin
ADMIN_EMAIL=admin@example.com
ADMIN_PASSWORD=changeme_admin
```

You can change these now or accept the defaults — you can always
change the password from the UI after first login.

---

## 2. Start the stack

```bash
make up
```

This builds and starts four containers: `postgres`, `existdb`,
`backend`, `frontend`. The first run downloads images and builds the
backend / frontend — expect ~5 minutes. Subsequent `make up` runs
take ~5 seconds.

Watch startup progress (press `Ctrl+C` to stop watching, the
containers keep running):

```bash
make logs
```

The stack is ready when you see `Application startup complete` in
the backend logs.

---

## 3. Run database migrations

```bash
make migrate
```

Runs `alembic upgrade head` inside the backend container, creating
all tables, triggers, and indexes in PostgreSQL. Run this any time
new migrations land (after a `git pull`).

---

## 4. Seed initial data

```bash
make seed
```

Creates:

- the five default roles: `Admin`, `EditorInChief`, `Designer`,
  `Editor`, `User`;
- the admin user defined in `.env` (`ADMIN_USERNAME`, `ADMIN_EMAIL`,
  `ADMIN_PASSWORD`);
- default licenses, system settings, and the AI prompt library.

The seed is **idempotent** — safe to run multiple times.

---

## 5. First login

Open http://localhost:5173 in your browser and log in with the
credentials from `.env`:

| Field    | Default value      |
|----------|--------------------|
| Username | `admin`            |
| Password | `changeme_admin`   |

> **Change the password from `Profile → Change password` immediately
> after first login.** The default is documented in this file and in
> `.env.example` — leaving it as-is on a publicly reachable instance
> is a security incident waiting to happen.

---

## 6. Verify everything is running

| Service    | URL                                          | Notes                              |
|------------|----------------------------------------------|------------------------------------|
| Frontend   | http://localhost:5173                        | Vue SPA with hot reload            |
| Backend    | http://localhost:8000/api/v1/health          | Should return `status: healthy`    |
| API docs   | http://localhost:8000/api/docs               | Swagger UI (dev mode only)         |
| eXist-db   | http://localhost:8080/exist/apps/dashboard   | Login: `admin` / *(empty password)* |
| PostgreSQL | `make shell-db`                              | psql in the container              |

Quick health check from the terminal:

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

## 7. Run the test suite

Tests run inside the backend container against a SQLite in-memory
database — no external services needed.

```bash
make test          # with coverage report
make test-v        # verbose output + short tracebacks
```

Run a single test file:

```bash
make test-file FILE=app/tests/test_scaffolding.py
```

---

## 8. Daily workflow

```bash
make up            # start (skips build if images are current)
make down          # stop (volumes are preserved → your data survives)
make restart       # down + up

make logs          # follow logs for all services (Ctrl+C to stop watching)
make logs-be       # backend logs only
make logs-db       # postgres logs only
make logs-xml      # existdb logs only

make lint          # ruff + mypy
make format        # ruff format
make typecheck     # mypy --strict

make help          # list every available make target with a one-line description
```

---

## 9. Reset everything

To wipe **all** data — every collection, user, document — and start
from scratch:

```bash
make down
docker volume rm aracne2_postgres_data aracne2_existdb_data
make up
make migrate
make seed
```

This is destructive. Keep a backup if you have any work-in-progress
data you care about.

---

## Troubleshooting

**`permission denied while trying to connect to the Docker daemon socket`**
→ Your user is not in the `docker` group, or Docker is installed via
  Snap. Install Docker Engine from https://get.docker.com, then:
  `sudo usermod -aG docker $USER && newgrp docker`.

**Backend fails with `error parsing value for field "cors_origins"`**
→ Your `.env` has inline comments (e.g.
  `CORS_ORIGINS=http://... # comment`). Comments must be on their own
  line — copy `.env.example` again and re-fill values.

**Backend fails with `JWT_SECRET must be at least 64 characters`**
→ Your `.env` has an empty or short `JWT_SECRET`. Generate one:
  `python3 -c "import secrets; print(secrets.token_hex(64))"`.

**eXist-db shows `status: error` in the health check**
→ Make sure `EXIST_PASSWORD=` is empty in your `.env` (no value after
  the `=`). Then do a full reset:
  `make down && docker volume rm aracne2_existdb_data && make up`.

**eXist-db dashboard asks for a password**
→ Leave the password field empty. eXist-db 6.4.1 starts with an
  empty admin password.

**Login page rejects `admin` / `changeme_admin`**
→ Step 4 (`make seed`) was not run. Run it now — it will create the
  admin user the first time and silently no-op on subsequent runs.

**Port already in use**
→ All ports are bound to `127.0.0.1` only. Check for conflicting
  local services: `sudo lsof -i :5432` / `:8080` / `:8000` / `:5173`.
  PostgreSQL running on the host? `sudo systemctl stop postgresql`.

**Frontend page is blank or stuck on a spinner**
→ Hard-refresh (`Ctrl+Shift+R` or `Cmd+Shift+R`). If it persists, the
  frontend container is probably still building — check
  `make logs` for `vite` output. The first build can take ~3
  minutes.
