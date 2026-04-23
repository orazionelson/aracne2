"""Runtime config loader for the Zotero import plugin."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.settings import get_decrypted_setting

K_API_KEY = "zotero_api_key"
K_LIBRARY_TYPE = "zotero_library_type"
K_LIBRARY_ID = "zotero_library_id"
K_API_BASE = "zotero_api_base"

_DEFAULT_API_BASE = "https://api.zotero.org"
_VALID_LIBRARY_TYPES = ("user", "group")


@dataclass(frozen=True)
class ZoteroRuntimeConfig:
    """Typed snapshot of the Zotero settings."""

    api_key: str
    library_type: str  # "user" | "group"
    library_id: str
    api_base: str

    @property
    def usable(self) -> bool:
        """True when the plugin has enough config to talk to Zotero."""
        return bool(self.api_key and self.library_type and self.library_id)

    def library_url(self) -> str:
        """Return the library root URL (``/users/{id}`` or ``/groups/{id}``)."""
        return f"{self.api_base.rstrip('/')}/{self.library_type}s/{self.library_id}"


async def load_runtime_config(db: AsyncSession) -> ZoteroRuntimeConfig:
    api_key = await get_decrypted_setting(db, K_API_KEY)
    lib_type_raw = (await get_decrypted_setting(db, K_LIBRARY_TYPE)) or "group"
    library_id = (await get_decrypted_setting(db, K_LIBRARY_ID)) or ""
    api_base = (await get_decrypted_setting(db, K_API_BASE)) or _DEFAULT_API_BASE

    # Defensive normalisation: an admin typo in the settings table
    # should never produce a silently broken URL at runtime.
    lib_type = lib_type_raw if lib_type_raw in _VALID_LIBRARY_TYPES else "group"

    return ZoteroRuntimeConfig(
        api_key=api_key,
        library_type=lib_type,
        library_id=library_id,
        api_base=api_base,
    )
