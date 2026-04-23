"""VIAF — non-native plugin (editor-side authority lookup).

Proxies the Virtual International Authority File so the TEI editor
can resolve a ``<persName>`` or ``<orgName>`` selection to a canonical
VIAF URI, written back as ``@ref`` on the enclosing tag. Mirrors the
ORCID / ROR / Wikidata panels — same interaction, different authority.

Scope: ``<persName>`` and ``<orgName>``. VIAF is the Virtual
International Authority File — it covers persons and corporate
bodies. Editors working on an institution may prefer ROR (which is
scoped to organisations only) and should be free to pick.

Configuration: no credentials required. The plugin page is a static
info notice — activation is all an admin has to do. A core
``/api/v1/viaf/autosuggest`` endpoint already exists for the
collection-create form; this plugin exposes a richer endpoint at
``/plugins/viaf/search`` that returns VIAF IDs + name-type alongside
the display label, which the editor needs to build ``@ref``.
"""

from app.core.plugin_base import PluginBase, PluginMeta
from app.plugins.viaf.router import router

PLUGIN_ID = "viaf"


class Plugin(PluginBase):
    meta = PluginMeta(
        id=PLUGIN_ID,
        name="VIAF lookup",
        version="1.0.0",
        native=False,
        description=(
            "Proxies the VIAF AutoSuggest API so editors can resolve a "
            "<persName> or <orgName> selection to a canonical VIAF URI "
            "and write it back as @ref. No API keys required — VIAF's "
            "public service is unauthenticated."
        ),
        author="Aracne2 Team",
        min_role="Admin",
    )
    router = router
