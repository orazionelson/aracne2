import math
import uuid
from typing import Annotated

import mimetypes

from fastapi import APIRouter, Depends, HTTPException, Query, Request, UploadFile
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AuthorizationError
from app.db.postgres import get_async_session
from app.core.constants import ROLE_LEVEL
from app.middleware.acl import get_current_user, require_role
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
    delete_avatar,
    delete_my_account,
    export_my_data,
    get_user,
    list_users,
    read_avatar,
    revoke_role,
    soft_delete_user,
    update_user,
    upload_avatar,
)
from sqlalchemy import select as _select

router = APIRouter(prefix="/users", tags=["users"])


# ── Self-service (GDPR) ───────────────────────────────────────────────────────
# These routes must be declared BEFORE /{user_id} to avoid path conflicts.

@router.get("/me/export")
async def export_me(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> DataResponse[UserExport]:
    """Export personal data for the authenticated user (GDPR art. 20).

    Returns profile fields, active roles, and session count.
    Password hash, IP address, and user-agent are never included.
    """
    data = await export_my_data(db, current_user)
    return DataResponse(data=data)


@router.delete("/me", status_code=204)
async def delete_me(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> None:
    """Permanently delete the authenticated user's account (GDPR art. 17).

    Hard-deletes the user row; cascades to sessions and user_roles.
    Audit log entries are anonymized (actor_id set to NULL).
    """
    await delete_my_account(db, current_user)


@router.patch("/me")
async def patch_me(
    body: UserUpdate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> DataResponse[UserResponse]:
    """Self-service profile patch.

    Limited to the fields a user can change about themselves —
    ``display_name``, ``preferred_lang``, ``orcid``, ``bio``.
    Anything else in the payload (``is_active``, ``email``,
    ``is_verified``) is silently ignored to avoid privilege
    escalation: a regular user must not flip themselves to active /
    verified or hijack someone else's email.
    """
    safe = UserUpdate(
        display_name=body.display_name,
        preferred_lang=body.preferred_lang,
        orcid=body.orcid,
        bio=body.bio,
    )
    data = await update_user(db, current_user.id, safe, current_user)
    return DataResponse(data=data)


@router.post("/me/avatar")
async def upload_my_avatar(
    file: UploadFile,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> DataResponse[UserResponse]:
    """Upload a new avatar for the authenticated user.

    Allowed: jpg/jpeg/png/gif/webp/avif, up to 1 MB. Replaces any
    previous upload. Returns the refreshed UserResponse.
    """
    payload = await file.read()
    data = await upload_avatar(db, current_user, payload, file.filename or "avatar")
    return DataResponse(data=data)


@router.delete("/me/avatar", status_code=204)
async def delete_my_avatar(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> None:
    """Remove the calling user's avatar — falls back to the monogram."""
    await delete_avatar(db, current_user)


@router.get("/{username}/avatar", include_in_schema=False)
async def serve_avatar(
    username: str,
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> Response:
    """Serve a user's uploaded avatar.

    Public (no auth) so the same image can be embedded in user-mention
    surfaces, the workflow timeline, and any other place that lists
    contributors. Returns 404 when the user has no upload — the UI
    falls back to the monogram in that case.
    """
    user = await db.scalar(_select(User).where(User.username == username))
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    result = read_avatar(user)
    if result is None:
        raise HTTPException(status_code=404, detail="No avatar uploaded")
    payload, content_type = result
    return Response(
        content=payload,
        media_type=content_type,
        headers={"Cache-Control": "public, max-age=300"},
    )


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
    """List users with optional filters.

    include_deleted is silently downgraded to False for non-Admin callers,
    even though the endpoint is accessible to EditorInChief.
    """
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
    """Create a new user account.

    Admin-created accounts are automatically pre-verified.
    The actor cannot assign a role whose level exceeds their own.
    """
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
    """Retrieve a user by UUID or username."""
    data = await get_user(db, user_id)
    return DataResponse(data=data)


@router.patch("/{user_id}")
async def user_update(
    user_id: uuid.UUID,
    body: UserUpdate,
    current_user: Annotated[User, Depends(require_role(min_role="Admin"))],
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> DataResponse[UserResponse]:
    """Update mutable user fields.

    Deactivating a user (is_active=False) revokes all their active sessions.
    """
    data = await update_user(db, user_id, body, current_user)
    return DataResponse(data=data)


@router.delete("/{user_id}", status_code=204)
async def user_soft_delete(
    user_id: uuid.UUID,
    current_user: Annotated[User, Depends(require_role(min_role="Admin"))],
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> None:
    """Soft-delete a user (sets deleted_at, deactivates, revokes sessions).

    Cannot be used to delete the calling user's own account.
    """
    await soft_delete_user(db, user_id, current_user)


# ── Role management ───────────────────────────────────────────────────────────

@router.post("/{user_id}/roles", status_code=201)
async def role_assign(
    user_id: uuid.UUID,
    body: RoleAssignRequest,
    current_user: Annotated[User, Depends(require_role(min_role="Admin"))],
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> DataResponse[UserResponse]:
    """Assign a role to a user.

    Invalidates all active sessions so the next token refresh picks up the
    new role. Raises 409 if the role is already active.
    """
    data = await assign_role(db, user_id, body.role_name, current_user)
    return DataResponse(data=data)


@router.delete("/{user_id}/roles/{role_name}", status_code=200)
async def role_revoke(
    user_id: uuid.UUID,
    role_name: str,
    current_user: Annotated[User, Depends(require_role(min_role="Admin"))],
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> DataResponse[UserResponse]:
    """Revoke an active role from a user.

    Invalidates all active sessions. Raises 404 if the role is not active.
    """
    data = await revoke_role(db, user_id, role_name, current_user)
    return DataResponse(data=data)
