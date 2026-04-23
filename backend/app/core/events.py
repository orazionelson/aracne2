"""Structured event name constants and emission helper.

Goal: one canonical name per meaningful platform action, consistent
field naming, so dashboards and log queries can rely on stable keys.

Usage::

    from app.core.events import emit_event, EVENT_LOGIN_SUCCESS

    emit_event(EVENT_LOGIN_SUCCESS, user_id=str(user.id),
               username=user.username, role=role.name)

Naming convention: ``<subject>_<verb_past>`` in ``snake_case``.

Common field names — use these rather than inventing synonyms:

- ``user_id``      — UUID string of the acting / target user
- ``username``     — plaintext username
- ``role``         — role name as string
- ``plugin``       — plugin slug
- ``key``          — setting key
- ``actor_user_id``— acting user when different from the subject
"""

from __future__ import annotations

from typing import Any

import structlog

_logger = structlog.get_logger()

# ── Authentication ───────────────────────────────────────────────────────────
EVENT_LOGIN_SUCCESS = "login_success"
EVENT_LOGIN_FAILED = "login_failed"
EVENT_LOGOUT = "logout"
EVENT_TOKEN_REFRESHED = "token_refreshed"
EVENT_IMPERSONATION_STARTED = "impersonation_started"

# ── Plugin lifecycle ─────────────────────────────────────────────────────────
EVENT_PLUGIN_ACTIVATED = "plugin_activated"
EVENT_PLUGIN_DEACTIVATED = "plugin_deactivated"
EVENT_PLUGIN_DELETED = "plugin_deleted"

# ── Settings ─────────────────────────────────────────────────────────────────
EVENT_SETTING_CHANGED = "setting_changed"

# ── Collections ──────────────────────────────────────────────────────────────
EVENT_COLLECTION_SUBMITTED = "collection_submitted"
EVENT_COLLECTION_PUBLISHED = "collection_published"
EVENT_COLLECTION_UNPUBLISHED = "collection_unpublished"
EVENT_COLLECTION_DELETED = "collection_deleted"


def emit_event(name: str, **fields: Any) -> None:
    """Emit a structured event through structlog.

    Thin wrapper: intentionally no extra validation — the constants
    above are the discipline. Keeping the helper minimal means log
    shipping, JSON rendering, and processor chain configuration stay
    in ``app.core.logging`` as before.
    """
    _logger.info(name, **fields)
