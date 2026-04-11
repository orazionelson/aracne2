"""
Scheduler — periodic background jobs.

Uses APScheduler (in-process, no external broker).  Jobs are registered
here and started/stopped in the FastAPI lifespan.

Current jobs:
  - purge_audit_log              daily   — deletes old audit_log rows
  - purge_expired_sessions       daily   — deletes fully-expired session rows
  - purge_search_engine_cache    hourly  — deletes expired search engine cache entries

Retention periods are read from system_settings at each job run so that
Admin changes take effect without a restart.
"""

import asyncio

import structlog
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.db.postgres import AsyncSessionLocal

logger = structlog.get_logger()

scheduler = AsyncIOScheduler(timezone="UTC")

# ── Helpers ────────────────────────────────────────────────────────────────────

async def _get_retention(key: str, default: int) -> int:
    """Read an integer setting from system_settings, falling back to *default*."""
    try:
        from sqlalchemy import select
        from app.models.system_setting import SystemSetting

        async with AsyncSessionLocal() as db:
            row = await db.get(SystemSetting, key)
            if row:
                return int(row.value)
    except Exception as exc:
        logger.warning("scheduler_setting_read_failed", key=key, error=str(exc))
    return default


# ── Job implementations ────────────────────────────────────────────────────────

async def purge_audit_log() -> None:
    """Delete audit_log rows older than audit_log_retention_days."""
    from datetime import UTC, datetime, timedelta
    from sqlalchemy import delete
    from app.models.audit_log import AuditLog

    days = await _get_retention("audit_log_retention_days", 90)
    cutoff = datetime.now(UTC) - timedelta(days=days)

    try:
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                delete(AuditLog).where(AuditLog.occurred_at < cutoff)
            )
            await db.commit()
            deleted = result.rowcount
        logger.info("purge_audit_log_done", deleted=deleted, cutoff=cutoff.date().isoformat())
    except Exception as exc:
        logger.error("purge_audit_log_failed", error=str(exc))


async def purge_expired_sessions() -> None:
    """Delete session rows whose refresh token has fully expired."""
    from datetime import UTC, datetime, timedelta
    from sqlalchemy import delete
    from app.models.session import Session

    days = await _get_retention("expired_sessions_retention_days", 30)
    cutoff = datetime.now(UTC) - timedelta(days=days)

    try:
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                delete(Session).where(Session.refresh_expires < cutoff)
            )
            await db.commit()
            deleted = result.rowcount
        logger.info(
            "purge_expired_sessions_done",
            deleted=deleted,
            cutoff=cutoff.date().isoformat(),
        )
    except Exception as exc:
        logger.error("purge_expired_sessions_failed", error=str(exc))


async def purge_search_engine_cache() -> None:
    """Delete search_engine_query_cache rows whose expires_at is in the past."""
    from datetime import UTC, datetime
    from sqlalchemy import delete
    from app.models.search_engine import SearchEngineQueryCache

    now = datetime.now(UTC)
    try:
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                delete(SearchEngineQueryCache).where(
                    SearchEngineQueryCache.expires_at < now
                )
            )
            await db.commit()
            deleted = result.rowcount
        logger.info("purge_search_engine_cache_done", deleted=deleted)
    except Exception as exc:
        logger.error("purge_search_engine_cache_failed", error=str(exc))


# ── Registration ───────────────────────────────────────────────────────────────

def register_jobs() -> None:
    """Add all periodic jobs to the scheduler. Call once at startup."""
    scheduler.add_job(
        lambda: asyncio.ensure_future(purge_audit_log()),
        trigger="cron",
        hour=2,
        minute=0,
        id="purge_audit_log",
        replace_existing=True,
    )
    scheduler.add_job(
        lambda: asyncio.ensure_future(purge_expired_sessions()),
        trigger="cron",
        hour=2,
        minute=30,
        id="purge_expired_sessions",
        replace_existing=True,
    )
    scheduler.add_job(
        lambda: asyncio.ensure_future(purge_search_engine_cache()),
        trigger="cron",
        minute=15,  # :15 of every hour
        id="purge_search_engine_cache",
        replace_existing=True,
    )
    logger.info("scheduler_jobs_registered", count=len(scheduler.get_jobs()))
