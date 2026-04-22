"""Runtime config loader for the Zenodo deposit plugin.

Reads values from ``system_settings`` and returns a typed snapshot.  All
values come from the core settings service — the plugin does not hold
its own secrets store.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.settings import get_decrypted_setting

# Setting keys used by this plugin (seeded in db/seed.py and migration 0047).
K_TOKEN = "zenodo_api_token"
K_BASE_URL = "zenodo_base_url"
K_COMMUNITY = "zenodo_default_community"
K_AUTO_PUBLISH = "zenodo_auto_publish"
K_ACCESS_RIGHT = "zenodo_access_right"
K_PUBLICATION_TYPE = "zenodo_publication_type"
K_PUBLIC_BASE_URL = "public_base_url"

_DEFAULT_BASE_URL = "https://sandbox.zenodo.org"
_DEFAULT_ACCESS_RIGHT = "open"
_DEFAULT_PUBLICATION_TYPE = "other"


@dataclass(frozen=True)
class ZenodoRuntimeConfig:
    """Typed view of the Zenodo settings as read at deposit time."""

    api_token: str
    base_url: str
    default_community: str
    auto_publish: bool
    access_right: str
    publication_type: str
    public_base_url: str


async def load_runtime_config(db: AsyncSession) -> ZenodoRuntimeConfig:
    token = await get_decrypted_setting(db, K_TOKEN)
    base_url = (await get_decrypted_setting(db, K_BASE_URL)) or _DEFAULT_BASE_URL
    community = await get_decrypted_setting(db, K_COMMUNITY)
    auto_publish_raw = await get_decrypted_setting(db, K_AUTO_PUBLISH)
    access_right = (
        await get_decrypted_setting(db, K_ACCESS_RIGHT)
    ) or _DEFAULT_ACCESS_RIGHT
    publication_type = (
        await get_decrypted_setting(db, K_PUBLICATION_TYPE)
    ) or _DEFAULT_PUBLICATION_TYPE
    public_base_url = await get_decrypted_setting(db, K_PUBLIC_BASE_URL)

    return ZenodoRuntimeConfig(
        api_token=token,
        base_url=base_url,
        default_community=community,
        auto_publish=auto_publish_raw == "true",
        access_right=access_right,
        publication_type=publication_type,
        public_base_url=public_base_url,
    )
