from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.postgres import get_async_session
from app.middleware.acl import get_current_user
from app.models.user import User
from app.schemas.common import DataResponse, PaginatedResponse
from app.schemas.notifications import NotificationResponse
from app.services.notifications import (
    delete_notification,
    list_notifications,
    mark_all_read,
    mark_read,
    unread_count,
)

router = APIRouter(prefix="/notifications", tags=["notifications"])

_auth = Depends(get_current_user)


# ── These routes MUST be declared before /{notification_id} ───────────────────

@router.get("/unread-count")
async def notifications_unread_count(
    current_user: Annotated[User, _auth],
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> DataResponse[int]:
    count = await unread_count(db, current_user)
    return DataResponse(data=count)


@router.post("/read-all")
async def notifications_read_all(
    current_user: Annotated[User, _auth],
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> DataResponse[int]:
    """Mark all unread notifications as read. Returns count updated."""
    count = await mark_all_read(db, current_user)
    return DataResponse(data=count)


# ── List + per-item operations ─────────────────────────────────────────────────

@router.get("")
async def notifications_list(
    current_user: Annotated[User, _auth],
    db: Annotated[AsyncSession, Depends(get_async_session)],
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
    unread_only: bool = Query(default=False),
) -> PaginatedResponse[NotificationResponse]:
    items, pagination = await list_notifications(
        db, current_user, page, per_page, unread_only
    )
    return PaginatedResponse(data=items, pagination=pagination)


@router.patch("/{notification_id}/read")
async def notification_read(
    notification_id: int,
    current_user: Annotated[User, _auth],
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> DataResponse[NotificationResponse]:
    data = await mark_read(db, notification_id, current_user)
    return DataResponse(data=data)


@router.delete("/{notification_id}", status_code=204)
async def notification_delete(
    notification_id: int,
    current_user: Annotated[User, _auth],
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> None:
    await delete_notification(db, notification_id, current_user)
