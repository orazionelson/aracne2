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

## Local AI (Ollama)

Aracne2 ships with an optional Ollama service for on-premise inference — the
AI plugin can dispatch prompts to a locally-hosted model (Llama, Qwen,
Mistral, Gemma …) instead of a remote provider. No data leaves the server.

### Enable the bundled Ollama service

```bash
# Start the stack with the ai-local profile (adds the ollama container):
docker compose --profile ai-local up -d

# Pull at least one model into the volume (one-time, 4–8 GB per model):
docker compose exec ollama ollama pull llama3.1:8b

# List installed models:
docker compose exec ollama ollama list
```

Then in the admin UI → **Settings → AI → Provider & API keys**:

| Key                    | Value                         |
| ---------------------- | ----------------------------- |
| `ai_provider`          | `ollama`                      |
| `ai_ollama_base_url`   | `http://ollama:11434` (default) |
| `ai_ollama_model`      | `llama3.1:8b` (or another pulled model) |

No API key is required for the `ollama` provider.

### Use a host-installed Ollama instead

If you already run Ollama on the host (`systemctl start ollama`), skip the
profile and point the backend at it:

```
ai_ollama_base_url = http://host.docker.internal:11434
```

On Linux without Docker Desktop, add to the backend service in
`docker-compose.yml`:

```yaml
    extra_hosts:
      - "host.docker.internal:host-gateway"
```

### Performance notes

- **CPU only**: works but slow. A 7–8B model quantised to Q4 takes 5–30 s
  for a typical response on a modern x86 CPU. Acceptable for background
  tasks (bibliography normalisation, named-entity extraction), painful for
  interactive chat.
- **GPU (NVIDIA)**: order-of-magnitude faster. Add to the `ollama` service:

  ```yaml
  deploy:
    resources:
      reservations:
        devices:
          - driver: nvidia
            count: all
            capabilities: [gpu]
  ```

  Requires the NVIDIA Container Toolkit on the host.
- **Apple Silicon**: run Ollama on the host (Metal acceleration); the
  bundled Docker service does not use Metal.

### Model choice

Sizes below are the default quantisation (Q4\_K\_M) as published on
[ollama.com/library](https://ollama.com/library); full-precision tags are 3–4×
larger. Rough RAM requirement ≈ model size + 1–2 GB for context / inference
state. Values are indicative and drift over time — always verify on the
library page before pulling.

#### General-purpose chat / instruction models

| Model              | Size    | Min RAM | Notes                                                  |
| ------------------ | ------- | ------- | ------------------------------------------------------ |
| `llama3.2:1b`      | ~1.3 GB | 2 GB    | Tiny; only for trivial extraction / classification     |
| `llama3.2:3b`      | ~2.0 GB | 3 GB    | Decent small model; limited reasoning                  |
| `gemma2:2b`        | ~1.6 GB | 3 GB    | Google's small model; OK multilingual                  |
| `qwen2.5:3b`       | ~1.9 GB | 3 GB    | Strong small multilingual (Italian passable)           |
| `phi3:3.8b`        | ~2.2 GB | 4 GB    | Microsoft, reasoning-oriented                          |
| `mistral:7b`       | ~4.1 GB | 6 GB    | Lightweight 7B, English-centric                        |
| `llama3.1:8b`      | ~4.7 GB | 6 GB    | **Default**; balanced general-purpose                  |
| `qwen2.5:7b`       | ~4.7 GB | 6 GB    | Often best Italian / multilingual at this tier         |
| `gemma2:9b`        | ~5.4 GB | 7 GB    | Strong reasoning for its size                          |
| `mistral-nemo:12b` | ~7.1 GB | 9 GB    | Tekken tokeniser, good on code + mixed text            |
| `qwen2.5:14b`      | ~9.0 GB | 11 GB   | Step up in quality; best Italian at this tier          |
| `phi4:14b`         | ~9.0 GB | 11 GB   | Strong reasoning, decent multilingual                  |
| `gemma2:27b`       | ~16 GB  | 20 GB   | Near GPT-3.5 quality; CPU-borderline                   |
| `qwen2.5:32b`      | ~20 GB  | 24 GB   | Large; wants lots of RAM or a GPU                      |
| `llama3.3:70b`     | ~42 GB  | 48 GB+  | Strongest open model at this size; GPU strongly advised |

#### Specialised models

| Model                | Size    | Use                                             |
| -------------------- | ------- | ----------------------------------------------- |
| `qwen2.5-coder:7b`   | ~4.7 GB | XSLT / code generation                          |
| `qwen2.5-coder:14b`  | ~9.0 GB | XSLT / code generation, better quality          |
| `codellama:13b`      | ~7.4 GB | Older code model, broad language coverage       |
| `nomic-embed-text`   | ~0.3 GB | Embeddings (future semantic search / RAG)       |

#### Sweet spots for Aracne2

- **Mid-range server (16 GB RAM, CPU only)**: `qwen2.5:7b` or `llama3.1:8b`.
- **Workstation (32 GB RAM, or NVIDIA GPU 12–16 GB)**: `gemma2:9b` or `qwen2.5:14b`.
- **Large server / GPU 24 GB+**: `qwen2.5:32b` or `llama3.3:70b`.

Pull once, run many times:

```bash
docker compose exec ollama ollama pull qwen2.5:7b
docker compose exec ollama ollama list          # verify size on disk
docker compose exec ollama ollama rm <tag>      # reclaim space if needed
```

#### Switching the active model

Changing the model in use is a DB-only operation — no restart, no image
rebuild. The backend reads `ai_ollama_model` on every AI request.

1. Pull the new model: `docker compose exec ollama ollama pull <tag>`.
2. In **Settings → AI → Provider & API keys**, edit `ai_ollama_model` and
   save the new tag.
3. (Optional) `docker compose exec ollama ollama rm <old-tag>` to free disk.

The first request after the switch triggers a cold load of the new model
into memory (~5–20 s depending on size); subsequent requests are fast.
Ollama keeps the most recently used model resident by default and evicts
the previous one on memory pressure.

For TEI-heavy tasks (complex XSLT generation, multi-step domain reasoning),
local models below ~30B will consistently lag behind Claude / GPT-4o.
Reserve local inference for extractive, templated, or privacy-sensitive
tasks (bibliography normalisation, named-entity extraction, proof-reading).

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
