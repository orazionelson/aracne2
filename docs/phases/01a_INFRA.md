# PHASE 01a — Infrastructure: Docker, nginx, Makefile, .env
# Prerequisite: CLAUDE.md loaded (automatic in Claude Code) or 00_SESSION_INIT.md sent.
# Goal: fully reproducible environment. Verifiable output:
#   `make up` → all services healthy
#   `curl http://localhost:8000/api/v1/health` → 200

Implement everything below. Do not omit any file. Do not add unrequested features.
Every file must be complete and working.

---

## File: docker-compose.yml

Four always-on services on internal network `aracne2` plus two optional
services activated through Compose profiles. Healthcheck on every service.
Backend and frontend depend on the databases with `condition: service_healthy`.

Optional services:

- **`evt`** under profile `evt` — EVT 2 viewer for public reading of
  published collections.
- **`ollama`** and **`pgvector`** under profile `ai-local` — local LLM
  inference (Ollama) and the RAG vector store (pgvector/pgvector:pg15).
  Bring them up together with `docker compose --profile ai-local up -d`.
  The backend connects lazily: if the profile is not active, AI keeps
  working through remote providers and RAG silently falls back to an
  empty injected context.

**postgres**
- image: `postgres:15-alpine`
- environment: POSTGRES_DB, POSTGRES_USER, POSTGRES_PASSWORD (from .env)
- volume: `postgres_data:/var/lib/postgresql/data`
- healthcheck: `pg_isready -U $$POSTGRES_USER -d $$POSTGRES_DB`
  interval 5s, timeout 5s, retries 10
- exposed port: 5432 (bind to 127.0.0.1 only)

**existdb**
- image: `existdb/existdb:6.2.0`
- environment: `EXIST_PASSWORD` (native image variable, from .env —
  distinct from `EXISTDB_PASSWORD` used by the backend)
- volume: `existdb_data:/exist/data`
- exposed port: 8080 (bind to 127.0.0.1 only)
- healthcheck: `wget -qO- http://localhost:8080/exist/rest/ || exit 1`
  interval 10s, timeout 10s, retries 12, start_period 30s
  (eXist-db is slow to start: start_period is mandatory)

**backend**
- build: `context: ./backend`
- env_file: `.env`
- volumes: `./backend:/app` (hot reload), anonymous volume for `__pycache__`
- command: `uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload`
- exposed port: 8000 (bind to 127.0.0.1 only)
- depends_on: postgres (healthy), existdb (healthy)
- healthcheck: `curl -f http://localhost:8000/api/v1/health || exit 1`
  interval 10s, timeout 5s, retries 5, start_period 10s

**frontend**
- build: `context: ./frontend`
- env_file: `.env`
- volumes: `./frontend/src:/app/src` (hot reload)
- command: `npm run dev -- --host 0.0.0.0`
- exposed port: 5173 (bind to 127.0.0.1 only)
- depends_on: backend (healthy)

---

## File: docker-compose.prod.yml

Extends and overrides docker-compose.yml for production:
- **backend**: command `uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4`
  No source code volumes. ENVIRONMENT=production.
- **frontend**: removed. Replaced by an **nginx** service serving files built
  from the multi-stage image (see frontend Dockerfile).
- **nginx** (new service): image `nginx:alpine`, port 80,
  volume for nginx.conf, depends_on backend.
  Routes: `/api/*` → proxy_pass http://backend:8000,
          everything else → /usr/share/nginx/html (SPA dist)
- No source code volumes on any service.

---

## File: nginx.conf

```nginx
server {
    listen 80;
    root /usr/share/nginx/html;
    index index.html;

    # Compression
    gzip on;
    gzip_types text/plain text/css application/json application/javascript;

    # Allow XML uploads up to 50MB
    client_max_body_size 50m;

    # Security headers
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;
    add_header Permissions-Policy "camera=(), microphone=(), geolocation=()" always;
    add_header Content-Security-Policy "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; font-src 'self'; frame-ancestors 'none'" always;
    # Uncomment when HTTPS is active:
    # add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;

    # API: proxy to backend
    location /api/ {
        proxy_pass http://backend:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        add_header Cache-Control "no-cache, no-store, must-revalidate";
    }

    # Hashed assets: aggressive cache
    location /assets/ {
        expires 1y;
        add_header Cache-Control "public, immutable";
    }

    # SPA fallback: serve index.html for all unmatched routes
    location / {
        try_files $uri $uri/ /index.html;
        add_header Cache-Control "no-cache";
    }
}
```

---

## File: .env.example

```bash
# ── PostgreSQL ───────────────────────────────────────────────────────────────
POSTGRES_HOST=postgres
POSTGRES_PORT=5432
POSTGRES_DB=aracne2
POSTGRES_USER=aracne2
POSTGRES_PASSWORD=changeme_postgres        # CHANGE in production

# ── eXist-db ─────────────────────────────────────────────────────────────────
EXISTDB_URL=http://existdb:8080
EXISTDB_USER=admin
EXISTDB_PASSWORD=changeme_existdb          # CHANGE in production — used by Python backend
EXIST_PASSWORD=changeme_existdb            # CHANGE in production — used by existdb container
                                           # must match EXISTDB_PASSWORD

# ── JWT ──────────────────────────────────────────────────────────────────────
# Generate with: python -c "import secrets; print(secrets.token_hex(64))"
JWT_SECRET=                                # REQUIRED — minimum 64 characters
JWT_ACCESS_EXPIRY_MINUTES=60
JWT_REFRESH_EXPIRY_DAYS=30

# ── Security ─────────────────────────────────────────────────────────────────
BCRYPT_ROUNDS=12
# Production: CORS_ORIGINS=https://yourdomain.com,https://www.yourdomain.com
CORS_ORIGINS=http://localhost:5173

# ── Application ──────────────────────────────────────────────────────────────
ENVIRONMENT=development                    # development | production | test
LOG_LEVEL=INFO
PLATFORM_NAME=Aracne2
PUBLIC_REGISTRATION=false
MAX_UPLOAD_SIZE_MB=50

# ── Initial admin seed (used only by `make seed`) ────────────────────────────
ADMIN_USERNAME=admin
ADMIN_EMAIL=admin@example.com
ADMIN_PASSWORD=changeme_admin              # CHANGE immediately after first seed
```

---

## File: Makefile

All targets must work on Linux and macOS.
Use `.PHONY` for all non-file targets. Use `@` to silence redundant output.
Each target prints a descriptive line before executing.

```makefile
.PHONY: up down restart logs logs-be logs-db logs-xml \
        shell-be shell-db shell-xml migrate migrate-new migrate-down \
        seed test test-v test-file lint format typecheck \
        build-prod up-prod help

up:           ## Start all services in background (build if needed)
down:         ## Stop and remove containers (volumes are preserved)
restart:      ## down + up
logs:         ## Follow logs for all services
logs-be:      ## Follow backend logs only
logs-db:      ## Follow postgres logs only
logs-xml:     ## Follow existdb logs only

shell-be:     ## Open bash in the backend container
shell-db:     ## Open psql in the postgres container
shell-xml:    ## Print eXist-db dashboard URL (http://localhost:8080/exist/apps/dashboard)

migrate:      ## Run alembic upgrade head in the backend container
migrate-new:  ## Create new migration (MSG="description" required)
migrate-down: ## Run alembic downgrade -1

seed:         ## Run seed.py in the backend container (idempotent)

test:         ## Run pytest with coverage in the backend container
test-v:       ## pytest -v --tb=short
test-file:    ## pytest on a specific file (FILE=path/to/test.py)

lint:         ## ruff check + mypy in the backend container
format:       ## ruff format in the backend container
typecheck:    ## mypy --strict in the backend container

build-prod:   ## Build production images
up-prod:      ## Start production stack

help:         ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
	awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'
```
