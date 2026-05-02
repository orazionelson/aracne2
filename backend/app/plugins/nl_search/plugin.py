"""``nl_search`` — natural-language search plugin manifest.

Non-native; default inactive. The plugin advertises the
``public_navigation`` capability so that, when activated and the
``public_link_nl_search_enabled`` admin toggle is on, the platform's
public-layout iterators surface a link to ``/search-nl`` in the
header / home / footer (per the section selected below).
"""

from app.core.plugin_base import PluginBase, PluginMeta
from app.plugins.nl_search.router import router

PLUGIN_ID = "nl_search"


class Plugin(PluginBase):
    meta = PluginMeta(
        id=PLUGIN_ID,
        name="Natural-language search",
        version="1.0.0",
        native=False,
        description=(
            "Public-facing chat-style search over the corpora exposed "
            "by the MCP server. Visitors type a question; the plugin "
            "runs an LLM tool-use loop against the MCP read tools and "
            "returns a synthesised answer with citations to real TEI "
            "documents. Off by default; admin must configure provider, "
            "budget cap, and the public-link toggle in /admin/plugins "
            "and /admin/public-pages."
        ),
        author="Aracne2 Team",
        min_role="Admin",
        capabilities=("public_navigation",),
        ui_descriptor={
            "public_navigation": {
                "component": "NlSearchPublicView",
                "url": "/search-nl",
                "section": "home_quick_links",
                "label_key": "nl_search.public_link_label",
                "label_en": "Natural-language search",
                "label_it": "Cerca in linguaggio naturale",
                "icon": "sparkles",
                "priority": 100,
            }
        },
    )
    router = router
