"""Populate ``/db/aracne2/published/{slug}`` for collections already in
``status='published'`` at the moment Aracne2 introduces the working/published
split (Phase A1 of document versioning).

Usage (from inside the backend container):

    docker compose exec backend python -m app.scripts.migrate_published_split

The script is **idempotent and re-runnable**. It iterates every collection
in PostgreSQL with ``status='published'``, ensures the published snapshot
exists in eXist-db at ``existdb.published_path(slug)`` by calling
``copy_collection_to_published(slug)``, and stores the resulting tree
fingerprint in ``Collection.last_published_tree_hash`` so subsequent
``publish_collection`` calls can short-circuit on unchanged content.

Failures on a single collection are logged and the loop continues with the
next collection — running the script again will retry the failed ones.

The PostgreSQL writes use ``sa.text(...)`` rather than ORM updates so the
script does not need every related model imported just to satisfy the
SQLAlchemy metadata's foreign-key resolution at flush time (Collection has
FKs to body_templates / tei_schemas / licenses that would otherwise need
explicit imports here).
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import sys
import uuid

import structlog
from sqlalchemy import text

from app.db.existdb import existdb_client
from app.db.postgres import AsyncSessionLocal

logger = structlog.get_logger()


async def _compute_tree_hash(slug: str) -> str:
    """Same fingerprint algorithm used by services.xmldb._compute_collection_tree_hash."""
    filenames = sorted(await existdb_client.list_collection(slug))
    parts: list[bytes] = []
    for fn in filenames:
        content = await existdb_client.get_document(slug, fn)
        digest = hashlib.sha256(content).hexdigest()
        parts.append(f"{fn}\0{digest}\n".encode())
    return hashlib.sha256(b"".join(parts)).hexdigest()


async def _migrate_one(
    db: object, col_id: uuid.UUID, slug: str
) -> bool:
    """Mirror one published collection into the snapshot path.

    On success, persists the freshly computed tree hash via a raw UPDATE so
    the ORM's metadata graph (foreign keys, related mappers) is not consulted.
    Returns True on success, False on any logged failure.
    """
    try:
        await existdb_client.copy_collection_to_published(slug)
        tree_hash = await _compute_tree_hash(slug)
        await db.execute(  # type: ignore[attr-defined]
            text(
                "UPDATE collections SET last_published_tree_hash = :h "
                "WHERE id = :id"
            ),
            {"h": tree_hash, "id": col_id},
        )
        logger.info(
            "published_split_migrated",
            slug=slug,
            tree_hash=tree_hash[:12],
        )
        return True
    except Exception as exc:  # noqa: BLE001 — diagnostic loop, do not abort
        logger.error(
            "published_split_migration_failed",
            slug=slug,
            error=str(exc),
        )
        return False


async def _run(dry_run: bool) -> int:
    await existdb_client.connect()
    try:
        async with AsyncSessionLocal() as db:
            rows = (
                await db.execute(
                    text(
                        "SELECT id, slug FROM collections "
                        "WHERE status = 'published' ORDER BY slug"
                    )
                )
            ).all()
            logger.info("published_split_start", total=len(rows), dry_run=dry_run)

            if dry_run:
                for row in rows:
                    logger.info("published_split_would_migrate", slug=row.slug)
                return 0

            ok = 0
            failed = 0
            for row in rows:
                if await _migrate_one(db, row.id, row.slug):
                    ok += 1
                else:
                    failed += 1
            await db.commit()
            logger.info("published_split_done", ok=ok, failed=failed)
            return 0 if failed == 0 else 1
    finally:
        await existdb_client.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List the collections that would be migrated without performing the copy.",
    )
    args = parser.parse_args()
    exit_code = asyncio.run(_run(dry_run=args.dry_run))
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
