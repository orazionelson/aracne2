"""Email Dispatcher — native plugin (Phase EM-B).

Translates collection workflow events (``ON_COLLECTION_SUBMITTED``,
``ON_COLLECTION_REJECTED``, ``ON_COLLECTION_PUBLISHED``) into outgoing
emails through ``services.email.send_mail`` and Jinja2 templates under
``app/email_templates/{event}/{lang}/``.

Hook handlers are registered at module import time as a side-effect, the
same pattern used by ``notification_dispatcher`` and
``webhook_dispatcher``. The plugin is native and always loaded; toggling
behaviour at runtime is via ``system_settings.email_enabled`` (platform
gate) and ``user.email_notifications_enabled`` (per-user opt-out).
"""

from fastapi import APIRouter

from app.core.hooks import HookEvent, hook_registry
from app.core.plugin_base import PluginBase, PluginMeta
from app.plugins._native.email_dispatcher.service import (
    on_collection_published,
    on_collection_rejected,
    on_collection_submitted,
    on_gdpr_request_submitted,
)


hook_registry.register(HookEvent.ON_COLLECTION_SUBMITTED, on_collection_submitted)
hook_registry.register(HookEvent.ON_COLLECTION_REJECTED, on_collection_rejected)
hook_registry.register(HookEvent.ON_COLLECTION_PUBLISHED, on_collection_published)
hook_registry.register(HookEvent.ON_GDPR_REQUEST_SUBMITTED, on_gdpr_request_submitted)


class Plugin(PluginBase):
    meta = PluginMeta(
        id="email_dispatcher",
        name="Email Dispatcher",
        version="1.0.0",
        native=True,
        description=(
            "Sends workflow emails (collection submitted / revisions requested / "
            "published) via the local Postfix container. Cannot be deactivated."
        ),
        author="Aracne2 Team",
        min_role="Admin",
    )
    # No HTTP routes — the dispatcher runs entirely off hook events.
    router = APIRouter()
