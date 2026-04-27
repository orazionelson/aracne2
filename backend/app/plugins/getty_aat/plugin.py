"""Getty AAT — non-native plugin (controlled vocabulary for
materials / techniques / objects).

The Getty Art & Architecture Thesaurus catalogues ~400k concepts in
the art, architecture and cultural-heritage domain: materials
(``lapis lazuli``), techniques (``oil painting``), object types
(``manuscript codices``), styles and periods. Editors working on
catalogues of objects or art-historical editions get a controlled
term with a stable URI instead of free-text.

Query target: written back as ``@ref`` on a TEI ``<term>`` element
(``<term type="aat" ref="...">lapis lazuli</term>``). The plugin
panel refuses to apply on any other enclosing tag — this is a term /
concept authority, not a name authority.

The upstream is a SPARQL endpoint (``vocab.getty.edu/sparql``), so
the service does a Lucene-style search via the ``luc:term`` extension
and parses the JSON result set. No authentication, no quotas.
"""

from app.core.plugin_base import PluginBase, PluginMeta
from app.plugins.getty_aat.router import router

PLUGIN_ID = "getty_aat"


class Plugin(PluginBase):
    meta = PluginMeta(
        id=PLUGIN_ID,
        name="Getty AAT",
        version="1.0.0",
        native=False,
        description=(
            "Looks up concepts in the Getty Art & Architecture "
            "Thesaurus via the public SPARQL endpoint. Writes @ref on "
            "a TEI <term> element for materials, techniques, object "
            "types, styles and periods. No API keys required."
        ),
        author="Aracne2 Team",
        min_role="Admin",
        capabilities=("inline_authority",),
        ui_descriptor={
            "inline_authority": {
                "component": "GettyAatLinkPanel",
                "label_key": "lookups.getty_aat",
                "icon_color": "text-fuchsia-500",
                "apply": "ref",
                "initial_context": "selection",
                "priority": 180,
            }
        },
    )
    router = router
