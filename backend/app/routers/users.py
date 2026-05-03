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
    PersonalAccessTokenIssueRequest,
    PersonalAccessTokenIssueResponse,
    PersonalAccessTokenView,
    RoleAssignRequest,
    UserCreate,
    UserExport,
    UserResponse,
    UserUpdate,
)
from app.services.uploads import read_capped
from app.services.personal_access_tokens import (
    issue_pat,
    list_pats,
    revoke_pat,
)
from app.services.gdpr import (
    export_personal_data,
    submit_anonymise_request,
)
from app.services.users import (
    assign_role,
    create_user,
    delete_avatar,
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
) -> DataResponse[dict]:
    """Self-service export of personal metadata (GDPR art. 15).

    Returns the full set of admin-side personal data the platform
    stores about the calling user — profile, role grants, sessions,
    audit_log rows, notifications, PAT metadata. Excludes password
    hashes, hashed IPs, bcrypt digests, and any document body.

    Editorial contributions to published documents are NOT included
    — they form the scientific record-of-work and are preserved
    under art. 17.3.d. See ``docs/reference/GDPR_POSTURE.md``.
    """
    data = await export_personal_data(db, current_user)
    return DataResponse(data=data)


class _AnonymiseRequestBody(__import__("pydantic").BaseModel):
    """Body for ``POST /users/me/anonymise-request``.

    ``reason`` is optional free text the operator may want when
    reviewing the request (e.g. a court-order reference number).
    """

    reason: str | None = None


@router.post("/me/anonymise-request", status_code=202)
async def request_anonymise_me(
    body: _AnonymiseRequestBody,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> DataResponse[dict]:
    """Submit an anonymisation request for Admin review.

    GDPR art. 17 in editorial-platform context: the platform does
    not honour self-service deletion of accounts that have
    contributed to published scientific work, because retraction of
    such contributions affects third parties (co-authors, the
    editor-of-record, citing works) and requires an external legal
    or institutional process. This endpoint creates a *request*
    that an Admin reviews; the actual anonymisation is performed
    by the Admin via ``POST /admin/gdpr/anonymise/{request_id}``
    after that external process completes.

    Status 202 (Accepted) reflects "we have received your request
    but processing it is mediated, not immediate". Re-submitting
    while a previous request is open returns 409.

    See ``docs/reference/GDPR_POSTURE.md`` for the full posture.
    """
    row = await submit_anonymise_request(
        db, user=current_user, reason=body.reason
    )
    return DataResponse(
        data={
            "request_id": str(row.id),
            "status": row.status,
            "submitted_at": row.submitted_at.isoformat(),
            "message": (
                "Your request has been recorded. An administrator will "
                "review it. You will be notified by email when the "
                "review concludes. Until then your account remains "
                "unchanged."
            ),
        }
    )


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
    from app.services.users import _AVATAR_MAX_BYTES

    # Stream the body in 64 KB chunks so a malicious / buggy client
    # can't allocate 50 MB (nginx cap) per request before the per-route
    # size check runs. read_capped raises FILE_TOO_LARGE early.
    payload = await read_capped(file, _AVATAR_MAX_BYTES)
    data = await upload_avatar(db, current_user, payload, file.filename or "avatar")
    return DataResponse(data=data)


@router.delete("/me/avatar", status_code=204)
async def delete_my_avatar(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> None:
    """Remove the calling user's avatar — falls back to the monogram."""
    await delete_avatar(db, current_user)


# ── Personal Access Tokens (Phase CLI-A) ──────────────────────────────────


@router.get("/me/tokens")
async def list_my_tokens(
    current_user: Annotated[
        User, Depends(require_role(min_role="Editor"))
    ],
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> DataResponse[list[PersonalAccessTokenView]]:
    """List the calling user's non-revoked personal access tokens.

    Plaintext is never included — that exists only in the response of
    the issue endpoint, exactly once. Editor+ only because Users
    (level 1) shouldn't have a CLI surface in v1.
    """
    rows = await list_pats(db, current_user)
    return DataResponse(
        data=[PersonalAccessTokenView.model_validate(r) for r in rows]
    )


@router.post("/me/tokens", status_code=201)
async def issue_my_token(
    body: PersonalAccessTokenIssueRequest,
    current_user: Annotated[
        User, Depends(require_role(min_role="Editor"))
    ],
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> DataResponse[PersonalAccessTokenIssueResponse]:
    """Mint a new PAT.

    The plaintext ``token`` field is shown in this response and never
    again — the frontend must surface it as "copy this once" UX.
    """
    row, plaintext = await issue_pat(db, user=current_user, label=body.label)
    return DataResponse(
        data=PersonalAccessTokenIssueResponse(
            id=row.id,
            label=row.label,
            token=plaintext,
            created_at=row.created_at,
        )
    )


@router.delete("/me/tokens/{token_id}", status_code=204)
async def revoke_my_token(
    token_id: uuid.UUID,
    current_user: Annotated[
        User, Depends(require_role(min_role="Editor"))
    ],
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> Response:
    """Revoke a PAT belonging to the calling user. Idempotent.

    Returns 204 on success and 404 when the row does not belong to
    *current_user* (or does not exist) — an editor cannot revoke
    another user's tokens by guessing IDs.
    """
    await revoke_pat(db, user=current_user, token_id=token_id)
    return Response(status_code=204)


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
