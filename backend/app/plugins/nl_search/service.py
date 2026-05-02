"""Endpoint orchestration glue — concurrency gate + auth/budget gates.

Phase NLS-D. The router calls into this module for the bits that
need to be testable independently of the SSE transport layer:

- :func:`auth_gate` — applies the ``nl_search_require_login`` setting.
- :func:`acquire_concurrency_slot` — non-blocking semaphore check;
  raises :class:`OverCapacityError` when full.
- :func:`format_sse` — SSE serialisation helper used by the router.
"""

from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager
from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.settings import get_decrypted_setting

logger = structlog.get_logger()


class AuthRequiredError(RuntimeError):
    """Endpoint hit by an anonymous request while
    ``nl_search_require_login`` is on."""


class OverCapacityError(RuntimeError):
    """The configured concurrency slots are full; reject this request."""


# Module-level semaphore — recreated when the configured limit changes.
_semaphore: asyncio.Semaphore | None = None
_semaphore_limit: int = 0
_semaphore_lock = asyncio.Lock()


async def _resolve_semaphore(db: AsyncSession) -> asyncio.Semaphore:
    """Return the singleton semaphore, rebuilding it if the cap changed.

    The orchestrator instantiates the limit at startup, but operators
    may bump it from the Settings UI without a restart. We honour the
    new value on the next request — there is no need for hot-resize
    of in-flight semaphores because raising the cap can only ever
    *allow* more concurrent runs, never reject existing ones.
    """
    global _semaphore, _semaphore_limit
    raw = (await get_decrypted_setting(db, "nl_search_max_concurrent")).strip() or "2"
    try:
        limit = max(1, int(raw))
    except ValueError:
        limit = 2
    async with _semaphore_lock:
        if _semaphore is None or _semaphore_limit != limit:
            _semaphore = asyncio.Semaphore(limit)
            _semaphore_limit = limit
        return _semaphore


async def auth_gate(db: AsyncSession, *, user_present: bool) -> None:
    """Raise :class:`AuthRequiredError` when login is required and missing."""
    require = (await get_decrypted_setting(db, "nl_search_require_login")) != "false"
    if require and not user_present:
        raise AuthRequiredError("Login required for natural-language search.")


@asynccontextmanager
async def acquire_concurrency_slot(db: AsyncSession):
    """Reject-on-full semaphore around the orchestrator run.

    Per the §25 spec the default ``concurrency_overflow`` mode is to
    reject (fast-fail with 503) rather than queue. asyncio.Semaphore
    has no public ``acquire_nowait``; we approximate with a
    short-deadline ``wait_for`` so a brief contention window is
    tolerated but a saturated server fails fast.
    """
    sem = await _resolve_semaphore(db)
    try:
        await asyncio.wait_for(sem.acquire(), timeout=0.05)
    except asyncio.TimeoutError as exc:
        raise OverCapacityError(
            "nl_search is at capacity; try again shortly."
        ) from exc
    try:
        yield
    finally:
        sem.release()


def format_sse(name: str, data: dict[str, Any]) -> str:
    """Serialise one SSE message — ``event:`` + ``data:`` + blank line."""
    payload = json.dumps(data, ensure_ascii=False)
    return f"event: {name}\ndata: {payload}\n\n"


__all__ = [
    "AuthRequiredError",
    "OverCapacityError",
    "auth_gate",
    "acquire_concurrency_slot",
    "format_sse",
]
