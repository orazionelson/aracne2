import asyncio

import structlog
from sqlalchemy import select

from app.config import settings
from app.db.postgres import AsyncSessionLocal
from app.models.role import Role, UserRole
from app.models.session import Session  # noqa: F401 — ensure model is registered
from app.models.system_setting import SystemSetting
from app.models.user import User

logger = structlog.get_logger()

ROLES: list[tuple[str, str]] = [
    ("Admin", "Full platform access"),
    ("EditorInChief", "Manages collections and publication workflow"),
    ("Designer", "Manages XSLT templates and CSS themes"),
    ("Editor", "Creates and edits documents"),
    ("User", "Read-only access to published content"),
]

DEFAULT_SETTINGS: list[tuple[str, str, str]] = [
    ("platform_name", settings.platform_name, "string"),
    ("default_language", "it", "string"),
    ("jwt_access_expiry_min", str(settings.jwt_access_expiry_minutes), "int"),
    ("jwt_refresh_expiry_days", str(settings.jwt_refresh_expiry_days), "int"),
    ("public_registration", str(settings.public_registration).lower(), "bool"),
    ("bcrypt_rounds", str(settings.bcrypt_rounds), "int"),
    ("max_upload_size_mb", str(settings.max_upload_size_mb), "int"),
    ("search_results_per_page", "10", "int"),
    ("audit_log_retention_days", "90", "int"),
    ("expired_sessions_retention_days", "30", "int"),
]


async def seed_roles(db: object) -> None:
    for name, desc in ROLES:
        exists = await db.scalar(select(Role).where(Role.name == name))  # type: ignore[union-attr]
        if not exists:
            db.add(Role(name=name, description=desc))  # type: ignore[union-attr]
    await db.flush()  # type: ignore[union-attr]
    logger.info("seed_roles_done")


async def seed_settings(db: object) -> None:
    for key, value, type_ in DEFAULT_SETTINGS:
        exists = await db.get(SystemSetting, key)  # type: ignore[union-attr]
        if not exists:
            db.add(SystemSetting(key=key, value=value, type=type_))  # type: ignore[union-attr]
    await db.flush()  # type: ignore[union-attr]
    logger.info("seed_settings_done")


async def seed_admin(db: object) -> None:
    if not settings.admin_password:
        logger.warning(
            "seed_admin_skipped",
            reason="ADMIN_PASSWORD not set in environment — set it and re-run `make seed`",
        )
        return
    exists = await db.scalar(  # type: ignore[union-attr]
        select(User).where(User.username == settings.admin_username)
    )
    if exists:
        logger.info("seed_admin_skipped", reason="already exists")
        return

    import passlib.hash as ph

    admin = User(
        username=settings.admin_username,
        email=settings.admin_email,
        password_hash=ph.bcrypt.hash(settings.admin_password, rounds=settings.bcrypt_rounds),
        is_active=True,
        is_verified=True,
    )
    db.add(admin)  # type: ignore[union-attr]
    await db.flush()  # type: ignore[union-attr]

    # The trigger assigns the 'User' role — revoke it and assign 'Admin'
    user_role = await db.scalar(  # type: ignore[union-attr]
        select(UserRole).where(
            UserRole.user_id == admin.id,
            UserRole.revoked_at.is_(None),
        )
    )
    if user_role:
        from datetime import UTC, datetime

        user_role.revoked_at = datetime.now(UTC)

    admin_role = await db.scalar(select(Role).where(Role.name == "Admin"))  # type: ignore[union-attr]
    db.add(UserRole(user_id=admin.id, role_id=admin_role.id))  # type: ignore[union-attr]
    logger.info("seed_admin_created", username=settings.admin_username)


async def main() -> None:
    async with AsyncSessionLocal() as db:
        await seed_roles(db)
        await seed_settings(db)
        await seed_admin(db)
        await db.commit()
    print("Seed completed successfully.")


if __name__ == "__main__":
    asyncio.run(main())
