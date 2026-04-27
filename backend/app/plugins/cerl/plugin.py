"""CERL Thesaurus — non-native plugin (editor-side lookup).

Proxies the Consortium of European Research Libraries Thesaurus so
the TEI editor can resolve a ``<persName>`` / ``<placeName>`` /
``<orgName>`` selection to a canonical CERL URI, written back as
``@ref`` on the enclosing tag.

Fills a gap no other authority covers: **early printed books
(pre-1830)**. CERL records historical imprints, printers,
booksellers, book owners, and the places where they operated —
including variant Latin / vernacular name forms, relationships with
other persons and places, and date ranges. Indispensable for
editions of early-modern texts.

Configuration: no credentials required. CERL exposes its Thesaurus
as a public JSON endpoint.
"""

from app.core.plugin_base import PluginBase, PluginMeta
from app.plugins.cerl.router import router

PLUGIN_ID = "cerl"


class Plugin(PluginBase):
    meta = PluginMeta(
        id=PLUGIN_ID,
        name="CERL Thesaurus",
        version="1.0.0",
        native=False,
        description=(
            "Proxies the CERL Thesaurus (Consortium of European "
            "Research Libraries) so editors can resolve a <persName> "
            "/ <placeName> / <orgName> selection to a canonical CERL "
            "URI and write it back as @ref. Especially useful for "
            "early printed books (pre-1830). No API keys required."
        ),
        author="Aracne2 Team",
        min_role="Admin",
        capabilities=("inline_authority",),
        ui_descriptor={
            "inline_authority": {
                "component": "CerlLinkPanel",
                "label_key": "lookups.cerl",
                "icon_color": "text-violet-500",
                "apply": "ref",
                "initial_context": "selection",
                "priority": 160,
            }
        },
    )
    router = router
