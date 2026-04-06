from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.existdb import ExistDBClient, get_existdb
from app.db.postgres import get_async_session
from app.schemas.common import DataResponse, HealthResponse, HealthService

router = APIRouter(tags=["system"])


@router.get("/health")
async def health_check(
    db: AsyncSession = Depends(get_async_session),  # noqa: B008
    existdb: ExistDBClient = Depends(get_existdb),  # noqa: B008
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
