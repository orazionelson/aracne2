"""End-to-end Dataverse deposit orchestration.

Two entry points:

- ``deposit_collection`` for TEI collections (mirror of the Zenodo
  collection flow; sources files from eXist-db).
- ``deposit_website`` for rendered website output (mirror of the
  Zenodo website flow; sources files from disk).

Both share the create-dataset → upload-files → optionally-publish
pattern. Per-collection / per-website plugin_data records under
``deposit`` (collection) and ``website_deposit`` (website) keys
under the ``dataverse_integration`` plugin namespace.

Hook handler: ``on_collection_published`` subscribes to
``ON_COLLECTION_PUBLISHED`` and runs a deposit when ``auto_deposit``
is enabled. Websites are manual-only — same precedent as Zenodo.
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
from app.plugins.dataverse_integration.config import (
    DataverseRuntimeConfig,
    load_runtime_config,
)
from app.plugins.dataverse_integration.mapping import (
    collection_to_metadata,
    to_dataverse_payload,
    website_to_metadata,
)
from app.plugins.dataverse_integration.service import (
    DataverseClient,
    DataverseError,
    DepositResult,
)
from app.services.plugin_data import PluginDataService

logger = structlog.get_logger()

PLUGIN_ID = "dataverse_integration"
DEPOSIT_KEY = "deposit"
WEBSITE_DEPOSIT_KEY = "website_deposit"

_WEBSITE_DEPOSIT_MAX_FILES = 5000
_WEBSITE_DEPOSIT_MAX_BYTES_PER_FILE = 25 * 1024 * 1024  # 25 MB


class DepositSkipped(RuntimeError):
    """Raised when the plugin decides not to deposit. Not an error."""


# ── Shared helpers ─────────────────────────────────────────────────────────


async def _plugin_id(db: AsyncSession) -> uuid.UUID:
    from sqlalchemy import select

    from app.models.plugin import Plugin

    row = await db.scalar(select(Plugin).where(Plugin.name == PLUGIN_ID))
    if row is None:
        raise DepositSkipped(
            f"Plugin registry row '{PLUGIN_ID}' not found — has the loader run?",
        )
    return row.id


async def _load_license(db: AsyncSession, col: Collection) -> License | None:
    if col.license_id is None:
        return None
    return await db.get(License, col.license_id)


async def _build_orcid_map(db: AsyncSession) -> dict[str, str]:
    from sqlalchemy import select

    from app.models.user import User

    rows = list(
        await db.scalars(
            select(User).where(User.orcid.is_not(None)),
        )
    )
    out: dict[str, str] = {}
    for u in rows:
        if u.orcid:
            if u.display_name:
                out[u.display_name] = u.orcid
            out[u.username] = u.orcid
    return out


def _bundle_zip(slug: str, files: list[tuple[str, bytes]]) -> tuple[str, bytes]:
    """Zip *files* in memory and return ``(zip_filename, zip_bytes)``."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, content in files:
            zf.writestr(name, content)
    return f"{slug}.zip", buffer.getvalue()


def _resolve_alias(cfg: DataverseRuntimeConfig, override: str | None) -> str:
    """Pick the effective Dataverse alias for a deposit.

    Per-link override wins over the plugin-global default. Either
    must be non-empty — otherwise the deposit cannot proceed.
    """
    alias = (override or "").strip() or cfg.default_alias.strip()
    if not alias:
        raise DepositSkipped(
            "Dataverse alias not set. Configure a default alias in the "
            "plugin config or pass one as a per-deposit override.",
        )
    return alias


def _resolve_contact(
    cfg: DataverseRuntimeConfig,
) -> tuple[str, str]:
    """Pick the dataset-contact name + email Dataverse requires.

    Falls back to the platform's admin email when the plugin's own
    contact is empty — Dataverse refuses datasets without a contact
    email so the deposit must always carry one.
    """
    name = cfg.contact_name.strip()
    email = cfg.contact_email.strip() or app_settings.admin_email
    if not email:
        raise DepositSkipped(
            "Dataverse requires a contact email; set it in the plugin "
            "config or in the platform's admin_email setting.",
        )
    return name, email


# ── Collection deposit ─────────────────────────────────────────────────────


async def _already_deposited(
    plugin_uuid: uuid.UUID, db: AsyncSession, collection_id: uuid.UUID,
) -> bool:
    svc = PluginDataService(plugin_id=plugin_uuid)
    existing = await svc.get(
        db, entity_type="collection", key=DEPOSIT_KEY,
        entity_id=collection_id,
    )
    if not existing:
        return False
    return existing.get("status") in {"draft", "published"}


async def _record_collection(
    *,
    plugin_uuid: uuid.UUID,
    db: AsyncSession,
    collection_id: uuid.UUID,
    data: dict[str, Any],
) -> None:
    svc = PluginDataService(plugin_id=plugin_uuid)
    await svc.set(
        db, entity_type="collection", key=DEPOSIT_KEY,
        data=data, entity_id=collection_id,
    )
    await db.commit()


async def _load_collection_files(
    existdb: ExistDBClient, slug: str,
) -> list[tuple[str, bytes]]:
    names = await existdb.list_collection(slug)
    files: list[tuple[str, bytes]] = []
    for name in names:
        try:
            content = await existdb.get_document(slug, name)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "dataverse_file_fetch_failed",
                filename=name, error=str(exc),
            )
            continue
        files.append((name, content))
    return files


async def deposit_collection(
    db: AsyncSession,
    collection: Collection,
    *,
    alias_override: str | None = None,
    existdb: ExistDBClient | None = None,
    dataverse_client: DataverseClient | None = None,
    force: bool = False,
) -> DepositResult:
    """Deposit *collection*'s TEI files on the configured Dataverse.

    ``alias_override`` lets the caller route this single deposit to a
    Dataverse other than the plugin's default — useful when one
    institutional installation hosts multiple research-group
    Dataverses.
    """
    cfg = await load_runtime_config(db)
    if not cfg.api_token:
        raise DepositSkipped("Dataverse API token not configured")

    plugin_uuid = await _plugin_id(db)

    if not force and await _already_deposited(plugin_uuid, db, collection.id):
        raise DepositSkipped(
            f"Collection {collection.slug} already deposited (no force)",
        )

    alias = _resolve_alias(cfg, alias_override)
    contact_name, contact_email = _resolve_contact(cfg)

    license_obj = await _load_license(db, collection)
    orcid_map = await _build_orcid_map(db)
    meta = collection_to_metadata(
        collection=collection,
        license_obj=license_obj,
        public_base_url=cfg.public_base_url or None,
        # Resource type is meaningless for Dataverse (it has its own
        # subject vocabulary instead) but we need to pass *something*
        # to the shared collection-to-metadata extractor.
        resource_type="publication-other",
        access="open",
        orcid_by_name=orcid_map,
    )
    payload = to_dataverse_payload(
        meta,
        subject=cfg.default_subject,
        contact_name=contact_name,
        contact_email=contact_email,
    )

    files = await _load_collection_files(
        existdb or existdb_client, collection.slug,
    )

    client = dataverse_client or DataverseClient(
        base_url=cfg.base_url, api_token=cfg.api_token,
    )
    submitted_at = datetime.now(UTC).isoformat()

    try:
        draft = await client.create_dataset(alias, payload)
        for filename, content in files:
            await client.upload_file(
                draft.persistent_id, filename, content,
            )
        if cfg.auto_publish:
            result = await client.publish(
                draft.persistent_id, publish_type=cfg.publish_type,
            )
        else:
            from app.plugins.dataverse_integration.service import (
                _extract_bare_doi,
            )
            result = DepositResult(
                persistent_id=draft.persistent_id,
                doi=_extract_bare_doi(draft.persistent_id) or "",
                landing_url=draft.landing_url,
                status="draft",
            )
    except DataverseError as exc:
        await _record_collection(
            plugin_uuid=plugin_uuid, db=db,
            collection_id=collection.id,
            data={
                "status": "failed",
                "error": str(exc),
                "http_status": exc.status_code,
                "submitted_at": submitted_at,
                "alias": alias,
            },
        )
        raise

    await _record_collection(
        plugin_uuid=plugin_uuid, db=db,
        collection_id=collection.id,
        data={
            "status": result.status,
            "persistent_id": result.persistent_id,
            "doi": result.doi or None,
            "landing_url": result.landing_url,
            "alias": alias,
            "submitted_at": submitted_at,
            "error": None,
        },
    )
    return result


# ── Website deposit ────────────────────────────────────────────────────────


def _collect_rendered_files(slug: str) -> list[tuple[str, bytes]]:
    """Walk ``settings.websites_root / slug`` and return file tuples.

    Skips dotfiles; caps total count and per-file size identically to
    the Zenodo / git-forge website helpers.
    """
    root = Path(app_settings.websites_root) / slug
    if not root.is_dir():
        raise DepositSkipped(
            f"Website '{slug}' has no rendered output on disk "
            f"({root}). Trigger a build first.",
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
                f"{_WEBSITE_DEPOSIT_MAX_BYTES_PER_FILE} byte cap.",
            )
        files.append((rel.as_posix(), path.read_bytes()))
        if len(files) > _WEBSITE_DEPOSIT_MAX_FILES:
            raise DepositSkipped(
                f"Rendered site exceeds the {_WEBSITE_DEPOSIT_MAX_FILES} "
                f"file cap.",
            )
    return files


async def _website_already_deposited(
    plugin_uuid: uuid.UUID, db: AsyncSession, website_id: uuid.UUID,
) -> bool:
    svc = PluginDataService(plugin_id=plugin_uuid)
    existing = await svc.get(
        db, entity_type="website", key=WEBSITE_DEPOSIT_KEY,
        entity_id=website_id,
    )
    if not existing:
        return False
    return existing.get("status") in {"draft", "published"}


async def _record_website(
    *,
    plugin_uuid: uuid.UUID,
    db: AsyncSession,
    website_id: uuid.UUID,
    data: dict[str, Any],
) -> None:
    svc = PluginDataService(plugin_id=plugin_uuid)
    await svc.set(
        db, entity_type="website", key=WEBSITE_DEPOSIT_KEY,
        data=data, entity_id=website_id,
    )
    await db.commit()


async def deposit_website(
    db: AsyncSession,
    website: Website,
    *,
    upload_as_zip: bool = True,
    alias_override: str | None = None,
    force: bool = False,
    dataverse_client: DataverseClient | None = None,
) -> DepositResult:
    """Deposit a *website*'s rendered output on the configured Dataverse.

    Refuses DYNAMIC mode (no static output) and unbuilt websites — same
    semantics as Zenodo's website-deposit feature.
    """
    cfg = await load_runtime_config(db)
    if not cfg.api_token:
        raise DepositSkipped("Dataverse API token not configured")
    if website.rendering_mode == RenderingMode.DYNAMIC:
        raise DepositSkipped(
            f"Website '{website.slug}' is DYNAMIC — no static output to deposit.",
        )
    if website.build_status != BuildStatus.done:
        raise DepositSkipped(
            f"Website '{website.slug}' has not been built successfully.",
        )

    plugin_uuid = await _plugin_id(db)

    if not force and await _website_already_deposited(plugin_uuid, db, website.id):
        raise DepositSkipped(
            f"Website '{website.slug}' already deposited (no force).",
        )

    alias = _resolve_alias(cfg, alias_override)
    contact_name, contact_email = _resolve_contact(cfg)

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
        public_base_url=cfg.public_base_url or None,
        resource_type="publication-other",  # ignored by Dataverse mapper
        access="open",
        orcid_by_name=orcid_map,
    )
    payload = to_dataverse_payload(
        meta,
        subject=cfg.default_subject,
        contact_name=contact_name,
        contact_email=contact_email,
    )

    files = _collect_rendered_files(website.slug)
    if not files:
        raise DepositSkipped("Rendered site tree is empty.")

    client = dataverse_client or DataverseClient(
        base_url=cfg.base_url, api_token=cfg.api_token,
    )
    submitted_at = datetime.now(UTC).isoformat()

    try:
        draft = await client.create_dataset(alias, payload)
        if upload_as_zip:
            zip_name, zip_bytes = _bundle_zip(website.slug, files)
            await client.upload_file(
                draft.persistent_id, zip_name, zip_bytes,
            )
        else:
            for path, content in files:
                # Split nested paths into ``directoryLabel`` (folders shown
                # in the Dataverse Files tab) + filename — Dataverse
                # rejects "/" in the file name slot.
                parts = path.rsplit("/", 1)
                if len(parts) == 2:
                    directory, filename = parts
                else:
                    directory, filename = "", parts[0]
                await client.upload_file(
                    draft.persistent_id, filename, content,
                    directory_label=directory or None,
                )
        if cfg.auto_publish:
            result = await client.publish(
                draft.persistent_id, publish_type=cfg.publish_type,
            )
        else:
            from app.plugins.dataverse_integration.service import (
                _extract_bare_doi,
            )
            result = DepositResult(
                persistent_id=draft.persistent_id,
                doi=_extract_bare_doi(draft.persistent_id) or "",
                landing_url=draft.landing_url,
                status="draft",
            )
    except DataverseError as exc:
        await _record_website(
            plugin_uuid=plugin_uuid, db=db, website_id=website.id,
            data={
                "status": "failed",
                "error": str(exc),
                "http_status": exc.status_code,
                "submitted_at": submitted_at,
                "alias": alias,
            },
        )
        raise

    await _record_website(
        plugin_uuid=plugin_uuid, db=db, website_id=website.id,
        data={
            "status": result.status,
            "persistent_id": result.persistent_id,
            "doi": result.doi or None,
            "landing_url": result.landing_url,
            "alias": alias,
            "uploaded_as_zip": upload_as_zip,
            "file_count": len(files),
            "submitted_at": submitted_at,
            "error": None,
        },
    )
    return result


# ── Hook handler ───────────────────────────────────────────────────────────


async def on_collection_published(collection: Collection, **_: object) -> None:
    """Fire-and-forget deposit when ``auto_deposit`` is on."""
    from app.db.postgres import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        cfg = await load_runtime_config(db)
        if not cfg.auto_deposit:
            logger.info(
                "dataverse_deposit_skipped",
                collection_id=str(collection.id),
                slug=collection.slug,
                reason="auto_deposit is off",
            )
            return
        try:
            result = await deposit_collection(db, collection)
        except DepositSkipped as exc:
            logger.info(
                "dataverse_deposit_skipped",
                collection_id=str(collection.id),
                slug=collection.slug,
                reason=str(exc),
            )
            return
        except DataverseError as exc:
            logger.warning(
                "dataverse_deposit_failed",
                collection_id=str(collection.id),
                slug=collection.slug,
                error=str(exc),
                status_code=exc.status_code,
            )
            return
        logger.info(
            "dataverse_deposit_recorded",
            collection_id=str(collection.id),
            slug=collection.slug,
            persistent_id=result.persistent_id,
            doi=result.doi,
            status=result.status,
        )


__all__ = [
    "DEPOSIT_KEY",
    "PLUGIN_ID",
    "WEBSITE_DEPOSIT_KEY",
    "DepositSkipped",
    "deposit_collection",
    "deposit_website",
    "on_collection_published",
]
