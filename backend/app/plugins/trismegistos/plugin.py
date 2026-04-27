"""Trismegistos — non-native plugin (ancient papyri / ostraca /
inscriptions authority lookup, ID-resolver model).

Trismegistos (TM) is the central registry for pre-800 AD documentary
texts from Egypt and the ancient Mediterranean: papyri, ostraca,
tablets, inscriptions, mummy labels, graffiti. It indexes texts
themselves as well as the persons, places, and archives attested in
them.

TM does not publish a free-text search API. Every public TM data
service is an **ID resolver**: you hand it a numeric TM ID (or, for
texts, a partner-project ID plus a ``source`` selector) and it
returns cross-references to other databases. The plugin therefore
ships a panel with three inputs — kind, id, optional source — and a
Resolve button. No API key is needed; no secret setting is stored.

Supported kinds:
- ``person``: URL composition only (TM has no person JSON endpoint;
  only RDF/XML).
- ``place``: ``dataservices/georelations/<id>`` JSON.
- ``text``: ``dataservices/texrelations/<id>[?source=<src>]`` JSON,
  with reverse lookup via ``source=ddbdp|hgv|phi|...``.
"""

from app.core.plugin_base import PluginBase, PluginMeta
from app.plugins.trismegistos.router import router

PLUGIN_ID = "trismegistos"


class Plugin(PluginBase):
    meta = PluginMeta(
        id=PLUGIN_ID,
        name="Trismegistos lookup",
        version="2.0.0",
        native=False,
        description=(
            "Resolves a Trismegistos ID (person / place / text) to the "
            "canonical TM URL and shows partner-database cross-references. "
            "Supports reverse lookup from partner IDs (DDBDP, HGV, PHI, "
            "EDH, EDCS, ...) via the ``source`` selector. No API key "
            "required — the plugin consumes only Trismegistos's public "
            "ID-resolver endpoints. Useful for papyrology, Greek/Latin "
            "epigraphy, and Coptic / Demotic / hieroglyphic sources."
        ),
        author="Aracne2 Team",
        min_role="Admin",
        capabilities=("inline_authority",),
        ui_descriptor={
            "inline_authority": {
                "component": "TrismegistosLinkPanel",
                "label_key": "lookups.trismegistos",
                "icon_color": "text-indigo-500",
                "apply": "ref",
                "initial_context": "kind-picker",
                "priority": 200,
            }
        },
    )
    router = router
