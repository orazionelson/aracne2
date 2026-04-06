import uuid
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.postgres import get_async_session
from app.middleware.acl import get_current_user
from app.middleware.rate_limiter import STRICT_LIMIT, limiter
from app.models.user import User
from app.schemas.auth import LoginRequest, PasswordChangeRequest, TokenResponse, UserMeResponse
from app.schemas.common import DataResponse
from app.services.auth import (
    authenticate_user,
    change_password,
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
    # Best-effort revocation — do not raise even if token is missing or invalid
    try:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header.removeprefix("Bearer ")
            payload = decode_token(token, "access")
            jti = uuid.UUID(str(payload["jti"]))
            await revoke_session(db, jti)
    except Exception:
        pass
    _clear_refresh_cookie(response)
    return DataResponse(data={"message": "Logged out successfully"})


@router.get("/me")
async def me(
    current_user: Annotated[User, Depends(get_current_user)],
    request: Request,
) -> DataResponse[UserMeResponse]:
    role = request.state.role
    return DataResponse(
        data=UserMeResponse(
            id=str(current_user.id),
            username=current_user.username,
            email=current_user.email,
            display_name=current_user.display_name,
            role=role,
            preferred_lang=current_user.preferred_lang,
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
    await change_password(db, current_user, body.current_password, body.new_password)
    return DataResponse(data={"message": "Password changed successfully"})
