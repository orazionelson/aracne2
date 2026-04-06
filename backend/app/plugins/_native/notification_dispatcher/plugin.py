"""
Notification Dispatcher — native plugin.

Delivers in-app notifications to users by writing rows to the
notifications table.  Triggered via hook_registry events emitted by
services/users.py and services/auth.py.
"""

from typing import cast

from fastapi import APIRouter
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.hooks import HookEvent, hook_registry
from app.core.plugin_base import PluginBase, PluginMeta
from app.models.user import User

# Localized welcome title by preferred_lang.
_WELCOME_TITLE: dict[str, str] = {
    "it": "Benvenuto su Aracne2",
    "en": "Welcome to Aracne2",
}
_WELCOME_BODY: dict[str, str] = {
    "it": "Il tuo account è stato creato con successo.",
    "en": "Your account has been created successfully.",
}


async def _on_user_created(**kwargs: object) -> None:
    # Lazy import to avoid circular deps at module load time.
    from app.models.notification import Notification

    db = cast(AsyncSession | None, kwargs.get("db"))
    user = cast(User | None, kwargs.get("user"))
    if db is None or user is None:
        return

    lang = getattr(user, "preferred_lang", "en") or "en"
    db.add(
        Notification(
            user_id=user.id,
            type="welcome",
            title=_WELCOME_TITLE.get(lang, _WELCOME_TITLE["en"]),
            body=_WELCOME_BODY.get(lang, _WELCOME_BODY["en"]),
        )
    )


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
