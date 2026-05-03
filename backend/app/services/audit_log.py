"""Service layer for the audit-log admin view (FUTURE_IDEAS §20).

Three responsibilities:

1. :func:`list_entries` — paginated, filtered list. Filters compose:
   the optional ``q`` free-text search runs ``ILIKE`` against
   ``actor_username`` / ``action`` / ``target_label`` so an admin
   typing "anna manzoni" can find every row touching either; the
   structured filters narrow the same query when used on top.
2. :func:`get_entry` — single-row detail including the JSONB payload.
3. :func:`stream_csv` — same filters, no pagination, async generator
   yielding CSV rows for ``StreamingResponse``.

Plus :data:`KNOWN_ACTIONS` — the curated drop-down vocabulary the
frontend's filter offers. Centralising the list here avoids the
"dropdown shows every typo ever inserted" pitfall noted in the
FUTURE_IDEAS spec.
"""

from __future__ import annotations

import csv
import io
import uuid
from collections.abc import AsyncGenerator
from datetime import datetime
from typing import Any

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.models.audit_log import AuditLog
from app.schemas.audit_log import AuditLogDetail, AuditLogEntry
from app.schemas.common import PaginatedResponse, PaginationMeta


#: Curated action vocabulary surfaced in the frontend filter dropdown.
#: New audit actions land here when introduced; the dropdown stays
#: predictable instead of advertising every distinct value the table
#: has ever seen (per FUTURE_IDEAS §20 decision Q5).
KNOWN_ACTIONS: tuple[str, ...] = (
    # auth
    "auth.login_success",
    "auth.password_changed",
    "auth.password_reset_confirmed",
    "auth.password_reset_requested",
    # users / roles
    "user.created",
    "user.updated",
    "user.deactivated",
    "user.soft_deleted",
    "user.self_deleted",
    "user.data_exported",
    "user.role_assigned",
    "user.role_revoked",
    "user.avatar_uploaded",
    "user.avatar_deleted",
    "user.impersonation_started",
    # collections
    "collection.created",
    "collection.updated",
    "collection.deleted",
    "collection.assigned",
    "collection.unassigned",
    "collection.reassigned",
    "collection.permission_granted",
    "collection.permission_revoked",
    "collection.submitted",
    "collection.rejected",
    "collection.published",
    "collection.direct_published",
    "collection.unpublished",
    # documents
    "document.uploaded",
    "document.updated",
    "document.deleted",
    "document.zip_uploaded",
    "document.zones_updated",
    "document.version_saved",
    "document.version_deleted",
    "document.rolled_back",
    # media
    "media.uploaded",
    "media.deleted",
    # plugins / settings
    "plugin.activated",
    "plugin.deactivated",
)


def _build_filters(
    *,
    q: str | None,
    actor_id: uuid.UUID | None,
    actor_username: str | None,
    action: str | None,
    target_type: str | None,
    target_id: str | None,
    from_dt: datetime | None,
    to_dt: datetime | None,
) -> list[Any]:
    """Translate the request filters into a list of SQLAlchemy clauses.

    The free-text ``q`` is ANDed with every structured filter; inside
    ``q`` itself the three searched columns are ORed.
    """
    clauses: list[Any] = []
    if actor_id is not None:
        clauses.append(AuditLog.actor_id == actor_id)
    if actor_username:
        clauses.append(AuditLog.actor_username.ilike(f"%{actor_username}%"))
    if action:
        clauses.append(AuditLog.action == action)
    if target_type:
        clauses.append(AuditLog.target_type == target_type)
    if target_id:
        clauses.append(AuditLog.target_id == target_id)
    if from_dt is not None:
        clauses.append(AuditLog.occurred_at >= from_dt)
    if to_dt is not None:
        clauses.append(AuditLog.occurred_at <= to_dt)
    if q:
        needle = f"%{q.strip()}%"
        clauses.append(
            or_(
                AuditLog.actor_username.ilike(needle),
                AuditLog.action.ilike(needle),
                AuditLog.target_label.ilike(needle),
            )
        )
    return clauses


async def list_entries(
    db: AsyncSession,
    *,
    page: int,
    per_page: int,
    q: str | None = None,
    actor_id: uuid.UUID | None = None,
    actor_username: str | None = None,
    action: str | None = None,
    target_type: str | None = None,
    target_id: str | None = None,
    from_dt: datetime | None = None,
    to_dt: datetime | None = None,
) -> PaginatedResponse[AuditLogEntry]:
    """Return a paginated, filtered audit-log slice newest-first."""
    page = max(1, int(page))
    per_page = max(1, min(100, int(per_page)))
    offset = (page - 1) * per_page

    clauses = _build_filters(
        q=q,
        actor_id=actor_id,
        actor_username=actor_username,
        action=action,
        target_type=target_type,
        target_id=target_id,
        from_dt=from_dt,
        to_dt=to_dt,
    )
    where = and_(*clauses) if clauses else None

    total_stmt = select(func.count()).select_from(AuditLog)
    if where is not None:
        total_stmt = total_stmt.where(where)
    total = int(await db.scalar(total_stmt) or 0)

    rows_stmt = select(AuditLog).order_by(AuditLog.occurred_at.desc()).offset(offset).limit(per_page)
    if where is not None:
        rows_stmt = rows_stmt.where(where)
    rows = list(await db.scalars(rows_stmt))

    total_pages = (total + per_page - 1) // per_page if total else 0
    return PaginatedResponse[AuditLogEntry](
        data=[AuditLogEntry.model_validate(r) for r in rows],
        pagination=PaginationMeta(
            page=page,
            per_page=per_page,
            total=total,
            total_pages=total_pages,
        ),
    )


async def get_entry(db: AsyncSession, entry_id: int) -> AuditLogDetail:
    row = await db.get(AuditLog, entry_id)
    if row is None:
        raise NotFoundError(f"Audit log entry {entry_id} not found")
    return AuditLogDetail.model_validate(row)


def list_known_actions() -> list[str]:
    """Return the curated dropdown vocabulary."""
    return list(KNOWN_ACTIONS)


# ── CSV export ────────────────────────────────────────────────────────────────

_CSV_COLUMNS = (
    "id",
    "occurred_at",
    "action",
    "actor_username",
    "target_type",
    "target_id",
    "target_label",
)


async def stream_csv(
    db: AsyncSession,
    *,
    q: str | None = None,
    actor_id: uuid.UUID | None = None,
    actor_username: str | None = None,
    action: str | None = None,
    target_type: str | None = None,
    target_id: str | None = None,
    from_dt: datetime | None = None,
    to_dt: datetime | None = None,
    chunk_size: int = 500,
) -> AsyncGenerator[str, None]:
    """Yield CSV rows for the filtered audit log.

    No pagination — the filters are the only knob that bounds the
    output. We page through the result set in ``chunk_size`` batches
    so a 5-million-row export does not load the whole table into
    memory before the first byte reaches the client.
    """
    clauses = _build_filters(
        q=q,
        actor_id=actor_id,
        actor_username=actor_username,
        action=action,
        target_type=target_type,
        target_id=target_id,
        from_dt=from_dt,
        to_dt=to_dt,
    )
    where = and_(*clauses) if clauses else None

    # Header
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(_CSV_COLUMNS)
    yield buf.getvalue()

    last_id: int | None = None
    while True:
        stmt = select(AuditLog).order_by(AuditLog.id.desc()).limit(chunk_size)
        if where is not None:
            stmt = stmt.where(where)
        if last_id is not None:
            stmt = stmt.where(AuditLog.id < last_id)
        rows = list(await db.scalars(stmt))
        if not rows:
            return
        buf = io.StringIO()
        writer = csv.writer(buf)
        for r in rows:
            writer.writerow(
                [
                    r.id,
                    r.occurred_at.isoformat() if r.occurred_at else "",
                    r.action,
                    r.actor_username or "",
                    r.target_type or "",
                    r.target_id or "",
                    (r.target_label or "").replace("\r", " ").replace("\n", " "),
                ]
            )
        yield buf.getvalue()
        last_id = rows[-1].id
        if len(rows) < chunk_size:
            return


__all__ = [
    "KNOWN_ACTIONS",
    "list_entries",
    "get_entry",
    "list_known_actions",
    "stream_csv",
]
