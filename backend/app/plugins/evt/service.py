"""EVT viewer integration service — public collection config and raw XML delivery."""

import re
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import DomainValidationError, NotFoundError
from app.db.existdb import ExistDBClient
from app.models.collection import Collection, CollectionStatus

logger = structlog.get_logger()

_FILENAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*\.xml$")
_MAX_FILENAME_LEN = 120


def _validate_filename(filename: str) -> None:
    """Reject filenames that could cause path traversal or be non-XML."""
    if len(filename) > _MAX_FILENAME_LEN:
        raise DomainValidationError(
            "INVALID_FILENAME",
            f"Filename must be {_MAX_FILENAME_LEN} characters or fewer",
        )
    if not _FILENAME_RE.match(filename):
        raise DomainValidationError(
            "INVALID_FILENAME",
            "Filename must start with a letter or digit and end with '.xml'",
        )


async def _get_public_collection(db: AsyncSession, slug: str) -> Collection:
    """Fetch a published + public collection by slug; raise 404 otherwise."""
    row = await db.scalar(
        select(Collection).where(
            Collection.slug == slug,
            Collection.status == CollectionStatus.published,
            Collection.is_public.is_(True),
        )
    )
    if not row:
        raise NotFoundError("Collection not found or not publicly available")
    return row


async def get_evt_config(
    db: AsyncSession,
    existdb: ExistDBClient,
    slug: str,
) -> dict[str, Any]:
    """Return an EVT 2-compatible config.json dict for a public collection."""
    col = await _get_public_collection(db, slug)
    filenames = await existdb.list_collection(slug)
    filenames.sort()
    logger.info("evt_config_served", slug=slug, file_count=len(filenames))
    # EVT 2 merges config.json directly into its defaults via angular.extend —
    # it does NOT unwrap a top-level "EVT" key.  Properties must be at the root.
    # dataUrl points to the first file; EVT 2 is designed for single-document editions.
    first = f"data/{filenames[0]}" if filenames else ""
    return {
        "projectName": col.title,
        "defaultEdition": "diplomatic",
        "dataUrl": first,
    }


async def get_document_xml(
    db: AsyncSession,
    existdb: ExistDBClient,
    slug: str,
    filename: str,
) -> bytes:
    """Return raw XML bytes for a document in a public collection."""
    await _get_public_collection(db, slug)
    _validate_filename(filename)
    return await existdb.get_document(slug, filename)
