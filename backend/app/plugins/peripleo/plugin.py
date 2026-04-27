"""Peripleo — non-native plugin (ancient places via Pelagios).

Proxies the Peripleo API (Pelagios Network's gazetteer aggregator)
so the TEI editor can resolve a ``<placeName>`` selection to a
canonical Pleiades / iDAI.gazetteer / Chronontology / … URI, written
back as ``@ref`` on the enclosing tag.

Why Peripleo and not Pleiades directly: Peripleo aggregates Pleiades
alongside half a dozen other ancient-world gazetteers (iDAI, ToposText,
ChronOntology, Vici, …) and exposes a clean JSON search API, whereas
Pleiades' own search returns RSS. The editor still gets Pleiades URIs
for most hits (Pleiades is the largest contributor) plus broader
coverage for places Pleiades does not (yet) catalogue.

Configuration: no credentials required.
"""

from app.core.plugin_base import PluginBase, PluginMeta
from app.plugins.peripleo.router import router

PLUGIN_ID = "peripleo"


class Plugin(PluginBase):
    meta = PluginMeta(
        id=PLUGIN_ID,
        name="Peripleo (ancient places)",
        version="1.0.0",
        native=False,
        description=(
            "Proxies Peripleo (Pelagios Network) so editors can "
            "resolve a <placeName> selection to an ancient-world "
            "gazetteer URI (Pleiades, iDAI, ChronOntology, etc.) "
            "and write it back as @ref. No API keys required — "
            "Peripleo is a public research infrastructure."
        ),
        author="Aracne2 Team",
        min_role="Admin",
        capabilities=("inline_authority",),
        ui_descriptor={
            "inline_authority": {
                "component": "PeripleoLinkPanel",
                "label_key": "lookups.peripleo",
                "icon_color": "text-sky-500",
                "apply": "ref",
                "initial_context": "selection",
                "priority": 170,
            }
        },
    )
    router = router
