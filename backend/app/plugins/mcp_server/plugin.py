"""MCP server — non-native plugin.

Exposes Aracne2 as a Model Context Protocol server so Claude Desktop,
Cursor, and Claude Code can read collections, documents, and entities
through standardised tools and resources. Read-only by design: every
tool intersects its query with the bearer token's corpus scope and
the public-published filter, so a token never sees data that wouldn't
already be reachable on the public site.

Configuration: Admin → /admin/corpora. The MCP plugin itself ships
no config of its own — corpora and tokens are platform primitives,
exposed via the dedicated /api/v1/corpora router.

Activate the plugin from /admin/plugins to mount the endpoint on
``/api/v1/mcp``. Hand the matching token + URL to the editor; they
paste them into Claude Desktop's mcpServers config and start chatting.
"""

from app.core.plugin_base import PluginBase, PluginMeta
from app.plugins.mcp_server.router import router

PLUGIN_ID = "mcp_server"


class Plugin(PluginBase):
    meta = PluginMeta(
        id=PLUGIN_ID,
        name="MCP Server",
        version="1.0.0",
        native=False,
        description=(
            "Expose Aracne2 as a Model Context Protocol server so "
            "editors can read collections, documents, and entities "
            "directly from Claude Desktop, Cursor, and Claude Code. "
            "Read-only; access is scoped to a corpus + bearer token "
            "issued from /admin/corpora."
        ),
        author="Aracne2 Team",
        min_role="Admin",
    )
    router = router
