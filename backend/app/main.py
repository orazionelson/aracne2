from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded

from app.config import settings
from app.core.exceptions import PlatformException
from app.core.logging import configure_logging
from app.core.plugin_loader import plugin_loader
from app.core.scheduler import register_jobs, scheduler
from app.db.existdb import existdb_client
from app.db.postgres import engine
from app.middleware.rate_limiter import limiter, rate_limit_exceeded_handler
from app.middleware.request_logger import RequestLoggerMiddleware
from app.routers import auth, body_templates as body_templates_router, health
from app.routers import licenses as licenses_router, notifications, plugins
from app.routers import media as media_router
from app.routers import zones as zones_router
from app.routers import public_view as public_view_router
from app.routers import schemas as schemas_router, settings as settings_router, users
from app.routers import viaf as viaf_router
from app.routers import wikidata as wikidata_router
from app.routers import geonames as geonames_router
from app.routers import bibliography as bibliography_router
from app.routers import seo as seo_router
from app.routers import search_engines as search_engines_router
from app.routers import websites as websites_router
from app.routers import xslt_templates as xslt_templates_router
from app.routers.embed import router as embed_router

configure_logging()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    # STARTUP
    await existdb_client.connect()
    # Ensure /db/aracne2/collections base structure exists (idempotent, admin)
    try:
        await existdb_client.ensure_root()
    except Exception as exc:
        structlog.get_logger().warning("existdb_ensure_root_failed", error=str(exc))
    # Create the dedicated runtime user and set collection ownership (idempotent, admin)
    try:
        await existdb_client.bootstrap_user()
    except Exception as exc:
        structlog.get_logger().warning("existdb_bootstrap_user_failed", error=str(exc))
    # Verify postgres connectivity — non-fatal so tests and degraded starts work
    try:
        from sqlalchemy import text

        from app.db.postgres import AsyncSessionLocal

        async with AsyncSessionLocal() as db:
            await db.execute(text("SELECT 1"))
    except Exception as exc:
        structlog.get_logger().warning("startup_postgres_check_failed", error=str(exc))
    # Seed default data (idempotent — safe to run on every startup)
    try:
        from app.db.postgres import AsyncSessionLocal
        from app.db.seed import seed_ai_prompts, seed_body_templates, seed_licenses, seed_settings

        async with AsyncSessionLocal() as db:
            await seed_settings(db)
            await seed_licenses(db)
            await seed_body_templates(db)
            await seed_ai_prompts(db)
            await db.commit()
    except Exception as exc:
        structlog.get_logger().warning("startup_seed_failed", error=str(exc))
    # Discover plugins, sync DB registry, mount active routers
    try:
        from app.db.postgres import AsyncSessionLocal

        async with AsyncSessionLocal() as db:
            await plugin_loader.load_active(app, db)
    except Exception as exc:
        structlog.get_logger().warning("plugin_loader_failed", error=str(exc))

    # pgvector — ensure extension and RAG tables. Lazy + non-fatal: when
    # the pgvector service is not configured or unreachable, RAG silently
    # becomes unavailable at the service layer.
    try:
        from app.db.pgvector import ensure_schema as ensure_pgvector_schema

        await ensure_pgvector_schema()
    except Exception as exc:
        structlog.get_logger().warning("pgvector_bootstrap_failed", error=str(exc))

    # Ensure required filesystem directories exist.
    settings.websites_root.mkdir(parents=True, exist_ok=True)
    settings.search_engines_root.mkdir(parents=True, exist_ok=True)
    settings.documents_media_root.mkdir(parents=True, exist_ok=True)
    settings.backup_root.mkdir(parents=True, exist_ok=True)

    # Start periodic background jobs (audit log + session cleanup)
    register_jobs()
    scheduler.start()

    yield

    # SHUTDOWN
    scheduler.shutdown(wait=False)
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
app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)  # type: ignore[arg-type]

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
    details: object = exc.details if settings.is_development else {}
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": exc.code, "message": exc.message, "details": details}},
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    errors = exc.errors()
    if settings.is_development:
        # Pydantic v2 includes Exception objects in ctx (e.g. ValueError).
        # Serialize with default=str to avoid TypeError in json.dumps.
        import json as _json

        details = _json.loads(_json.dumps(errors, default=str))
    else:
        details = {}

    # Surface the FIRST concrete error message to the UI instead of the generic
    # "Request validation failed" one. Without this the frontend cannot tell
    # the user *why* the submission failed ("spaces are not allowed in the
    # username" vs "password must be at least 8 characters" etc.) and ends up
    # showing an opaque string. The full list of per-field errors is still
    # available in `details` for clients that want to drill down.
    message = "Request validation failed"
    if errors:
        first = errors[0]
        loc = [str(p) for p in first.get("loc", ()) if p != "body"]
        raw_msg = first.get("msg", "")
        # Pydantic v2 prefixes custom-validator errors with "Value error, " —
        # strip it for a cleaner user-facing message.
        if raw_msg.startswith("Value error, "):
            raw_msg = raw_msg[len("Value error, "):]
        if loc and raw_msg:
            message = f"{'.'.join(loc)}: {raw_msg}"
        elif raw_msg:
            message = raw_msg

    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "code": "VALIDATION_ERROR",
                "message": message,
                "details": details,
            }
        },
    )


_HTTP_CODE_MAP: dict[int, str] = {
    400: "BAD_REQUEST",
    401: "UNAUTHORIZED",
    403: "FORBIDDEN",
    404: "NOT_FOUND",
    405: "METHOD_NOT_ALLOWED",
    409: "CONFLICT",
    422: "UNPROCESSABLE_ENTITY",
    429: "RATE_LIMIT_EXCEEDED",
    500: "INTERNAL_SERVER_ERROR",
    503: "SERVICE_UNAVAILABLE",
}


async def _http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    code = _HTTP_CODE_MAP.get(exc.status_code, "HTTP_ERROR")
    message = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": code, "message": message, "details": {}}},
    )


# Register both by class (FastAPI routes) and by status code (Starlette routing
# layer 404/405 which bypasses the class-based handler).
app.add_exception_handler(HTTPException, _http_exception_handler)  # type: ignore[arg-type]
app.add_exception_handler(404, _http_exception_handler)  # type: ignore[arg-type]
app.add_exception_handler(405, _http_exception_handler)  # type: ignore[arg-type]


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    structlog.get_logger().error("unhandled_exception", exc=str(exc))
    detail: object = str(exc) if settings.is_development else {}
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


# ── Embed sub-app ─────────────────────────────────────────────────────────────
# Mounted as a separate ASGI app so its CORSMiddleware can allow all origins
# for preflight.  Actual origin enforcement (whitelist) is done in each handler.
embed_app = FastAPI(openapi_url=None, docs_url=None, redoc_url=None)
embed_app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],        # open preflight — whitelist enforced per-handler
    allow_credentials=False,    # no JWT/cookies for the public embed endpoints
    allow_methods=["GET", "OPTIONS"],
    allow_headers=["*"],
)


# Mirror the main app's exception handlers so PlatformException subclasses
# (NotFoundError, AuthorizationError) are serialised correctly in the sub-app.
@embed_app.exception_handler(PlatformException)
async def _embed_platform_exc(request: Request, exc: PlatformException) -> JSONResponse:
    details: object = exc.details if settings.is_development else {}
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": exc.code, "message": exc.message, "details": details}},
    )


@embed_app.exception_handler(RequestValidationError)
async def _embed_validation_exc(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "code": "VALIDATION_ERROR",
                "message": "Request validation failed",
                "details": {},
            }
        },
    )


embed_app.include_router(embed_router)
app.mount("/api/v1/embed", embed_app)

# Routers
app.include_router(health.router, prefix="/api/v1")
app.include_router(auth.router, prefix="/api/v1")
app.include_router(users.router, prefix="/api/v1")
app.include_router(notifications.router, prefix="/api/v1")
app.include_router(plugins.router, prefix="/api/v1")
app.include_router(settings_router.router, prefix="/api/v1")
app.include_router(schemas_router.router, prefix="/api/v1")
app.include_router(licenses_router.router, prefix="/api/v1")
app.include_router(body_templates_router.router, prefix="/api/v1")
app.include_router(viaf_router.router, prefix="/api/v1")
app.include_router(wikidata_router.router, prefix="/api/v1")
app.include_router(geonames_router.router, prefix="/api/v1")
app.include_router(bibliography_router.router, prefix="/api/v1")
app.include_router(seo_router.router, prefix="/api/v1")
app.include_router(public_view_router.router, prefix="/api/v1")
app.include_router(websites_router.router, prefix="/api/v1")
app.include_router(xslt_templates_router.router, prefix="/api/v1")
app.include_router(search_engines_router.router, prefix="/api/v1")
app.include_router(media_router.router, prefix="/api/v1")
app.include_router(zones_router.router, prefix="/api/v1")
