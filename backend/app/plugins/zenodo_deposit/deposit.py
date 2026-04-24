"""End-to-end deposit orchestration.

``deposit_collection`` is the single entry point — call it from the hook
handler or from the manual re-deposit endpoint.  It reads config from
``system_settings``, fetches the collection's documents from eXist-db,
pushes them to Zenodo, and records the outcome in ``plugin_data`` so
the UI can surface a DOI badge next to the collection.

This flow talks to the **new** Zenodo (InvenioRDM) ``/api/records`` API:
create draft → upload files (init/upload/commit) → optionally publish.
"""

from __future__ import annotations

import io
import uuid
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings as app_settings
from app.db.existdb import ExistDBClient, existdb_client
from app.models.collection import Collection
from app.models.license import License
from app.models.website import BuildStatus, RenderingMode, Website
from app.plugins.zenodo_deposit.config import ZenodoRuntimeConfig, load_runtime_config
from app.plugins.zenodo_deposit.mapping import (
    collection_to_metadata,
    to_zenodo_payload,
    website_to_metadata,
)
from app.plugins.zenodo_deposit.service import DepositResult, ZenodoClient, ZenodoError
from app.services.plugin_data import PluginDataService

logger = structlog.get_logger()

# The plugin slug used both as the ``Plugin.name`` DB value and as the
# ``entity_type`` namespace in ``plugin_data``.
PLUGIN_ID = "zenodo_deposit"

# Per-collection plugin_data key — most recent deposit record for this plugin.
DEPOSIT_KEY = "deposit"

# Per-website plugin_data key — kept distinct so the same plugin can carry
# both a collection deposit (under "deposit") and a website-snapshot deposit
# (under "website_deposit") without one overwriting the other.
WEBSITE_DEPOSIT_KEY = "website_deposit"

# Safety caps for the website-deposit file walk. Identical to those used by
# the git-forge website push so the operator's intuition about what fits in
# a deposit transfers between plugins.
_WEBSITE_DEPOSIT_MAX_FILES = 5000
_WEBSITE_DEPOSIT_MAX_BYTES_PER_FILE = 25 * 1024 * 1024  # 25 MB


class DepositSkipped(RuntimeError):
    """Raised when the plugin decides not to deposit (missing token, already
    deposited, …).  Not an error — the hook swallows it silently."""


async def _load_license(db: AsyncSession, col: Collection) -> License | None:
    if col.license_id is None:
        return None
    return await db.get(License, col.license_id)


async def _build_orcid_map(db: AsyncSession) -> dict[str, str]:
    """Load every User that has an ORCID into a name→ORCID map.

    Keyed on both ``display_name`` and ``username`` so either form of
    the creator name in the Collection (free-text author, resp_stmt
    name) can match a user. For a platform with tens of users this
    is cheap enough to run on every deposit.
    """
    from sqlalchemy import select

    from app.models.user import User

    rows = list(
        await db.scalars(
            select(User).where(User.orcid.is_not(None))
        )
    )
    out: dict[str, str] = {}
    for u in rows:
        if u.orcid:
            if u.display_name:
                out[u.display_name] = u.orcid
            out[u.username] = u.orcid
    return out


async def _load_files(
    existdb: ExistDBClient, slug: str
) -> list[tuple[str, bytes]]:
    """Return the list of ``(filename, xml_bytes)`` for all docs in *slug*."""
    names = await existdb.list_collection(slug)
    files: list[tuple[str, bytes]] = []
    for name in names:
        try:
            content = await existdb.get_document(slug, name)
        except Exception as exc:  # noqa: BLE001 — one missing doc shouldn't nuke deposit
            logger.warning("zenodo_file_fetch_failed", filename=name, error=str(exc))
            continue
        files.append((name, content))
    return files


def _bundle_zip(slug: str, files: list[tuple[str, bytes]]) -> tuple[str, bytes]:
    """Zip *files* in memory and return ``(zip_filename, zip_bytes)``.

    Uses ``ZIP_DEFLATED`` — TEI XML compresses well (~10× reduction is
    typical) so the Zenodo bucket receives a fraction of the raw bytes.
    """
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, content in files:
            zf.writestr(name, content)
    return f"{slug}.zip", buffer.getvalue()


async def _plugin_id(db: AsyncSession) -> uuid.UUID:
    """Resolve the Plugin row UUID for this plugin slug."""
    from sqlalchemy import select

    from app.models.plugin import Plugin

    row = await db.scalar(select(Plugin).where(Plugin.name == PLUGIN_ID))
    if row is None:
        raise DepositSkipped(
            f"Plugin registry row '{PLUGIN_ID}' not found — has the loader run?"
        )
    return row.id


async def _already_deposited(
    plugin_uuid: uuid.UUID, db: AsyncSession, collection_id: uuid.UUID
) -> bool:
    svc = PluginDataService(plugin_id=plugin_uuid)
    existing = await svc.get(
        db, entity_type="collection", key=DEPOSIT_KEY, entity_id=collection_id
    )
    if not existing:
        return False
    status = existing.get("status")
    return status in {"draft", "published"}


async def _record_status(
    *,
    plugin_uuid: uuid.UUID,
    db: AsyncSession,
    collection_id: uuid.UUID,
    data: dict[str, Any],
) -> None:
    svc = PluginDataService(plugin_id=plugin_uuid)
    await svc.set(
        db,
        entity_type="collection",
        key=DEPOSIT_KEY,
        data=data,
        entity_id=collection_id,
    )
    await db.commit()


async def deposit_collection(
    db: AsyncSession,
    collection: Collection,
    *,
    existdb: ExistDBClient | None = None,
    zenodo_client: ZenodoClient | None = None,
    force: bool = False,
) -> DepositResult:
    """Deposit *collection* on Zenodo.

    Call with ``force=True`` from the manual re-deposit endpoint to
    ignore an existing successful record; the automatic hook path leaves
    force at its default (False).
    """
    cfg = await load_runtime_config(db)
    if not cfg.api_token:
        raise DepositSkipped("Zenodo API token not configured")

    plugin_uuid = await _plugin_id(db)

    if not force and await _already_deposited(plugin_uuid, db, collection.id):
        raise DepositSkipped(
            f"Collection {collection.slug} already deposited (no force)"
        )

    license_obj = await _load_license(db, collection)
    orcid_map = await _build_orcid_map(db)
    # Per-collection override for the resource_type (e.g. "publication-book"
    # for a manuscript vs. the global default "publication-other"). NULL on
    # the collection means "inherit the global zenodo_resource_type setting".
    effective_resource_type = collection.zenodo_resource_type or cfg.resource_type
    meta = collection_to_metadata(
        collection=collection,
        license_obj=license_obj,
        public_base_url=cfg.public_base_url,
        resource_type=effective_resource_type,
        access=cfg.access,
        orcid_by_name=orcid_map,
    )
    payload = to_zenodo_payload(meta, community=cfg.default_community or None)

    files = await _load_files(existdb or existdb_client, collection.slug)

    client = zenodo_client or ZenodoClient(
        base_url=cfg.base_url, api_token=cfg.api_token
    )

    try:
        draft = await client.create_draft(payload)
        if collection.zenodo_upload_as_zip:
            # Per-collection opt-in: bundle every document into a single ZIP
            # archive so the Zenodo record's Files tab has one downloadable
            # artefact instead of N small XMLs.
            zip_name, zip_bytes = _bundle_zip(collection.slug, files)
            await client.upload_file(draft.id, zip_name, zip_bytes)
        else:
            for filename, content in files:
                await client.upload_file(draft.id, filename, content)

        if cfg.auto_publish:
            result = await client.publish(draft.id)
        else:
            result = DepositResult(
                id=draft.id,
                doi=None,
                record_url=draft.record_url,
                status="draft",
            )
    except ZenodoError as exc:
        await _record_status(
            plugin_uuid=plugin_uuid,
            db=db,
            collection_id=collection.id,
            data={
                "status": "failed",
                "error": str(exc),
                "http_status": exc.status_code,
                "submitted_at": datetime.now(UTC).isoformat(),
            },
        )
        raise

    await _record_status(
        plugin_uuid=plugin_uuid,
        db=db,
        collection_id=collection.id,
        data={
            "status": result.status,
            "deposit_id": result.id,
            "doi": result.doi,
            "record_url": result.record_url,
            "submitted_at": datetime.now(UTC).isoformat(),
            "error": None,
        },
    )
    return result


# ── Website deposit ─────────────────────────────────────────────────────────


def _collect_rendered_files(slug: str) -> list[tuple[str, bytes]]:
    """Walk the rendered-site tree under ``settings.websites_root / slug``.

    Returns ``(forge-relative POSIX path, bytes)`` tuples — same shape
    as :func:`_load_files` for collections, so ``_bundle_zip`` can
    reuse it. Skips dotfiles and dot-prefixed directories. Hard caps
    on total file count and per-file size mirror those used by the
    git-forge website push.
    """
    root = Path(app_settings.websites_root) / slug
    if not root.is_dir():
        raise DepositSkipped(
            f"Website '{slug}' has no rendered output on disk "
            f"({root}). Trigger a build first."
        )
    files: list[tuple[str, bytes]] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(root)
        if any(part.startswith(".") for part in rel.parts):
            continue
        size = path.stat().st_size
        if size > _WEBSITE_DEPOSIT_MAX_BYTES_PER_FILE:
            raise DepositSkipped(
                f"'{rel.as_posix()}' exceeds the "
                f"{_WEBSITE_DEPOSIT_MAX_BYTES_PER_FILE} byte cap for "
                f"website deposits."
            )
        files.append((rel.as_posix(), path.read_bytes()))
        if len(files) > _WEBSITE_DEPOSIT_MAX_FILES:
            raise DepositSkipped(
                f"Rendered site exceeds the {_WEBSITE_DEPOSIT_MAX_FILES} "
                f"file cap; trim or split the site before depositing."
            )
    return files


async def _website_already_deposited(
    plugin_uuid: uuid.UUID, db: AsyncSession, website_id: uuid.UUID,
) -> bool:
    svc = PluginDataService(plugin_id=plugin_uuid)
    existing = await svc.get(
        db, entity_type="website", key=WEBSITE_DEPOSIT_KEY, entity_id=website_id,
    )
    if not existing:
        return False
    return existing.get("status") in {"draft", "published"}


async def _record_website_status(
    *,
    plugin_uuid: uuid.UUID,
    db: AsyncSession,
    website_id: uuid.UUID,
    data: dict[str, Any],
) -> None:
    svc = PluginDataService(plugin_id=plugin_uuid)
    await svc.set(
        db,
        entity_type="website",
        key=WEBSITE_DEPOSIT_KEY,
        data=data,
        entity_id=website_id,
    )
    await db.commit()


async def deposit_website(
    db: AsyncSession,
    website: Website,
    *,
    upload_as_zip: bool = True,
    force: bool = False,
    zenodo_client: ZenodoClient | None = None,
) -> DepositResult:
    """Deposit the rendered output of *website* on Zenodo.

    The website must be **STATIC** or **HYBRID** (a DYNAMIC site has no
    static output to deposit) and its ``build_status`` must be ``done``.
    The optional source collection is used to enrich the deposit
    metadata (creators, license, publication date) when available.

    ``upload_as_zip`` is decided at request time, not as a persistent
    setting — the caller passes True (default) to bundle every file
    into ``{slug}.zip`` for a single archival artefact, or False to
    upload each file individually.
    """
    cfg = await load_runtime_config(db)
    if not cfg.api_token:
        raise DepositSkipped("Zenodo API token not configured")
    if website.rendering_mode == RenderingMode.DYNAMIC:
        raise DepositSkipped(
            f"Website '{website.slug}' is DYNAMIC — no static output to deposit."
        )
    if website.build_status != BuildStatus.done:
        raise DepositSkipped(
            f"Website '{website.slug}' has not been built successfully; "
            f"trigger a build before depositing."
        )

    plugin_uuid = await _plugin_id(db)

    if not force and await _website_already_deposited(plugin_uuid, db, website.id):
        raise DepositSkipped(
            f"Website '{website.slug}' already deposited (no force)."
        )

    # Optional source collection — enriches the metadata with the
    # collection's authors and license.
    source_collection: Collection | None = None
    if website.collection_id is not None:
        source_collection = await db.get(Collection, website.collection_id)

    license_obj: License | None = None
    if source_collection is not None:
        license_obj = await _load_license(db, source_collection)
    orcid_map = await _build_orcid_map(db)

    meta = website_to_metadata(
        website=website,
        source_collection=source_collection,
        license_obj=license_obj,
        public_base_url=cfg.public_base_url,
        resource_type=cfg.resource_type,
        access=cfg.access,
        orcid_by_name=orcid_map,
    )
    payload = to_zenodo_payload(meta, community=cfg.default_community or None)

    files = _collect_rendered_files(website.slug)
    if not files:
        raise DepositSkipped(
            f"Website '{website.slug}' rendered tree is empty — nothing to deposit."
        )

    client = zenodo_client or ZenodoClient(
        base_url=cfg.base_url, api_token=cfg.api_token,
    )

    try:
        draft = await client.create_draft(payload)
        if upload_as_zip:
            zip_name, zip_bytes = _bundle_zip(website.slug, files)
            await client.upload_file(draft.id, zip_name, zip_bytes)
        else:
            for filename, content in files:
                # Forge-relative POSIX paths can include sub-directories
                # ("css/theme.css"). Zenodo's filename slot accepts the
                # full path verbatim — InvenioRDM stores it as the key.
                await client.upload_file(draft.id, filename, content)

        if cfg.auto_publish:
            result = await client.publish(draft.id)
        else:
            result = DepositResult(
                id=draft.id,
                doi=None,
                record_url=draft.record_url,
                status="draft",
            )
    except ZenodoError as exc:
        await _record_website_status(
            plugin_uuid=plugin_uuid,
            db=db,
            website_id=website.id,
            data={
                "status": "failed",
                "error": str(exc),
                "http_status": exc.status_code,
                "submitted_at": datetime.now(UTC).isoformat(),
            },
        )
        raise

    await _record_website_status(
        plugin_uuid=plugin_uuid,
        db=db,
        website_id=website.id,
        data={
            "status": result.status,
            "deposit_id": result.id,
            "doi": result.doi,
            "record_url": result.record_url,
            "submitted_at": datetime.now(UTC).isoformat(),
            "uploaded_as_zip": upload_as_zip,
            "file_count": len(files),
            "error": None,
        },
    )
    return result


# ── Hook handler ────────────────────────────────────────────────────────────

async def on_collection_published(collection: Collection, **_: object) -> None:
    """Fire-and-forget: run a deposit in a fresh session, never block publish."""
    from app.db.postgres import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        try:
            result = await deposit_collection(db, collection)
        except DepositSkipped as exc:
            logger.info(
                "zenodo_deposit_skipped",
                collection_id=str(collection.id),
                slug=collection.slug,
                reason=str(exc),
            )
            return
        except ZenodoError as exc:
            logger.warning(
                "zenodo_deposit_failed",
                collection_id=str(collection.id),
                slug=collection.slug,
                error=str(exc),
                status_code=exc.status_code,
            )
            return
        logger.info(
            "zenodo_deposit_recorded",
            collection_id=str(collection.id),
            slug=collection.slug,
            deposit_id=result.id,
            doi=result.doi,
            status=result.status,
        )


__all__ = [
    "DEPOSIT_KEY",
    "PLUGIN_ID",
    "WEBSITE_DEPOSIT_KEY",
    "DepositSkipped",
    "ZenodoRuntimeConfig",
    "deposit_collection",
    "deposit_website",
    "on_collection_published",
]
