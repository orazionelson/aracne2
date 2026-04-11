import math
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AuthorizationError
from app.db.postgres import get_async_session
from app.middleware.acl import ROLE_LEVEL, get_current_user, require_role
from app.models.user import User
from app.schemas.common import DataResponse, PaginatedResponse, PaginationMeta
from app.schemas.users import (
    RoleAssignRequest,
    UserCreate,
    UserExport,
    UserResponse,
    UserUpdate,
)
from app.services.users import (
    assign_role,
    create_user,
    delete_my_account,
    export_my_data,
    get_user,
    list_users,
    revoke_role,
    soft_delete_user,
    update_user,
)

router = APIRouter(prefix="/users", tags=["users"])


# ── Self-service (GDPR) ───────────────────────────────────────────────────────
# These routes must be declared BEFORE /{user_id} to avoid path conflicts.

@router.get("/me/export")
async def export_me(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> DataResponse[UserExport]:
    data = await export_my_data(db, current_user)
    return DataResponse(data=data)


@router.delete("/me", status_code=204)
async def delete_me(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> None:
    await delete_my_account(db, current_user)


# ── Admin/EiC user management ─────────────────────────────────────────────────

@router.get("")
async def users_list(
    current_user: Annotated[User, Depends(require_role(min_role="EditorInChief"))],
    request: Request,
    db: Annotated[AsyncSession, Depends(get_async_session)],
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
    search: str | None = Query(default=None),
    role: str | None = Query(default=None),
    is_active: bool | None = Query(default=None),
    include_deleted: bool = Query(default=False),
) -> PaginatedResponse[UserResponse]:
    # include_deleted is restricted to Admin
    if include_deleted and ROLE_LEVEL.get(request.state.role, 0) < ROLE_LEVEL["Admin"]:
        include_deleted = False

    users, total = await list_users(
        db, page, per_page, search, role, is_active, include_deleted
    )
    return PaginatedResponse(
        data=users,
        pagination=PaginationMeta(
            page=page,
            per_page=per_page,
            total=total,
            total_pages=math.ceil(total / per_page) if total else 0,
        ),
    )


@router.post("", status_code=201)
async def user_create(
    request: Request,
    body: UserCreate,
    current_user: Annotated[User, Depends(require_role(min_role="EditorInChief"))],
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> DataResponse[UserResponse]:
    # An actor cannot assign a role whose level exceeds their own.
    actor_level = ROLE_LEVEL.get(request.state.role, 0)
    if ROLE_LEVEL.get(body.role, 0) > actor_level:
        raise AuthorizationError()
    data = await create_user(db, body, current_user)
    return DataResponse(data=data)


@router.get("/{user_id}")
async def user_detail(
    user_id: str,
    current_user: Annotated[User, Depends(require_role(min_role="EditorInChief"))],
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> DataResponse[UserResponse]:
    data = await get_user(db, user_id)
    return DataResponse(data=data)


@router.patch("/{user_id}")
async def user_update(
    user_id: uuid.UUID,
    body: UserUpdate,
    current_user: Annotated[User, Depends(require_role(min_role="Admin"))],
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> DataResponse[UserResponse]:
    data = await update_user(db, user_id, body, current_user)
    return DataResponse(data=data)


@router.delete("/{user_id}", status_code=204)
async def user_soft_delete(
    user_id: uuid.UUID,
    current_user: Annotated[User, Depends(require_role(min_role="Admin"))],
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> None:
    await soft_delete_user(db, user_id, current_user)


# ── Role management ───────────────────────────────────────────────────────────

@router.post("/{user_id}/roles", status_code=201)
async def role_assign(
    user_id: uuid.UUID,
    body: RoleAssignRequest,
    current_user: Annotated[User, Depends(require_role(min_role="Admin"))],
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> DataResponse[UserResponse]:
    data = await assign_role(db, user_id, body.role_name, current_user)
    return DataResponse(data=data)


@router.delete("/{user_id}/roles/{role_name}", status_code=200)
async def role_revoke(
    user_id: uuid.UUID,
    role_name: str,
    current_user: Annotated[User, Depends(require_role(min_role="Admin"))],
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> DataResponse[UserResponse]:
    data = await revoke_role(db, user_id, role_name, current_user)
    return DataResponse(data=data)
