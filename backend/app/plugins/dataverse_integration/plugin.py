"""Dataverse Integration — non-native plugin.

Deposits a published Aracne2 collection or website on a Dataverse
instance (the public sandbox at https://demo.dataverse.org by
default; any institutional Dataverse via the ``base_url`` setting).

Architecturally a sibling of the Zenodo plugin: same hook-on-publish
auto-deposit shape for collections, manual website deposit, draft /
publish lifecycle, ``DepositMetadata`` intermediate reused from the
Zenodo plugin's mapping module.

Per-deposit alias override lets a single Aracne2 install route
different collections / websites to different sub-Dataverses inside
the same instance — useful when one institution has multiple
research-group Dataverses.

Configuration: Admin → /admin/plugins/dataverse_integration/config.
The API token is Fernet-encrypted in ``system_settings`` via
``SENSITIVE_KEYS``.
"""

from app.core.hooks import HookEvent, hook_registry
from app.core.plugin_base import PluginBase, PluginMeta
from app.plugins.dataverse_integration.deposit import (
    PLUGIN_ID,
    on_collection_published,
)
from app.plugins.dataverse_integration.router import router

# Subscribe to the publish hook at import time. The handler exits early
# (``DepositSkipped``) when the API token is empty or auto_deposit is
# off, which is the default state of an inactive install.
hook_registry.register(HookEvent.ON_COLLECTION_PUBLISHED, on_collection_published)


class Plugin(PluginBase):
    meta = PluginMeta(
        id=PLUGIN_ID,
        name="Dataverse Integration",
        version="1.0.0",
        native=False,
        description=(
            "Deposits published collections and websites on a Dataverse "
            "instance — the public sandbox at demo.dataverse.org or any "
            "institutional Dataverse via the configurable base URL. "
            "Auto-deposit on collection publish (toggleable); websites "
            "are manual. Per-deposit Dataverse alias override. "
            "Configure under Plugins → Dataverse Integration."
        ),
        author="Aracne2 Team",
        min_role="Admin",
        capabilities=("collection_deposit",),
        ui_descriptor={
            "collection_deposit": {
                "component": "DataverseCollectionDepositPanel",
                "label": "Dataverse",
                "priority": 230,
            }
        },
    )
    router = router
