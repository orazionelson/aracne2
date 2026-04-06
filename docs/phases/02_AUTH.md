# PHASE 02 — Authentication: JWT, sessions, ACL middleware
# Prerequisite: CLAUDE.md loaded. Phases 01a–01e complete and passing.
# Goal: full authentication flow working end-to-end:
#   POST /auth/login → access_token (body) + refresh_token (httpOnly cookie)
#   POST /auth/refresh → new access_token
#   POST /auth/logout → cookie cleared, session revoked
#   GET  /auth/me → current user profile
#   POST /auth/password/change → password update

# Implement everything below. Every file must be complete and working.
# Do not add unrequested features. Do not leave placeholder TODOs.

---

## Overview

Token strategy (already in frontend, now implemented in backend):
- `access_token`: short-lived JWT (default 60 min), returned in response body only.
  Frontend stores it in Pinia memory (never localStorage).
- `refresh_token`: long-lived JWT (default 30 days), sent via `Set-Cookie` with
  `HttpOnly; SameSite=Strict; Secure` (Secure omitted in development).
  Frontend never reads it — browser sends it automatically to `/auth/refresh`.

Every active session is tracked in the `sessions` table. Logout revokes the session.
The middleware validates the access token against `sessions.revoked_at`.

---

## File: backend/app/services/auth.py

Business logic for all auth operations. No FastAPI imports — pure async functions.

```python
import uuid
from datetime import UTC, datetime, timedelta

import passlib.hash as ph
import structlog
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.exceptions import AuthenticationError, DomainValidationError
from app.models.role import UserRole
from app.models.session import Session
from app.models.user import User

logger = structlog.get_logger()

# ── Token helpers ─────────────────────────────────────────────────────────────

def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def create_access_token(user_id: uuid.UUID, jti: uuid.UUID, role: str) -> str:
    """Return a signed JWT access token."""
    expire = _now() + timedelta(minutes=settings.jwt_access_expiry_minutes)
    payload = {
        "sub": str(user_id),
        "jti": str(jti),
        "role": role,
        "exp": expire,
        "iat": _now(),
        "type": "access",
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def create_refresh_token(user_id: uuid.UUID, jti: uuid.UUID) -> str:
    """Return a signed JWT refresh token."""
    expire = _now() + timedelta(days=settings.jwt_refresh_expiry_days)
    payload = {
        "sub": str(user_id),
        "jti": str(jti),
        "exp": expire,
        "iat": _now(),
        "type": "refresh",
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def decode_token(token: str, expected_type: str) -> dict[str, object]:
    """
    Decode and validate a JWT. Raises AuthenticationError on any failure.
    expected_type: "access" | "refresh"
    """
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
    except JWTError as exc:
        raise AuthenticationError(
            code="INVALID_TOKEN", message="Token is invalid or expired"
        ) from exc
    if payload.get("type") != expected_type:
        raise AuthenticationError(
            code="INVALID_TOKEN", message=f"Expected {expected_type} token"
        )
    return payload


# ── Auth operations ───────────────────────────────────────────────────────────

async def authenticate_user(
    db: AsyncSession,
    username_or_email: str,
    password: str,
) -> User:
    """
    Verify credentials. Raises AuthenticationError on failure.
    Does NOT distinguish between wrong username and wrong password (timing-safe).
    """
    stmt = select(User).where(
        (User.username == username_or_email) | (User.email == username_or_email),
        User.deleted_at.is_(None),
    )
    user = await db.scalar(stmt)
    # Always run hash check to avoid timing attacks even when user is not found
    dummy = "$2b$12$" + "a" * 53
    candidate_hash = user.password_hash if user else dummy
    valid = ph.bcrypt.verify(password, candidate_hash)
    if not user or not valid or not user.is_active:
        raise AuthenticationError(
            code="INVALID_CREDENTIALS",
            message="Invalid credentials",
        )
    return user


async def get_active_role(db: AsyncSession, user_id: uuid.UUID) -> str:
    """Return the highest active role name for a user."""
    from app.models.role import Role

    ROLE_LEVEL: dict[str, int] = {
        "Admin": 4, "EditorInChief": 3,
        "Designer": 2, "Editor": 2, "User": 1,
    }
    stmt = (
        select(Role.name)
        .join(UserRole, UserRole.role_id == Role.id)
        .where(
            UserRole.user_id == user_id,
            UserRole.revoked_at.is_(None),
        )
    )
    roles = list(await db.scalars(stmt))
    if not roles:
        return "User"
    return max(roles, key=lambda r: ROLE_LEVEL.get(str(r), 0))


async def create_session(
    db: AsyncSession,
    user: User,
    role: str,
    ip_address: str | None,
    user_agent: str | None,
) -> tuple[str, str]:
    """
    Create a new session row and return (access_token, refresh_token).
    Both JTIs are generated fresh for every login.
    """
    access_jti = uuid.uuid4()
    refresh_jti = uuid.uuid4()

    access_expires = _now() + timedelta(minutes=settings.jwt_access_expiry_minutes)
    refresh_expires = _now() + timedelta(days=settings.jwt_refresh_expiry_days)

    session = Session(
        user_id=user.id,
        access_jti=access_jti,
        refresh_jti=refresh_jti,
        ip_address=ip_address,
        user_agent=user_agent,
        access_expires=access_expires,
        refresh_expires=refresh_expires,
    )
    db.add(session)
    await db.flush()

    access_token = create_access_token(user.id, access_jti, role)
    refresh_token = create_refresh_token(user.id, refresh_jti)

    logger.info(
        "session_created",
        user_id=str(user.id),
        username=user.username,
        role=role,
    )
    return access_token, refresh_token


async def refresh_session(
    db: AsyncSession,
    refresh_token: str,
    ip_address: str | None,
    user_agent: str | None,
) -> tuple[str, str]:
    """
    Validate a refresh token, rotate both tokens, and return
    (new_access_token, new_refresh_token).
    Old session is revoked; new session row is created.
    """
    payload = decode_token(refresh_token, "refresh")
    refresh_jti = uuid.UUID(str(payload["jti"]))

    stmt = select(Session).where(
        Session.refresh_jti == refresh_jti,
        Session.revoked_at.is_(None),
    )
    session = await db.scalar(stmt)
    if not session:
        raise AuthenticationError(
            code="SESSION_NOT_FOUND",
            message="Session not found or already revoked",
        )
    if session.refresh_expires and session.refresh_expires < _now():
        raise AuthenticationError(
            code="TOKEN_EXPIRED",
            message="Refresh token has expired",
        )

    user = await db.get(User, session.user_id)
    if not user or not user.is_active or user.deleted_at:
        raise AuthenticationError(
            code="USER_INACTIVE",
            message="User account is inactive",
        )

    # Revoke old session
    session.revoked_at = _now()
    session.revoked_reason = "rotated"

    role = await get_active_role(db, user.id)
    return await create_session(db, user, role, ip_address, user_agent)


async def revoke_session(db: AsyncSession, access_jti: uuid.UUID) -> None:
    """Revoke the session identified by its access JTI."""
    stmt = select(Session).where(
        Session.access_jti == access_jti,
        Session.revoked_at.is_(None),
    )
    session = await db.scalar(stmt)
    if session:
        session.revoked_at = _now()
        session.revoked_reason = "logout"


async def change_password(
    db: AsyncSession,
    user: User,
    current_password: str,
    new_password: str,
) -> None:
    """Verify current password and set new hash. Invalidates all sessions."""
    if not ph.bcrypt.verify(current_password, user.password_hash):
        raise AuthenticationError(
            code="INVALID_CREDENTIALS",
            message="Current password is incorrect",
        )
    if len(new_password) < 8:
        raise DomainValidationError(
            code="PASSWORD_TOO_SHORT",
            message="Password must be at least 8 characters",
        )
    user.password_hash = ph.bcrypt.hash(new_password, rounds=settings.bcrypt_rounds)

    # Revoke all active sessions for this user
    stmt = select(Session).where(
        Session.user_id == user.id,
        Session.revoked_at.is_(None),
    )
    sessions = list(await db.scalars(stmt))
    for s in sessions:
        s.revoked_at = _now()
        s.revoked_reason = "password_change"

    logger.info("password_changed", user_id=str(user.id))
```

---

## File: backend/app/middleware/acl.py

`require_role()` returns a FastAPI dependency that validates the Bearer token
and checks the role. Inject it with `Depends(require_role(...))`.

```python
import uuid
from typing import Annotated

import structlog
from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AuthenticationError, AuthorizationError
from app.db.postgres import get_async_session
from app.models.session import Session
from app.models.user import User
from app.services.auth import decode_token

logger = structlog.get_logger()

_bearer = HTTPBearer(auto_error=False)

ROLE_LEVEL: dict[str, int] = {
    "Admin": 4,
    "EditorInChief": 3,
    "Designer": 2,
    "Editor": 2,
    "User": 1,
}


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


def require_role(min_role: str | None = None, exact_role: str | None = None):
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
```

---

## File: backend/app/schemas/auth.py

```python
from pydantic import BaseModel, EmailStr, field_validator


class LoginRequest(BaseModel):
    username_or_email: str
    password: str


class PasswordChangeRequest(BaseModel):
    current_password: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def password_min_length(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        return v


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserMeResponse(BaseModel):
    id: str
    username: str
    email: str
    display_name: str | None
    role: str
    preferred_lang: str
    created_at: str
    last_login_at: str | None

    model_config = {"from_attributes": True}
```

---

## File: backend/app/routers/auth.py

Cookie settings:
- Development: `secure=False`, `samesite="lax"` (HTTP allowed)
- Production: `secure=True`, `samesite="strict"` (HTTPS only)

```python
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
    from app.middleware.acl import _bearer
    from fastapi.security import HTTPAuthorizationCredentials
    import uuid
    try:
        from app.services.auth import decode_token
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
```

---

## File: backend/app/main.py (update only)

Add the auth router. The rest of `main.py` is unchanged.

```python
# Add this import alongside the existing health import:
from app.routers import auth

# Add this line alongside app.include_router(health.router, ...):
app.include_router(auth.router, prefix="/api/v1")
```

---

## File: backend/app/dependencies.py

Centralised dependency re-exports so routers can import from one place.

```python
from app.db.postgres import get_async_session
from app.db.existdb import get_existdb
from app.middleware.acl import get_current_user, require_role

__all__ = ["get_async_session", "get_existdb", "get_current_user", "require_role"]
```

---

## Tests: backend/app/tests/test_auth.py

Use the existing `client` and `db_session` fixtures from `conftest.py`.
The test database is SQLite in-memory — no real PostgreSQL required.

```python
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_login_wrong_credentials(client: AsyncClient) -> None:
    """Login with wrong password returns 401 in Aracne2 error format."""
    res = await client.post("/api/v1/auth/login", json={
        "username_or_email": "nonexistent",
        "password": "wrong",
    })
    assert res.status_code == 401
    body = res.json()
    assert "error" in body
    assert body["error"]["code"] == "INVALID_CREDENTIALS"


@pytest.mark.asyncio
async def test_refresh_without_cookie_returns_401(client: AsyncClient) -> None:
    """POST /auth/refresh with no cookie returns 401."""
    res = await client.post("/api/v1/auth/refresh")
    assert res.status_code == 401
    assert res.json()["error"]["code"] == "MISSING_REFRESH_TOKEN"


@pytest.mark.asyncio
async def test_me_without_token_returns_401(client: AsyncClient) -> None:
    """GET /auth/me without Bearer token returns 401."""
    res = await client.get("/api/v1/auth/me")
    assert res.status_code == 401


@pytest.mark.asyncio
async def test_password_change_without_token_returns_401(client: AsyncClient) -> None:
    """POST /auth/password/change without token returns 401."""
    res = await client.post("/api/v1/auth/password/change", json={
        "current_password": "old",
        "new_password": "newpassword",
    })
    assert res.status_code == 401


@pytest.mark.asyncio
async def test_logout_without_token_returns_200(client: AsyncClient) -> None:
    """POST /auth/logout is best-effort — returns 200 even without a token."""
    res = await client.post("/api/v1/auth/logout")
    assert res.status_code == 200
    assert res.json()["data"]["message"] == "Logged out successfully"
```

---

## Frontend: update LoginView.vue

The login view already exists. It must use `i18n` keys (already done in phase 01d
after the i18n fix). Verify that `auth.login()` in the store calls the correct
endpoint and handles the `data.data` envelope correctly.

The store already maps the response: `res.data.data.access_token` and
`res.data.data.user`. No changes needed if the phase 01d implementation is correct.

---

## Checklist before committing

- [ ] `make test` passes (all 5 new tests + all 6 scaffolding tests = 11 total)
- [ ] `make lint` clean (ruff + mypy)
- [ ] `POST /api/v1/auth/login` with valid credentials returns 200 + sets cookie
- [ ] `POST /api/v1/auth/refresh` with valid cookie returns 200 + rotates cookie
- [ ] `POST /api/v1/auth/logout` clears cookie and revokes session
- [ ] `GET /api/v1/auth/me` returns 401 without token, 200 with valid token
- [ ] Login form at `localhost:5173/login` accepts credentials and redirects to `/`
- [ ] Page reload after login silently recovers session via `hydrate()`
