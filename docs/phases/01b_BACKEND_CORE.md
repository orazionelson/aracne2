# PHASE 01b — Backend Core: config, db, middleware, main, health
# Prerequisite: CLAUDE.md loaded. Phase 01a (infrastructure) complete.
# Goal: backend container starts, GET /api/v1/health returns 200.

Implement everything below. Every file must be complete and working.
See docs/reference/DB_SCHEMA.md for the full SQL schema.
See docs/reference/API_FORMAT.md for response format and Pydantic common schemas.

---

## File: backend/Dockerfile

```dockerfile
FROM python:3.12-slim

WORKDIR /app

# gcc and libpq-dev required by asyncpg; curl required by healthcheck
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl gcc libpq-dev && rm -rf /var/lib/apt/lists/*

# Cache layer: copy requirements before source code
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Non-root user for security
RUN useradd -m -u 1000 appuser && chown -R appuser /app
USER appuser

EXPOSE 8000
```

---

## File: backend/requirements.txt (pinned versions)

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
defusedxml==0.7.1
pytest==8.3.4
pytest-asyncio==0.24.0
anyio==4.7.0
aiosqlite==0.20.0
ruff==0.8.4
mypy==1.13.0
coverage==7.6.9
```

---

## File: backend/pyproject.toml

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

## File: backend/app/config.py

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

    # Security
    bcrypt_rounds: int = 12
    cors_origins: list[str] = ["http://localhost:5173"]

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, v: str | list) -> list[str]:
        if isinstance(v, str):
            return [o.strip() for o in v.split(",")]
        return v

    # Application
    environment: Literal["development", "production", "test"] = "development"
    log_level: str = "INFO"
    platform_name: str = "Aracne2"
    public_registration: bool = False
    max_upload_size_mb: int = 50

    # Admin seed — required only for `make seed`; None skips admin creation with warning
    admin_username: str = "admin"
    admin_email: str = "admin@example.com"
    admin_password: str | None = None

    @property
    def is_development(self) -> bool:
        return self.environment == "development"

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

# Singleton — import everywhere with: from app.config import settings
settings = Settings()
```

---

## File: backend/app/db/postgres.py

```python
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    AsyncEngine,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase
from typing import AsyncGenerator
from app.config import settings

engine: AsyncEngine = create_async_engine(
    settings.database_url,
    echo=settings.is_development,  # log SQL only in development
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,            # verify connection before use
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,        # prevent lazy load after commit
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

## File: backend/app/db/existdb.py

Implement `ExistDBClient` with all methods. Methods not yet implemented must raise
`NotImplementedError("Implemented in PHASE 05")` — never bare `pass`.

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
        """GET /exist/rest/ — returns True if 200, False otherwise. Never raises."""
        if not self._client:
            return False
        try:
            r = await self._client.get("/exist/rest/")
            return r.status_code == 200
        except Exception:
            return False

    # Stubs — implemented in PHASE 05
    async def xquery(self, query_name: str, params: dict | None = None) -> dict:
        raise NotImplementedError("Implemented in PHASE 05")

    async def store_document(
        self,
        collection_path: str,
        filename: str,
        xml_bytes: bytes,
        create_if_missing: bool = True,
    ) -> str:
        raise NotImplementedError("Implemented in PHASE 05")

    async def delete_document(self, collection_path: str, filename: str) -> None:
        raise NotImplementedError("Implemented in PHASE 05")

    async def create_collection(self, path: str) -> None:
        raise NotImplementedError("Implemented in PHASE 05")

    async def collection_exists(self, path: str) -> bool:
        raise NotImplementedError("Implemented in PHASE 05")

    async def list_collection(self, path: str) -> list[str]:
        raise NotImplementedError("Implemented in PHASE 05")

existdb_client = ExistDBClient()

async def get_existdb() -> ExistDBClient:
    return existdb_client
```

---

## File: backend/app/core/exceptions.py

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

## File: backend/app/middleware/request_logger.py

Implement as an ASGI class (not as `@app.middleware`):

```python
import uuid
import time
import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from app.config import settings

logger = structlog.get_logger()

class RequestLoggerMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = str(uuid.uuid4())
        start = time.perf_counter()

        request.state.request_id = request_id

        response = await call_next(request)

        duration_ms = round((time.perf_counter() - start) * 1000, 2)

        # Skip health endpoint in production to reduce log noise
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
                ip=request.headers.get(
                    "X-Forwarded-For",
                    request.client.host if request.client else "unknown",
                ),
            )

        response.headers["X-Request-ID"] = request_id
        return response
```

Also implement structlog configuration in `app/core/logging.py`:
- Development: human-readable console output with colors
- Production: JSON output on stdout (for log aggregators)
- Called from `main.py` before creating the app

---

## File: backend/app/middleware/rate_limiter.py

```python
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from fastapi import Request
from fastapi.responses import JSONResponse

limiter = Limiter(key_func=get_remote_address, default_limits=["200/minute"])

# Applied to: POST /auth/login, POST /auth/register, POST /auth/password/change
STRICT_LIMIT = "10/minute"
GLOBAL_LIMIT = "200/minute"

def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    return JSONResponse(
        status_code=429,
        content={
            "error": {
                "code": "RATE_LIMIT_EXCEEDED",
                "message": "Too many requests. Please try again later.",
            }
        },
        headers={
            "Retry-After": str(exc.retry_after) if hasattr(exc, "retry_after") else "60"
        },
    )
```

---

## File: backend/app/main.py

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
# Stub imports for future phases (empty files with APIRouter()):
# from app.routers import auth, users, roles, plugins

configure_logging()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # STARTUP
    await existdb_client.connect()
    # Verify postgres connectivity
    from sqlalchemy import text
    from app.db.postgres import AsyncSessionLocal
    async with AsyncSessionLocal() as db:
        await db.execute(text("SELECT 1"))
    # PHASE 04: plugin_loader.load_all_active() will be added here
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

# Middleware — last added = first executed
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
async def platform_exception_handler(request: Request, exc: PlatformException) -> JSONResponse:
    details = exc.details if settings.is_development else {}
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": exc.code, "message": exc.message, "details": details}},
    )

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "code": "VALIDATION_ERROR",
                "message": "Request validation failed",
                "details": exc.errors() if settings.is_development else {},
            }
        },
    )

@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    import structlog
    structlog.get_logger().error("unhandled_exception", exc=str(exc))
    detail = str(exc) if settings.is_development else {}
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "code": "INTERNAL_SERVER_ERROR",
                "message": "An unexpected error occurred",
                "details": detail,
            }
        },
    )

# Routers
app.include_router(health.router, prefix="/api/v1")
# Stubs (add in subsequent phases):
# app.include_router(auth.router, prefix="/api/v1")
# app.include_router(users.router, prefix="/api/v1")
```

---

## File: backend/app/routers/health.py

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

    # PostgreSQL check
    pg_status = "ok"
    pg_detail: str | None = None
    try:
        await db.execute(text("SELECT 1"))
    except Exception as e:
        pg_status = "error"
        pg_detail = str(e) if settings.is_development else None

    # eXist-db check
    xml_ok = await existdb.ping()
    xml_status = "ok" if xml_ok else "error"

    overall = "healthy" if pg_status == "ok" and xml_status == "ok" else "degraded"

    return DataResponse(
        data=HealthResponse(
            status=overall,
            version="1.0.0",
            environment=settings.environment,
            services={
                "postgres": HealthService(status=pg_status, detail=pg_detail),
                "existdb": HealthService(status=xml_status),
            },
        )
    )
```

---

## File: backend/app/db/seed.py

```python
import asyncio
import structlog
from sqlalchemy import select
from app.db.postgres import AsyncSessionLocal
from app.models import Role, User, UserRole, SystemSetting
from app.config import settings
import passlib.hash as ph

logger = structlog.get_logger()

ROLES: list[tuple[str, str]] = [
    ("Admin",         "Full platform access"),
    ("EditorInChief", "Manages collections and publication workflow"),
    ("Designer",      "Manages XSLT templates and CSS themes"),
    ("Editor",        "Creates and edits documents"),
    ("User",          "Read-only access to published content"),
]

DEFAULT_SETTINGS: list[tuple[str, str, str]] = [
    ("platform_name",           settings.platform_name,                        "string"),
    ("default_language",        "it",                                           "string"),
    ("jwt_access_expiry_min",   str(settings.jwt_access_expiry_minutes),        "int"),
    ("jwt_refresh_expiry_days", str(settings.jwt_refresh_expiry_days),          "int"),
    ("public_registration",     str(settings.public_registration).lower(),      "bool"),
    ("bcrypt_rounds",           str(settings.bcrypt_rounds),                    "int"),
    ("max_upload_size_mb",      str(settings.max_upload_size_mb),               "int"),
    ("search_results_per_page", "10",                                           "int"),
    ("audit_log_retention_days",          "90",                                 "int"),
    ("expired_sessions_retention_days",   "30",                                 "int"),
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
        password_hash=ph.bcrypt.hash(
            settings.admin_password, rounds=settings.bcrypt_rounds
        ),
        is_active=True,
        is_verified=True,
    )
    db.add(admin)
    await db.flush()
    # The trigger assigns the 'User' role — revoke it and assign 'Admin'
    user_role = await db.scalar(
        select(UserRole).where(
            UserRole.user_id == admin.id,
            UserRole.revoked_at.is_(None),
        )
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
