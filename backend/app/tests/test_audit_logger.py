"""Tests for the native Audit Logger plugin.

The plugin currently registers three no-op hook handlers as scaffolding
for future audit rows. These tests lock in the contract so the handler
signature (accepts arbitrary ``**kwargs``) cannot regress, and
verify that the plugin metadata matches expectations.
"""

from __future__ import annotations

import pytest

from app.core.hooks import HookEvent, hook_registry
from app.plugins._native.audit_logger import plugin as audit_plugin
from app.plugins._native.audit_logger.plugin import Plugin


def test_plugin_metadata() -> None:
    meta = Plugin.meta
    assert meta.id == "audit_logger"
    assert meta.native is True
    assert meta.min_role == "Admin"
    # Cannot be deactivated — the description is part of the contract
    # because the admin UI renders it.
    assert "audit" in (meta.description or "").lower()


def test_handlers_registered_for_user_lifecycle_events() -> None:
    """Importing the plugin registers one handler per user-lifecycle event."""
    for event in (
        HookEvent.ON_USER_CREATED,
        HookEvent.ON_USER_UPDATED,
        HookEvent.ON_USER_DELETED,
    ):
        handlers = hook_registry._handlers.get(event, [])  # type: ignore[attr-defined]
        assert any(
            h.__module__.endswith("audit_logger.plugin") for h in handlers
        ), f"no audit_logger handler on {event}"


@pytest.mark.asyncio
async def test_handlers_accept_arbitrary_kwargs() -> None:
    """Handlers must accept any kwargs emit() passes; they should never raise."""
    await audit_plugin._on_user_created(actor=object(), target_user=object(), db=None)
    await audit_plugin._on_user_updated(actor=object(), target_user=object(), db=None)
    await audit_plugin._on_user_deleted(actor=object(), target_user=object(), db=None)


@pytest.mark.asyncio
async def test_handlers_survive_emit_without_kwargs() -> None:
    """Defensive: emit() might pass no kwargs at all on edge cases."""
    await audit_plugin._on_user_created()
    await audit_plugin._on_user_updated()
    await audit_plugin._on_user_deleted()


@pytest.mark.asyncio
async def test_emit_reaches_audit_handlers_without_error() -> None:
    """Full round-trip: emitting each event through the registry does not raise."""
    for event in (
        HookEvent.ON_USER_CREATED,
        HookEvent.ON_USER_UPDATED,
        HookEvent.ON_USER_DELETED,
    ):
        await hook_registry.emit(event, actor=None, target_user=None, db=None)


def test_plugin_router_is_empty() -> None:
    """The plugin exposes no HTTP routes — it operates via hooks only."""
    assert len(Plugin.router.routes) == 0
