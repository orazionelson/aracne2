"""Runtime config loader for the Zenodo (InvenioRDM) deposit plugin.

Reads values from ``system_settings`` and returns a typed snapshot.  All
values come from the core settings service — the plugin does not hold
its own secrets store.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.settings import get_decrypted_setting

# Setting keys used by this plugin (seeded in db/seed.py and migration 0048).
K_TOKEN = "zenodo_api_token"
K_BASE_URL = "zenodo_base_url"
K_COMMUNITY = "zenodo_default_community"
K_AUTO_PUBLISH = "zenodo_auto_publish"
K_ACCESS = "zenodo_access"
K_RESOURCE_TYPE = "zenodo_resource_type"
K_PUBLIC_BASE_URL = "public_base_url"

_DEFAULT_BASE_URL = "https://sandbox.zenodo.org"
_DEFAULT_ACCESS = "open"
_DEFAULT_RESOURCE_TYPE = "publication-other"


@dataclass(frozen=True)
class ZenodoRuntimeConfig:
    """Typed view of the Zenodo settings as read at deposit time."""

    api_token: str
    base_url: str
    default_community: str
    auto_publish: bool
    access: str
    resource_type: str
    public_base_url: str


async def load_runtime_config(db: AsyncSession) -> ZenodoRuntimeConfig:
    token = await get_decrypted_setting(db, K_TOKEN)
    base_url = (await get_decrypted_setting(db, K_BASE_URL)) or _DEFAULT_BASE_URL
    community = await get_decrypted_setting(db, K_COMMUNITY)
    auto_publish_raw = await get_decrypted_setting(db, K_AUTO_PUBLISH)
    access = (await get_decrypted_setting(db, K_ACCESS)) or _DEFAULT_ACCESS
    resource_type = (
        await get_decrypted_setting(db, K_RESOURCE_TYPE)
    ) or _DEFAULT_RESOURCE_TYPE
    public_base_url = await get_decrypted_setting(db, K_PUBLIC_BASE_URL)

    return ZenodoRuntimeConfig(
        api_token=token,
        base_url=base_url,
        default_community=community,
        auto_publish=auto_publish_raw == "true",
        access=access,
        resource_type=resource_type,
        public_base_url=public_base_url,
    )
