"""Platform pre-fill helpers — Phase PP-E of Milestone 3.

A small set of zero-argument callables that built-in templates
declare as ``Field(kind="platform", source=...)``. Each helper
introspects the running deployment and returns a JSON-serialisable
value the public render template splices in.

The helpers live in this module rather than inside each template
file so the same helper can be reused by multiple templates (e.g.
``platform_active_deposit_targets`` is read by both
``continuity_plan`` and ``preservation_plan``). Adding a new
helper is a one-function addition here.

Helpers are **synchronous** — the public render path runs them
inline. Anything that needs an awaitable should be wrapped via
``asyncio.run`` upstream rather than leaking awaitables into the
template surface.
"""

from __future__ import annotations

import os
import platform as _platform
from typing import Any


# ── Versioning ───────────────────────────────────────────────────────────────


def python_version() -> str:
    """Return the running Python version (e.g. ``"3.12.4"``)."""
    return _platform.python_version()


def aracne_version() -> str:
    """Return the Aracne2 release tag from the environment.

    Defaults to ``"dev"`` when the deployment didn't set
    ``ARACNE_VERSION`` at build time. Operators wanting the
    release surfaced in policy pages can wire it in the Dockerfile.
    """
    return os.environ.get("ARACNE_VERSION", "dev")


def postgres_version() -> str:
    """Return the PostgreSQL server version, or ``"unknown"`` on
    failure. Synchronous wrapper around the async DB metadata
    query so it can be called from inside a Jinja2 template."""
    import asyncio

    from sqlalchemy import text

    from app.db.postgres import AsyncSessionLocal

    async def _q() -> str:
        async with AsyncSessionLocal() as db:
            row = await db.execute(text("SHOW server_version"))
            value = row.scalar_one()
            return str(value) if value else "unknown"

    try:
        return asyncio.run(_q())
    except Exception:
        return "unknown"


def existdb_version() -> str:
    """Return the eXist-db version reported by the configured client.

    Best-effort: if eXist-db is unreachable, returns ``"unknown"``
    rather than crashing the policy render.
    """
    try:
        import asyncio

        from app.config import settings
        from app.db.existdb import ExistDBClient

        async def _q() -> str:
            client = ExistDBClient(
                base_url=str(settings.existdb_base_url),
                username=settings.existdb_username,
                password=settings.exist_password,
            )
            try:
                return await client.version()
            finally:
                await client.close()

        return asyncio.run(_q())
    except Exception:
        return "unknown"


# ── Plugin / setting introspection ───────────────────────────────────────────


def plugin_active(plugin_id: str) -> bool:
    """Return True when the named plugin is active in the registry."""
    import asyncio

    from sqlalchemy import select

    from app.db.postgres import AsyncSessionLocal
    from app.models.plugin import Plugin, PluginStatus

    async def _q() -> bool:
        async with AsyncSessionLocal() as db:
            row = await db.scalar(select(Plugin).where(Plugin.name == plugin_id))
            return row is not None and row.status == PluginStatus.active

    try:
        return asyncio.run(_q())
    except Exception:
        return False


def system_setting(key: str, default: str = "") -> str:
    """Return the ``system_settings`` value for *key*, or *default*."""
    import asyncio

    from app.db.postgres import AsyncSessionLocal
    from app.models.system_setting import SystemSetting

    async def _q() -> str:
        async with AsyncSessionLocal() as db:
            row = await db.get(SystemSetting, key)
            if row is None:
                return default
            return row.value

    try:
        return asyncio.run(_q())
    except Exception:
        return default


def active_deposit_targets() -> list[str]:
    """Return the human-readable names of every active deposit
    plugin (``zenodo``, ``internet_archive``, ``codeberg``,
    ``github``, ``gitlab``, ``dataverse``).

    Drives the ``continuity_plan`` and ``preservation_plan`` templates
    so the published policy auto-lists the redundancy targets the
    deployment is actually using.
    """
    import asyncio

    from sqlalchemy import select

    from app.db.postgres import AsyncSessionLocal
    from app.models.plugin import Plugin, PluginStatus

    deposit_ids = {
        "zenodo": "Zenodo",
        "internet_archive": "Internet Archive",
        "codeberg": "Codeberg",
        "github": "GitHub",
        "gitlab": "GitLab",
        "dataverse": "Dataverse",
    }

    async def _q() -> list[str]:
        async with AsyncSessionLocal() as db:
            rows = list(
                await db.scalars(
                    select(Plugin).where(
                        Plugin.status == PluginStatus.active,
                        Plugin.name.in_(list(deposit_ids.keys())),
                    )
                )
            )
            return [deposit_ids[r.name] for r in rows]

    try:
        return asyncio.run(_q())
    except Exception:
        return []


def published_collection_count() -> int:
    """Return the number of currently-published collections."""
    import asyncio

    from sqlalchemy import func, select

    from app.db.postgres import AsyncSessionLocal
    from app.models.collection import Collection, CollectionStatus

    async def _q() -> int:
        async with AsyncSessionLocal() as db:
            n = await db.scalar(
                select(func.count())
                .select_from(Collection)
                .where(Collection.status == CollectionStatus.published)
            )
            return int(n or 0)

    try:
        return asyncio.run(_q())
    except Exception:
        return 0


def schema_catalogue() -> list[dict[str, Any]]:
    """Return ``[{name, version}]`` for every registered TEI schema."""
    import asyncio

    from sqlalchemy import select

    from app.db.postgres import AsyncSessionLocal
    from app.models.tei_schema import TeiSchema

    async def _q() -> list[dict[str, Any]]:
        async with AsyncSessionLocal() as db:
            rows = list(await db.scalars(select(TeiSchema)))
            return [
                {"name": r.name, "version": r.version or ""}
                for r in rows
            ]

    try:
        return asyncio.run(_q())
    except Exception:
        return []


def retention_defaults() -> dict[str, int]:
    """Return the platform's data-retention windows in days.

    Surface for ``privacy_dpia``: the policy auto-states
    "the platform retains audit logs for N days; expired sessions
    for M days" without the operator having to copy those numbers
    by hand.
    """
    return {
        "audit_log": int(system_setting("audit_log_retention_days", "90") or "90"),
        "expired_sessions": int(
            system_setting("expired_sessions_retention_days", "30") or "30"
        ),
    }


__all__ = [
    "python_version",
    "aracne_version",
    "postgres_version",
    "existdb_version",
    "plugin_active",
    "system_setting",
    "active_deposit_targets",
    "published_collection_count",
    "schema_catalogue",
    "retention_defaults",
]
