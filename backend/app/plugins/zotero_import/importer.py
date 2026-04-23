"""End-to-end import orchestration.

Two entry points:

- :func:`preview` — fetch every item in the configured Zotero library,
  compare their keys against the per-collection "already imported"
  list in ``plugin_data``, and return both sides of the diff plus the
  gross count.
- :func:`commit_import` — given a list of Zotero keys to import, build
  a ``<listBibl>`` merging the freshly imported biblStructs with the
  previous bibliography version, persist a new CollectionBibliography
  row, and add the new keys to ``plugin_data.imported_zotero_keys``.

The diff is keyed on Zotero's opaque item ``key`` (stable per
library) — not on DOI or title — so re-importing the same item
is a no-op even when the editor tweaks the generated biblStruct
in a later manual edit.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import structlog
from defusedxml import ElementTree as DET
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.collection import Collection
from app.models.collection_bibliography import CollectionBibliography
from app.plugins.zotero_import.config import ZoteroRuntimeConfig, load_runtime_config
from app.plugins.zotero_import.mapping import (
    zotero_item_to_biblstruct,
    zotero_item_to_preview,
)
from app.plugins.zotero_import.schemas import (
    ImportPreview,
    ImportResult,
    ZoteroItemPreview,
)
from app.plugins.zotero_import.service import ZoteroClient, ZoteroError
from app.services.plugin_data import PluginDataService

logger = structlog.get_logger()

PLUGIN_ID = "zotero_import"
STATE_KEY = "import"  # entity_type="collection", key="import"


class ImportSkipped(RuntimeError):
    """Raised for well-known pre-conditions (missing config, etc.)."""


# ── plugin_data helpers ────────────────────────────────────────────────────


async def _plugin_uuid(db: AsyncSession) -> uuid.UUID:
    from app.models.plugin import Plugin

    row = await db.scalar(select(Plugin).where(Plugin.name == PLUGIN_ID))
    if row is None:
        raise ImportSkipped(
            f"Plugin registry row '{PLUGIN_ID}' not found — has the loader run?"
        )
    return row.id


async def _get_state(
    db: AsyncSession, plugin_id: uuid.UUID, collection_id: uuid.UUID
) -> dict[str, object]:
    svc = PluginDataService(plugin_id=plugin_id)
    data = await svc.get(
        db, entity_type="collection", key=STATE_KEY, entity_id=collection_id
    )
    return data or {"imported_zotero_keys": [], "count": 0}


async def _set_state(
    db: AsyncSession,
    plugin_id: uuid.UUID,
    collection_id: uuid.UUID,
    data: dict[str, object],
) -> None:
    svc = PluginDataService(plugin_id=plugin_id)
    await svc.set(
        db,
        entity_type="collection",
        key=STATE_KEY,
        data=data,
        entity_id=collection_id,
    )


# ── Preview ────────────────────────────────────────────────────────────────


async def preview(
    db: AsyncSession,
    collection: Collection,
    *,
    zotero_client: ZoteroClient | None = None,
) -> ImportPreview:
    """Fetch the library and split its items into new vs already-imported."""
    cfg = await load_runtime_config(db)
    if not cfg.usable:
        raise ImportSkipped(
            "Zotero plugin is not fully configured (API key and library id required)"
        )

    client = zotero_client or ZoteroClient(
        api_key=cfg.api_key, library_url=cfg.library_url()
    )
    items = await client.fetch_all_items()

    plugin_uuid = await _plugin_uuid(db)
    state = await _get_state(db, plugin_uuid, collection.id)
    imported_keys = {
        k for k in (state.get("imported_zotero_keys") or []) if isinstance(k, str)
    }

    new: list[ZoteroItemPreview] = []
    already: list[ZoteroItemPreview] = []
    for item in items:
        preview_row = zotero_item_to_preview(item.key, item.data)
        (already if item.key in imported_keys else new).append(preview_row)

    return ImportPreview(
        new=new, already_imported=already, total_fetched=len(items)
    )


# ── Commit ─────────────────────────────────────────────────────────────────


async def commit_import(
    db: AsyncSession,
    collection: Collection,
    actor_id: uuid.UUID,
    *,
    keys: list[str] | None = None,
    all_new: bool = False,
    zotero_client: ZoteroClient | None = None,
) -> ImportResult:
    """Persist the requested items as a new CollectionBibliography version.

    Either ``keys`` (an explicit subset) or ``all_new=True`` must be
    supplied. When ``all_new`` wins, ``keys`` is ignored and every
    not-previously-imported Zotero key is pulled in.
    """
    cfg = await load_runtime_config(db)
    if not cfg.usable:
        raise ImportSkipped("Zotero plugin is not fully configured")

    client = zotero_client or ZoteroClient(
        api_key=cfg.api_key, library_url=cfg.library_url()
    )
    items = await client.fetch_all_items()

    plugin_uuid = await _plugin_uuid(db)
    state = await _get_state(db, plugin_uuid, collection.id)
    imported_keys_set = {
        k for k in (state.get("imported_zotero_keys") or []) if isinstance(k, str)
    }

    requested: set[str]
    if all_new:
        requested = {i.key for i in items if i.key not in imported_keys_set}
    else:
        requested = set(keys or [])

    to_import = [i for i in items if i.key in requested and i.key not in imported_keys_set]
    if not to_import:
        # Nothing to do — surface an empty-but-honest result rather than
        # persisting a no-op bibliography version.
        return ImportResult(
            imported=0,
            skipped=len(requested),
            bibliography_version=_current_version(await _max_version(db, collection.id)),
            imported_at=datetime.now(UTC),
        )

    # Build the new <listBibl> by merging the fresh biblStructs with the
    # ones already in the latest version (if any). Parsing errors on the
    # previous content fall back to "start fresh" so a corrupt version
    # never blocks an import.
    new_fragments = [zotero_item_to_biblstruct(i.data) for i in to_import]
    merged_xml = _merge_listbibl(
        await _latest_content(db, collection.id), new_fragments
    )

    next_version = await _next_version(db, collection.id)
    entry = CollectionBibliography(
        collection_id=collection.id,
        version=next_version,
        content=merged_xml,
        created_by_id=actor_id,
    )
    db.add(entry)
    await db.flush()

    # Extend the imported-keys list — deduped + sorted for stable storage.
    new_keys = sorted(imported_keys_set | {i.key for i in to_import})
    await _set_state(
        db,
        plugin_uuid,
        collection.id,
        {
            "imported_zotero_keys": new_keys,
            "count": len(new_keys),
            "last_imported_at": datetime.now(UTC).isoformat(),
        },
    )
    await db.commit()

    return ImportResult(
        imported=len(to_import),
        skipped=len(requested) - len(to_import),
        bibliography_version=next_version,
        imported_at=datetime.now(UTC),
    )


# ── Bibliography version helpers ───────────────────────────────────────────


async def _max_version(db: AsyncSession, collection_id: uuid.UUID) -> int:
    row = await db.execute(
        select(func.coalesce(func.max(CollectionBibliography.version), 0)).where(
            CollectionBibliography.collection_id == collection_id
        )
    )
    return int(row.scalar_one() or 0)


def _current_version(value: int) -> int:
    return value


async def _next_version(db: AsyncSession, collection_id: uuid.UUID) -> int:
    return (await _max_version(db, collection_id)) + 1


async def _latest_content(db: AsyncSession, collection_id: uuid.UUID) -> str:
    """Return the content of the latest bibliography version, or '' when
    none exists yet."""
    row = await db.scalar(
        select(CollectionBibliography)
        .where(CollectionBibliography.collection_id == collection_id)
        .order_by(CollectionBibliography.version.desc())
        .limit(1)
    )
    return row.content if row else ""


def _merge_listbibl(existing: str, new_biblstructs: list[str]) -> str:
    """Merge ``existing`` ``<listBibl>`` content with freshly generated
    ``<biblStruct>`` fragments. Falls back to a fresh ``<listBibl>`` when
    the existing content cannot be parsed."""
    prior_fragments: list[str] = []
    if existing.strip():
        try:
            root = DET.fromstring(existing)
            # The stored content is expected to be a <listBibl> at the top,
            # but admins may have wrapped it in a TEI-style root. Handle both.
            list_bibl = root if _localname(root) == "listBibl" else root.find(".//listBibl")
            if list_bibl is not None:
                for child in list_bibl:
                    if _localname(child) == "biblStruct":
                        import xml.etree.ElementTree as ET
                        ET.indent(child, space="  ")
                        prior_fragments.append(
                            ET.tostring(child, encoding="unicode")
                        )
        except Exception:  # noqa: BLE001 — defensive, see docstring
            prior_fragments = []

    merged = "<listBibl>\n"
    for frag in prior_fragments + new_biblstructs:
        # indent each fragment one level
        for line in frag.strip().splitlines():
            merged += "  " + line + "\n"
    merged += "</listBibl>\n"
    return merged


def _localname(el: object) -> str:
    """Return the tag without namespace prefix (handles Clark notation)."""
    tag = getattr(el, "tag", "")
    if not isinstance(tag, str):
        return ""
    if "}" in tag:
        return tag.rsplit("}", 1)[1]
    return tag


__all__ = [
    "PLUGIN_ID",
    "STATE_KEY",
    "ImportSkipped",
    "commit_import",
    "preview",
]
