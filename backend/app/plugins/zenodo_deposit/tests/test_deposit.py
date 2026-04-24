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
from app.plugins.zenodo_deposit.service import DepositDraft, DepositResult, ZenodoError  # noqa: F401
from app.services.plugin_data import PluginDataService


# ── Fixtures ────────────────────────────────────────────────────────────────


def _store_value(key: str, value: str) -> str:
    if value and key in SENSITIVE_KEYS:
        return encrypt_value(value, app_settings.jwt_secret)
    return value


async def _seed_settings(db: AsyncSession, **overrides: str) -> None:
    """Seed the settings migration 0047/0048 add, with test defaults."""
    defaults: dict[str, tuple[str, str]] = {
        "zenodo_api_token": ("token-123", "string"),
        "zenodo_base_url": ("https://sandbox.zenodo.org", "string"),
        "zenodo_default_community": ("", "string"),
        "zenodo_auto_publish": ("false", "bool"),
        "zenodo_access": ("open", "string"),
        "zenodo_resource_type": ("publication-other", "string"),
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
        version="1.1.0",
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
    mock = AsyncMock(spec=ExistDBClient)
    mock.list_collection = AsyncMock(return_value=[f for f, _ in files])
    body_map = dict(files)
    mock.get_document = AsyncMock(side_effect=lambda slug, name: body_map[name])
    return mock


class _FakeZenodo:
    """Hand-rolled fake with the new ZenodoClient surface.

    Mirrors the three operations the deposit orchestration uses:
    ``create_draft(payload)``, ``upload_file(draft_id, filename, bytes)``,
    and ``publish(draft_id)``. The call log records both the method
    name and the significant argument so tests can assert ordering.
    """

    def __init__(
        self,
        *,
        draft_id: str = "abc12-xy345",
        doi: str | None = "10.5281/zenodo.42",
        fail_after: str | None = None,
    ) -> None:
        self.draft_id = draft_id
        self.doi = doi
        self.fail_after = fail_after
        self.calls: list[tuple[str, Any]] = []
        self.last_payload: dict[str, Any] | None = None

    async def create_draft(self, payload: dict[str, Any]) -> DepositDraft:
        self.calls.append(("create_draft", payload))
        self.last_payload = payload
        if self.fail_after == "create":
            raise ZenodoError("boom", status_code=500)
        return DepositDraft(
            id=self.draft_id,
            record_url=f"https://sandbox.zenodo.org/uploads/{self.draft_id}",
        )

    async def upload_file(self, draft_id: str, filename: str, content: bytes) -> None:
        self.calls.append(("upload_file", filename))
        if self.fail_after == "upload":
            raise ZenodoError("bucket full", status_code=507)

    async def publish(self, deposit_id: str) -> DepositResult:
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
    svc = PluginDataService(plugin_id=seeded_plugin_row.id)
    await svc.set(
        db_session,
        entity_type="collection",
        key=DEPOSIT_KEY,
        entity_id=seeded_collection.id,
        data={"status": "published", "deposit_id": "abc", "doi": "10.5281/zenodo.1"},
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
    # Expected sequence: create_draft → upload(a) → upload(b). No publish.
    names = [c[0] for c in fake.calls]
    assert names == ["create_draft", "upload_file", "upload_file"]

    # The create_draft payload should be the InvenioRDM record shape.
    assert fake.last_payload is not None
    assert set(fake.last_payload.keys()) == {"access", "files", "metadata"}
    md = fake.last_payload["metadata"]
    assert md["title"] == "Divina Commedia"
    assert md["resource_type"] == {"id": "publication-other"}

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
    fake = _FakeZenodo(doi="10.5281/zenodo.99", draft_id="xyz-99")
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
    fake = _FakeZenodo(fail_after="upload")
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
    assert "bucket full" in (stored.get("error") or "")


@pytest.mark.asyncio
async def test_deposit_force_overrides_already_deposited_guard(
    db_session: AsyncSession,
    seeded_plugin_row: Plugin,
    seeded_collection: Collection,
) -> None:
    await _seed_settings(db_session, zenodo_auto_publish="true")
    svc = PluginDataService(plugin_id=seeded_plugin_row.id)
    await svc.set(
        db_session,
        entity_type="collection",
        key=DEPOSIT_KEY,
        entity_id=seeded_collection.id,
        data={"status": "published", "deposit_id": "old", "doi": "10.5281/zenodo.1"},
    )
    await db_session.commit()

    fake = _FakeZenodo(draft_id="new-7", doi="10.5281/zenodo.7")
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
    assert stored["deposit_id"] == "new-7"


@pytest.mark.asyncio
async def test_creator_orcid_overlay_from_user_table(
    db_session: AsyncSession,
    seeded_plugin_row: Plugin,
) -> None:
    """A User whose display_name matches a creator name has their ORCID
    propagated into the Zenodo creator.identifiers payload."""
    from app.core.password import hash_password
    from app.models.user import User

    await _seed_settings(db_session)
    # Seed a user with an ORCID whose display_name matches the collection
    # author string ("Dante Alighieri" → matches exactly, case-folded).
    u = User(
        username="dante",
        email="dante@example.org",
        password_hash=hash_password("irrelevant1"),
        display_name="Dante Alighieri",
        is_active=True,
        is_verified=True,
        orcid="0000-0002-1825-0097",
    )
    db_session.add(u)
    await db_session.flush()

    col = Collection(
        slug="commedia",
        title="Divina Commedia",
        author="Dante Alighieri",
        status=CollectionStatus.published,
    )
    db_session.add(col)
    await db_session.flush()

    fake = _FakeZenodo()
    await deposit_collection(
        db_session,
        col,
        existdb=_fake_existdb([("doc.xml", b"<tei/>")]),
        zenodo_client=fake,  # type: ignore[arg-type]
    )
    assert fake.last_payload is not None
    creators = fake.last_payload["metadata"]["creators"]
    dante = next(
        c for c in creators
        if c["person_or_org"].get("family_name") == "Alighieri"
    )
    identifiers = dante["person_or_org"]["identifiers"]
    assert identifiers == [
        {"scheme": "orcid", "identifier": "0000-0002-1825-0097"}
    ]


@pytest.mark.asyncio
async def test_license_id_ends_up_in_inveniordm_payload(
    db_session: AsyncSession,
    seeded_plugin_row: Plugin,
) -> None:
    """A Collection linked to CC-BY yields rights=[{id:'cc-by-4.0'}] in the payload."""
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

    fake = _FakeZenodo()
    await deposit_collection(
        db_session,
        col,
        existdb=_fake_existdb([("doc.xml", b"<tei/>")]),
        zenodo_client=fake,  # type: ignore[arg-type]
    )
    assert fake.last_payload is not None
    assert fake.last_payload["metadata"]["rights"] == [{"id": "cc-by-4.0"}]


@pytest.mark.asyncio
async def test_deposit_uses_configured_resource_type(
    db_session: AsyncSession,
    seeded_plugin_row: Plugin,
    seeded_collection: Collection,
) -> None:
    await _seed_settings(db_session, zenodo_resource_type="publication-book")
    fake = _FakeZenodo()
    await deposit_collection(
        db_session,
        seeded_collection,
        existdb=_fake_existdb([("a.xml", b"<a/>")]),
        zenodo_client=fake,  # type: ignore[arg-type]
    )
    assert fake.last_payload is not None
    assert fake.last_payload["metadata"]["resource_type"] == {"id": "publication-book"}


@pytest.mark.asyncio
async def test_per_collection_resource_type_overrides_global_setting(
    db_session: AsyncSession,
    seeded_plugin_row: Plugin,
    seeded_collection: Collection,
) -> None:
    """A non-NULL collection.zenodo_resource_type wins over the global setting."""
    await _seed_settings(db_session, zenodo_resource_type="publication-other")
    seeded_collection.zenodo_resource_type = "image-photo"
    await db_session.flush()

    fake = _FakeZenodo()
    await deposit_collection(
        db_session,
        seeded_collection,
        existdb=_fake_existdb([("a.xml", b"<a/>")]),
        zenodo_client=fake,  # type: ignore[arg-type]
    )
    assert fake.last_payload is not None
    assert fake.last_payload["metadata"]["resource_type"] == {"id": "image-photo"}


@pytest.mark.asyncio
async def test_zip_upload_bundles_all_files_into_single_archive(
    db_session: AsyncSession,
    seeded_plugin_row: Plugin,
    seeded_collection: Collection,
) -> None:
    """When zenodo_upload_as_zip=True the plugin uploads one ZIP instead of N xmls."""
    import io
    import zipfile

    await _seed_settings(db_session)
    seeded_collection.zenodo_upload_as_zip = True
    await db_session.flush()

    # Capture the bytes uploaded so we can open the ZIP and confirm it has
    # exactly the two documents that were in the collection.
    captured: list[tuple[str, bytes]] = []

    class _ZipCapturingFake(_FakeZenodo):
        async def upload_file(self, draft_id: str, filename: str, content: bytes) -> None:
            captured.append((filename, content))
            await super().upload_file(draft_id, filename, content)

    files = [("a.xml", b"<a/>"), ("b.xml", b"<b/>")]
    await deposit_collection(
        db_session,
        seeded_collection,
        existdb=_fake_existdb(files),
        zenodo_client=_ZipCapturingFake(),  # type: ignore[arg-type]
    )

    assert len(captured) == 1
    name, body = captured[0]
    assert name == "divina-commedia.zip"

    with zipfile.ZipFile(io.BytesIO(body)) as zf:
        assert sorted(zf.namelist()) == ["a.xml", "b.xml"]
        assert zf.read("a.xml") == b"<a/>"
        assert zf.read("b.xml") == b"<b/>"


@pytest.mark.asyncio
async def test_zip_flag_false_uploads_per_file(
    db_session: AsyncSession,
    seeded_plugin_row: Plugin,
    seeded_collection: Collection,
) -> None:
    await _seed_settings(db_session)
    seeded_collection.zenodo_upload_as_zip = False
    await db_session.flush()

    fake = _FakeZenodo()
    await deposit_collection(
        db_session,
        seeded_collection,
        existdb=_fake_existdb([("a.xml", b"<a/>"), ("b.xml", b"<b/>")]),
        zenodo_client=fake,  # type: ignore[arg-type]
    )
    # Two upload_file calls — one per document.
    uploads = [c for c in fake.calls if c[0] == "upload_file"]
    assert len(uploads) == 2
    assert {u[1] for u in uploads} == {"a.xml", "b.xml"}


@pytest.mark.asyncio
async def test_null_collection_resource_type_falls_back_to_global(
    db_session: AsyncSession,
    seeded_plugin_row: Plugin,
    seeded_collection: Collection,
) -> None:
    """NULL on the collection means "inherit the global setting"."""
    await _seed_settings(db_session, zenodo_resource_type="dataset")
    seeded_collection.zenodo_resource_type = None
    await db_session.flush()

    fake = _FakeZenodo()
    await deposit_collection(
        db_session,
        seeded_collection,
        existdb=_fake_existdb([("a.xml", b"<a/>")]),
        zenodo_client=fake,  # type: ignore[arg-type]
    )
    assert fake.last_payload is not None
    assert fake.last_payload["metadata"]["resource_type"] == {"id": "dataset"}


@pytest.mark.asyncio
async def test_deposit_restricted_access_blocks_rights_block(
    db_session: AsyncSession,
    seeded_plugin_row: Plugin,
) -> None:
    """A restricted record should not emit a license, per mapping rules."""
    await _seed_settings(db_session, zenodo_access="restricted")
    lic = License(
        name="CC-BY 4.0",
        target="https://creativecommons.org/licenses/by/4.0/",
        is_active=True,
    )
    db_session.add(lic)
    await db_session.flush()

    col = Collection(
        slug="restricted-edition",
        title="Restricted Edition",
        license_id=lic.id,
        status=CollectionStatus.published,
    )
    db_session.add(col)
    await db_session.flush()

    fake = _FakeZenodo()
    await deposit_collection(
        db_session,
        col,
        existdb=_fake_existdb([("doc.xml", b"<tei/>")]),
        zenodo_client=fake,  # type: ignore[arg-type]
    )
    assert fake.last_payload is not None
    md = fake.last_payload["metadata"]
    assert "rights" not in md
    assert fake.last_payload["access"] == {"record": "restricted", "files": "restricted"}
