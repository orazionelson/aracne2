"""
Notification Dispatcher — native plugin.

Delivers in-app notifications to users by writing rows to the
notifications table.  Triggered via hook_registry events emitted by
other parts of the platform.
"""

from fastapi import APIRouter

from app.core.hooks import HookEvent, hook_registry
from app.core.plugin_base import PluginBase, PluginMeta


async def _on_user_created(**kwargs: object) -> None:
    # Future: create a welcome notification for the new user.
    # kwargs will contain: actor, target_user, db
    pass


hook_registry.register(HookEvent.ON_USER_CREATED, _on_user_created)


class Plugin(PluginBase):
    meta = PluginMeta(
        id="notification_dispatcher",
        name="Notification Dispatcher",
        version="1.0.0",
        native=True,
        description=(
            "Delivers in-app notifications to users via the notifications table. "
            "Cannot be deactivated."
        ),
        author="Aracne2 Team",
        min_role="Admin",
    )
    # No HTTP routes — notifications are created internally via hooks.
    router = APIRouter()
