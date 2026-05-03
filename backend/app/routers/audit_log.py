"""``/audit-log`` admin surface — FUTURE_IDEAS §20.

Four endpoints, all Admin-gated:

- ``GET  /audit-log`` — paginated, filtered list.
- ``GET  /audit-log/actions`` — curated dropdown vocabulary.
- ``GET  /audit-log/{entry_id}`` — full single row including JSONB
  payload and user_agent.
- ``GET  /audit-log/export.csv`` — CSV stream of the same filtered
  query, no pagination.

The structured filters and the ``q`` free-text box compose: any
combination is valid; the service ANDs them. Date filters accept
ISO-8601 strings (``2026-04-01T00:00:00Z``); naive strings are
treated as UTC.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.postgres import get_async_session
from app.middleware.acl import require_role
from app.middleware.rate_limiter import limiter
from app.models.user import User
from app.schemas.audit_log import AuditLogDetail, AuditLogEntry
from app.schemas.common import DataResponse, PaginatedResponse
from app.services.audit_log import (
    get_entry,
    list_entries,
    list_known_actions,
    stream_csv,
)


router = APIRouter(prefix="/audit-log", tags=["audit_log"])
_admin = Depends(require_role(min_role="Admin"))


def _parse_dt(raw: str | None) -> datetime | None:
    """ISO-8601 → tz-aware UTC datetime; ``None`` passes through.

    Naive strings get UTC stamped on so the comparison against the
    tz-aware ``occurred_at`` column is unambiguous.
    """
    if raw is None or not raw.strip():
        return None
    text = raw.strip().replace("Z", "+00:00")
    dt = datetime.fromisoformat(text)
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


@router.get("")
@limiter.limit("60/minute")
async def audit_log_list(
    request: Request,
    current_user: Annotated[User, _admin],
    db: Annotated[AsyncSession, Depends(get_async_session)],
    page: Annotated[int, Query(ge=1)] = 1,
    per_page: Annotated[int, Query(ge=1, le=100)] = 20,
    q: Annotated[str | None, Query(max_length=200)] = None,
    actor_id: Annotated[uuid.UUID | None, Query()] = None,
    actor_username: Annotated[str | None, Query(max_length=64)] = None,
    action: Annotated[str | None, Query(max_length=128)] = None,
    target_type: Annotated[str | None, Query(max_length=64)] = None,
    target_id: Annotated[str | None, Query(max_length=128)] = None,
    from_: Annotated[str | None, Query(alias="from")] = None,
    to: Annotated[str | None, Query()] = None,
) -> PaginatedResponse[AuditLogEntry]:
    """Paginated audit-log listing. Filters compose; ``q`` is ILIKE."""
    return await list_entries(
        db,
        page=page,
        per_page=per_page,
        q=q,
        actor_id=actor_id,
        actor_username=actor_username,
        action=action,
        target_type=target_type,
        target_id=target_id,
        from_dt=_parse_dt(from_),
        to_dt=_parse_dt(to),
    )


@router.get("/actions")
@limiter.limit("60/minute")
async def audit_log_actions(
    request: Request,
    current_user: Annotated[User, _admin],
) -> DataResponse[list[str]]:
    """Curated action vocabulary for the filter dropdown."""
    return DataResponse(data=list_known_actions())


@router.get("/export.csv")
@limiter.limit("10/minute")
async def audit_log_export_csv(
    request: Request,
    current_user: Annotated[User, _admin],
    db: Annotated[AsyncSession, Depends(get_async_session)],
    q: Annotated[str | None, Query(max_length=200)] = None,
    actor_id: Annotated[uuid.UUID | None, Query()] = None,
    actor_username: Annotated[str | None, Query(max_length=64)] = None,
    action: Annotated[str | None, Query(max_length=128)] = None,
    target_type: Annotated[str | None, Query(max_length=64)] = None,
    target_id: Annotated[str | None, Query(max_length=128)] = None,
    from_: Annotated[str | None, Query(alias="from")] = None,
    to: Annotated[str | None, Query()] = None,
) -> StreamingResponse:
    """Stream the filtered audit log as CSV. Same filters as the list."""
    generator = stream_csv(
        db,
        q=q,
        actor_id=actor_id,
        actor_username=actor_username,
        action=action,
        target_type=target_type,
        target_id=target_id,
        from_dt=_parse_dt(from_),
        to_dt=_parse_dt(to),
    )
    return StreamingResponse(
        generator,
        media_type="text/csv",
        headers={
            "Content-Disposition": 'attachment; filename="audit-log.csv"',
            "Cache-Control": "no-store",
        },
    )


@router.get("/{entry_id}")
@limiter.limit("60/minute")
async def audit_log_detail(
    request: Request,
    entry_id: int,
    current_user: Annotated[User, _admin],
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> DataResponse[AuditLogDetail]:
    """One audit-log row + JSONB payload + user_agent."""
    entry = await get_entry(db, entry_id)
    return DataResponse(data=entry)
