"""Zotero import — non-native plugin.

Imports bibliographic entries from a Zotero group or user library into
a collection's bibliography. Unlike the Zenodo / Internet Archive
plugins, this one does **not** register a lifecycle hook: Zotero
imports are pulled manually by an EiC, not triggered automatically
when a collection changes state.

Configuration: Admin → /admin/plugins/zotero_import/config.
API key is Fernet-encrypted in ``system_settings``.
"""

from app.core.plugin_base import PluginBase, PluginMeta
from app.plugins.zotero_import.importer import PLUGIN_ID
from app.plugins.zotero_import.router import router


class Plugin(PluginBase):
    meta = PluginMeta(
        id=PLUGIN_ID,
        name="Zotero Import",
        version="1.0.0",
        native=False,
        description=(
            "Imports bibliographic entries from a configured Zotero "
            "group or user library into a collection's bibliography. "
            "Entries are mapped to TEI <biblStruct>; imports are "
            "de-duplicated by Zotero item key so re-running the "
            "import never duplicates. Configure the read-only API "
            "key under Plugins → Zotero Import."
        ),
        author="Aracne2 Team",
        min_role="Admin",
    )
    router = router
