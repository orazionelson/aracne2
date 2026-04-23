"""Importer-level tests: preview diff + commit with bibliography append."""

from __future__ import annotations

from typing import Any, cast

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings as app_settings
from app.core.encryption import SENSITIVE_KEYS, encrypt_value
from app.models.collection import Collection, CollectionStatus
from app.models.collection_bibliography import CollectionBibliography
from app.models.plugin import Plugin, PluginStatus
from app.models.system_setting import SystemSetting
from app.plugins.zotero_import.importer import (
    ImportSkipped,
    STATE_KEY,
    commit_import,
    preview,
)
from app.plugins.zotero_import.service import ZoteroClient, ZoteroItem
from app.services.plugin_data import PluginDataService


# ── fixtures ───────────────────────────────────────────────────────────────


def _store(key: str, value: str) -> str:
    if value and key in SENSITIVE_KEYS:
        return encrypt_value(value, app_settings.jwt_secret)
    return value


async def _seed_settings(db: AsyncSession, **overrides: str) -> None:
    defaults: dict[str, tuple[str, str]] = {
        "zotero_api_key": ("ZK-test", "string"),
        "zotero_library_type": ("group", "string"),
        "zotero_library_id": ("12345", "string"),
        "zotero_api_base": ("", "string"),
    }
    for key, (value, type_) in defaults.items():
        raw = overrides.get(key, value)
        db.add(SystemSetting(key=key, value=_store(key, raw), type=type_))
    await db.flush()


@pytest_asyncio.fixture
async def seeded_plugin_row(db_session: AsyncSession) -> Plugin:
    row = Plugin(
        name="zotero_import",
        display_name="Zotero Import",
        version="1.0.0",
        status=PluginStatus.active,
        is_native=False,
    )
    db_session.add(row)
    await db_session.flush()
    return row


@pytest_asyncio.fixture
async def seeded_collection(db_session: AsyncSession) -> Collection:
    col = Collection(
        slug="dante-letters",
        title="Dante's Letters",
        status=CollectionStatus.draft,
    )
    db_session.add(col)
    await db_session.flush()
    return col


class _FakeZoteroClient:
    """Replaces ZoteroClient; returns a canned list of items."""

    def __init__(self, items: list[ZoteroItem]) -> None:
        self._items = list(items)

    async def fetch_all_items(self) -> list[ZoteroItem]:
        return list(self._items)


def _item(key: str, itemType: str = "book", title: str = "x", **extra: Any) -> ZoteroItem:
    data: dict[str, Any] = {"itemType": itemType, "title": title}
    data.update(extra)
    return ZoteroItem(key=key, data=data)


# ── preview ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_preview_skipped_when_config_incomplete(
    db_session: AsyncSession,
    seeded_plugin_row: Plugin,
    seeded_collection: Collection,
) -> None:
    await _seed_settings(db_session, zotero_library_id="")
    with pytest.raises(ImportSkipped):
        await preview(
            db_session,
            seeded_collection,
            zotero_client=cast(ZoteroClient, _FakeZoteroClient([])),
        )


@pytest.mark.asyncio
async def test_preview_splits_new_vs_already_imported(
    db_session: AsyncSession,
    seeded_plugin_row: Plugin,
    seeded_collection: Collection,
) -> None:
    await _seed_settings(db_session)

    # Seed plugin_data with a previous import of AAA + BBB.
    svc = PluginDataService(plugin_id=seeded_plugin_row.id)
    await svc.set(
        db_session,
        entity_type="collection",
        key=STATE_KEY,
        entity_id=seeded_collection.id,
        data={"imported_zotero_keys": ["AAA", "BBB"], "count": 2},
    )
    await db_session.commit()

    fake = _FakeZoteroClient(
        [
            _item("AAA", title="Already A"),
            _item("CCC", title="Fresh C"),
            _item("BBB", title="Already B"),
            _item("DDD", title="Fresh D"),
        ]
    )
    result = await preview(
        db_session, seeded_collection, zotero_client=cast(ZoteroClient, fake)
    )
    assert result.total_fetched == 4
    assert sorted(p.key for p in result.new) == ["CCC", "DDD"]
    assert sorted(p.key for p in result.already_imported) == ["AAA", "BBB"]


# ── commit ─────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_commit_all_new_creates_first_bibliography_version(
    db_session: AsyncSession,
    seeded_admin,  # actor for the created_by_id FK
    seeded_plugin_row: Plugin,
    seeded_collection: Collection,
) -> None:
    await _seed_settings(db_session)
    fake = _FakeZoteroClient(
        [
            _item("K1", "journalArticle", "Paper one", creators=[
                {"creatorType": "author", "firstName": "A", "lastName": "Smith"},
            ], date="1998"),
            _item("K2", "book", "Book two", date="2000"),
        ]
    )
    result = await commit_import(
        db_session,
        seeded_collection,
        seeded_admin.id,
        all_new=True,
        zotero_client=cast(ZoteroClient, fake),
    )
    assert result.imported == 2
    assert result.skipped == 0
    assert result.bibliography_version == 1

    # A CollectionBibliography row exists.
    from sqlalchemy import select
    row = await db_session.scalar(
        select(CollectionBibliography).where(
            CollectionBibliography.collection_id == seeded_collection.id
        )
    )
    assert row is not None
    assert "<biblStruct" in row.content
    assert "Paper one" in row.content
    assert "Book two" in row.content

    # plugin_data state reflects both keys.
    svc = PluginDataService(plugin_id=seeded_plugin_row.id)
    state = await svc.get(
        db_session,
        entity_type="collection",
        key=STATE_KEY,
        entity_id=seeded_collection.id,
    )
    assert state is not None
    assert set(state["imported_zotero_keys"]) == {"K1", "K2"}
    assert state["count"] == 2


@pytest.mark.asyncio
async def test_commit_second_run_appends_only_new_items(
    db_session: AsyncSession,
    seeded_admin,
    seeded_plugin_row: Plugin,
    seeded_collection: Collection,
) -> None:
    """A second import appends fresh biblStructs to the prior version's
    content instead of replacing it."""
    await _seed_settings(db_session)

    # First run: import K1, K2.
    fake_first = _FakeZoteroClient(
        [_item("K1", "book", "First"), _item("K2", "book", "Second")]
    )
    await commit_import(
        db_session, seeded_collection, seeded_admin.id, all_new=True,
        zotero_client=cast(ZoteroClient, fake_first),
    )

    # Second run: library now contains K1+K2 (already imported) plus K3.
    fake_second = _FakeZoteroClient(
        [
            _item("K1", "book", "First"),
            _item("K2", "book", "Second"),
            _item("K3", "book", "Third"),
        ]
    )
    result = await commit_import(
        db_session, seeded_collection, seeded_admin.id, all_new=True,
        zotero_client=cast(ZoteroClient, fake_second),
    )
    assert result.imported == 1   # only K3 is new
    assert result.bibliography_version == 2

    from sqlalchemy import select
    rows = list(await db_session.scalars(
        select(CollectionBibliography).where(
            CollectionBibliography.collection_id == seeded_collection.id
        ).order_by(CollectionBibliography.version)
    ))
    assert [r.version for r in rows] == [1, 2]
    # Second version contains all three titles (K1 + K2 carried forward, plus K3).
    v2 = rows[1].content
    assert "First" in v2
    assert "Second" in v2
    assert "Third" in v2


@pytest.mark.asyncio
async def test_commit_with_explicit_keys_subset(
    db_session: AsyncSession,
    seeded_admin,
    seeded_plugin_row: Plugin,
    seeded_collection: Collection,
) -> None:
    """When ``keys`` is explicit, only the listed Zotero items are imported."""
    await _seed_settings(db_session)
    fake = _FakeZoteroClient(
        [_item("A"), _item("B"), _item("C")]
    )
    result = await commit_import(
        db_session, seeded_collection, seeded_admin.id,
        keys=["A", "C"],
        zotero_client=cast(ZoteroClient, fake),
    )
    assert result.imported == 2
    svc = PluginDataService(plugin_id=seeded_plugin_row.id)
    state = await svc.get(
        db_session, entity_type="collection", key=STATE_KEY,
        entity_id=seeded_collection.id,
    )
    assert state is not None
    assert set(state["imported_zotero_keys"]) == {"A", "C"}


@pytest.mark.asyncio
async def test_commit_noop_when_all_keys_already_imported(
    db_session: AsyncSession,
    seeded_admin,
    seeded_plugin_row: Plugin,
    seeded_collection: Collection,
) -> None:
    """Calling ``all_new=True`` again with no new items must not create a
    new (empty) bibliography version — it returns imported=0 with the
    current version number."""
    await _seed_settings(db_session)
    fake = _FakeZoteroClient([_item("A"), _item("B")])
    await commit_import(
        db_session, seeded_collection, seeded_admin.id, all_new=True,
        zotero_client=cast(ZoteroClient, fake),
    )
    # Re-run: same items, nothing new to import.
    result = await commit_import(
        db_session, seeded_collection, seeded_admin.id, all_new=True,
        zotero_client=cast(ZoteroClient, fake),
    )
    assert result.imported == 0

    from sqlalchemy import select, func
    version_count = await db_session.scalar(
        select(func.count()).select_from(CollectionBibliography).where(
            CollectionBibliography.collection_id == seeded_collection.id
        )
    )
    # Only the first run should have persisted a version.
    assert version_count == 1
