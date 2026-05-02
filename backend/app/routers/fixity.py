"""``/admin/fixity`` REST surface — CTS R7 deliverable.

Three endpoints, all Admin-gated:

- ``GET  /fixity`` — paginated, filterable list of fixity rows.
- ``GET  /fixity/summary`` — per-status counts for the dashboard.
- ``POST /fixity/recheck`` — synchronous re-check of every row;
  returns the per-status tally so the admin can see the result
  immediately.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.postgres import get_async_session
from app.middleware.acl import require_role
from app.middleware.rate_limiter import limiter
from app.models.fixity_record import FixityStatus
from app.models.user import User
from app.schemas.common import DataResponse, PaginatedResponse, PaginationMeta
from app.schemas.fixity import (
    FixityRecheckResult,
    FixityRecordView,
    FixitySummary,
)
from app.services.fixity import list_records, recheck_all, status_summary


router = APIRouter(prefix="/fixity", tags=["fixity"])
_admin = Depends(require_role(min_role="Admin"))


@router.get("")
@limiter.limit("60/minute")
async def fixity_list(
    request: Request,
    current_user: Annotated[User, _admin],
    db: Annotated[AsyncSession, Depends(get_async_session)],
    page: Annotated[int, Query(ge=1)] = 1,
    per_page: Annotated[int, Query(ge=1, le=200)] = 50,
    status: Annotated[FixityStatus | None, Query()] = None,
    collection_id: Annotated[uuid.UUID | None, Query()] = None,
) -> PaginatedResponse[FixityRecordView]:
    """List fixity rows newest-drift-first.

    Filters: ``status`` (one of ok / drifted / missing / error) and
    ``collection_id`` (UUID). Both can be combined.
    """
    rows, total = await list_records(
        db,
        page=page,
        per_page=per_page,
        status=status,
        collection_id=collection_id,
    )
    total_pages = (total + per_page - 1) // per_page if total else 0
    return PaginatedResponse[FixityRecordView](
        data=[FixityRecordView.model_validate(r) for r in rows],
        pagination=PaginationMeta(
            page=page,
            per_page=per_page,
            total=total,
            total_pages=total_pages,
        ),
    )


@router.get("/summary")
@limiter.limit("60/minute")
async def fixity_summary(
    request: Request,
    current_user: Annotated[User, _admin],
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> DataResponse[FixitySummary]:
    """Per-status row counts. Drives the dashboard cards."""
    counts = await status_summary(db)
    return DataResponse(data=FixitySummary(**counts))


@router.post("/recheck")
@limiter.limit("6/minute")
async def fixity_recheck_now(
    request: Request,
    current_user: Annotated[User, _admin],
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> DataResponse[FixityRecheckResult]:
    """Re-hash every fixity row immediately; return the per-status tally.

    Synchronous — the admin clicks the button and waits. For very
    large tables (>10k rows) the operator should rely on the
    scheduled cadence instead and treat this endpoint as a spot-
    check.
    """
    tally = await recheck_all(db)
    total = sum(tally.values())
    return DataResponse(data=FixityRecheckResult(**tally, total=total))
