"""Codeberg Integration — non-native plugin.

Deposits an Aracne2 collection to a Codeberg (or any self-hosted
Forgejo / Gitea) repository in a single commit per push. Uses the
shared ``app.plugins._lib.git_forge`` abstraction so that GitHub and
GitLab plugins can ship alongside without duplicating the push
orchestration.

Source-of-truth contract (inherited from the FUTURE_IDEAS entry):

- eXist-db is always the source of truth.
- Push (Aracne2 → forge) is the only repeatable operation and is
  available whenever the link exists.
- Initialize (forge → empty Aracne2 collection) is a one-shot
  available in Phase 2; once any document exists it is permanently
  disabled.

Per-link PAT override wins over the global plugin PAT — see
``system_settings.codeberg_integration_pat`` (Fernet-encrypted at
rest, added to ``SENSITIVE_KEYS``).
"""

from app.core.plugin_base import PluginBase, PluginMeta
from app.plugins.codeberg_integration.router import router


class Plugin(PluginBase):
    meta = PluginMeta(
        id="codeberg_integration",
        name="Codeberg Integration",
        version="1.2.0",
        native=False,
        description=(
            "Deposits a collection or website to a Codeberg repository "
            "in one commit per push. Supports one-shot Initialize for "
            "empty collections (forge → Aracne2) and website-tree "
            "deposit. Self-hosted Forgejo/Gitea works via a configurable "
            "base URL. Uses a global PAT with optional per-link override. "
            "Non-native, opt-in."
        ),
        author="Aracne2 Team",
        min_role="Admin",
        capabilities=("collection_deposit", "website_deposit"),
        ui_descriptor={
            "collection_deposit": {
                "component": "CodebergCollectionDepositPanel",
                "label": "Codeberg",
                "priority": 200,
            },
            "website_deposit": {
                "component": "CodebergWebsiteSection",
                "label": "Codeberg",
                "priority": 200,
            },
        },
    )
    router = router
