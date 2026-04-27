"""ROR — non-native plugin (editor-side institution lookup).

Proxies the Research Organization Registry so the TEI editor can resolve
an ``<orgName>`` selection to a canonical ROR URI, written back as
``@ref`` on the enclosing tag. Mirrors the ORCID and Wikidata panels —
same interaction, different authority, scoped to institutions only.

Deliberately editor-only (like ORCID): attaching a ROR to a user lives
on the user model when that is needed; this plugin is purely a
TEI-encoding aid.

Configuration: no credentials required — ROR's public API is
unauthenticated. The plugin page is a static info notice.
"""

from app.core.plugin_base import PluginBase, PluginMeta
from app.plugins.ror.router import router

PLUGIN_ID = "ror"


class Plugin(PluginBase):
    meta = PluginMeta(
        id=PLUGIN_ID,
        name="ROR",
        version="1.0.0",
        native=False,
        description=(
            "Proxies the public ROR (Research Organization Registry) "
            "search API so editors can resolve a TEI <orgName> "
            "selection to a canonical ROR URI and write it back as "
            "@ref. No API keys required — ROR's public registry is "
            "unauthenticated."
        ),
        author="Aracne2 Team",
        min_role="Admin",
        capabilities=("inline_authority",),
        ui_descriptor={
            "inline_authority": {
                "component": "RorLinkPanel",
                "label_key": "lookups.ror",
                "icon_color": "text-cyan-500",
                "apply": "ref",
                "initial_context": "selection",
                "priority": 120,
            }
        },
    )
    router = router
