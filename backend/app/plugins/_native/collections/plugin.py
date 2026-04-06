"""
Collections — native plugin.

Manages XML document collections: creation, workflow transitions
(draft → assigned → review → published), document upload/download,
and role-based access control.

This is a native plugin: it cannot be deactivated.
"""

from app.core.plugin_base import PluginBase, PluginMeta
from app.plugins._native.collections.router import router


class Plugin(PluginBase):
    meta = PluginMeta(
        id="collections",
        name="Collections",
        version="1.0.0",
        native=True,
        description=(
            "Manages XML document collections with a full editorial workflow: "
            "draft → assigned → review → published. Cannot be deactivated."
        ),
        author="Aracne2 Team",
        min_role="Editor",
    )
    router = router
