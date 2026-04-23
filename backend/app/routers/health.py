from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.existdb import ExistDBClient, get_existdb
from app.db.postgres import get_async_session
from app.schemas.common import DataResponse, HealthResponse, HealthService

router = APIRouter(tags=["system"])


@router.get("/health/live", include_in_schema=False)
async def liveness() -> JSONResponse:
    """Liveness probe — process is running.

    Intentionally free of any dependency check: if the ASGI worker can
    answer, it is alive. This endpoint is what a Kubernetes livenessProbe
    should target — a failure here means "restart the container",
    which must NOT be triggered by a downstream blip (Postgres, eXist-db).
    """
    return JSONResponse({"status": "alive"})


@router.get("/health/ready", include_in_schema=False)
async def readiness(
    db: AsyncSession = Depends(get_async_session),  # noqa: B008
    existdb: ExistDBClient = Depends(get_existdb),  # noqa: B008
) -> JSONResponse:
    """Readiness probe — process is ready to serve traffic.

    Pings PostgreSQL and eXist-db. Returns 200 when both are reachable,
    503 when either is not. Kubernetes readinessProbe + load-balancer
    health checks should target this endpoint so that a pod with a bad
    dependency is pulled from rotation rather than restarted in a loop.
    """
    pg_ok = True
    try:
        await db.execute(text("SELECT 1"))
    except Exception:
        pg_ok = False

    xml_ok = await existdb.ping()

    ready = pg_ok and xml_ok
    return JSONResponse(
        status_code=200 if ready else 503,
        content={
            "status": "ready" if ready else "not_ready",
            "services": {
                "postgres": "ok" if pg_ok else "error",
                "existdb": "ok" if xml_ok else "error",
            },
        },
    )


@router.get("/health")
async def health_check(
    db: AsyncSession = Depends(get_async_session),  # noqa: B008
    existdb: ExistDBClient = Depends(get_existdb),  # noqa: B008
) -> DataResponse[HealthResponse]:
    """Check connectivity to PostgreSQL and eXist-db.

    Returns status "healthy" when both services respond, "degraded" otherwise.
    Error details are included in development mode only.

    **Kept for backward compatibility** — new integrations should prefer
    ``/health/live`` (liveness, no deps) and ``/health/ready`` (readiness,
    dependency-checking). This rich-body variant continues to power the
    Admin dashboard.
    """
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
