"""Help — non-native plugin (in-app documentation browser).

Serves the Markdown files under ``backend/help_docs/`` as sanitised HTML
so editors can consult day-to-day documentation without leaving the UI.

Activation adds a "Help" link to the sidebar and a badge on the
dashboard (both driven client-side by ``usePluginStore.isActive``).

Design notes:

- The ``help_docs`` directory is a sibling of ``app/``. That placement
  keeps everything under the Docker build context so production images
  and development bind-mounts pick it up identically — the docs folder
  at repo root is technical reference material that does **not** belong
  here.
- Rendering is lazy with an mtime-fingerprinted in-process cache: any
  change to a ``.md`` file is reflected on the next request without a
  restart.
- Assets (images) are served from a dedicated endpoint with a strict
  extension whitelist and a resolved-path check to block traversal.

Configuration: no credentials required. The plugin page is purely
informational.
"""

from app.core.plugin_base import PluginBase, PluginMeta
from app.plugins.help.router import router

PLUGIN_ID = "help"


class Plugin(PluginBase):
    meta = PluginMeta(
        id=PLUGIN_ID,
        name="Help",
        version="1.0.0",
        native=False,
        description=(
            "In-app help browser. Renders the Markdown files under "
            "backend/help_docs/ as sanitised HTML and exposes a search "
            "endpoint so editors can look up the user manual without "
            "leaving the platform."
        ),
        author="Aracne2 Team",
        min_role="User",
    )
    router = router
