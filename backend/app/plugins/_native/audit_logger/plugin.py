"""
Audit Logger — native plugin.

Records sensitive platform actions (login, user create/update/delete,
role changes) to the audit_log table.  Handlers are registered on the
hook_registry at import time and called by services via hook_registry.emit().
"""

from fastapi import APIRouter

from app.core.hooks import HookEvent, hook_registry
from app.core.plugin_base import PluginBase, PluginMeta


async def _on_user_created(**kwargs: object) -> None:
    # Future: write AuditLog row via injected db session.
    # kwargs will contain: actor, target_user, db
    pass


async def _on_user_deleted(**kwargs: object) -> None:
    pass


async def _on_user_updated(**kwargs: object) -> None:
    pass


# Register handlers immediately at import so they are active for the
# entire lifetime of the process.
hook_registry.register(HookEvent.ON_USER_CREATED, _on_user_created)
hook_registry.register(HookEvent.ON_USER_UPDATED, _on_user_updated)
hook_registry.register(HookEvent.ON_USER_DELETED, _on_user_deleted)


class Plugin(PluginBase):
    meta = PluginMeta(
        id="audit_logger",
        name="Audit Logger",
        version="1.0.0",
        native=True,
        description=(
            "Records sensitive platform actions to the audit_log table. "
            "Cannot be deactivated."
        ),
        author="Aracne2 Team",
        min_role="Admin",
    )
    # No HTTP routes — this plugin operates via the hook system only.
    router = APIRouter()
