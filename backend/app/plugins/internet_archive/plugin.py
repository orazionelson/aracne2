"""Internet Archive — non-native plugin.

Submits a published collection's public URL to Save Page Now 2 (SPN2)
on ``ON_COLLECTION_PUBLISHED``, polls for up to 60 seconds, and records
the resulting Wayback Machine URL in ``plugin_data`` so the UI can
surface a "Archived on the Wayback Machine" badge next to the
collection.

Configuration: Admin → /admin/plugins/internet_archive/config.
Credentials (S3-style access/secret key) are Fernet-encrypted in
``system_settings`` via ``SENSITIVE_KEYS``.
"""

from app.core.hooks import HookEvent, hook_registry
from app.core.plugin_base import PluginBase, PluginMeta
from app.plugins.internet_archive.archive import (
    PLUGIN_ID,
    on_collection_published,
)
from app.plugins.internet_archive.router import router

hook_registry.register(HookEvent.ON_COLLECTION_PUBLISHED, on_collection_published)


class Plugin(PluginBase):
    meta = PluginMeta(
        id=PLUGIN_ID,
        name="Internet Archive",
        version="1.1.0",
        native=False,
        description=(
            "Submits published collections AND websites to the Internet "
            "Archive's Wayback Machine via Save Page Now 2. Records the "
            "Wayback URL on the entity and shows an archive badge. Auto "
            "on collection publish; manual for websites. Configure the "
            "API keys under Plugins → Internet Archive."
        ),
        author="Aracne2 Team",
        min_role="Admin",
    )
    router = router
