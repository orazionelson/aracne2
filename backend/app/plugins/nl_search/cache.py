"""Identical-query response cache for the NL search plugin.

Phase NLS-C. The endpoint computes a SHA-256 key over
``(corpus_id, provider, model, query)`` (see :func:`build_key`) and
either:

- looks the row up; if found and not expired, replays the stored
  SSE-event list verbatim (one less LLM round-trip), or
- runs the orchestrator and stores the resulting event list with
  ``expires_at = now + nl_search_cache_ttl_minutes``.

The cached payload is the ``data`` payload of every SSE event the
endpoint would otherwise have emitted — encoded as a JSON list. The
endpoint replays them with original ``event:`` names preserved.

Expired rows are not deleted on read (it would slow down the hot
path); a future cleanup job can sweep them periodically.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from typing import Any

import structlog
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.nl_search_cache import NlSearchCache

logger = structlog.get_logger()


def build_key(
    *, corpus_id: str, provider: str, model: str, query: str
) -> str:
    """Stable SHA-256 of the cache-defining tuple.

    Whitespace-trimmed and lowercased on the query so trivially-
    different formulations of the same question hit the same row.
    """
    norm_query = " ".join(query.strip().lower().split())
    raw = f"{corpus_id}\x1f{provider}\x1f{model}\x1f{norm_query}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _now() -> datetime:
    return datetime.now(UTC)


def _as_utc(dt: datetime) -> datetime:
    """SQLite drops tzinfo on a ``DateTime(timezone=True)`` column;
    PostgreSQL keeps it. Normalise so equality comparisons work in
    both runners."""
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


async def lookup(
    db: AsyncSession, key: str
) -> list[dict[str, Any]] | None:
    """Return the cached event list if present and unexpired, else None.

    Bumps ``hits`` so an operator can chart cache effectiveness without
    instrumenting every endpoint call.
    """
    row = await db.get(NlSearchCache, key)
    if row is None:
        return None
    if _as_utc(row.expires_at) <= _now():
        return None
    try:
        events = json.loads(row.response_json)
    except json.JSONDecodeError:
        logger.warning("nl_search_cache_corrupt", key=key)
        return None
    if not isinstance(events, list):
        return None
    # Bump hits in a separate UPDATE so a slow row-version read never
    # blocks the caller.
    await db.execute(
        update(NlSearchCache)
        .where(NlSearchCache.key == key)
        .values(hits=NlSearchCache.hits + 1)
    )
    return events


async def store(
    db: AsyncSession,
    *,
    key: str,
    events: list[dict[str, Any]],
    ttl_minutes: int,
) -> None:
    """Upsert the cached event list, refreshing ``expires_at``.

    A re-run of the same query over a stale cache writes a brand-new
    row body — the orchestrator's output is the source of truth.
    """
    payload = json.dumps(events, ensure_ascii=False)
    expires_at = _now() + timedelta(minutes=max(1, ttl_minutes))
    existing = await db.get(NlSearchCache, key)
    if existing is None:
        db.add(
            NlSearchCache(
                key=key,
                response_json=payload,
                expires_at=expires_at,
                hits=0,
            )
        )
    else:
        existing.response_json = payload
        existing.expires_at = expires_at
    await db.flush()


__all__ = ["build_key", "lookup", "store"]
