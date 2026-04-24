"""Integration test for the Dataverse deposit orchestration.

Uses the SQLite in-memory test engine; the Dataverse HTTP client and
the eXist client are both faked. Asserts the full create → upload →
record flow plus all the precondition guards.
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
from app.models.plugin import Plugin, PluginStatus
from app.models.system_setting import SystemSetting
from app.plugins.dataverse_integration.deposit import (
    DEPOSIT_KEY,
    DepositSkipped,
    deposit_collection,
)
from app.plugins.dataverse_integration.service import (
    DatasetDraft,
    DataverseError,
    DepositResult,
)
from app.services.plugin_data import PluginDataService


def _store(key: str, value: str) -> str:
    if value and key in SENSITIVE_KEYS:
        return encrypt_value(value, app_settings.jwt_secret)
    return value


async def _seed_settings(db: AsyncSession, **overrides: str) -> None:
    defaults: dict[str, tuple[str, str]] = {
        "dataverse_api_token": ("token-dv", "string"),
        "dataverse_base_url": ("https://demo.dataverse.org", "string"),
        "dataverse_default_alias": ("tei-editions", "string"),
        "dataverse_auto_deposit": ("false", "bool"),
        "dataverse_auto_publish": ("false", "bool"),
        "dataverse_default_subject": ("Arts and Humanities", "string"),
        "dataverse_contact_name": ("Plat Form", "string"),
        "dataverse_contact_email": ("curator@example.org", "string"),
        "dataverse_publish_type": ("major", "string"),
        "public_base_url": ("https://edition.example.org", "string"),
    }
    for key, (value, type_) in defaults.items():
        raw = overrides.get(key, value)
        db.add(SystemSetting(key=key, value=_store(key, raw), type=type_))
    await db.flush()


@pytest_asyncio.fixture
async def seeded_plugin_row(db_session: AsyncSession) -> Plugin:
    row = Plugin(
        name="dataverse_integration",
        display_name="Dataverse Integration",
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
        author="Dante Alighieri",
        publisher="Editor X",
        status=CollectionStatus.published,
    )
    db_session.add(col)
    await db_session.flush()
    return col


def _fake_existdb(files: list[tuple[str, bytes]]) -> ExistDBClient:
    mock = AsyncMock(spec=ExistDBClient)
    mock.list_collection = AsyncMock(return_value=[f for f, _ in files])
    body_map = dict(files)
    mock.get_document = AsyncMock(side_effect=lambda slug, name: body_map[name])
    return mock


class _FakeDataverse:
    """Fake DataverseClient that records calls without hitting the wire."""

    def __init__(
        self,
        *,
        persistent_id: str = "doi:10.5072/FK2/AB12CD",
        fail_on: str | None = None,
    ) -> None:
        self.persistent_id = persistent_id
        self.fail_on = fail_on
        self.calls: list[tuple[str, Any]] = []

    async def create_dataset(self, alias: str, payload: dict[str, Any]) -> DatasetDraft:
        self.calls.append(("create_dataset", {"alias": alias, "payload": payload}))
        if self.fail_on == "create":
            raise DataverseError("nope", status_code=502)
        return DatasetDraft(
            persistent_id=self.persistent_id,
            database_id=42,
            landing_url=f"https://demo.dataverse.org/dataset.xhtml?persistentId={self.persistent_id}",
        )

    async def upload_file(
        self,
        persistent_id: str,
        filename: str,
        content: bytes,
        *,
        directory_label: str | None = None,
        description: str | None = None,
    ) -> None:
        self.calls.append(("upload_file", {
            "filename": filename,
            "size": len(content),
            "directory_label": directory_label,
        }))
        if self.fail_on == "upload":
            raise DataverseError("bucket full", status_code=507)

    async def publish(
        self, persistent_id: str, *, publish_type: str = "major",
    ) -> DepositResult:
        self.calls.append(("publish", {
            "persistent_id": persistent_id, "publish_type": publish_type,
        }))
        return DepositResult(
            persistent_id=persistent_id,
            doi=persistent_id.removeprefix("doi:"),
            landing_url=f"https://demo.dataverse.org/dataset.xhtml?persistentId={persistent_id}",
            status="published",
        )


# ── Tests ──────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_skips_when_token_missing(
    db_session: AsyncSession,
    seeded_plugin_row: Plugin,
    seeded_collection: Collection,
) -> None:
    await _seed_settings(db_session, dataverse_api_token="")
    with pytest.raises(DepositSkipped, match="API token"):
        await deposit_collection(
            db_session, seeded_collection,
            existdb=_fake_existdb([]), dataverse_client=_FakeDataverse(),
        )


@pytest.mark.asyncio
async def test_skips_when_alias_missing(
    db_session: AsyncSession,
    seeded_plugin_row: Plugin,
    seeded_collection: Collection,
) -> None:
    await _seed_settings(db_session, dataverse_default_alias="")
    with pytest.raises(DepositSkipped, match="alias"):
        await deposit_collection(
            db_session, seeded_collection,
            existdb=_fake_existdb([]), dataverse_client=_FakeDataverse(),
        )


@pytest.mark.asyncio
async def test_alias_override_wins_over_default(
    db_session: AsyncSession,
    seeded_plugin_row: Plugin,
    seeded_collection: Collection,
) -> None:
    await _seed_settings(db_session, dataverse_default_alias="default-dv")
    fake = _FakeDataverse()
    await deposit_collection(
        db_session, seeded_collection,
        alias_override="override-dv",
        existdb=_fake_existdb([("doc.xml", b"<a/>")]),
        dataverse_client=fake,
    )
    create_call = next(c for c in fake.calls if c[0] == "create_dataset")
    assert create_call[1]["alias"] == "override-dv"


@pytest.mark.asyncio
async def test_records_draft_when_auto_publish_off(
    db_session: AsyncSession,
    seeded_plugin_row: Plugin,
    seeded_collection: Collection,
) -> None:
    await _seed_settings(db_session)
    fake = _FakeDataverse(persistent_id="doi:10.5072/FK2/XYZ")
    result = await deposit_collection(
        db_session, seeded_collection,
        existdb=_fake_existdb([("a.xml", b"<a/>"), ("b.xml", b"<b/>")]),
        dataverse_client=fake,
    )
    # auto_publish=false → status=draft, no publish call.
    assert result.status == "draft"
    assert result.doi == "10.5072/FK2/XYZ"
    assert not any(c[0] == "publish" for c in fake.calls)
    # Persisted record carries the DOI even for the draft.
    svc = PluginDataService(plugin_id=seeded_plugin_row.id)
    record = await svc.get(
        db_session, entity_type="collection",
        key=DEPOSIT_KEY, entity_id=seeded_collection.id,
    )
    assert record is not None
    assert record["status"] == "draft"
    assert record["doi"] == "10.5072/FK2/XYZ"
    assert record["alias"] == "tei-editions"


@pytest.mark.asyncio
async def test_publishes_when_auto_publish_on(
    db_session: AsyncSession,
    seeded_plugin_row: Plugin,
    seeded_collection: Collection,
) -> None:
    await _seed_settings(db_session, dataverse_auto_publish="true")
    fake = _FakeDataverse()
    result = await deposit_collection(
        db_session, seeded_collection,
        existdb=_fake_existdb([("a.xml", b"<a/>")]),
        dataverse_client=fake,
    )
    assert result.status == "published"
    publish_call = next(c for c in fake.calls if c[0] == "publish")
    assert publish_call[1]["publish_type"] == "major"


@pytest.mark.asyncio
async def test_records_failed_when_create_dataset_errors(
    db_session: AsyncSession,
    seeded_plugin_row: Plugin,
    seeded_collection: Collection,
) -> None:
    await _seed_settings(db_session)
    fake = _FakeDataverse(fail_on="create")
    with pytest.raises(DataverseError):
        await deposit_collection(
            db_session, seeded_collection,
            existdb=_fake_existdb([]), dataverse_client=fake,
        )
    svc = PluginDataService(plugin_id=seeded_plugin_row.id)
    record = await svc.get(
        db_session, entity_type="collection",
        key=DEPOSIT_KEY, entity_id=seeded_collection.id,
    )
    assert record is not None
    assert record["status"] == "failed"
    assert record["http_status"] == 502


@pytest.mark.asyncio
async def test_skips_when_already_deposited_unless_force(
    db_session: AsyncSession,
    seeded_plugin_row: Plugin,
    seeded_collection: Collection,
) -> None:
    await _seed_settings(db_session)
    # First deposit succeeds.
    await deposit_collection(
        db_session, seeded_collection,
        existdb=_fake_existdb([]), dataverse_client=_FakeDataverse(),
    )
    # Second without force is refused.
    with pytest.raises(DepositSkipped):
        await deposit_collection(
            db_session, seeded_collection,
            existdb=_fake_existdb([]), dataverse_client=_FakeDataverse(),
        )
    # With force, it goes through.
    await deposit_collection(
        db_session, seeded_collection,
        existdb=_fake_existdb([]),
        dataverse_client=_FakeDataverse(persistent_id="doi:10.5072/FK2/NEW"),
        force=True,
    )


@pytest.mark.asyncio
async def test_contact_email_falls_back_to_admin_email(
    db_session: AsyncSession,
    seeded_plugin_row: Plugin,
    seeded_collection: Collection,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When the plugin's own contact_email is empty, the deposit should
    fall back to the platform's admin_email rather than refusing."""
    monkeypatch.setattr(app_settings, "admin_email", "fallback@example.org")
    await _seed_settings(db_session, dataverse_contact_email="")
    fake = _FakeDataverse()
    await deposit_collection(
        db_session, seeded_collection,
        existdb=_fake_existdb([("a.xml", b"<a/>")]),
        dataverse_client=fake,
    )
    create_call = next(c for c in fake.calls if c[0] == "create_dataset")
    payload = create_call[1]["payload"]
    contact_field = next(
        f for f in payload["datasetVersion"]["metadataBlocks"]["citation"]["fields"]
        if f["typeName"] == "datasetContact"
    )
    assert (
        contact_field["value"][0]["datasetContactEmail"]["value"]
        == "fallback@example.org"
    )
