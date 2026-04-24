"""GitLab Integration — non-native plugin.

Deposits an Aracne2 collection or website to a GitLab repository in
a single commit per push. Uses the shared
``app.plugins._lib.git_forge`` abstraction (already exercised by
the Codeberg and GitHub plugins) so push orchestration and token
resolution are not duplicated.

Source-of-truth contract:

- eXist-db is always the source of truth for collections.
- Push (Aracne2 → GitLab) is the only repeatable operation and is
  available whenever the link exists.
- Initialize (GitLab → empty Aracne2 collection) is one-shot; once
  any document exists it is permanently disabled.
- Websites are always derived from a collection: push-only, no
  Initialize.

Self-hosted GitLab instances are supported transparently via the
per-link ``base_url`` column — point at ``https://gitlab.example.edu``
and the adapter targets that host's ``/api/v4/`` namespace.

Per-link PAT override wins over the global plugin PAT — see
``system_settings.gitlab_integration_pat`` (Fernet-encrypted at
rest, added to ``SENSITIVE_KEYS``).
"""

from app.core.plugin_base import PluginBase, PluginMeta
from app.plugins.gitlab_integration.router import router


class Plugin(PluginBase):
    meta = PluginMeta(
        id="gitlab_integration",
        name="GitLab Integration",
        version="1.0.0",
        native=False,
        description=(
            "Deposits a collection or website to a GitLab repository "
            "in one commit per push. Supports self-hosted GitLab via "
            "a configurable base URL. Uses a global PAT with optional "
            "per-link override. Non-native, opt-in."
        ),
        author="Aracne2 Team",
        min_role="Admin",
    )
    router = router
