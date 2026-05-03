"""``/admin/capabilities`` — Phase PP-B of Milestone 3.

Three Admin-gated endpoints around the singleton capability role
primitives. The pattern is generic; today the only capability is
``PolicyManager`` but ``Translator``, ``Annotator``, etc. could
land here later as additional values of the ``RoleName`` enum
without API changes.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.db.postgres import get_async_session
from app.middleware.acl import require_role
from app.middleware.rate_limiter import limiter
from app.models.user import User
from app.schemas.common import DataResponse
from app.services.roles import (
    get_capability_holder,
    revoke_singleton_role,
    transfer_singleton_role,
)


router = APIRouter(prefix="/admin/capabilities", tags=["capabilities"])
_admin = Depends(require_role(min_role="Admin"))


class CapabilityHolderView(BaseModel):
    """The current holder of a singleton capability role, or ``null``.

    The frontend role-management UI uses this to render
    "Current PolicyManager: [user X]" and a Change button that
    opens the user-picker.
    """

    role_name: str
    holder_user_id: uuid.UUID | None = None
    holder_username: str | None = None
    holder_display_name: str | None = None


class CapabilityTransferRequest(BaseModel):
    """Request body for ``PUT /admin/capabilities/{role_name}``.

    A single ``user_id`` field — the target. The previous holder
    is revoked transactionally inside the service.
    """

    user_id: uuid.UUID


def _to_view(role_name: str, holder: User | None) -> CapabilityHolderView:
    return CapabilityHolderView(
        role_name=role_name,
        holder_user_id=holder.id if holder else None,
        holder_username=holder.username if holder else None,
        holder_display_name=(
            holder.display_name if holder else None
        ) if holder else None,
    )


@router.get("/{role_name}")
@limiter.limit("60/minute")
async def get_capability(
    request: Request,
    role_name: str,
    current_user: Annotated[User, _admin],
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> DataResponse[CapabilityHolderView]:
    """Return the current holder of *role_name*, or ``null``."""
    holder = await get_capability_holder(db, role_name=role_name)
    return DataResponse(data=_to_view(role_name, holder))


@router.put("/{role_name}")
@limiter.limit("30/minute")
async def transfer_capability(
    request: Request,
    role_name: str,
    body: CapabilityTransferRequest,
    current_user: Annotated[User, _admin],
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> DataResponse[CapabilityHolderView]:
    """Transactionally transfer *role_name* to ``body.user_id``.

    Revokes the role from the previous holder (if any) and grants
    it to the target user in the same transaction. Idempotent on
    "target already holds it".
    """
    target = await db.get(User, body.user_id)
    if target is None:
        raise NotFoundError(f"User {body.user_id} not found")
    holder = await transfer_singleton_role(
        db, role_name=role_name, target_user=target, actor=current_user
    )
    return DataResponse(data=_to_view(role_name, holder))


@router.delete("/{role_name}", status_code=204)
@limiter.limit("30/minute")
async def revoke_capability(
    request: Request,
    role_name: str,
    current_user: Annotated[User, _admin],
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> None:
    """Revoke *role_name* from its current holder. Idempotent."""
    await revoke_singleton_role(db, role_name=role_name, actor=current_user)
    return None
