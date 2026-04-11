import uuid
from collections.abc import Callable, Coroutine
from typing import Annotated, Any

import structlog
from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import ROLE_LEVEL
from app.core.exceptions import AuthenticationError, AuthorizationError
from app.db.postgres import get_async_session
from app.models.session import Session
from app.models.user import User
from app.services.auth import decode_raw_token, decode_token

logger = structlog.get_logger()

_bearer = HTTPBearer(auto_error=False)


async def _get_current_user(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> User:
    """
    Validate Bearer token, check session is not revoked, return User.
    Raises AuthenticationError on any failure.
    """
    if not credentials:
        raise AuthenticationError(
            code="MISSING_TOKEN", message="Authorization header required"
        )

    # Peek at the token type before dispatching to the appropriate path.
    raw = decode_raw_token(credentials.credentials)

    if raw.get("type") == "impersonation":
        # Stateless impersonation token: no session row, non-renewable.
        user_id = uuid.UUID(str(raw["sub"]))
        user = await db.get(User, user_id)
        if not user or not user.is_active or user.deleted_at:
            raise AuthenticationError(
                code="USER_INACTIVE", message="User account is inactive"
            )
        request.state.user = user
        request.state.role = str(raw.get("role", "User"))
        request.state.impersonated_by = str(raw.get("impersonated_by", ""))
        return user

    # Normal access token: validate type claim and look up the session.
    payload = decode_token(credentials.credentials, "access")
    jti = uuid.UUID(str(payload["jti"]))

    stmt = select(Session).where(
        Session.access_jti == jti,
        Session.revoked_at.is_(None),
    )
    session = await db.scalar(stmt)
    if not session:
        raise AuthenticationError(
            code="SESSION_REVOKED", message="Session not found or revoked"
        )

    user = await db.get(User, session.user_id)
    if not user or not user.is_active or user.deleted_at:
        raise AuthenticationError(
            code="USER_INACTIVE", message="User account is inactive"
        )

    # Attach role from token payload to request state (avoids extra DB query)
    request.state.user = user
    request.state.role = str(payload.get("role", "User"))
    return user


# Convenience alias for endpoints that only need authentication, not role check
get_current_user = _get_current_user


async def get_optional_user(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> User | None:
    """Like get_current_user, but returns None instead of raising on missing or
    invalid credentials.  Also accepts the token via the ``?_preview=`` query
    parameter so that browser-opened URLs (which cannot carry an Authorization
    header) can still reach unpublished sites.
    """
    # Prefer the Authorization header; fall back to ?_preview= query param.
    token_str: str | None = None
    if credentials:
        token_str = credentials.credentials
    elif "_preview" in request.query_params:
        token_str = request.query_params["_preview"]

    if not token_str:
        return None

    try:
        raw = decode_raw_token(token_str)
        if raw.get("type") == "impersonation":
            user_id = uuid.UUID(str(raw["sub"]))
            user = await db.get(User, user_id)
            if not user or not user.is_active or user.deleted_at:
                return None
            request.state.user = user
            request.state.role = str(raw.get("role", "User"))
            return user

        payload = decode_token(token_str, "access")
        jti = uuid.UUID(str(payload["jti"]))
        stmt = select(Session).where(
            Session.access_jti == jti,
            Session.revoked_at.is_(None),
        )
        session = await db.scalar(stmt)
        if not session:
            return None
        user = await db.get(User, session.user_id)
        if not user or not user.is_active or user.deleted_at:
            return None
        request.state.user = user
        request.state.role = str(payload.get("role", "User"))
        return user
    except (AuthenticationError, ValueError, KeyError):
        # Invalid/malformed token: missing claims, bad UUID, expired signature.
        # Any other exception is a genuine bug and should propagate.
        return None


def require_role(
    min_role: str | None = None, exact_role: str | None = None
) -> Callable[..., Coroutine[Any, Any, User]]:
    """
    Returns a FastAPI dependency that enforces ACL.

    min_role:   numeric level check — user level >= min_role level
                Use for: [auth], [E+], [EiC+], [A]
    exact_role: exact role name check (for lateral roles)
                Use for: Designer-only or Editor-only endpoints

    Both can be combined: user must satisfy both checks.
    If neither is specified, only authentication is required.
    """
    async def dependency(
        user: Annotated[User, Depends(_get_current_user)],
        request: Request,
    ) -> User:
        role = request.state.role
        user_level = ROLE_LEVEL.get(role, 0)

        if min_role is not None:
            required_level = ROLE_LEVEL.get(min_role, 0)
            if user_level < required_level:
                raise AuthorizationError()

        if exact_role is not None and role != exact_role:
            raise AuthorizationError()

        return user

    return dependency
