# Aracne2 — Operations Guide

Operational reference for whoever runs the Aracne2 stack (sysadmin / operator).
Scope: how to apply configuration changes, rotate credentials, diagnose
common problems.

For in-app administration (users, roles, collections, settings UI) see
[USER_MANUAL.md](USER_MANUAL.md). For the eXist-db user model and bootstrap
details see [reference/EXISTDB_SETUP.md](reference/EXISTDB_SETUP.md).

---

## Post-pull checklist

After `git pull` in the test/production directory, the commands needed
depend on *what* changed in the pull.

| Change touched…                                                                        | Command                                             |
| -------------------------------------------------------------------------------------- | --------------------------------------------------- |
| `frontend/src/` or `frontend/public/` only                                             | nothing — Vite hot-reload picks it up               |
| any file in `frontend/` *outside* `src/`/`public/` (`tailwind.config.js`, `vite.config.ts`, `tsconfig.json`, `package.json`, `postcss.config.*`, `Dockerfile`) | `docker compose up -d --build frontend`             |
| Python dependencies (`backend/requirements.txt`) or `backend/app/main.py`              | `docker compose up -d --build backend`              |
| New Alembic migration (files in `backend/alembic/versions/`)                           | `docker compose exec backend alembic upgrade head`  |
| `.env` (most variables — see next section for exceptions)                              | `docker compose up -d`                              |
| `docker-compose.yml` or `docker-compose.prod.yml`                                      | `docker compose up -d`                              |

If nothing above applies, `git pull` alone is enough.

---

## Environment variables (`.env`)

### General rule

After editing `.env`:

```bash
docker compose up -d
```

Compose compares the effective environment of each running container with the
new configuration and **recreates** the services whose variables changed. A
plain `docker compose restart` is **not enough** — restart reuses the original
environment the container was created with. If Compose fails to detect the
change (rare), force it:

```bash
docker compose up -d --force-recreate backend frontend
```

### Exceptions — first-boot-only variables

These are consumed the very first time the corresponding service starts and
then ignored. Changing them later in `.env` has no effect on the running
system; you must rotate the underlying secret inside the service itself. See
[Credential rotation](#credential-rotation) below.

| Variable                     | Used at              | Where the value actually lives after first boot |
| ---------------------------- | -------------------- | ----------------------------------------------- |
| `POSTGRES_PASSWORD`          | PostgreSQL first init | `postgres_data` volume (pg\_shadow)             |
| `EXIST_PASSWORD`             | eXist-db admin       | `existdb_data` volume (security config)         |
| `EXISTDB_APP_PASSWORD`       | Aracne2 bootstrap    | `existdb_data` volume (aracne user)             |
| `ADMIN_USERNAME` / `ADMIN_EMAIL` / `ADMIN_PASSWORD` | Backend seed | `users` table in PostgreSQL                    |

---

## Credential rotation

### PostgreSQL (`POSTGRES_PASSWORD`)

```bash
# 1. Change the password inside the running DB
docker compose exec postgres psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
  -c "ALTER USER \"$POSTGRES_USER\" WITH PASSWORD 'new_password';"

# 2. Update .env with the same new value

# 3. Recreate backend so it picks up the new connection string
docker compose up -d backend
```

### eXist-db admin (`EXIST_PASSWORD`) and aracne runtime user (`EXISTDB_APP_PASSWORD`)

See the full recipe in
[reference/EXISTDB_SETUP.md § First-run sequence](reference/EXISTDB_SETUP.md#first-run-sequence)
and § "Changing the admin password (production)".

Short version for post-bootstrap rotation:

```bash
# 1. Change the password via the eXist-db Dashboard
#    (http://localhost:8080/exist/apps/dashboard → Security → Users)
#    OR via an XQuery call:
#      sm:passwd('admin', 'new_admin_password')

# 2. Update EXIST_PASSWORD (and/or EXISTDB_APP_PASSWORD) in .env

# 3. Recreate backend
docker compose up -d backend
```

### Platform admin user (`ADMIN_*`)

These seed variables create the first admin on the first backend boot. After
that, change the admin credentials inside the app:

- **Username / email**: the admin user edits their own profile at
  `/profile` (or another Admin edits them via `/users/:username`).
- **Password**: `POST /api/v1/auth/password/change` (or the "Change password"
  form under `/profile`).

### JWT secret (`JWT_SECRET`)

Rotating invalidates every active session (users will have to log in again)
and every refresh cookie. After editing:

```bash
docker compose up -d backend
```

---

## Troubleshooting

### `Bind for 0.0.0.0:<port> failed: port is already allocated`

Another container or host process is bound to the same port (Postgres 5432,
backend 8000, frontend 5173, eXist-db 8080). Typical causes:

- A sibling project's stack is still up (e.g. another docker-compose project).
  `docker ps | grep <port>` identifies the culprit; `docker stop <name>`
  releases it.
- A native PostgreSQL service is running on the host.
  `systemctl stop postgresql` or `pg_ctlcluster stop`.

After freeing the port, `docker compose up -d` again.

> **Watch-out**: if the first `docker compose up -d` partially succeeded with
> the port still taken, one container may be in a half-attached state
> (`NetworkSettings.Networks = {}` in `docker inspect`), making other services
> unable to resolve its name over the Compose network. Fix by bringing the
> whole stack down and back up:
> `docker compose down && docker compose up -d`.

### Backend returns `relation "users" does not exist` on login

The backend started before PostgreSQL was ready; the lifespan seed failed;
Alembic was never run. Apply migrations, then re-seed:

```bash
docker compose exec backend alembic upgrade head
docker compose restart backend   # re-runs lifespan seed
```

### DNS: service name resolves to `127.0.0.1` instead of the container IP

Some consumer routers (notably Telecom Italia *homenet* DHCP) inject a search
domain into `/etc/resolv.conf` and wildcard every unknown name to `127.0.0.1`.
Symptom: inside the backend container,

```bash
getent hosts postgres
# 127.0.0.1  postgres.homenet.telecomitalia.it
```

while `getent hosts existdb` resolves correctly. Root cause is almost always
a container that was created with `NetworkSettings.Networks = {}` (see the
previous troubleshooting note — not actually a DNS problem). Recreate the
affected container with `docker compose up -d --force-recreate <service>`.

### eXist-db: `401 Unauthorized` on `ensure_root.xq` or `bootstrap_user.xq`

The backend cannot authenticate to eXist-db as `admin`. eXist-db 6.x starts
with an **empty** admin password by default. The recommended first-boot
recipe:

1. Leave `EXIST_PASSWORD=` (empty) in `.env` at first boot. This matches
   eXist-db's default.
2. Set a non-empty `EXISTDB_APP_PASSWORD=<something>` so the backend can
   create the `aracne` runtime user.
3. `docker compose up -d` — the backend's lifespan runs `ensure_root.xq` and
   `bootstrap_user.xq` against the empty admin password and creates `aracne`.
4. Verify in the eXist-db Dashboard (`http://localhost:8080/exist/apps/dashboard/`
   → Security → Users) that `aracne` exists.
5. Set a non-empty admin password in the Dashboard (Security → Users → admin
   → Edit).
6. Update `EXIST_PASSWORD=<the_new_admin_password>` in `.env` and
   `docker compose up -d backend`. At this point bootstrap XQueries use the
   new admin password, but in practice the `aracne` user already exists and
   subsequent runs are idempotent.

If you see `401` on a running system (not first boot), the likely cause is a
mismatch between `.env` and the actual password set in the eXist-db Users
table. Reset via the Dashboard and run `docker compose up -d backend`.

---

## Logs and diagnostics

*(Placeholder — to be filled in as we encounter cases worth documenting.)*

Quick commands:

```bash
docker compose logs -f               # all services, follow
docker compose logs backend --tail=100
docker compose logs postgres --tail=50
docker compose logs existdb --tail=50
```

Backend emits structured JSON logs via structlog in production and console
logs in development. Every HTTP request carries a `request_id` that is also
echoed in the `X-Request-ID` response header — use it to correlate frontend
errors with backend traces.

Health endpoint (also used by the Docker healthcheck):

```bash
curl -s http://127.0.0.1:8000/api/v1/health | jq
```

Returns per-service status for PostgreSQL and eXist-db plus the overall
backend version.

---

## Backup and restore

*(Placeholder — to be expanded.)*

Three layers to back up:

1. **Platform data** — `postgres_data` volume. `pg_dump` for logical
   backups, or `docker run --rm -v aracne2_postgres_data:/data ...` snapshot
   for volume-level copies.
2. **Document data** — `existdb_data` volume plus the per-collection archives
   downloadable from the built-in Backup plugin (`Admin → Backup`).
3. **Configuration** — `.env`, `docker-compose.yml`, any uploaded TEI schemas
   and XSLT templates (paths configured by `SCHEMAS_DIR`, persistent media
   under `MEDIA_DIR`).

---

## Dependency upgrades

*(Placeholder — to be expanded.)*

- **Backend Python deps**: edit `backend/requirements.txt`, then
  `docker compose up -d --build backend`.
- **Frontend Node deps**: edit `frontend/package.json` (and regenerate
  `package-lock.json` locally with `npm install`), then
  `docker compose up -d --build frontend`.
- **Base images** (Postgres, eXist-db, Node, Python): edit
  `docker-compose.yml` / `Dockerfile`. Pin exact versions and review the
  upgrade notes before bumping.
