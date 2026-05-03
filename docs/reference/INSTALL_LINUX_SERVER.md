# Aracne2 — Linux server installation (test/dev and production)

Step-by-step guide to deploy Aracne2 on a Linux server in two
flavours: a **test/dev** instance for staging and integration work
(the kind a research group hosts to give editors a sandbox before
real publication), and a **production** instance reachable from the
public Internet.

For a *laptop install* see [quickstart.md](../quickstart.md). For
day-2 operations (credential rotation, log access, backups, AI
extras) see [docs/reference/OPERATIONS.md](OPERATIONS.md).

---

## Table of contents

1. [System requirements](#1-system-requirements)
2. [System dependencies](#2-system-dependencies)
3. [Test/dev install](#3-testdev-install)
4. [Production install](#4-production-install)
5. [Differences between test/dev and production](#5-differences-between-testdev-and-production)
6. [Optional services](#6-optional-services)
7. [Hardening checklist](#7-hardening-checklist)
8. [Upgrades](#8-upgrades)

---

## 1. System requirements

### Hardware

| Resource | Test/dev minimum | Production recommended |
|---|---|---|
| CPU | 2 vCPU | 4+ vCPU |
| RAM | 4 GB | 8+ GB (16 GB if you enable local AI / RAG) |
| Disk | 20 GB SSD | 50+ GB SSD on a separate data partition |
| Network | Outbound 443 (image pulls, lookups) | Inbound 80/443 reachable from clients; outbound 443 |

### OS

Anything recent that runs Docker Engine ≥ 24:

- Debian 12 / Ubuntu 22.04 LTS / Ubuntu 24.04 LTS — primary targets
- AlmaLinux / Rocky 9 — supported via the official Docker repo
- Other distros work; the commands below assume `apt`, adapt for
  `dnf` / `pacman` as needed.

> **Avoid Snap-based Docker.** It causes socket-permission
> incidents that are tedious to debug. Always install from the
> official Docker repo (https://get.docker.com) or your distro's
> packaged Docker Engine.

---

## 2. System dependencies

### Required for both test/dev and production

| Component | Why | Install |
|---|---|---|
| **Docker Engine ≥ 24** | runs all four containers | `curl -fsSL https://get.docker.com \| sh` |
| **Docker Compose plugin** | `docker compose` subcommand | bundled with the script above |
| **GNU Make** | wraps the compose commands | `sudo apt install -y make` |
| **git** | clone + pull updates | `sudo apt install -y git` |
| **curl** | health checks, secrets generation, image pulls | `sudo apt install -y curl` |
| **Python 3** (host) | one-liner to generate `JWT_SECRET` + scripts in `OPERATIONS.md` | `sudo apt install -y python3` |

After installing Docker, add your operator user to the `docker`
group so you don't need `sudo` for every command:

```bash
sudo usermod -aG docker "$USER"
newgrp docker     # re-evaluate group membership in current shell
docker run --rm hello-world   # smoke test
```

### Production only

| Component | Why | Notes |
|---|---|---|
| **A reverse proxy (nginx, Caddy, or Traefik)** on the host | terminate TLS, serve a single 443 surface, route to the bundled internal nginx on port 80 | The compose stack ships its **own** internal nginx (serves the SPA + proxies `/api` / `/sites` to backend). The host-level proxy you add **in front** of it does TLS termination + multi-tenancy. |
| **A TLS certificate** | HTTPS in production is non-negotiable | Free via Let's Encrypt + `certbot`; or commercial cert at your discretion. |
| **A persistent backup destination** | nightly Postgres + eXist + media dumps | S3, NFS, or rsync to a second host. See `docs/reference/OPERATIONS.md §Backup and restore`. |
| **systemd service for the docker stack** *(optional but strongly recommended)* | bring the stack up automatically after a reboot | A 12-line service unit; example below. |
| **A monitoring agent** *(optional)* | logs + metrics shipping | The platform already exposes Prometheus metrics at `/api/v1/metrics` and emits structured JSON logs in production. Wire to your existing infra. |

### Optional (both environments)

| Component | When to add it |
|---|---|
| **Ollama** *(host or compose profile)* | local AI provider for chat + embeddings — see `docs/reference/OPERATIONS.md §Local AI` |
| **GROBID** *(separate container)* | PDF → TEI conversion (future plugin) |
| **A SMTP relay** | when the deployment starts sending mail (password resets, notifications) |

---

## 3. Test/dev install

The test/dev profile is a **single-host, single-user** install
intended for editors to try things out, not for public traffic. It
uses the development compose file, the `vite` dev server with hot
reload, and the default `EXIST_PASSWORD=` empty for friction-less
first boot.

### 3.1 Clone and configure

```bash
git clone <repo-url> /opt/aracne2
cd /opt/aracne2
cp .env.example .env
```

Edit `.env`:

```dotenv
# Required — paste the output of:
#   python3 -c "import secrets; print(secrets.token_hex(64))"
JWT_SECRET=<a 64-char hex string>

POSTGRES_PASSWORD=<a strong random password>

# Leave empty for first boot; eXist-db starts with an empty admin password.
EXIST_PASSWORD=

# Required at first boot. Pick one and remember it — see § eXist-db notes
# in OPERATIONS.md if you ever need to rotate.
EXISTDB_APP_PASSWORD=<a strong random password>

# Default admin account that gets created by `make seed`.
# Pick a *non-default* password before running seed.
ADMIN_USERNAME=admin
ADMIN_EMAIL=ops@yourorg.example
ADMIN_PASSWORD=<a strong random password>

# CORS — the dev SPA is on :5173.
CORS_ORIGINS=["http://localhost:5173"]
```

### 3.2 Start

```bash
make up         # builds + starts postgres / existdb / backend / frontend
make migrate    # alembic upgrade head
make seed       # roles + default settings + admin user
```

### 3.3 First reach

The compose binds every port to `127.0.0.1` only — the test/dev
stack is **not** reachable from outside the host:

| Surface | URL on the host |
|---|---|
| SPA (Vite dev server) | http://127.0.0.1:5173 |
| Backend API | http://127.0.0.1:8000/api/v1 |
| eXist-db dashboard | http://127.0.0.1:8080/exist/apps/dashboard |

To let teammates use the test/dev instance, **don't expose it
directly**: use SSH port-forwarding or set up a separate reverse
proxy with HTTP basic-auth in front. Don't change `127.0.0.1:` to
`0.0.0.0:` in `docker-compose.yml` — the dev compose has no TLS and
the dev SPA prints debug info.

### 3.4 Day-to-day

```bash
make logs       # follow all services (Ctrl+C to stop watching)
make restart    # down + up (preserves volumes)
make test       # backend test suite
git pull && make migrate    # after code updates
```

After a `git pull` the right command depends on what changed —
[OPERATIONS.md §Post-pull checklist](OPERATIONS.md#post-pull-checklist)
has the matrix.

---

## 4. Production install

The production profile is a **public-facing** install: real
hostname, HTTPS, the SPA served as static assets by the bundled
internal nginx, the backend running with multiple uvicorn workers,
no Vite dev server, no debug surfaces.

### 4.1 Clone and configure

```bash
sudo mkdir -p /srv/aracne2
sudo chown "$USER:$USER" /srv/aracne2
git clone <repo-url> /srv/aracne2
cd /srv/aracne2
cp .env.example .env
```

Edit `.env`:

```dotenv
# Required — long-lived; keep in a secrets vault, not in version control.
JWT_SECRET=<a 64-char hex string>

POSTGRES_PASSWORD=<a strong random password>

# Set to a non-empty value before first boot — see OPERATIONS.md
# §Credential rotation if you need to rotate later.
EXIST_PASSWORD=<a strong random password>
EXISTDB_APP_PASSWORD=<a strong random password>

# Production environment — disables Swagger, switches to JSON logs,
# enables CSP enforcement and stricter cookie flags.
ENVIRONMENT=production

# Real CORS origins. Use the public hostname(s) the SPA is served
# from. No localhost in production. JSON array, no trailing comma.
CORS_ORIGINS=["https://aracne2.yourorg.example"]

# Admin user that `make seed` creates on first boot. The password
# is replaced at first login; pick something random and rotate it
# from the UI, then drop it from the .env once the user exists.
ADMIN_USERNAME=admin
ADMIN_EMAIL=ops@yourorg.example
ADMIN_PASSWORD=<a strong random password>
```

> **About `ENVIRONMENT=production`**: the backend reads this at
> startup. Setting it has cascading effects — Swagger / OpenAPI
> endpoints disappear, IP addresses are SHA-256-hashed before
> logging, structured logs switch from console-coloured to JSON,
> the CORS validator rejects bare-`http://` non-localhost origins,
> and rate-limit / CSP enforcement become non-bypassable. Don't
> ship a production deployment with `development`.

### 4.2 Build and start

```bash
make build-prod    # docker compose -f docker-compose.yml -f docker-compose.prod.yml build
make up-prod       # docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

The production compose merges the two files: it disables the Vite
dev `frontend` service, builds the SPA into static assets stored in
the `frontend_dist` volume, and runs an internal `nginx:alpine`
container that serves the SPA + proxies `/api/`, `/sites/`,
`/robots.txt`, `/sitemap*.xml` to the backend. The backend itself
runs uvicorn with **4 workers** (vs. `--reload` in dev).

The internal nginx listens on port `80` of the container; the
compose file maps it to host `:80`. **Don't expose `:80` directly
to the Internet** — terminate TLS in the host-level reverse proxy
and forward to `127.0.0.1:80`.

### 4.3 Run migrations and seed

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml \
  exec backend alembic upgrade head
docker compose -f docker-compose.yml -f docker-compose.prod.yml \
  exec backend python -m app.db.seed
```

(`make migrate` and `make seed` work too — they delegate to the
backend container regardless of which compose files are active.)

### 4.4 Host-level reverse proxy + TLS

Example `nginx` site config terminating TLS on the host and
forwarding to the bundled internal nginx (which is on `127.0.0.1:80`
on the same host):

```nginx
server {
    listen 80;
    server_name aracne2.yourorg.example;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl http2;
    server_name aracne2.yourorg.example;

    ssl_certificate     /etc/letsencrypt/live/aracne2.yourorg.example/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/aracne2.yourorg.example/privkey.pem;
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;

    # Body size: matches the bundled nginx's 50 MB cap (large XML uploads).
    client_max_body_size 50m;

    location / {
        proxy_pass http://127.0.0.1:80;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;
    }
}
```

After the cert is in place, **uncomment** the
`Strict-Transport-Security` line in `aracne2/nginx.conf` and run
`docker compose ... up -d --force-recreate nginx` so HSTS is also
emitted by the bundled nginx in case it's ever reached without the
host proxy in front.

### 4.5 systemd unit (optional but recommended)

Bring the stack up after a host reboot. Save as
`/etc/systemd/system/aracne2.service`:

```ini
[Unit]
Description=Aracne2 docker compose stack
Requires=docker.service
After=docker.service network-online.target

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=/srv/aracne2
ExecStart=/usr/bin/docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
ExecStop=/usr/bin/docker compose -f docker-compose.yml -f docker-compose.prod.yml down

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now aracne2.service
```

### 4.6 First reach

`https://aracne2.yourorg.example` → SPA login. Sign in with the
seeded admin, change the password from `Profile → Change password`,
and start onboarding editors.

---

## 5. Differences between test/dev and production

A side-by-side reference. The first two columns are what changes
out of the box; the third is what *should* change but won't be
caught by the compose files.

| Aspect | Test/dev | Production |
|---|---|---|
| Compose files | `docker-compose.yml` | `docker-compose.yml` + `docker-compose.prod.yml` |
| Frontend | `vite` dev server with hot reload, served from container :5173 | Built once into `frontend_dist`, served as static by the bundled internal nginx on :80 |
| Backend command | `uvicorn ... --reload` (single worker) | `uvicorn ... --workers 4` |
| `ENVIRONMENT` env var | `development` | `production` |
| Swagger / OpenAPI | exposed at `/api/docs` and `/api/openapi.json` | disabled |
| Logging | console-coloured human-readable | JSON-lines via structlog |
| IP addresses in logs | plaintext | SHA-256-hashed (salt = `JWT_SECRET`) |
| CORS validator | accepts `http://` for non-localhost (warning only) | rejects bare `http://` for non-localhost |
| `EXIST_PASSWORD` | empty (first boot) | non-empty mandatory |
| `EXISTDB_APP_PASSWORD` | optional in initial dev | required |
| Default admin password | `changeme_admin` from `.env.example` | **must** be rotated before exposing the install |
| Cookie flags on refresh token | `httpOnly; SameSite=Strict` | `httpOnly; SameSite=Strict; Secure` (HTTPS only) |
| HSTS header | commented out in `nginx.conf` | uncommented after TLS is in place |
| Rate limiting | active, generous defaults | active, **same** defaults — tune in `app/middleware/rate_limiter.py` if you expect high traffic |
| Port binding | `127.0.0.1:5173/8000/8080/5432` | `:80` (mapped from internal nginx) — sit behind a host reverse proxy with TLS |
| TLS | none | mandatory, terminated on the host reverse proxy |
| Backups | optional | nightly minimum — see `docs/reference/OPERATIONS.md §Backup and restore` |
| systemd auto-start | optional | recommended — see §4.5 |
| Frontend hot reload | yes | no (rebuild + redeploy required after code changes) |

---

## 6. Optional services

These services are gated behind Compose `profiles` so they don't
run by default. Activate explicitly when you need them.

### 6.1 EVT 2 viewer

Public reading interface for published editions. See
[reference/NON_NATIVE_PLUGINS.md §11](reference/NON_NATIVE_PLUGINS.md).

```bash
docker compose --profile evt build evt
docker compose --profile evt up -d evt
```

Then activate the `evt` plugin in `/admin/plugins` and flip the
`evt_enabled` setting in **Settings → General**.

### 6.2 Local AI (Ollama + pgvector for RAG)

Self-hosted AI provider — no external API keys, traffic stays on
the host. Both modest hardware-hungry: budget at least 4 extra GB
of RAM and an SSD.

See `docs/reference/OPERATIONS.md §Local AI (Ollama)` and `§Local AI — RAG`
for full instructions, model choice, and ingestion of the TEI P5
Guidelines into the embeddings index.

```bash
docker compose --profile ai-local up -d
```

### 6.3 Cloud AI

OpenAI / Anthropic / Gemini work without any compose profile —
just configure the API key in **Settings → AI** in the SPA. The
keys are Fernet-encrypted at rest (key derived from `JWT_SECRET`).

---

## 7. Hardening checklist

Before exposing a production install to the public:

- [ ] All passwords in `.env` are random, not the `changeme_*`
      defaults from `.env.example`.
- [ ] `JWT_SECRET` is ≥ 64 hex chars and stored in a secrets
      vault, not in any git history.
- [ ] `ENVIRONMENT=production` is set.
- [ ] `CORS_ORIGINS` lists only the public HTTPS origins of the
      SPA. No `http://`, no localhost.
- [ ] The default admin password was changed from the UI after the
      first login, and the `.env` `ADMIN_PASSWORD` was scrubbed.
- [ ] TLS cert is in place on the host-level reverse proxy.
- [ ] HSTS is uncommented in `aracne2/nginx.conf`.
- [ ] The compose ports for postgres / eXist-db / backend
      (`5432 / 8080 / 8000`) are bound to `127.0.0.1` only — never
      exposed to the public Internet. The bundled nginx on `:80`
      is the only public surface.
- [ ] systemd unit is enabled, so the stack survives a host
      reboot.
- [ ] A backup job is scheduled and a restore was rehearsed at
      least once.
- [ ] Logs are shipped or rotated — Docker's default JSON log
      driver retains forever otherwise.
- [ ] If you enabled **plugins that hold credentials** (Zenodo,
      Codeberg, GitHub, GitLab, Dataverse, Internet Archive,
      Zotero, MCP server), the values are entered through the
      Admin UI — they're stored Fernet-encrypted, never in `.env`.
- [ ] If the deployment runs **MCP**, every issued token has a
      meaningful label and `last_used_at` is monitored — see the
      corpora admin panel.
- [ ] A maintenance contact is documented somewhere visible
      (`/admin/settings → Contact email` is the conventional
      place — surfaced on the public homepage when set).
- [ ] You ran `pytest` at least once on this host to confirm the
      suite passes against the local Postgres / eXist-db.

---

## 8. Upgrades

```bash
cd /srv/aracne2
git pull
```

Then apply the right command from
[docs/reference/OPERATIONS.md §Post-pull checklist](OPERATIONS.md#post-pull-checklist) —
which command to run depends on whether the pull touched
migrations, Python deps, frontend root configs, or `src/` only.

For production, prefer to **stop the stack outside business hours**
when the pull contains migrations:

```bash
make down
git pull
make build-prod    # only if frontend root or backend deps changed
make up-prod
docker compose ... exec backend alembic upgrade head
```

A migration that adds an index to a large table can take minutes —
don't run it during a peak.

---

## See also

- [quickstart.md](../quickstart.md) — laptop / first-time-with-the-codebase install
- [docs/reference/OPERATIONS.md](OPERATIONS.md) — credential rotation, logs, backups, AI extras
- [docs/reference/EXISTDB_SETUP.md](reference/EXISTDB_SETUP.md) — eXist-db user model + bootstrap details
- [docs/reference/API_FORMAT.md](reference/API_FORMAT.md) — API response envelope spec
- [docs/reference/NON_NATIVE_PLUGINS.md](reference/NON_NATIVE_PLUGINS.md) — per-plugin operational notes
- [CLAUDE.md](../CLAUDE.md) — development context (codebase conventions, stack)
