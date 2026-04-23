import uuid
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.postgres import get_async_session
from app.middleware.acl import get_current_user, require_role
from app.middleware.rate_limiter import STRICT_LIMIT, limiter
from app.models.audit_log import AuditLog
from app.models.user import User
from app.schemas.auth import (
    ImpersonationResponse,
    LoginRequest,
    PasswordChangeRequest,
    TokenResponse,
    UserMeResponse,
    UserMeUpdate,
)
from app.schemas.common import DataResponse
from app.services.auth import (
    authenticate_user,
    change_password,
    create_impersonation_token,
    create_session,
    decode_token,
    get_active_role,
    refresh_session,
    revoke_session,
)

router = APIRouter(prefix="/auth", tags=["auth"])
logger = structlog.get_logger()

_REFRESH_COOKIE = "refresh_token"
_COOKIE_MAX_AGE = settings.jwt_refresh_expiry_days * 86400  # seconds


def _set_refresh_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=_REFRESH_COOKIE,
        value=token,
        httponly=True,
        secure=settings.is_production,
        samesite="strict" if settings.is_production else "lax",
        max_age=_COOKIE_MAX_AGE,
        path="/api/v1/auth",  # restrict cookie scope to auth endpoints
    )


def _clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(
        key=_REFRESH_COOKIE,
        path="/api/v1/auth",
    )


@router.post("/login")
@limiter.limit(STRICT_LIMIT)
async def login(
    request: Request,
    response: Response,
    body: LoginRequest,
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> DataResponse[dict[str, object]]:
    """Authenticate with username/email and password.

    Returns the access token in the response body and sets the refresh token
    in an httpOnly, SameSite=Strict cookie scoped to /api/v1/auth.
    """
    user = await authenticate_user(db, body.username_or_email, body.password)
    role = await get_active_role(db, user.id)
    ip = request.headers.get("X-Forwarded-For", request.client.host if request.client else None)
    user_agent = request.headers.get("User-Agent")
    access_token, refresh_token = await create_session(db, user, role, ip, user_agent)
    _set_refresh_cookie(response, refresh_token)
    return DataResponse(
        data={
            "access_token": access_token,
            "token_type": "bearer",
            "user": UserMeResponse(
                id=str(user.id),
                username=user.username,
                email=user.email,
                display_name=user.display_name,
                role=role,
                preferred_lang=user.preferred_lang,
                orcid=user.orcid,
                created_at=user.created_at.isoformat(),
                last_login_at=user.last_login_at.isoformat() if user.last_login_at else None,
            ).model_dump(),
        }
    )


@router.post("/refresh")
async def refresh(
    request: Request,
    response: Response,
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> DataResponse[TokenResponse]:
    """Rotate the refresh token and issue a new access token.

    Reads the refresh token from the httpOnly cookie, revokes the old session,
    and creates a new one. Sets an updated refresh cookie on success.
    """
    refresh_token = request.cookies.get(_REFRESH_COOKIE)
    if not refresh_token:
        from app.core.exceptions import AuthenticationError
        raise AuthenticationError(
            code="MISSING_REFRESH_TOKEN",
            message="Refresh token cookie not found",
        )
    ip = request.headers.get("X-Forwarded-For", request.client.host if request.client else None)
    user_agent = request.headers.get("User-Agent")
    access_token, new_refresh_token = await refresh_session(db, refresh_token, ip, user_agent)
    _set_refresh_cookie(response, new_refresh_token)
    return DataResponse(data=TokenResponse(access_token=access_token))


@router.post("/logout")
async def logout(
    request: Request,
    response: Response,
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> DataResponse[dict[str, str]]:
    """Revoke the current session and clear the refresh cookie.

    Best-effort: always returns 204, even if the access token is missing,
    expired, or already revoked.
    """
    # Best-effort revocation — do not raise even if token is missing or invalid
    try:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header.removeprefix("Bearer ")
            payload = decode_token(token, "access")
            jti = uuid.UUID(str(payload["jti"]))
            await revoke_session(db, jti)
    except Exception:  # noqa: BLE001
        logger.debug("logout_token_revoke_skipped", reason="invalid or expired token")
    _clear_refresh_cookie(response)
    return DataResponse(data={"message": "Logged out successfully"})


@router.patch("/me")
async def update_me(
    body: UserMeUpdate,
    current_user: Annotated[User, Depends(get_current_user)],
    request: Request,
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> DataResponse[UserMeResponse]:
    """Self-service patch: display_name, preferred_lang, orcid.

    An empty-string ``orcid`` clears the stored value; any other value
    is validated upstream (Pydantic) for format + checksum, so here we
    just apply it verbatim.
    """
    if "display_name" in body.model_fields_set:
        current_user.display_name = body.display_name
    if body.preferred_lang is not None:
        current_user.preferred_lang = body.preferred_lang
    if "orcid" in body.model_fields_set:
        current_user.orcid = body.orcid or None
    await db.flush()
    role = request.state.role
    return DataResponse(
        data=UserMeResponse(
            id=str(current_user.id),
            username=current_user.username,
            email=current_user.email,
            display_name=current_user.display_name,
            role=role,
            preferred_lang=current_user.preferred_lang,
            orcid=current_user.orcid,
            created_at=current_user.created_at.isoformat(),
            last_login_at=(
                current_user.last_login_at.isoformat()
                if current_user.last_login_at
                else None
            ),
        )
    )


@router.get("/me")
async def me(
    current_user: Annotated[User, Depends(get_current_user)],
    request: Request,
) -> DataResponse[UserMeResponse]:
    """Return the authenticated user's profile.

    The role is read from the JWT payload — no additional DB query is issued.
    """
    role = request.state.role
    return DataResponse(
        data=UserMeResponse(
            id=str(current_user.id),
            username=current_user.username,
            email=current_user.email,
            display_name=current_user.display_name,
            role=role,
            preferred_lang=current_user.preferred_lang,
            orcid=current_user.orcid,
            created_at=current_user.created_at.isoformat(),
            last_login_at=(
                current_user.last_login_at.isoformat()
                if current_user.last_login_at
                else None
            ),
        )
    )


@router.post("/password/change")
@limiter.limit(STRICT_LIMIT)
async def password_change(
    request: Request,
    body: PasswordChangeRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> DataResponse[dict[str, str]]:
    """Change the current user's password and invalidate all active sessions.

    Forbidden while acting under an impersonation token.
    """
    from app.core.exceptions import AuthorizationError
    if getattr(request.state, "impersonated_by", None):
        raise AuthorizationError()
    await change_password(db, current_user, body.current_password, body.new_password)
    return DataResponse(data={"message": "Password changed successfully"})


@router.post("/impersonate/{user_id}")
async def impersonate(
    user_id: uuid.UUID,
    request: Request,
    current_user: Annotated[User, Depends(require_role(min_role="Admin"))],
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> DataResponse[ImpersonationResponse]:
    """Start an impersonation session as a non-Admin user.

    Returns a short-lived (30 min) stateless JWT. The caller's refresh cookie
    is left untouched, so calling POST /auth/refresh after restoring the
    original access token resumes the Admin session normally.

    Restrictions:
    - Cannot impersonate while already impersonating.
    - Cannot impersonate Admin users.
    - Target user must be active and not deleted.
    """
    from app.core.exceptions import AuthorizationError, NotFoundError

    if getattr(request.state, "impersonated_by", None):
        raise AuthorizationError()

    target = await db.get(User, user_id)
    if not target or not target.is_active or target.deleted_at:
        raise NotFoundError(message="User not found")

    target_role = await get_active_role(db, target.id)
    if target_role == "Admin":
        raise AuthorizationError()

    token = create_impersonation_token(current_user, target, target_role)

    db.add(AuditLog(
        action="user.impersonation_started",
        actor_id=current_user.id,
        actor_username=current_user.username,
        target_type="user",
        target_id=str(target.id),
        target_label=target.username,
        payload={"target_role": target_role},
    ))

    logger.info(
        "impersonation_started",
        admin=current_user.username,
        target=target.username,
        target_role=target_role,
    )
    return DataResponse(
        data=ImpersonationResponse(
            access_token=token,
            impersonated_user=UserMeResponse(
                id=str(target.id),
                username=target.username,
                email=target.email,
                display_name=target.display_name,
                role=target_role,
                preferred_lang=target.preferred_lang,
                orcid=target.orcid,
                created_at=target.created_at.isoformat(),
                last_login_at=target.last_login_at.isoformat() if target.last_login_at else None,
            ),
        )
    )
