"""ORCID — non-native plugin (editor-side lookup only).

Proxies the ORCID public registry so the TEI editor can resolve a
``<persName>`` selection to a canonical ORCID URI, written back as
``@ref`` on the enclosing tag. Mirrors the Wikidata panel shape —
same interaction, different authority.

Deliberately editor-only: attaching an ORCID to an **Aracne2 user**
lives on the ``User`` model and is a core feature, not a plugin
concern, because the value has to flow to downstream consumers
(Zenodo creator.identifiers, LOD ``sameAs``) that would otherwise
need cross-plugin data snooping.

Configuration: no credentials required. The plugin page is a static
info notice — activation is all an admin has to do.
"""

from app.core.plugin_base import PluginBase, PluginMeta
from app.plugins.orcid.router import router

PLUGIN_ID = "orcid"


class Plugin(PluginBase):
    meta = PluginMeta(
        id=PLUGIN_ID,
        name="ORCID lookup",
        version="1.0.0",
        native=False,
        description=(
            "Proxies the public ORCID search API so editors can resolve "
            "a TEI <persName> selection to a canonical ORCID URI and "
            "write it back as @ref. No API keys required — ORCID's "
            "public registry is unauthenticated."
        ),
        author="Aracne2 Team",
        min_role="Admin",
        capabilities=("inline_authority",),
        ui_descriptor={
            "inline_authority": {
                "component": "OrcidLinkPanel",
                "label_key": "lookups.orcid",
                "icon_color": "text-emerald-500",
                "apply": "ref",
                "initial_context": "selection",
                "priority": 110,
            }
        },
    )
    router = router
