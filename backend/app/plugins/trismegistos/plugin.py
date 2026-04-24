"""Trismegistos — non-native plugin (ancient papyri / ostraca /
inscriptions authority lookup).

Trismegistos (TM) is the central registry for pre-800 AD documentary
texts from Egypt and the ancient Mediterranean: papyri, ostraca,
tablets, inscriptions, mummy labels, graffiti. It indexes texts
themselves as well as the persons, places, and archives attested in
them. Editors working on papyrology, Greek/Latin epigraphy, or
Coptic / Demotic / hieroglyphic sources can resolve a
``<persName>`` / ``<placeName>`` selection to a TM URI (or link a
text to its ``<bibl>`` via the TM text id).

**Requires registration**: TM moved to a freemium model. Basic
search works with a free API key obtained at
https://www.trismegistos.org/api — set it in the plugin config
panel. Without a key the plugin returns an empty list and surfaces
a clear "Set API key" banner in the editor panel.

The exact upstream response shape has changed across TM versions.
The service parses defensively and degrades to empty results on any
mismatch; the plugin is marked beta and the maintainer should verify
against the current TM API docs after first activation.
"""

from app.core.plugin_base import PluginBase, PluginMeta
from app.plugins.trismegistos.router import router

PLUGIN_ID = "trismegistos"


class Plugin(PluginBase):
    meta = PluginMeta(
        id=PLUGIN_ID,
        name="Trismegistos lookup",
        version="1.0.0",
        native=False,
        description=(
            "Looks up persons, places and texts in Trismegistos — the "
            "central registry of pre-800 AD documentary texts from "
            "Egypt and the ancient Mediterranean. Requires a free "
            "API key from https://www.trismegistos.org/api (the admin "
            "sets it in the plugin config). Useful for papyrology, "
            "Greek/Latin epigraphy, and Coptic / Demotic / "
            "hieroglyphic sources."
        ),
        author="Aracne2 Team",
        min_role="Admin",
    )
    router = router
