"""EVT viewer integration — non-native plugin.

Connects Aracne2 to the [EVT 2](https://visualizationtechnology.wordpress.com/)
viewer: a TEI reading/visualisation UI served from a separate nginx
container (the ``evt`` docker-compose profile). This plugin exposes
two public endpoints the EVT container proxies:

- ``GET /public/collections/{slug}/evt-config`` → EVT 2 ``config.json``
- ``GET /public/collections/{slug}/documents/{filename}/raw`` → raw XML

The plugin is opt-in. Activating it in ``/admin/plugins`` mounts the
endpoints and surfaces the "Read in EVT" button on public pages. When
inactive, the endpoints are not mounted (404) and the reader route
shows a friendly "viewer not enabled on this installation" fallback.

Per-collection opt-in (the ``collections.evt_enabled`` column)
remains, so an admin can expose EVT only for specific editions even
when the plugin itself is active.
"""

from app.core.plugin_base import PluginBase, PluginMeta
from app.plugins.evt.router import router


class Plugin(PluginBase):
    meta = PluginMeta(
        id="evt",
        name="EVT Viewer",
        version="2.0.0",
        native=False,
        description=(
            "Feeds the EVT 2 viewer with collection config and raw XML "
            "via two public API endpoints. Enable the 'evt' Docker "
            "Compose profile for the viewer UI itself. Per-collection "
            "opt-in is controlled by the 'evt_enabled' flag on each "
            "collection. Global visibility is controlled by the "
            "'evt_enabled' system setting."
        ),
        author="Aracne2 Team",
        min_role="User",
    )
    router = router
