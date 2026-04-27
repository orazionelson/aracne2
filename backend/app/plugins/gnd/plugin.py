"""GND — non-native plugin (editor-side lookup via lobid.org).

Proxies the GND (Gemeinsame Normdatei, the German national authority
file) via the lobid.org JSON API so the TEI editor can resolve a
``<persName>`` / ``<placeName>`` / ``<orgName>`` selection to a
canonical GND URI, written back as ``@ref`` on the enclosing tag.

Why GND + VIAF/Wikidata/ORCID together: GND carries fine-grained
entries for German-language scholarship (authors, institutions,
localities) that are not always reflected in VIAF or Wikidata, and
German cataloguing practice still prefers the GND URI as the
canonical ``@ref``. No overlap with the other plugins from the
editor's point of view — each service is a separate button.

Configuration: no credentials required. lobid.org is an open wrapper
maintained by the hbz (North Rhine-Westphalian library consortium).
"""

from app.core.plugin_base import PluginBase, PluginMeta
from app.plugins.gnd.router import router

PLUGIN_ID = "gnd"


class Plugin(PluginBase):
    meta = PluginMeta(
        id=PLUGIN_ID,
        name="GND",
        version="1.0.0",
        native=False,
        description=(
            "Proxies the GND (Gemeinsame Normdatei) via lobid.org so "
            "editors can resolve a <persName> / <placeName> / <orgName> "
            "selection to a canonical GND URI and write it back as "
            "@ref. No API keys required — lobid.org is a free open "
            "wrapper."
        ),
        author="Aracne2 Team",
        min_role="Admin",
        capabilities=("inline_authority",),
        ui_descriptor={
            "inline_authority": {
                "component": "GndLinkPanel",
                "label_key": "lookups.gnd",
                "icon_color": "text-yellow-500",
                "apply": "ref",
                "initial_context": "selection",
                "priority": 150,
            }
        },
    )
    router = router
