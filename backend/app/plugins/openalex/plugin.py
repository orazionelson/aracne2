"""OpenAlex — non-native plugin (bibliographic search, inserts biblStruct).

Complements the CrossRef plugin: where CrossRef resolves *a known DOI*
to a biblStruct, OpenAlex lets the editor **search** by title / author
across the ~250M-record open bibliographic index. Covers works that
CrossRef does not register (preprints, theses, report-like papers,
early-modern reprints without DOI) and exposes the same TEI
``<biblStruct>`` output shape as CrossRef.

Configuration: one optional tunable — a contact email used for the
OpenAlex "polite pool" (sent as ``?mailto=…``), same spirit as the
CrossRef contact email. Empty falls back to ``admin_email``.
"""

from app.core.plugin_base import PluginBase, PluginMeta
from app.plugins.openalex.router import router

PLUGIN_ID = "openalex"


class Plugin(PluginBase):
    meta = PluginMeta(
        id=PLUGIN_ID,
        name="OpenAlex",
        version="1.0.0",
        native=False,
        description=(
            "Searches the OpenAlex open bibliographic index and "
            "returns TEI <biblStruct> fragments ready to paste at the "
            "cursor. Complements the CrossRef plugin for works "
            "without DOIs (preprints, theses, grey literature). "
            "No API keys required; an optional contact email enters "
            "OpenAlex's polite pool for better rate limits."
        ),
        author="Aracne2 Team",
        min_role="Admin",
        capabilities=("inline_authority",),
        ui_descriptor={
            "inline_authority": {
                "component": "OpenAlexPanel",
                "label_key": "lookups.openalex",
                "icon_color": "text-blue-500",
                "apply": "fragment",
                "initial_context": "selection",
                "priority": 190,
            }
        },
    )
    router = router
