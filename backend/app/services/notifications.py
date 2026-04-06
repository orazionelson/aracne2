from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AuthorizationError, NotFoundError
from app.models.notification import Notification
from app.models.user import User
from app.schemas.common import PaginationMeta
from app.schemas.notifications import NotificationResponse


async def list_notifications(
    db: AsyncSession,
    user: User,
    page: int = 1,
    per_page: int = 20,
    unread_only: bool = False,
) -> tuple[list[NotificationResponse], PaginationMeta]:
    stmt = select(Notification).where(Notification.user_id == user.id)
    if unread_only:
        stmt = stmt.where(Notification.is_read.is_(False))

    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = await db.scalar(count_stmt) or 0

    stmt = stmt.order_by(Notification.is_read.asc(), Notification.created_at.desc())
    stmt = stmt.offset((page - 1) * per_page).limit(per_page)
    rows = list(await db.scalars(stmt))

    import math

    return (
        [NotificationResponse.model_validate(r) for r in rows],
        PaginationMeta(
            page=page,
            per_page=per_page,
            total=total,
            total_pages=math.ceil(total / per_page) if total else 0,
        ),
    )


async def unread_count(db: AsyncSession, user: User) -> int:
    result = await db.scalar(
        select(func.count()).where(
            Notification.user_id == user.id,
            Notification.is_read.is_(False),
        )
    )
    return result or 0


async def _get_own_or_404(db: AsyncSession, notification_id: int, user: User) -> Notification:
    row = await db.get(Notification, notification_id)
    if not row:
        raise NotFoundError("Notification not found")
    if row.user_id != user.id:
        raise AuthorizationError("Access denied")
    return row


async def mark_read(
    db: AsyncSession, notification_id: int, user: User
) -> NotificationResponse:
    row = await _get_own_or_404(db, notification_id, user)
    if not row.is_read:
        row.is_read = True
        row.read_at = datetime.now(UTC)
        await db.flush()
    return NotificationResponse.model_validate(row)


async def mark_all_read(db: AsyncSession, user: User) -> int:
    """Mark all unread notifications as read. Returns the count updated."""
    now = datetime.now(UTC)
    rows = list(
        await db.scalars(
            select(Notification).where(
                Notification.user_id == user.id,
                Notification.is_read.is_(False),
            )
        )
    )
    for row in rows:
        row.is_read = True
        row.read_at = now
    await db.flush()
    return len(rows)


async def delete_notification(
    db: AsyncSession, notification_id: int, user: User
) -> None:
    row = await _get_own_or_404(db, notification_id, user)
    await db.delete(row)
    await db.flush()
