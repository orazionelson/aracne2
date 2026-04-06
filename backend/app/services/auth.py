import uuid
from datetime import UTC, datetime, timedelta

import structlog
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.exceptions import AuthenticationError
from app.core.password import hash_password, verify_password
from app.models.role import UserRole
from app.models.session import Session
from app.models.user import User

logger = structlog.get_logger()

# ── Token helpers ─────────────────────────────────────────────────────────────


def _now() -> datetime:
    return datetime.now(UTC)


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
    valid = verify_password(password, candidate_hash)
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
    user.last_login_at = _now()
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
    if not verify_password(current_password, user.password_hash):
        raise AuthenticationError(
            code="INVALID_CREDENTIALS",
            message="Current password is incorrect",
        )
    # Minimum length is enforced by PasswordChangeRequest schema validator (422).
    # No duplicate check here.
    user.password_hash = hash_password(new_password)
    user.updated_at = _now()

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
