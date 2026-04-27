"""CrossRef Lookup — non-native plugin.

Proxies the public CrossRef ``/works/{doi}`` API so editors can paste
a DOI into the TEI editor's "DOI" panel and get back a ready-to-insert
``<biblStruct>``. No credentials — CrossRef identifies the operator
via a ``mailto:`` token in the ``User-Agent`` header (polite pool)
which the plugin sources from its ``crossref_contact_email`` setting
(or the platform ``admin_email`` as fallback).

Editor-side only: no lifecycle hook, no automatic action. The plugin
exists so that:
- an admin can opt-out of any outbound CrossRef traffic by simply
  leaving the plugin deactivated;
- the "DOI" toolbar button in the TEI editor is visible only when
  this plugin is active (same pattern as the Zotero import button
  inside the bibliography panel and the ORCID lookup toolbar).
"""

from app.core.plugin_base import PluginBase, PluginMeta
from app.plugins.crossref_lookup.router import router

PLUGIN_ID = "crossref_lookup"


class Plugin(PluginBase):
    meta = PluginMeta(
        id=PLUGIN_ID,
        name="CrossRef",
        version="1.0.0",
        native=False,
        description=(
            "Resolves a DOI via CrossRef and produces a TEI <biblStruct> "
            "fragment that can be inserted into the document at the "
            "cursor. Uses the public /works/{doi} endpoint — no "
            "credentials required. Configure a polite-pool contact "
            "email under Plugins → CrossRef Lookup."
        ),
        author="Aracne2 Team",
        min_role="Admin",
        capabilities=("inline_authority",),
        ui_descriptor={
            "inline_authority": {
                "component": "CrossrefPanel",
                "label_key": "lookups.crossref",
                "icon_color": "text-slate-600",
                "apply": "fragment",
                "initial_context": "doi",
                "priority": 210,
            }
        },
    )
    router = router
