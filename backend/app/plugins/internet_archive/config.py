"""Runtime config loader for the Internet Archive plugin."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.settings import get_decrypted_setting

K_ACCESS_KEY = "internet_archive_access_key"
K_SECRET_KEY = "internet_archive_secret_key"
K_AUTO_ARCHIVE = "internet_archive_auto_archive"
K_PUBLIC_BASE_URL = "public_base_url"


@dataclass(frozen=True)
class IARuntimeConfig:
    """Typed view of the IA settings as read at archive time."""

    access_key: str
    secret_key: str
    auto_archive: bool
    public_base_url: str

    @property
    def credentials_set(self) -> bool:
        return bool(self.access_key and self.secret_key)


async def load_runtime_config(db: AsyncSession) -> IARuntimeConfig:
    access = await get_decrypted_setting(db, K_ACCESS_KEY)
    secret = await get_decrypted_setting(db, K_SECRET_KEY)
    auto_raw = await get_decrypted_setting(db, K_AUTO_ARCHIVE)
    public_base_url = await get_decrypted_setting(db, K_PUBLIC_BASE_URL)

    return IARuntimeConfig(
        access_key=access,
        secret_key=secret,
        auto_archive=auto_raw == "true",
        public_base_url=public_base_url,
    )
