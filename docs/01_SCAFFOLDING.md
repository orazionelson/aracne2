# ═══════════════════════════════════════════════════════════════════════════════
# PROMPT 01 — SCAFFOLDING & INFRASTRUTTURA
# Prerequisito: invia 00_MASTER_CONTEXT.md prima di questo prompt.
# Obiettivo: ambiente completamente riproducibile. Output verificabile:
#   `make up` → tutti i servizi healthy
#   `curl http://localhost:8000/api/v1/health` → 200
# ═══════════════════════════════════════════════════════════════════════════════

Implementa TUTTO ciò che segue. Non omettere nessun file. Non aggiungere
funzionalità non richieste. Ogni file deve essere completo e funzionante.

---

## PARTE A — Infrastruttura Docker e ambiente

### File: docker-compose.yml

Quattro servizi su rete interna `teiplatform`. Healthcheck su ogni servizio.
Backend e frontend dipendono dai DB con `condition: service_healthy`.

**postgres**
- image: `postgres:15-alpine`
- environment: POSTGRES_DB, POSTGRES_USER, POSTGRES_PASSWORD (da .env)
- volume: `postgres_data:/var/lib/postgresql/data`
- healthcheck: `pg_isready -U $$POSTGRES_USER -d $$POSTGRES_DB`
  interval 5s, timeout 5s, retries 10
- porta esposta: 5432 (bind solo su 127.0.0.1)

**existdb**
- image: `existdb/existdb:6.2.0`
- environment: `EXIST_PASSWORD` (variabile nativa dell'immagine, da .env — distinta da `EXISTDB_PASSWORD` usata dal backend)
- volume: `existdb_data:/exist/data`
- porta esposta: 8080 (bind solo su 127.0.0.1)
- healthcheck: `wget -qO- http://localhost:8080/exist/rest/ || exit 1`
  interval 10s, timeout 10s, retries 12, start_period 30s
  (eXist-db è lento ad avviarsi: start_period è obbligatorio)

**backend**
- build: `context: ./backend`
- env_file: `.env`
- volumes: `./backend:/app` (hot reload), anonymous volume per `__pycache__`
- command: `uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload`
- porta esposta: 8000 (bind solo su 127.0.0.1)
- depends_on: postgres (healthy), existdb (healthy)
- healthcheck: `curl -f http://localhost:8000/api/v1/health || exit 1`
  interval 10s, timeout 5s, retries 5, start_period 10s

**frontend**
- build: `context: ./frontend`
- env_file: `.env`
- volumes: `./frontend/src:/app/src` (hot reload)
- command: `npm run dev -- --host 0.0.0.0`
- porta esposta: 5173 (bind solo su 127.0.0.1)
- depends_on: backend (healthy)

---

### File: docker-compose.prod.yml

Estende e sovrascrive docker-compose.yml per produzione:
- **backend**: command `uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4`
  Nessun volume di codice sorgente. ENVIRONMENT=production.
- **frontend**: rimosso. Al suo posto un servizio **nginx** che serve
  i file buildati dalla image multi-stage (vedi Dockerfile frontend).
- **nginx** (nuovo servizio): image `nginx:alpine`, porta 80,
  volume per nginx.conf, depends_on backend.
  Serve: `/api/*` → proxy_pass http://backend:8000,
         tutto il resto → /usr/share/nginx/html (SPA dist)
- Nessun volume di codice sorgente su nessun servizio.

---

### File: nginx.conf

```nginx
server {
    listen 80;
    root /usr/share/nginx/html;
    index index.html;

    # Compressione
    gzip on;
    gzip_types text/plain text/css application/json application/javascript;

    # Upload XML fino a 50MB
    client_max_body_size 50m;

    # Security headers
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;
    add_header Permissions-Policy "camera=(), microphone=(), geolocation=()" always;
    add_header Content-Security-Policy "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; font-src 'self'; frame-ancestors 'none'" always;
    # Decommenta quando HTTPS è attivo:
    # add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;

    # API: proxy al backend
    location /api/ {
        proxy_pass http://backend:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        add_header Cache-Control "no-cache, no-store, must-revalidate";
    }

    # Assets con hash: cache aggressiva
    location /assets/ {
        expires 1y;
        add_header Cache-Control "public, immutable";
    }

    # SPA fallback: tutto il resto serve index.html
    location / {
        try_files $uri $uri/ /index.html;
        add_header Cache-Control "no-cache";
    }
}
```

---

### File: .env.example

```bash
# ── PostgreSQL ──────────────────────────────────────────────────────────────
POSTGRES_HOST=postgres
POSTGRES_PORT=5432
POSTGRES_DB=teiplatform
POSTGRES_USER=teiplatform
POSTGRES_PASSWORD=changeme_postgres       # CAMBIA in produzione

# ── eXist-db ────────────────────────────────────────────────────────────────
EXISTDB_URL=http://existdb:8080
EXISTDB_USER=admin
EXISTDB_PASSWORD=changeme_existdb         # CAMBIA in produzione — usata dal backend Python
EXIST_PASSWORD=changeme_existdb           # CAMBIA in produzione — usata dal container existdb (deve corrispondere a EXISTDB_PASSWORD)

# ── JWT ─────────────────────────────────────────────────────────────────────
# Genera con: python -c "import secrets; print(secrets.token_hex(64))"
JWT_SECRET=                               # OBBLIGATORIO — min 64 caratteri
JWT_ACCESS_EXPIRY_MINUTES=60
JWT_REFRESH_EXPIRY_DAYS=30

# ── Sicurezza ────────────────────────────────────────────────────────────────
BCRYPT_ROUNDS=12
# In produzione: CORS_ORIGINS=https://tuodominio.it,https://www.tuodominio.it
CORS_ORIGINS=http://localhost:5173

# ── Applicazione ─────────────────────────────────────────────────────────────
ENVIRONMENT=development                   # development | production | test
LOG_LEVEL=INFO
PLATFORM_NAME=Aracne2
PUBLIC_REGISTRATION=false
MAX_UPLOAD_SIZE_MB=50

# ── Seed admin iniziale (usato solo da `make seed`) ──────────────────────────
ADMIN_USERNAME=admin
ADMIN_EMAIL=admin@example.com
ADMIN_PASSWORD=changeme_admin             # CAMBIA immediatamente dopo il seed
```

---

### File: Makefile

Tutti i target devono funzionare su Linux e macOS.
Usa `.PHONY` per tutti i target non-file. Usa `@` per silenziare comandi ridondanti.
Ogni target stampa una riga descrittiva prima di eseguire.

```makefile
.PHONY: up down restart logs logs-be logs-db logs-xml \
        shell-be shell-db migrate migrate-new migrate-down \
        seed test test-v test-file lint format typecheck \
        build-prod up-prod help

up:           ## Avvia tutti i servizi in background (build se necessario)
down:         ## Ferma e rimuove i container (i volumi sono preservati)
restart:      ## down + up
logs:         ## Segui i log di tutti i servizi
logs-be:      ## Segui i log del solo backend
logs-db:      ## Segui i log del solo postgres
logs-xml:     ## Segui i log del solo existdb

shell-be:     ## Apre bash nel container backend
shell-db:     ## Apre psql nel container postgres
shell-xml:    ## Stampa URL dashboard eXist-db (http://localhost:8080/exist/apps/dashboard)

migrate:             ## Esegue alembic upgrade head nel container backend
migrate-new:         ## Crea nuova migrazione (MSG="descrizione" obbligatorio)
migrate-down:        ## Esegue alembic downgrade -1

seed:                ## Esegue seed.py nel container backend (idempotente)

test:                ## Esegue pytest con coverage nel container backend
test-v:              ## pytest -v --tb=short
test-file:           ## pytest su file specifico (FILE=path/to/test.py)

lint:                ## ruff check + mypy nel container backend
format:              ## ruff format nel container backend
typecheck:           ## mypy --strict nel container backend

build-prod:          ## Build immagini production
up-prod:             ## Avvia stack production

help:                ## Mostra questo help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
	awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'
```

---

## PARTE B — Backend

### File: backend/Dockerfile

```dockerfile
FROM python:3.12-slim

WORKDIR /app

# gcc e libpq-dev per asyncpg, curl per healthcheck
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl gcc libpq-dev && rm -rf /var/lib/apt/lists/*

# Layer cache: solo requirements prima del codice
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Utente non-root per sicurezza
RUN useradd -m -u 1000 appuser && chown -R appuser /app
USER appuser

EXPOSE 8000
```

---

### File: backend/requirements.txt (versioni pinnate)

```
fastapi==0.115.6
uvicorn[standard]==0.32.1
sqlalchemy[asyncio]==2.0.36
asyncpg==0.30.0
alembic==1.14.0
pydantic[email]==2.10.3
pydantic-settings==2.6.1
python-jose[cryptography]==3.3.0
passlib[bcrypt]==1.7.4
httpx==0.28.1
python-multipart==0.0.20
structlog==24.4.0
slowapi==0.1.9
pytest==8.3.4
pytest-asyncio==0.24.0
anyio==4.7.0
aiosqlite==0.20.0
ruff==0.8.4
mypy==1.13.0
coverage==7.6.9
```

---

### File: backend/pyproject.toml

```toml
[tool.ruff]
target-version = "py312"
line-length = 100

[tool.ruff.lint]
select = ["E","F","W","I","N","UP","ASYNC","S","B","A","C4","PT"]
ignore = ["S101"]

[tool.ruff.lint.per-file-ignores]
"app/tests/*" = ["S", "ARG"]

[tool.mypy]
python_version = "3.12"
strict = true
ignore_missing_imports = true
plugins = ["pydantic.mypy"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["app/tests"]
```

---

### File: backend/app/config.py

```python
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import computed_field, field_validator
from typing import Literal

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # PostgreSQL
    postgres_host: str
    postgres_port: int = 5432
    postgres_db: str
    postgres_user: str
    postgres_password: str

    @computed_field
    @property
    def database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    # eXist-db
    existdb_url: str
    existdb_user: str
    existdb_password: str

    # JWT
    jwt_secret: str
    jwt_access_expiry_minutes: int = 60
    jwt_refresh_expiry_days: int = 30

    @field_validator("jwt_secret")
    @classmethod
    def jwt_secret_min_length(cls, v: str) -> str:
        if len(v) < 64:
            raise ValueError("JWT_SECRET must be at least 64 characters")
        return v

    # Sicurezza
    bcrypt_rounds: int = 12
    cors_origins: list[str] = ["http://localhost:5173"]

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, v: str | list) -> list[str]:
        if isinstance(v, str):
            return [o.strip() for o in v.split(",")]
        return v

    # Applicazione
    environment: Literal["development", "production", "test"] = "development"
    log_level: str = "INFO"
    platform_name: str = "TEI Platform"
    public_registration: bool = False
    max_upload_size_mb: int = 50

    # Seed admin (obbligatorio solo per il comando `make seed`)
    admin_username: str = "admin"
    admin_email: str = "admin@example.com"
    admin_password: str | None = None  # None → seed admin skippato con warning esplicito

    @property
    def is_development(self) -> bool:
        return self.environment == "development"

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

# Singleton importato ovunque con: from app.config import settings
settings = Settings()
```

---

### File: backend/app/db/postgres.py

```python
from sqlalchemy.ext.asyncio import (
    AsyncSession, AsyncEngine,
    async_sessionmaker, create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase
from typing import AsyncGenerator
from app.config import settings

engine: AsyncEngine = create_async_engine(
    settings.database_url,
    echo=settings.is_development,  # logga SQL solo in dev
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,            # verifica la connessione prima dell'uso
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,        # evita lazy load dopo commit
    autoflush=False,
)

class Base(DeclarativeBase):
    pass

async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
```

---

### File: backend/app/db/existdb.py

Implementa `ExistDBClient` con tutti i metodi. Quelli non ancora implementati
sollevano `NotImplementedError("Implemented in FASE 05")` — non `pass` nudo.

```python
import httpx
from app.config import settings

class ExistDBClient:
    _client: httpx.AsyncClient | None = None

    async def connect(self) -> None:
        self._client = httpx.AsyncClient(
            base_url=settings.existdb_url,
            auth=(settings.existdb_user, settings.existdb_password),
            timeout=30.0,
            headers={"Accept": "application/json"},
        )

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()

    async def ping(self) -> bool:
        # GET /exist/rest/ — restituisce True se 200, False altrimenti. Never raise.
        if not self._client:
            return False
        try:
            r = await self._client.get("/exist/rest/")
            return r.status_code == 200
        except Exception:
            return False

    # Stub — implementati in FASE 05
    async def xquery(self, query_name: str, params: dict | None = None) -> dict:
        raise NotImplementedError("Implemented in FASE 05")

    async def store_document(
        self, collection_path: str, filename: str, xml_bytes: bytes,
        create_if_missing: bool = True
    ) -> str:
        raise NotImplementedError("Implemented in FASE 05")

    async def delete_document(self, collection_path: str, filename: str) -> None:
        raise NotImplementedError("Implemented in FASE 05")

    async def create_collection(self, path: str) -> None:
        raise NotImplementedError("Implemented in FASE 05")

    async def collection_exists(self, path: str) -> bool:
        raise NotImplementedError("Implemented in FASE 05")

    async def list_collection(self, path: str) -> list[str]:
        raise NotImplementedError("Implemented in FASE 05")

existdb_client = ExistDBClient()

async def get_existdb() -> ExistDBClient:
    return existdb_client
```

---

### File: backend/app/core/exceptions.py

```python
from dataclasses import dataclass, field

@dataclass
class PlatformException(Exception):
    code: str
    message: str
    status_code: int = 400
    details: dict = field(default_factory=dict)

class NotFoundError(PlatformException):
    def __init__(self, resource: str, identifier: str = "") -> None:
        label = f"{resource} '{identifier}'" if identifier else resource
        super().__init__(
            code="RESOURCE_NOT_FOUND",
            message=f"{label} not found",
            status_code=404,
        )

class ConflictError(PlatformException):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(code=code, message=message, status_code=409)

class AuthenticationError(PlatformException):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(code=code, message=message, status_code=401)

class AuthorizationError(PlatformException):
    def __init__(self, message: str = "Insufficient permissions") -> None:
        super().__init__(
            code="INSUFFICIENT_PERMISSIONS",
            message=message,
            status_code=403,
        )

class DomainValidationError(PlatformException):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(code=code, message=message, status_code=422)

class ExternalServiceError(PlatformException):
    def __init__(self, service: str, detail: str = "") -> None:
        super().__init__(
            code="EXTERNAL_SERVICE_ERROR",
            message=f"Service '{service}' unavailable",
            status_code=503,
            details={"service": service, "detail": detail},
        )
```

---

### File: backend/app/schemas/common.py

```python
from pydantic import BaseModel
from typing import Generic, TypeVar

T = TypeVar("T")

class PaginationMeta(BaseModel):
    page: int
    per_page: int
    total: int
    total_pages: int

class PaginatedResponse(BaseModel, Generic[T]):
    data: list[T]
    pagination: PaginationMeta

class DataResponse(BaseModel, Generic[T]):
    data: T

class ErrorDetail(BaseModel):
    code: str
    message: str
    details: dict = {}

class ErrorResponse(BaseModel):
    error: ErrorDetail

class HealthService(BaseModel):
    status: str   # "ok" | "error"
    detail: str | None = None  # solo in development

class HealthResponse(BaseModel):
    status: str   # "healthy" | "degraded"
    version: str
    environment: str
    services: dict[str, HealthService]
```

---

### File: backend/app/middleware/request_logger.py

Implementa come classe ASGI (non come `@app.middleware`):

```python
import uuid, time, structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = structlog.get_logger()

class RequestLoggerMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = str(uuid.uuid4())
        start = time.perf_counter()

        request.state.request_id = request_id

        response = await call_next(request)

        duration_ms = round((time.perf_counter() - start) * 1000, 2)

        # Non loggare /health in production per ridurre rumore
        skip = (
            request.url.path == "/api/v1/health"
            and not settings.is_development
        )
        if not skip:
            logger.info(
                "http_request",
                method=request.method,
                path=request.url.path,
                status_code=response.status_code,
                duration_ms=duration_ms,
                request_id=request_id,
                ip=request.headers.get("X-Forwarded-For", request.client.host
                   if request.client else "unknown"),
            )

        response.headers["X-Request-ID"] = request_id
        return response
```

Configura anche structlog in un modulo `app/core/logging.py`:
- In development: output console human-readable con colori
- In production: output JSON su stdout (per aggregatori di log)
- Chiamato da `main.py` prima di creare l'app

---

### File: backend/app/middleware/rate_limiter.py

```python
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from fastapi import Request
from fastapi.responses import JSONResponse

limiter = Limiter(key_func=get_remote_address, default_limits=["200/minute"])

STRICT_LIMIT = "10/minute"   # per /auth/login e /auth/register
GLOBAL_LIMIT = "200/minute"

def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded):
    return JSONResponse(
        status_code=429,
        content={"error": {"code": "RATE_LIMIT_EXCEEDED",
                           "message": "Too many requests. Please try again later."}},
        headers={"Retry-After": str(exc.retry_after) if hasattr(exc, "retry_after") else "60"},
    )
```

---

### File: backend/app/main.py

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from slowapi.errors import RateLimitExceeded

from app.config import settings
from app.core.logging import configure_logging
from app.core.exceptions import PlatformException
from app.db.existdb import existdb_client
from app.db.postgres import engine
from app.middleware.request_logger import RequestLoggerMiddleware
from app.middleware.rate_limiter import limiter, rate_limit_exceeded_handler
from app.routers import health
# Stub import per fasi future (file vuoti con APIRouter()):
# from app.routers import auth, users, roles, plugins

configure_logging()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # STARTUP
    await existdb_client.connect()
    # Verifica postgres
    from sqlalchemy import text
    from app.db.postgres import AsyncSessionLocal
    async with AsyncSessionLocal() as db:
        await db.execute(text("SELECT 1"))
    # (FASE 04: plugin_loader.load_all_active sarà aggiunto qui)
    yield
    # SHUTDOWN
    await existdb_client.close()
    await engine.dispose()

app = FastAPI(
    title="Aracne2 API",
    version="1.0.0",
    docs_url="/api/docs" if settings.is_development else None,
    redoc_url="/api/redoc" if settings.is_development else None,
    openapi_url="/api/openapi.json" if settings.is_development else None,
    lifespan=lifespan,
)

# Middleware (ordine: ultimo aggiunto = primo eseguito)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(RequestLoggerMiddleware)

# Exception handlers
@app.exception_handler(PlatformException)
async def platform_exception_handler(request: Request, exc: PlatformException):
    details = exc.details if settings.is_development else {}
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": exc.code, "message": exc.message,
                           "details": details}},
    )

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content={"error": {"code": "VALIDATION_ERROR",
                           "message": "Request validation failed",
                           "details": exc.errors() if settings.is_development else {}}},
    )

@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    import structlog
    structlog.get_logger().error("unhandled_exception", exc=str(exc))
    detail = str(exc) if settings.is_development else {}
    return JSONResponse(
        status_code=500,
        content={"error": {"code": "INTERNAL_SERVER_ERROR",
                           "message": "An unexpected error occurred",
                           "details": detail}},
    )

# Routers
app.include_router(health.router, prefix="/api/v1")
# Stub (aggiungere in fasi successive):
# app.include_router(auth.router, prefix="/api/v1")
# app.include_router(users.router, prefix="/api/v1")
```

---

### File: backend/app/routers/health.py

```python
from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.postgres import get_async_session
from app.db.existdb import get_existdb, ExistDBClient
from app.schemas.common import DataResponse, HealthResponse, HealthService
from app.config import settings

router = APIRouter(tags=["system"])

@router.get("/health", response_model=DataResponse[HealthResponse])
async def health_check(
    db: AsyncSession = Depends(get_async_session),
    existdb: ExistDBClient = Depends(get_existdb),
) -> DataResponse[HealthResponse]:

    # Postgres check
    pg_status = "ok"
    pg_detail = None
    try:
        await db.execute(text("SELECT 1"))
    except Exception as e:
        pg_status = "error"
        pg_detail = str(e) if settings.is_development else None

    # eXist-db check
    xml_ok = await existdb.ping()
    xml_status = "ok" if xml_ok else "error"

    overall = "healthy" if pg_status == "ok" and xml_status == "ok" else "degraded"

    return DataResponse(data=HealthResponse(
        status=overall,
        version="1.0.0",
        environment=settings.environment,
        services={
            "postgres": HealthService(status=pg_status, detail=pg_detail),
            "existdb":  HealthService(status=xml_status),
        },
    ))
```

---

### File: backend/app/models/

Implementa tutti i modelli SQLAlchemy 2.x con la sintassi `Mapped[T]`.
Ogni file deve importare `Base` da `app.db.postgres`.

**models/user.py** — classe `User`
Tutti i campi dallo schema SQL del Master Context.
Relationship: `roles` (via UserRole), `sessions`, `audit_logs`

**models/role.py** — classi `Role` e `UserRole`
`Role`: id, name (Enum), description, created_at
`UserRole`: tutti i campi. Relationship verso User e Role.

**models/session.py** — classe `Session`
Tutti i campi. Relationship verso User.

**models/audit_log.py** — classe `AuditLog`
Tutti i campi. `payload` come `JSONB` di SQLAlchemy.

**models/plugin.py** — classe `Plugin`
Tutti i campi. `config` e `hooks` come `JSONB`.

**models/notification.py** — classe `Notification`

**models/system_setting.py** — classe `SystemSetting`

**models/__init__.py**
```python
# Importa tutti i modelli in modo che Alembic li veda
from app.models.user import User
from app.models.role import Role, UserRole
from app.models.session import Session
from app.models.audit_log import AuditLog
from app.models.plugin import Plugin
from app.models.notification import Notification
from app.models.system_setting import SystemSetting

__all__ = [
    "User", "Role", "UserRole", "Session",
    "AuditLog", "Plugin", "Notification", "SystemSetting",
]
```

---

### File: backend/alembic/env.py

Configura per SQLAlchemy asincrono:

```python
import asyncio
from alembic import context
from sqlalchemy.ext.asyncio import create_async_engine
from app.config import settings
from app.db.postgres import Base
import app.models  # noqa: F401 — importa tutti i modelli per autogenerate

def run_migrations_online() -> None:
    connectable = create_async_engine(settings.database_url)

    async def run_async_migrations() -> None:
        async with connectable.connect() as connection:
            await connection.run_sync(do_run_migrations)
        await connectable.dispose()

    asyncio.run(run_async_migrations())

def do_run_migrations(connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=Base.metadata,
        compare_type=True,
        include_schemas=True,
    )
    with context.begin_transaction():
        context.run_migrations()

run_migrations_online()
```

---

### File: backend/alembic/versions/0001_initial_schema.py

Migrazione iniziale **scritta manualmente** (non autogenerata).

```python
"""Initial schema

Revision ID: 0001
Revises:
Create Date: 2026-03-24
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB, INET

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

def upgrade() -> None:
    # 1. Estensioni
    op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')
    op.execute('CREATE EXTENSION IF NOT EXISTS "pgcrypto"')
    op.execute('CREATE EXTENSION IF NOT EXISTS "pg_trgm"')

    # 2. ENUM types
    role_name = sa.Enum(
        "Admin","EditorInChief","Designer","Editor","User",
        name="role_name"
    )
    plugin_status = sa.Enum("active","inactive","error", name="plugin_status")
    role_name.create(op.get_bind())
    plugin_status.create(op.get_bind())

    # 3. Tabelle (nell'ordine che rispetta le FK)
    # roles, users, user_roles, sessions,
    # system_settings, audit_log, plugins, notifications
    # (implementa op.create_table() per ognuna)

    # 4. Indici

    # 5. Trigger fn_set_updated_at e fn_assign_default_role
    op.execute("""
        CREATE OR REPLACE FUNCTION fn_set_updated_at()
        RETURNS TRIGGER LANGUAGE plpgsql AS $func$
        BEGIN NEW.updated_at = NOW(); RETURN NEW; END;
        $func$;
    """)
    op.execute("""
        CREATE TRIGGER trg_users_updated_at
        BEFORE UPDATE ON users
        FOR EACH ROW EXECUTE FUNCTION fn_set_updated_at();
    """)
    op.execute("""
        CREATE OR REPLACE FUNCTION fn_assign_default_role()
        RETURNS TRIGGER LANGUAGE plpgsql AS $func$
        BEGIN
            INSERT INTO user_roles (user_id, role_id)
            SELECT NEW.id, id FROM roles WHERE name = 'User';
            RETURN NEW;
        END;
        $func$;
    """)
    op.execute("""
        CREATE TRIGGER trg_default_role
        AFTER INSERT ON users
        FOR EACH ROW EXECUTE FUNCTION fn_assign_default_role();
    """)

def downgrade() -> None:
    # Trigger e funzioni
    op.execute("DROP TRIGGER IF EXISTS trg_default_role ON users")
    op.execute("DROP TRIGGER IF EXISTS trg_users_updated_at ON users")
    op.execute("DROP FUNCTION IF EXISTS fn_assign_default_role()")
    op.execute("DROP FUNCTION IF EXISTS fn_set_updated_at()")

    # Tabelle in ordine inverso rispetto alle FK
    op.drop_table("notifications")
    op.drop_table("plugins")
    op.drop_table("audit_log")
    op.drop_table("system_settings")
    op.drop_table("sessions")
    op.drop_table("user_roles")
    op.drop_table("users")
    op.drop_table("roles")

    # Enum types
    op.execute("DROP TYPE IF EXISTS plugin_status")
    op.execute("DROP TYPE IF EXISTS role_name")

    # Estensioni (opzionale: potrebbe rompere altri DB nello stesso cluster)
    # op.execute('DROP EXTENSION IF EXISTS "pg_trgm"')
    # op.execute('DROP EXTENSION IF EXISTS "pgcrypto"')
    # op.execute('DROP EXTENSION IF EXISTS "uuid-ossp"')
```

---

### File: backend/app/db/seed.py

```python
import asyncio
import structlog
from sqlalchemy import select
from app.db.postgres import AsyncSessionLocal
from app.models import Role, User, UserRole, SystemSetting
from app.config import settings
import passlib.hash as ph

logger = structlog.get_logger()

ROLES = [
    ("Admin",         "Full platform access"),
    ("EditorInChief", "Manages collections and publication workflow"),
    ("Designer",      "Manages XSLT templates and CSS themes"),
    ("Editor",        "Creates and edits documents"),
    ("User",          "Read-only access to published content"),
]

DEFAULT_SETTINGS = [
    ("platform_name",            settings.platform_name,         "string"),
    ("default_language",         "it",                           "string"),
    ("jwt_access_expiry_min",    str(settings.jwt_access_expiry_minutes), "int"),
    ("jwt_refresh_expiry_days",  str(settings.jwt_refresh_expiry_days),   "int"),
    ("public_registration",      str(settings.public_registration).lower(),"bool"),
    ("bcrypt_rounds",            str(settings.bcrypt_rounds),    "int"),
    ("max_upload_size_mb",       str(settings.max_upload_size_mb),"int"),
    ("search_results_per_page",  "10",                           "int"),
]

async def seed_roles(db) -> None:
    for name, desc in ROLES:
        exists = await db.scalar(select(Role).where(Role.name == name))
        if not exists:
            db.add(Role(name=name, description=desc))
    await db.flush()
    logger.info("seed_roles_done")

async def seed_settings(db) -> None:
    for key, value, type_ in DEFAULT_SETTINGS:
        exists = await db.get(SystemSetting, key)
        if not exists:
            db.add(SystemSetting(key=key, value=value, type=type_))
    await db.flush()
    logger.info("seed_settings_done")

async def seed_admin(db) -> None:
    if not settings.admin_password:
        logger.warning(
            "seed_admin_skipped",
            reason="ADMIN_PASSWORD not set in environment — set it and re-run `make seed`",
        )
        return
    exists = await db.scalar(
        select(User).where(User.username == settings.admin_username)
    )
    if exists:
        logger.info("seed_admin_skipped", reason="already exists")
        return
    admin = User(
        username=settings.admin_username,
        email=settings.admin_email,
        password_hash=ph.bcrypt.hash(settings.admin_password,
                                     rounds=settings.bcrypt_rounds),
        is_active=True,
        is_verified=True,
    )
    db.add(admin)
    await db.flush()
    # Il trigger assegna User — revoca e assegna Admin
    user_role = await db.scalar(
        select(UserRole).where(UserRole.user_id == admin.id,
                               UserRole.revoked_at.is_(None))
    )
    if user_role:
        from datetime import datetime, UTC
        user_role.revoked_at = datetime.now(UTC)
    admin_role = await db.scalar(select(Role).where(Role.name == "Admin"))
    db.add(UserRole(user_id=admin.id, role_id=admin_role.id))
    logger.info("seed_admin_created", username=settings.admin_username)

async def main() -> None:
    async with AsyncSessionLocal() as db:
        await seed_roles(db)
        await seed_settings(db)
        await seed_admin(db)
        await db.commit()
    print("Seed completed successfully.")

if __name__ == "__main__":
    asyncio.run(main())
```

---

## PARTE C — Frontend

### File: frontend/Dockerfile

```dockerfile
# Development stage
FROM node:20-alpine AS development
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
EXPOSE 5173
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]

# Build stage
FROM node:20-alpine AS builder
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

# Production stage
FROM nginx:alpine AS production
COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
```

---

### File: frontend/vite.config.ts

```typescript
import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";
import { fileURLToPath, URL } from "node:url";

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) },
  },
  server: {
    proxy: {
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
      },
    },
  },
  build: {
    sourcemap: true,
    outDir: "dist",
  },
});
```

---

### File: frontend/src/services/api.ts

```typescript
import axios, { type AxiosInstance, type InternalAxiosRequestConfig } from "axios";
import { useAuthStore } from "@/stores/auth";

const api: AxiosInstance = axios.create({
  baseURL: "/api/v1",
  headers: { "Content-Type": "application/json" },
  withCredentials: true,  // necessario per inviare il cookie httpOnly del refresh token
});

// Request interceptor: inietta token e request ID
api.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  const auth = useAuthStore();
  if (auth.accessToken) {
    config.headers.Authorization = `Bearer ${auth.accessToken}`;
  }
  config.headers["X-Request-ID"] = crypto.randomUUID();
  return config;
});

// Response interceptor: gestisce 401 con refresh automatico
let isRefreshing = false;
let failedQueue: Array<{
  resolve: (token: string) => void;
  reject: (err: unknown) => void;
}> = [];

const processQueue = (error: Error | null, token: string | null = null) => {
  failedQueue.forEach(({ resolve, reject }) =>
    error ? reject(error) : resolve(token)
  );
  failedQueue = [];
};

api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const original = error.config;
    if (error.response?.status !== 401 || original._retry) {
      return Promise.reject(error);
    }
    if (isRefreshing) {
      return new Promise((resolve, reject) => {
        failedQueue.push({ resolve, reject });
      }).then((token) => {
        original.headers.Authorization = `Bearer ${token}`;
        return api(original);
      });
    }
    original._retry = true;
    isRefreshing = true;
    const auth = useAuthStore();
    try {
      await auth.refresh();
      processQueue(null, auth.accessToken);
      original.headers.Authorization = `Bearer ${auth.accessToken}`;
      return api(original);
    } catch (refreshError) {
      processQueue(refreshError as Error, null);
      await auth.logout();
      window.location.href = "/login";
      return Promise.reject(refreshError);
    } finally {
      isRefreshing = false;
    }
  }
);

// Helper tipizzati che estraggono .data automaticamente
export const apiClient = {
  get: <T>(url: string, config = {}) =>
    api.get<{ data: T }>(url, config).then((r) => r.data.data),
  post: <T>(url: string, data?: unknown, config = {}) =>
    api.post<{ data: T }>(url, data, config).then((r) => r.data.data),
  patch: <T>(url: string, data?: unknown, config = {}) =>
    api.patch<{ data: T }>(url, data, config).then((r) => r.data.data),
  put: <T>(url: string, data?: unknown, config = {}) =>
    api.put<{ data: T }>(url, data, config).then((r) => r.data.data),
  delete: <T>(url: string, config = {}) =>
    api.delete<{ data: T }>(url, config).then((r) => r.data.data),
  // Per endpoint che ritornano liste paginate:
  getPaginated: <T>(url: string, config = {}) =>
    api.get<{ data: T[]; pagination: unknown }>(url, config).then((r) => r.data),
  // Per upload multipart (non serializza come JSON):
  upload: <T>(url: string, form: FormData) =>
    api.post<{ data: T }>(url, form, {
      headers: { "Content-Type": "multipart/form-data" },
    }).then((r) => r.data.data),
};

export default api;
```

---

### File: frontend/src/stores/auth.ts

```typescript
import { defineStore } from "pinia";
import { ref, computed } from "vue";
import api from "@/services/api";

const ROLE_ORDER: Record<string, number> = {
  User: 0, Editor: 1, Designer: 2, EditorInChief: 3, Admin: 4,
};

interface UserMe {
  id: string;
  username: string;
  email: string;
  display_name: string | null;
  role: string;
  preferred_lang: string;
  created_at: string;
  last_login_at: string | null;
}

// Strategia token:
// - access_token: in memoria (ref Pinia) — perso al reload, recuperato da hydrate()
// - refresh_token: NON gestito dal frontend — viaggia come httpOnly cookie
//   impostato dal server su POST /auth/login e rinnovato su POST /auth/refresh
//   Il browser lo invia automaticamente. Il frontend non lo legge mai.

export const useAuthStore = defineStore("auth", () => {
  const user = ref<UserMe | null>(null);
  const accessToken = ref<string | null>(null);
  const isLoading = ref(false);

  const isAuthenticated = computed(() => !!accessToken.value && !!user.value);

  const userRole = computed(() => user.value?.role ?? "User");

  const hasMinRole = (minRole: string): boolean => {
    const userLevel = ROLE_ORDER[userRole.value] ?? 0;
    const minLevel = ROLE_ORDER[minRole] ?? 0;
    return userLevel >= minLevel;
  };

  async function login(usernameOrEmail: string, password: string): Promise<void> {
    isLoading.value = true;
    try {
      // Il server risponde con Set-Cookie: refresh_token=...; HttpOnly; SameSite=Strict
      // Il frontend riceve solo access_token e user nel body
      const res = await api.post<{
        access_token: string; user: UserMe;
      }>("/auth/login", { username_or_email: usernameOrEmail, password });
      accessToken.value = res.data.data.access_token;
      user.value = res.data.data.user;
    } finally {
      isLoading.value = false;
    }
  }

  async function logout(): Promise<void> {
    // Il server revoca il refresh token e fa Set-Cookie con Max-Age=0
    try { await api.post("/auth/logout"); } catch { /* ignora errori di rete */ }
    user.value = null;
    accessToken.value = null;
  }

  async function refresh(): Promise<void> {
    // Nessun body: il browser invia automaticamente il cookie httpOnly
    // withCredentials è già true nell'istanza axios base
    const res = await api.post<{ access_token: string }>("/auth/refresh");
    accessToken.value = res.data.data.access_token;
  }

  async function loadMe(): Promise<void> {
    const res = await api.get<UserMe>("/auth/me");
    user.value = res.data.data;
  }

  // Chiamata al boot della SPA: tenta refresh silenzioso.
  // Se il cookie di refresh è presente e valido, recupera access_token e user.
  // Se fallisce, l'utente è considerato non autenticato.
  async function hydrate(): Promise<void> {
    try {
      await refresh();
      await loadMe();
    } catch {
      user.value = null;
      accessToken.value = null;
    }
  }

  return {
    user, accessToken, isLoading,
    isAuthenticated, userRole, hasMinRole,
    login, logout, refresh, loadMe, hydrate,
  };
});
```

---

### File: frontend/src/router/index.ts

```typescript
import { createRouter, createWebHistory } from "vue-router";
import { useAuthStore } from "@/stores/auth";

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: "/",        name: "home",      component: () => import("@/views/HomeView.vue") },
    { path: "/login",   name: "login",     component: () => import("@/views/auth/LoginView.vue") },
    { path: "/profile", name: "profile",   component: () => import("@/views/auth/ProfileView.vue"),
      meta: { requiresAuth: true } },
    { path: "/:pathMatch(.*)*", name: "not-found",
      component: () => import("@/views/NotFoundView.vue") },
  ],
});

let hydrated = false;
router.beforeEach(async (to) => {
  const auth = useAuthStore();
  if (!hydrated) { await auth.hydrate(); hydrated = true; }
  if (to.meta.requiresAuth && !auth.isAuthenticated) {
    return { name: "login", query: { redirect: to.fullPath } };
  }
  if (to.name === "login" && auth.isAuthenticated) {
    return { name: "home" };
  }
  if (to.meta.requiresRole && !auth.hasMinRole(to.meta.requiresRole as string)) {
    return { name: "home" };
  }
});

export default router;
```

---

### Views stub da creare (file minimali, nessuna logica):

**src/views/HomeView.vue**: `<template><h1>TEI Platform</h1></template>`
**src/views/NotFoundView.vue**: `<template><h1>404 — Pagina non trovata</h1></template>`
**src/views/auth/ProfileView.vue**: `<template><p>Profile — work in progress</p></template>`
**src/views/auth/LoginView.vue**: form completo (descritto di seguito)

---

### File: frontend/src/views/auth/LoginView.vue

```vue
<script setup lang="ts">
import { ref } from "vue";
import { useRouter, useRoute } from "vue-router";
import { useAuthStore } from "@/stores/auth";

const auth = useAuthStore();
const router = useRouter();
const route = useRoute();

const usernameOrEmail = ref("");
const password = ref("");
const showPassword = ref(false);
const errorMessage = ref("");
const isLoading = ref(false);

// Valida che il redirect sia un path interno sicuro (no open redirect)
function isSafeRedirect(url: string): boolean {
  return url.startsWith("/") && !url.startsWith("//") && !url.includes(":");
}

async function handleLogin() {
  errorMessage.value = "";
  isLoading.value = true;
  try {
    await auth.login(usernameOrEmail.value, password.value);
    const raw = route.query.redirect as string | undefined;
    const redirect = raw && isSafeRedirect(raw) ? raw : "/";
    await router.push(redirect);
  } catch (err: unknown) {
    // Messaggio generico — non distinguere username da password (sicurezza)
    errorMessage.value = "Credenziali non valide. Riprova.";
  } finally {
    isLoading.value = false;
  }
}
</script>

<template>
  <div class="min-h-screen flex items-center justify-center bg-gray-50">
    <div class="w-full max-w-md bg-white rounded-xl shadow p-8">
      <h1 class="text-2xl font-bold text-center mb-6">Accedi</h1>
      <form @submit.prevent="handleLogin" novalidate>
        <div class="mb-4">
          <label class="block text-sm font-medium mb-1">Username o Email</label>
          <input v-model="usernameOrEmail" type="text" required autocomplete="username"
                 class="w-full border rounded-lg px-3 py-2 focus:outline-none focus:ring-2" />
        </div>
        <div class="mb-6 relative">
          <label class="block text-sm font-medium mb-1">Password</label>
          <input v-model="password" :type="showPassword ? 'text' : 'password'" required
                 autocomplete="current-password"
                 class="w-full border rounded-lg px-3 py-2 pr-10 focus:outline-none focus:ring-2" />
          <button type="button" @click="showPassword = !showPassword"
                  class="absolute right-3 top-8 text-gray-500 text-sm">
            {{ showPassword ? "Nascondi" : "Mostra" }}
          </button>
        </div>
        <p v-if="errorMessage" class="text-red-600 text-sm mb-4">{{ errorMessage }}</p>
        <button type="submit" :disabled="isLoading"
                class="w-full bg-blue-600 text-white py-2 rounded-lg font-semibold
                       hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed">
          {{ isLoading ? "Accesso in corso..." : "Accedi" }}
        </button>
      </form>
    </div>
  </div>
</template>
```

---

## PARTE D — Test

### File: backend/app/tests/conftest.py

```python
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.pool import StaticPool
from app.main import app
from app.db.postgres import Base, get_async_session
from app.models import Role, User, UserRole  # noqa: F401

TEST_DB_URL = "sqlite+aiosqlite:///:memory:"

@pytest_asyncio.fixture(scope="session")
async def test_engine():
    engine = create_async_engine(
        TEST_DB_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()

@pytest_asyncio.fixture
async def db_session(test_engine) -> AsyncSession:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    async with factory() as session:
        yield session
        await session.rollback()

@pytest_asyncio.fixture
async def client(db_session: AsyncSession) -> AsyncClient:
    async def override_get_session():
        yield db_session
    app.dependency_overrides[get_async_session] = override_get_session
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as c:
        yield c
    app.dependency_overrides.clear()

@pytest_asyncio.fixture
async def seeded_roles(db_session: AsyncSession):
    roles = ["Admin","EditorInChief","Designer","Editor","User"]
    for name in roles:
        db_session.add(Role(name=name, description=f"{name} role"))
    await db_session.flush()
    return roles
```

---

### File: backend/app/tests/test_scaffolding.py

```python
import pytest
from httpx import AsyncClient

async def test_health_endpoint_returns_200(client: AsyncClient):
    r = await client.get("/api/v1/health")
    assert r.status_code == 200
    body = r.json()
    assert "data" in body
    assert body["data"]["status"] in ["healthy", "degraded"]
    assert "services" in body["data"]
    assert "postgres" in body["data"]["services"]
    assert "existdb" in body["data"]["services"]

async def test_health_response_has_version(client: AsyncClient):
    r = await client.get("/api/v1/health")
    assert r.json()["data"]["version"] == "1.0.0"

async def test_unknown_route_returns_404_in_error_format(client: AsyncClient):
    r = await client.get("/api/v1/this-does-not-exist")
    assert r.status_code == 404
    body = r.json()
    assert "error" in body
    assert "code" in body["error"]
    assert "message" in body["error"]

async def test_request_id_header_present(client: AsyncClient):
    r = await client.get("/api/v1/health")
    assert "x-request-id" in r.headers
    # Verifica che sia un UUID valido
    import uuid
    uuid.UUID(r.headers["x-request-id"])  # non deve sollevare

async def test_settings_jwt_secret_too_short():
    from pydantic import ValidationError
    from app.config import Settings
    import pytest
    with pytest.raises((ValidationError, ValueError)):
        Settings(
            postgres_host="localhost", postgres_db="x",
            postgres_user="x", postgres_password="x",
            existdb_url="http://x", existdb_user="x",
            existdb_password="x",
            jwt_secret="tooshort",  # < 64 caratteri
        )

async def test_default_role_assigned_on_user_insert(
    db_session, seeded_roles
):
    from app.models import User, UserRole, Role
    from sqlalchemy import select
    from datetime import datetime, UTC
    import uuid, passlib.hash as ph

    user = User(
        id=uuid.uuid4(), username="testuser_scaffold",
        email="scaffold@test.com",
        password_hash=ph.bcrypt.hash("Password1"),
    )
    db_session.add(user)
    await db_session.flush()

    # NOTA: questo test verifica solo che il flush non sollevi eccezioni
    # e che la struttura ORM sia corretta. Il trigger PostgreSQL fn_assign_default_role
    # NON viene eseguito su SQLite in-memory.
    # Il test di integrazione con trigger reale è in tests/integration/test_pg_triggers.py
    # (eseguito in CI contro un container PostgreSQL reale).
    result = await db_session.execute(
        select(UserRole).where(UserRole.user_id == user.id)
    )
    roles_assigned = result.scalars().all()
    assert isinstance(roles_assigned, list)  # SQLite: lista vuota, PG: lista con 1 elemento
```

---

## CHECKLIST di completamento

Prima di considerare questa fase conclusa, verifica manualmente:

- [ ] `cp .env.example .env` + compilazione valori obbligatori (passwords, JWT_SECRET)
- [ ] `make up` porta tutti e 4 i servizi a `healthy` in meno di 90 secondi
- [ ] `curl http://localhost:8000/api/v1/health` restituisce `{"data": {"status": ...}}`
- [ ] `make migrate` esegue senza errori (`0001_initial_schema` applicata)
- [ ] `make seed` crea admin e 5 ruoli, è idempotente (eseguirlo 2 volte non crea duplicati)
- [ ] `make test` → tutti i test passano, nessun warning asyncio
- [ ] `make lint` → nessun errore ruff, nessun errore mypy critico
- [ ] `http://localhost:5173` → Vue app si carica, LoginView visibile
- [ ] `http://localhost:8080/exist/apps/dashboard` → dashboard eXist-db accessibile
- [ ] `http://localhost:8000/api/docs` → Swagger UI accessibile
- [ ] Login form visibile, errore generico su credenziali errate
