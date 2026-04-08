"""EVT viewer integration — native plugin.

Exposes two public endpoints used by the EVT nginx container:
  - GET /public/collections/{slug}/evt-config   → EVT 2 config.json
  - GET /public/collections/{slug}/documents/{filename}/raw → raw XML

The viewer UI itself (EVT static files + nginx routing) is activated via
the 'evt' Docker Compose profile. See evt/README.md for setup instructions.
"""

from app.core.plugin_base import PluginBase, PluginMeta
from app.plugins._native.evt.router import router


class Plugin(PluginBase):
    meta = PluginMeta(
        id="evt",
        name="EVT Viewer",
        version="1.0.0",
        native=True,
        description=(
            "Feeds the EVT 2 viewer with collection config and raw XML via "
            "public API endpoints. Enable the 'evt' Docker Compose profile "
            "for the viewer UI. Toggle visibility with the evt_enabled setting."
        ),
        author="Aracne2 Team",
        min_role="User",
    )
    router = router
