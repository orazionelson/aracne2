"""``policy_pages`` — institutional declarations plugin manifest.

Non-native, default inactive. The plugin advertises the
``public_navigation`` capability (M1 §24) so that, when activated
and the ``public_link_policy_pages_enabled`` admin toggle is on,
the platform's public-layout iterators surface a single
**Policies** link in the footer pointing at ``/policies`` (per
the M3 brainstorm Q7 decision: single index link, not per-policy).
"""

from app.core.plugin_base import PluginBase, PluginMeta
from app.plugins.policy_pages.router import router

PLUGIN_ID = "policy_pages"


class Plugin(PluginBase):
    meta = PluginMeta(
        id=PLUGIN_ID,
        name="Policy pages",
        version="1.0.0",
        native=False,
        description=(
            "Institutional declarations (mission, privacy / DPIA, "
            "storage policy, continuity plan, CTS self-assessment, "
            "etc.) as live forms inside Aracne2. Twelve built-in "
            "templates with platform pre-fill, IT / EN locales, "
            "draft / publish workflow, append-only versioning, and "
            "delegation through the singleton PolicyManager role."
        ),
        author="Aracne2 Team",
        min_role="Admin",
        capabilities=("public_navigation",),
        ui_descriptor={
            "public_navigation": {
                "component": "PolicyPagesIndexView",
                "url": "/policies",
                "section": "footer",
                "label_key": "policy_pages.public_link_label",
                "label_en": "Policies",
                "label_it": "Politiche",
                "icon": "document-text",
                "priority": 200,
            }
        },
    )
    router = router
