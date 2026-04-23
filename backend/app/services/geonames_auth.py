"""Shared GeoNames username resolution.

The GeoNames account name used by every outbound request lives in the
``system_settings`` table under key ``geonames_username`` (migration
0057). Both the core ``/api/v1/geonames/search`` endpoint and the
non-native ``geonames`` plugin must read the same value so operators
have a single place to configure it.

The default seed is ``"aracne"`` — shared across any installation
that never changed it. The seeded default is documented as a nudge,
not a recommendation: GeoNames' ToS require each application to
register its own username, and the free tier is quota-limited per
account, so sharing leads to noisy "hourly limit exceeded" errors
that Aracne2 cannot usefully recover from.

``SHARED_DEFAULT_USERNAME`` is the canonical value that triggers the
startup warning emitted from ``main.py``.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.system_setting import SystemSetting

SHARED_DEFAULT_USERNAME = "aracne"
K_GEONAMES_USERNAME = "geonames_username"


async def get_geonames_username(db: AsyncSession) -> str:
    """Return the configured GeoNames username, or the shared default.

    Never raises — a missing or empty row degrades to the shared
    default so the first-boot experience (before migration 0057 runs)
    keeps working. The caller should still be prepared for GeoNames
    to reject the request when quota is exhausted.
    """
    row = await db.get(SystemSetting, K_GEONAMES_USERNAME)
    if row is None:
        return SHARED_DEFAULT_USERNAME
    value = (row.value or "").strip()
    return value or SHARED_DEFAULT_USERNAME
