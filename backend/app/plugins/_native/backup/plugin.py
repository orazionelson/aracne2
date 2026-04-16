"""
Backup — native plugin.

Provides Admin-only endpoints to create, monitor and download ZIP backups of:
  - PostgreSQL tables (serialised to JSON)
  - eXist-db collections (XML documents)
  - Filesystem media (platform assets and document images)

A daily APScheduler job automatically purges old archives, keeping the 10 most
recent completed backups.

Configuration: Admin → /admin/backup
"""

from __future__ import annotations

import asyncio

from app.core.plugin_base import PluginBase, PluginMeta
from app.core.scheduler import scheduler
from app.plugins._native.backup.router import router
from app.plugins._native.backup.service import purge_old_backups


def _schedule_purge() -> None:
    """Register the daily backup purge job with APScheduler.

    Called lazily on first import so the scheduler is already running.
    """
    if scheduler.get_job("purge_old_backups"):
        return
    scheduler.add_job(
        lambda: asyncio.ensure_future(purge_old_backups()),
        trigger="cron",
        hour=3,
        minute=0,
        id="purge_old_backups",
        replace_existing=True,
    )


_schedule_purge()


class Plugin(PluginBase):
    meta = PluginMeta(
        id="backup",
        name="Backup",
        version="1.0.0",
        native=True,
        description=(
            "Creates ZIP archives of PostgreSQL data, eXist-db collections and "
            "filesystem media. Archives are stored in the backup_root volume and "
            "available for download from the Admin panel."
        ),
        author="Aracne2 Team",
        min_role="Admin",
    )
    router = router
