"""Integration test for the deposit orchestration.

Uses the conftest test engine (SQLite in-memory) so the Collection,
License, Plugin and PluginData tables behave exactly as in production.
eXist-db and the Zenodo HTTP service are both faked — no network.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings as app_settings
from app.core.encryption import SENSITIVE_KEYS, encrypt_value
from app.db.existdb import ExistDBClient
from app.models.collection import Collection, CollectionStatus
from app.models.license import License
from app.models.plugin import Plugin, PluginStatus
from app.models.system_setting import SystemSetting
from app.plugins.zenodo_deposit.deposit import (
    DEPOSIT_KEY,
    DepositSkipped,
    deposit_collection,
)
from app.plugins.zenodo_deposit.service import DepositDraft, DepositResult, ZenodoError
from app.services.plugin_data import PluginDataService


# ── Fixtures ────────────────────────────────────────────────────────────────


def _store_value(key: str, value: str) -> str:
    """Mirror the production settings service: encrypt sensitive keys at rest."""
    if value and key in SENSITIVE_KEYS:
        return encrypt_value(value, app_settings.jwt_secret)
    return value


async def _seed_settings(db: AsyncSession, **overrides: str) -> None:
    """Seed the settings migration 0047 adds, with test-friendly defaults."""
    defaults: dict[str, tuple[str, str]] = {
        "zenodo_api_token": ("token-123", "string"),
        "zenodo_base_url": ("https://sandbox.zenodo.org", "string"),
        "zenodo_default_community": ("", "string"),
        "zenodo_auto_publish": ("false", "bool"),
        "zenodo_access_right": ("open", "string"),
        "zenodo_publication_type": ("other", "string"),
        "public_base_url": ("https://edition.example.org", "string"),
    }
    for key, (value, type_) in defaults.items():
        raw_value = overrides.get(key, value)
        db.add(SystemSetting(key=key, value=_store_value(key, raw_value), type=type_))
    await db.flush()


@pytest_asyncio.fixture
async def seeded_plugin_row(db_session: AsyncSession) -> Plugin:
    row = Plugin(
        name="zenodo_deposit",
        display_name="Zenodo Deposit",
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
        slug="divina-commedia",
        title="Divina Commedia",
        description="Testo critico.",
        author="Dante Alighieri",
        publisher="Editore X",
        status=CollectionStatus.published,
    )
    db_session.add(col)
    await db_session.flush()
    return col


def _fake_existdb(files: list[tuple[str, bytes]]) -> ExistDBClient:
    """Async mock with list_collection + get_document behaviour pinned to *files*."""
    mock = AsyncMock(spec=ExistDBClient)
    mock.list_collection = AsyncMock(return_value=[f for f, _ in files])
    body_map = dict(files)
    mock.get_document = AsyncMock(side_effect=lambda slug, name: body_map[name])
    return mock


class _FakeZenodo:
    """Hand-rolled fake with the same public surface as ZenodoClient.

    We avoid Mock here because we care about the call sequence: create →
    upload (per file) → update_metadata → [publish].
    """

    def __init__(
        self,
        *,
        draft_id: int = 42,
        doi: str | None = "10.5281/zenodo.42",
        fail_after: str | None = None,
    ) -> None:
        self.draft_id = draft_id
        self.doi = doi
        self.fail_after = fail_after
        self.calls: list[tuple[str, Any]] = []

    async def create_draft(self) -> DepositDraft:
        self.calls.append(("create_draft", None))
        if self.fail_after == "create":
            raise ZenodoError("boom", status_code=500)
        return DepositDraft(
            id=self.draft_id,
            bucket_url=f"https://example.test/bucket/{self.draft_id}",
            record_url=f"https://sandbox.zenodo.org/deposit/{self.draft_id}",
        )

    async def upload_file(self, bucket_url: str, filename: str, content: bytes) -> None:
        self.calls.append(("upload_file", filename))
        if self.fail_after == "upload":
            raise ZenodoError("bucket full", status_code=507)

    async def update_metadata(self, deposit_id: int, payload: dict[str, Any]) -> None:
        self.calls.append(("update_metadata", deposit_id))
        if self.fail_after == "metadata":
            raise ZenodoError("bad metadata", status_code=400)

    async def publish(self, deposit_id: int) -> DepositResult:
        self.calls.append(("publish", deposit_id))
        return DepositResult(
            id=deposit_id,
            doi=self.doi,
            record_url=f"https://sandbox.zenodo.org/records/{deposit_id}",
            status="published",
        )


# ── Tests ───────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_deposit_skipped_when_token_missing(
    db_session: AsyncSession,
    seeded_plugin_row: Plugin,
    seeded_collection: Collection,
) -> None:
    await _seed_settings(db_session, zenodo_api_token="")
    with pytest.raises(DepositSkipped):
        await deposit_collection(
            db_session,
            seeded_collection,
            existdb=_fake_existdb([("a.xml", b"<x/>")]),
            zenodo_client=_FakeZenodo(),  # type: ignore[arg-type]
        )


@pytest.mark.asyncio
async def test_deposit_skipped_when_already_published(
    db_session: AsyncSession,
    seeded_plugin_row: Plugin,
    seeded_collection: Collection,
) -> None:
    await _seed_settings(db_session)

    # Pretend we have already deposited this collection successfully.
    svc = PluginDataService(plugin_id=seeded_plugin_row.id)
    await svc.set(
        db_session,
        entity_type="collection",
        key=DEPOSIT_KEY,
        entity_id=seeded_collection.id,
        data={"status": "published", "deposit_id": 1, "doi": "10.5281/zenodo.1"},
    )
    await db_session.commit()

    with pytest.raises(DepositSkipped):
        await deposit_collection(
            db_session,
            seeded_collection,
            existdb=_fake_existdb([("a.xml", b"<x/>")]),
            zenodo_client=_FakeZenodo(),  # type: ignore[arg-type]
        )


@pytest.mark.asyncio
async def test_deposit_records_draft_when_auto_publish_disabled(
    db_session: AsyncSession,
    seeded_plugin_row: Plugin,
    seeded_collection: Collection,
) -> None:
    await _seed_settings(db_session, zenodo_auto_publish="false")
    fake = _FakeZenodo()
    result = await deposit_collection(
        db_session,
        seeded_collection,
        existdb=_fake_existdb([("a.xml", b"<a/>"), ("b.xml", b"<b/>")]),
        zenodo_client=fake,  # type: ignore[arg-type]
    )
    assert result.status == "draft"
    assert result.doi is None
    # Expected call sequence: create → upload(a) → upload(b) → update_metadata.
    names = [c[0] for c in fake.calls]
    assert names == ["create_draft", "upload_file", "upload_file", "update_metadata"]

    svc = PluginDataService(plugin_id=seeded_plugin_row.id)
    stored = await svc.get(
        db_session, entity_type="collection", key=DEPOSIT_KEY, entity_id=seeded_collection.id
    )
    assert stored is not None
    assert stored["status"] == "draft"
    assert stored["deposit_id"] == fake.draft_id


@pytest.mark.asyncio
async def test_deposit_publishes_when_auto_publish_enabled(
    db_session: AsyncSession,
    seeded_plugin_row: Plugin,
    seeded_collection: Collection,
) -> None:
    await _seed_settings(db_session, zenodo_auto_publish="true")
    fake = _FakeZenodo(doi="10.5281/zenodo.99", draft_id=99)
    result = await deposit_collection(
        db_session,
        seeded_collection,
        existdb=_fake_existdb([("a.xml", b"<a/>")]),
        zenodo_client=fake,  # type: ignore[arg-type]
    )
    assert result.status == "published"
    assert result.doi == "10.5281/zenodo.99"
    assert any(c[0] == "publish" for c in fake.calls)


@pytest.mark.asyncio
async def test_deposit_writes_failed_status_when_zenodo_errors(
    db_session: AsyncSession,
    seeded_plugin_row: Plugin,
    seeded_collection: Collection,
) -> None:
    await _seed_settings(db_session)
    fake = _FakeZenodo(fail_after="metadata")
    with pytest.raises(ZenodoError):
        await deposit_collection(
            db_session,
            seeded_collection,
            existdb=_fake_existdb([("a.xml", b"<a/>")]),
            zenodo_client=fake,  # type: ignore[arg-type]
        )
    svc = PluginDataService(plugin_id=seeded_plugin_row.id)
    stored = await svc.get(
        db_session,
        entity_type="collection",
        key=DEPOSIT_KEY,
        entity_id=seeded_collection.id,
    )
    assert stored is not None
    assert stored["status"] == "failed"
    assert "bad metadata" in (stored.get("error") or "")


@pytest.mark.asyncio
async def test_deposit_force_overrides_already_deposited_guard(
    db_session: AsyncSession,
    seeded_plugin_row: Plugin,
    seeded_collection: Collection,
) -> None:
    await _seed_settings(db_session, zenodo_auto_publish="true")
    # Seed a previous successful deposit.
    svc = PluginDataService(plugin_id=seeded_plugin_row.id)
    await svc.set(
        db_session,
        entity_type="collection",
        key=DEPOSIT_KEY,
        entity_id=seeded_collection.id,
        data={"status": "published", "deposit_id": 1, "doi": "10.5281/zenodo.1"},
    )
    await db_session.commit()

    fake = _FakeZenodo(draft_id=7, doi="10.5281/zenodo.7")
    result = await deposit_collection(
        db_session,
        seeded_collection,
        existdb=_fake_existdb([("a.xml", b"<a/>")]),
        zenodo_client=fake,  # type: ignore[arg-type]
        force=True,
    )
    assert result.doi == "10.5281/zenodo.7"
    stored = await svc.get(
        db_session,
        entity_type="collection",
        key=DEPOSIT_KEY,
        entity_id=seeded_collection.id,
    )
    assert stored is not None
    assert stored["deposit_id"] == 7


@pytest.mark.asyncio
async def test_license_slug_ends_up_in_zenodo_payload(
    db_session: AsyncSession,
    seeded_plugin_row: Plugin,
) -> None:
    """Integration check: a Collection linked to a CC-BY license yields
    'cc-by-4.0' in the payload sent to Zenodo (via update_metadata)."""
    await _seed_settings(db_session)
    lic = License(
        name="CC-BY 4.0",
        target="https://creativecommons.org/licenses/by/4.0/",
        is_active=True,
    )
    db_session.add(lic)
    await db_session.flush()

    col = Collection(
        slug="licensed",
        title="Licensed Edition",
        license_id=lic.id,
        author="Test Author",
        status=CollectionStatus.published,
    )
    db_session.add(col)
    await db_session.flush()

    captured_payload: dict[str, Any] = {}

    class _CapturingFake(_FakeZenodo):
        async def update_metadata(self, deposit_id: int, payload: dict[str, Any]) -> None:
            captured_payload.update(payload)
            await super().update_metadata(deposit_id, payload)

    await deposit_collection(
        db_session,
        col,
        existdb=_fake_existdb([("doc.xml", b"<tei/>")]),
        zenodo_client=_CapturingFake(),  # type: ignore[arg-type]
    )
    assert captured_payload["metadata"]["license"] == "cc-by-4.0"
