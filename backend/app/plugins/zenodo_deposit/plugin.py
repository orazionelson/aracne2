"""Zenodo Deposit — non-native plugin.

Deposits a collection's TEI files + derived metadata on Zenodo when the
collection is published, and stores the resulting DOI (or draft URL) on
the collection via PluginDataService so the UI can surface it.

Configuration: Admin → /admin/plugins → "Zenodo Deposit".
Credentials and endpoint live in system_settings (zenodo_api_token is
Fernet-encrypted via SENSITIVE_KEYS).
"""

from app.core.hooks import HookEvent, hook_registry
from app.core.plugin_base import PluginBase, PluginMeta
from app.plugins.zenodo_deposit.deposit import (
    PLUGIN_ID,
    on_collection_published,
)
from app.plugins.zenodo_deposit.router import router

# Register the publish hook once at import time.  The loader imports this
# module during discover(), so the handler is attached whether or not the
# plugin is "active" in the DB — but the handler reads runtime config and
# exits early (DepositSkipped) when the API token is empty, which is the
# default state of an inactive install.
hook_registry.register(HookEvent.ON_COLLECTION_PUBLISHED, on_collection_published)


class Plugin(PluginBase):
    meta = PluginMeta(
        id=PLUGIN_ID,
        name="Zenodo Deposit",
        version="1.1.0",
        native=False,
        description=(
            "Deposits published collections on Zenodo and records the "
            "returned DOI on the collection. Also deposits a website's "
            "rendered static output (file-by-file or as a single ZIP). "
            "Supports sandbox and production endpoints, draft-for-review "
            "and auto-publish modes. Configure the API token under "
            "Plugins → Zenodo Deposit."
        ),
        author="Aracne2 Team",
        min_role="Admin",
        capabilities=("collection_deposit", "website_deposit"),
        ui_descriptor={
            "collection_deposit": {
                "component": "ZenodoCollectionDepositPanel",
                "label": "Zenodo",
                "priority": 100,
            },
            "website_deposit": {
                "component": "ZenodoWebsiteSection",
                "label": "Zenodo",
                "priority": 100,
            },
        },
    )
    router = router
