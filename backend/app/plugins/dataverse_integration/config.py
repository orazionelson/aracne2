"""Runtime config for the Dataverse Integration plugin.

Reads from ``system_settings`` and returns a typed snapshot. The
plugin's settings keys are seeded by Alembic migration 0064.

Defaults are tuned for the public sandbox (``demo.dataverse.org``)
so first activation is safe — no risk of an Editor accidentally
creating draft datasets on a production instance before the admin
points the plugin at it.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.settings import get_decrypted_setting

# Setting keys.
K_TOKEN = "dataverse_api_token"
K_BASE_URL = "dataverse_base_url"
K_DEFAULT_ALIAS = "dataverse_default_alias"
K_AUTO_DEPOSIT = "dataverse_auto_deposit"
K_AUTO_PUBLISH = "dataverse_auto_publish"
K_DEFAULT_SUBJECT = "dataverse_default_subject"
K_CONTACT_NAME = "dataverse_contact_name"
K_CONTACT_EMAIL = "dataverse_contact_email"
K_PUBLISH_TYPE = "dataverse_publish_type"
K_PUBLIC_BASE_URL = "public_base_url"

_DEFAULT_BASE_URL = "https://demo.dataverse.org"
_DEFAULT_ALIAS = ""  # admin must set; deposit refuses when empty
_DEFAULT_SUBJECT = "Arts and Humanities"
_DEFAULT_PUBLISH_TYPE = "major"  # alternatives: "minor", "updatecurrent"


@dataclass(frozen=True)
class DataverseRuntimeConfig:
    """Typed view of the Dataverse settings as read at deposit time."""

    api_token: str
    base_url: str
    default_alias: str
    auto_deposit: bool
    auto_publish: bool
    default_subject: str
    contact_name: str
    contact_email: str
    publish_type: str
    public_base_url: str


async def load_runtime_config(db: AsyncSession) -> DataverseRuntimeConfig:
    token = (await get_decrypted_setting(db, K_TOKEN)) or ""
    base_url = (await get_decrypted_setting(db, K_BASE_URL)) or _DEFAULT_BASE_URL
    default_alias = (await get_decrypted_setting(db, K_DEFAULT_ALIAS)) or _DEFAULT_ALIAS
    auto_deposit_raw = await get_decrypted_setting(db, K_AUTO_DEPOSIT)
    auto_publish_raw = await get_decrypted_setting(db, K_AUTO_PUBLISH)
    default_subject = (
        await get_decrypted_setting(db, K_DEFAULT_SUBJECT)
    ) or _DEFAULT_SUBJECT
    contact_name = (await get_decrypted_setting(db, K_CONTACT_NAME)) or ""
    contact_email = (await get_decrypted_setting(db, K_CONTACT_EMAIL)) or ""
    publish_type = (
        await get_decrypted_setting(db, K_PUBLISH_TYPE)
    ) or _DEFAULT_PUBLISH_TYPE
    public_base_url = (await get_decrypted_setting(db, K_PUBLIC_BASE_URL)) or ""

    return DataverseRuntimeConfig(
        api_token=token,
        base_url=base_url.rstrip("/"),
        default_alias=default_alias,
        auto_deposit=auto_deposit_raw == "true",
        auto_publish=auto_publish_raw == "true",
        default_subject=default_subject,
        contact_name=contact_name,
        contact_email=contact_email,
        publish_type=publish_type,
        public_base_url=public_base_url.rstrip("/") if public_base_url else "",
    )
