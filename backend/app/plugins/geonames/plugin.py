"""GeoNames — non-native plugin (editor-side place lookup).

Proxies the GeoNames ``searchJSON`` API so the TEI editor can resolve
a ``<placeName>`` selection to a canonical GeoNames URI, written
back as ``@ref`` on the enclosing tag. Mirrors the ORCID / ROR /
Wikidata panels — same interaction, different authority, scoped to
places.

The plugin shares ``system_settings.geonames_username`` with the
core ``/api/v1/geonames/search`` endpoint (used by the collection
create form). There is only one GeoNames account per deployment.

Configuration: one tunable beyond activation — the URL format used
for ``@ref``. Some deployments prefer the human-readable
``https://www.geonames.org/{id}`` variant; others, following Linked
Open Data conventions, prefer the semantic-web URI
``http://sws.geonames.org/{id}/``. Default is the former.
"""

from app.core.plugin_base import PluginBase, PluginMeta
from app.plugins.geonames.router import router

PLUGIN_ID = "geonames"


class Plugin(PluginBase):
    meta = PluginMeta(
        id=PLUGIN_ID,
        name="GeoNames lookup",
        version="1.0.0",
        native=False,
        description=(
            "Proxies the GeoNames place-search API so editors can "
            "resolve a <placeName> selection to a canonical GeoNames "
            "URI and write it back as @ref. Uses the shared "
            "'geonames_username' system setting; no additional keys "
            "required."
        ),
        author="Aracne2 Team",
        min_role="Admin",
        capabilities=("inline_authority",),
        ui_descriptor={
            "inline_authority": {
                "component": "GeonamesLinkPanel",
                "label_key": "lookups.geonames",
                "icon_color": "text-orange-500",
                "apply": "ref",
                "initial_context": "selection",
                "priority": 140,
            }
        },
    )
    router = router
