import structlog
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded

from app.config import settings
from app.core.exceptions import PlatformException
from app.core.logging import configure_logging
from app.db.existdb import existdb_client
from app.db.postgres import engine
from app.middleware.rate_limiter import limiter, rate_limit_exceeded_handler
from app.middleware.request_logger import RequestLoggerMiddleware
from app.routers import health

# Stub imports for future phases (empty files with APIRouter()):
# from app.routers import auth, users, roles, plugins

configure_logging()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    # STARTUP
    await existdb_client.connect()
    # Verify postgres connectivity — non-fatal so tests and degraded starts work
    try:
        from sqlalchemy import text

        from app.db.postgres import AsyncSessionLocal

        async with AsyncSessionLocal() as db:
            await db.execute(text("SELECT 1"))
    except Exception as exc:
        structlog.get_logger().warning("startup_postgres_check_failed", error=str(exc))
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


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    code = _HTTP_CODE_MAP.get(exc.status_code, "HTTP_ERROR")
    message = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": code, "message": message, "details": {}}},
    )


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


# Routers
app.include_router(health.router, prefix="/api/v1")
# Stubs (add in subsequent phases):
# app.include_router(auth.router, prefix="/api/v1")
# app.include_router(users.router, prefix="/api/v1")
