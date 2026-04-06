"""
HookRegistry — central event bus for plugin hooks.

Plugins register async handlers for named events. The core emits events
at well-defined lifecycle points (login, user creation, etc.) without
knowing which plugins are listening.
"""

from collections.abc import Awaitable, Callable
from typing import Any


class HookEvent:
    """Constants for built-in system hook events."""

    ON_USER_LOGIN = "user.login"
    ON_USER_LOGOUT = "user.logout"
    ON_USER_CREATED = "user.created"
    ON_USER_UPDATED = "user.updated"
    ON_USER_DELETED = "user.deleted"
    ON_PLUGIN_ACTIVATED = "plugin.activated"
    ON_PLUGIN_DEACTIVATED = "plugin.deactivated"


HookHandler = Callable[..., Awaitable[None]]


class HookRegistry:
    """Async event bus. Plugins register handlers; the core emits events."""

    def __init__(self) -> None:
        self._handlers: dict[str, list[HookHandler]] = {}

    def register(self, event: str, handler: HookHandler) -> None:
        """Register *handler* to be called when *event* is emitted."""
        self._handlers.setdefault(event, []).append(handler)

    def unregister(self, event: str, handler: HookHandler) -> None:
        """Remove a previously registered handler (idempotent)."""
        handlers = self._handlers.get(event, [])
        if handler in handlers:
            handlers.remove(handler)

    async def emit(self, event: str, **kwargs: Any) -> None:
        """Call all handlers registered for *event* in registration order."""
        for handler in self._handlers.get(event, []):
            await handler(**kwargs)


hook_registry = HookRegistry()
