"""Wikidata — non-native plugin (editor-side entity lookup).

Proxies ``wbsearchentities`` so the TEI editor can resolve a
``<persName>`` / ``<placeName>`` / ``<orgName>`` selection to a
canonical Wikidata entity URI, written back as ``@ref`` on the
enclosing tag. Same shape as the ORCID / ROR / VIAF / GeoNames /
CrossRef plugins — opt-in activation, editor-side only, no
credentials.

Ships as a non-native plugin for consistency with every other
authority lookup. Before this refactor Wikidata was a core router
(``/api/v1/wikidata/search``); the endpoint had a single consumer
(``WikidataLinkPanel``) and no other module referenced it, so the
move is clean rather than an expansion.

Configuration: no credentials required. The plugin page is a static
info notice — activation is all an admin has to do.
"""

from app.core.plugin_base import PluginBase, PluginMeta
from app.plugins.wikidata.router import router

PLUGIN_ID = "wikidata"


class Plugin(PluginBase):
    meta = PluginMeta(
        id=PLUGIN_ID,
        name="Wikidata lookup",
        version="1.0.0",
        native=False,
        description=(
            "Proxies the public Wikidata wbsearchentities API so editors "
            "can resolve a TEI <persName> / <placeName> / <orgName> "
            "selection to a canonical Wikidata entity URI and write it "
            "back as @ref. No API keys required — Wikidata's public "
            "search is unauthenticated."
        ),
        author="Aracne2 Team",
        min_role="Admin",
    )
    router = router
