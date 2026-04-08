import asyncio

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.postgres import AsyncSessionLocal
from app.models.body_template import BodyTemplate
from app.models.license import License
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
    ("zip_max_size_mb", "50", "int"),
    ("zip_max_extracted_mb", "200", "int"),
    ("zip_max_files", "500", "int"),
    ("document_editor_mode", "single", "string"),
    ("platform_logo_url", "/aracne-logo.png", "string"),
    ("navbar_bg_color", "#1e40af", "string"),
]

# Default Creative Commons licenses (name, target).
# All are seeded as active. Admins can add, edit or deactivate them.
DEFAULT_LICENSES: list[tuple[str, str]] = [
    (
        "CC0 1.0 Universal (CC0 1.0) Public Domain Dedication",
        "https://creativecommons.org/publicdomain/zero/1.0/",
    ),
    (
        "Attribution 4.0 International (CC BY 4.0)",
        "https://creativecommons.org/licenses/by/4.0/",
    ),
    (
        "Attribution-ShareAlike 4.0 International (CC BY-SA 4.0)",
        "https://creativecommons.org/licenses/by-sa/4.0/",
    ),
    (
        "Attribution-NonCommercial 4.0 International (CC BY-NC 4.0)",
        "https://creativecommons.org/licenses/by-nc/4.0/",
    ),
    (
        "Attribution-NonCommercial-ShareAlike 4.0 International (CC BY-NC-SA 4.0)",
        "https://creativecommons.org/licenses/by-nc-sa/4.0/",
    ),
    (
        "Attribution-NoDerivatives 4.0 International (CC BY-ND 4.0)",
        "https://creativecommons.org/licenses/by-nd/4.0/",
    ),
    (
        "Attribution-NonCommercial-NoDerivatives 4.0 International (CC BY-NC-ND 4.0)",
        "https://creativecommons.org/licenses/by-nc-nd/4.0/",
    ),
]


async def seed_roles(db: AsyncSession) -> None:
    for name, desc in ROLES:
        exists = await db.scalar(select(Role).where(Role.name == name))
        if not exists:
            db.add(Role(name=name, description=desc))
    await db.flush()
    logger.info("seed_roles_done")


async def seed_settings(db: AsyncSession) -> None:
    for key, value, type_ in DEFAULT_SETTINGS:
        exists = await db.get(SystemSetting, key)
        if not exists:
            db.add(SystemSetting(key=key, value=value, type=type_))
    await db.flush()
    logger.info("seed_settings_done")


async def seed_licenses(db: AsyncSession) -> None:
    """Seed default Creative Commons licenses if not already present (matched by name)."""
    for name, target in DEFAULT_LICENSES:
        exists = await db.scalar(select(License).where(License.name == name))
        if not exists:
            db.add(License(name=name, target=target, is_active=True))
    await db.flush()
    logger.info("seed_licenses_done")


DEFAULT_BODY_TEMPLATES: list[tuple[str, str]] = [
    (
        "generic",
        "<docDate>\n  <date>YYYY-MM-DD</date>\n</docDate>\n"
        "<div type=\"protocollo\"/>\n"
        "<div type=\"testo\"/>\n"
        "<div type=\"escatocollo\"/>",
    ),
    (
        "epistola",
        "<docDate>\n  <date/>\n</docDate>\n"
        "<div type=\"inscriptio\"/>\n"
        "<div type=\"rubrica\"/>\n"
        "<div type=\"salutatio\"/>\n"
        "<div type=\"exordium\"/>\n"
        "<div type=\"narratio\"/>\n"
        "<div type=\"petitio\"/>\n"
        "<div type=\"conclusio\"/>",
    ),
]


async def seed_body_templates(db: AsyncSession) -> None:
    """Seed default body templates if not already present (matched by label)."""
    for label, snippet in DEFAULT_BODY_TEMPLATES:
        exists = await db.scalar(select(BodyTemplate).where(BodyTemplate.label == label))
        if not exists:
            db.add(BodyTemplate(label=label, snippet=snippet, is_native=True))
    await db.flush()
    logger.info("seed_body_templates_done")


async def seed_admin(db: AsyncSession) -> None:
    if not settings.admin_password:
        logger.warning(
            "seed_admin_skipped",
            reason="ADMIN_PASSWORD not set in environment — set it and re-run `make seed`",
        )
        return
    exists = await db.scalar(select(User).where(User.username == settings.admin_username))
    if exists:
        logger.info("seed_admin_skipped", reason="already exists")
        return

    from app.core.password import hash_password

    admin = User(
        username=settings.admin_username,
        email=settings.admin_email,
        password_hash=hash_password(settings.admin_password),
        is_active=True,
        is_verified=True,
    )
    db.add(admin)
    await db.flush()

    # The trigger assigns the 'User' role — revoke it and assign 'Admin'
    user_role = await db.scalar(
        select(UserRole).where(
            UserRole.user_id == admin.id,
            UserRole.revoked_at.is_(None),
        )
    )
    if user_role:
        from datetime import UTC, datetime

        user_role.revoked_at = datetime.now(UTC)

    admin_role = await db.scalar(select(Role).where(Role.name == "Admin"))
    assert admin_role is not None, "Admin role not found — run seed_roles first"
    db.add(UserRole(user_id=admin.id, role_id=admin_role.id))
    logger.info("seed_admin_created", username=settings.admin_username)


async def main() -> None:
    async with AsyncSessionLocal() as db:
        await seed_roles(db)
        await seed_settings(db)
        await seed_licenses(db)
        await seed_body_templates(db)
        await seed_admin(db)
        await db.commit()
    print("Seed completed successfully.")


if __name__ == "__main__":
    asyncio.run(main())
