"""GitHub Integration — non-native plugin.

Deposits an Aracne2 collection or website to a GitHub repository in
a single commit per push. Uses the shared
``app.plugins._lib.git_forge`` abstraction so it ships alongside the
Codeberg plugin (and the forthcoming GitLab plugin) without
duplicating the push orchestration.

Source-of-truth contract (inherited from the FUTURE_IDEAS entry):

- eXist-db is always the source of truth for collections.
- Push (Aracne2 → GitHub) is the only repeatable operation and is
  available whenever the link exists.
- Initialize (GitHub → empty Aracne2 collection) is a one-shot
  operation; once any document exists it is permanently disabled.
- Websites are always derived from a collection: push-only, no
  Initialize.

GitHub Enterprise Server is supported transparently via the
per-link ``base_url`` column — point at ``https://ghe.example.com``
and the adapter rewrites every API call to the /api/v3/ prefix.

Per-link PAT override wins over the global plugin PAT — see
``system_settings.github_integration_pat`` (Fernet-encrypted at
rest, added to ``SENSITIVE_KEYS``).
"""

from app.core.plugin_base import PluginBase, PluginMeta
from app.plugins.github_integration.router import router


class Plugin(PluginBase):
    meta = PluginMeta(
        id="github_integration",
        name="GitHub Integration",
        version="1.0.0",
        native=False,
        description=(
            "Deposits a collection or website to a GitHub repository "
            "in one commit per push. Supports GitHub Enterprise "
            "Server via a configurable base URL. Uses a global PAT "
            "with optional per-link override. Non-native, opt-in."
        ),
        author="Aracne2 Team",
        min_role="Admin",
        capabilities=("collection_deposit", "website_deposit"),
        ui_descriptor={
            "collection_deposit": {
                "component": "GithubCollectionDepositPanel",
                "label": "GitHub",
                "priority": 210,
            },
            "website_deposit": {
                "component": "GithubWebsiteSection",
                "label": "GitHub",
                "priority": 210,
            },
        },
    )
    router = router
