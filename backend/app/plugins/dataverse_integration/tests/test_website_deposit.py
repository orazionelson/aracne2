"""Website-deposit tests: tmp_path stands in for the websites_root."""

from __future__ import annotations

import io
import zipfile
from pathlib import Path
from typing import Any

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings as app_settings
from app.core.encryption import SENSITIVE_KEYS, encrypt_value
from app.models.plugin import Plugin, PluginStatus
from app.models.system_setting import SystemSetting
from app.models.website import BuildStatus, RenderingMode, Website
from app.plugins.dataverse_integration.deposit import (
    WEBSITE_DEPOSIT_KEY,
    DepositSkipped,
    deposit_website,
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
        "dataverse_api_token": ("token-w", "string"),
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
async def seeded_website(db_session: AsyncSession) -> Website:
    site = Website(
        slug="my-edition",
        title="My Edition",
        rendering_mode=RenderingMode.STATIC,
        build_status=BuildStatus.done,
    )
    db_session.add(site)
    await db_session.flush()
    return site


def _write_site(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "index.html").write_bytes(b"<html>home</html>")
    css = root / "css"
    css.mkdir()
    (css / "theme.css").write_bytes(b"body{font-family:serif}")
    docs = root / "docs"
    docs.mkdir()
    (docs / "doc1.html").write_bytes(b"<html>doc1</html>")
    (root / ".DS_Store").write_bytes(b"junk")


class _FakeDataverse:
    def __init__(self) -> None:
        self.calls: list[tuple[str, Any]] = []

    async def create_dataset(self, alias: str, payload: dict[str, Any]) -> DatasetDraft:
        self.calls.append(("create_dataset", {"alias": alias}))
        return DatasetDraft(
            persistent_id="doi:10.5072/FK2/SITE",
            database_id=1,
            landing_url="https://demo.dataverse.org/dataset.xhtml?persistentId=doi:10.5072/FK2/SITE",
        )

    async def upload_file(
        self, persistent_id: str, filename: str, content: bytes,
        *, directory_label: str | None = None, description: str | None = None,
    ) -> None:
        self.calls.append((
            "upload_file",
            {
                "filename": filename,
                "directory_label": directory_label,
                "size": len(content),
            },
        ))

    async def publish(
        self, persistent_id: str, *, publish_type: str = "major",
    ) -> DepositResult:  # pragma: no cover — auto_publish off in these tests
        raise NotImplementedError


# ── Tests ──────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_zip_mode_uploads_one_archive(
    db_session: AsyncSession,
    tmp_path: Path,
    seeded_plugin_row: Plugin,
    seeded_website: Website,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(app_settings, "websites_root", tmp_path)
    _write_site(tmp_path / seeded_website.slug)
    await _seed_settings(db_session)
    fake = _FakeDataverse()
    await deposit_website(
        db_session, seeded_website,
        upload_as_zip=True, dataverse_client=fake,
    )
    uploads = [c for c in fake.calls if c[0] == "upload_file"]
    assert len(uploads) == 1
    assert uploads[0][1]["filename"] == "my-edition.zip"


@pytest.mark.asyncio
async def test_file_mode_uploads_each_with_directory_label(
    db_session: AsyncSession,
    tmp_path: Path,
    seeded_plugin_row: Plugin,
    seeded_website: Website,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(app_settings, "websites_root", tmp_path)
    _write_site(tmp_path / seeded_website.slug)
    await _seed_settings(db_session)
    fake = _FakeDataverse()
    await deposit_website(
        db_session, seeded_website,
        upload_as_zip=False, dataverse_client=fake,
    )
    by_filename = {
        c[1]["filename"]: c[1]
        for c in fake.calls if c[0] == "upload_file"
    }
    # Dotfile skipped; nested files split into directory + name.
    assert sorted(by_filename.keys()) == [
        "doc1.html", "index.html", "theme.css",
    ]
    assert by_filename["index.html"]["directory_label"] is None
    assert by_filename["theme.css"]["directory_label"] == "css"
    assert by_filename["doc1.html"]["directory_label"] == "docs"


@pytest.mark.asyncio
async def test_dynamic_mode_refuses(
    db_session: AsyncSession,
    tmp_path: Path,
    seeded_plugin_row: Plugin,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(app_settings, "websites_root", tmp_path)
    site = Website(
        slug="dyn",
        title="Dyn",
        rendering_mode=RenderingMode.DYNAMIC,
        build_status=BuildStatus.done,
    )
    db_session.add(site)
    await db_session.flush()
    await _seed_settings(db_session)
    with pytest.raises(DepositSkipped, match="DYNAMIC"):
        await deposit_website(
            db_session, site, dataverse_client=_FakeDataverse(),
        )


@pytest.mark.asyncio
async def test_unbuilt_refuses(
    db_session: AsyncSession,
    tmp_path: Path,
    seeded_plugin_row: Plugin,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(app_settings, "websites_root", tmp_path)
    site = Website(
        slug="unbuilt", title="x",
        rendering_mode=RenderingMode.STATIC,
        build_status=BuildStatus.idle,
    )
    db_session.add(site)
    await db_session.flush()
    await _seed_settings(db_session)
    with pytest.raises(DepositSkipped, match="not been built"):
        await deposit_website(
            db_session, site, dataverse_client=_FakeDataverse(),
        )


@pytest.mark.asyncio
async def test_persisted_record_carries_alias_and_file_count(
    db_session: AsyncSession,
    tmp_path: Path,
    seeded_plugin_row: Plugin,
    seeded_website: Website,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(app_settings, "websites_root", tmp_path)
    _write_site(tmp_path / seeded_website.slug)
    await _seed_settings(db_session)
    await deposit_website(
        db_session, seeded_website,
        upload_as_zip=False, alias_override="custom-dv",
        dataverse_client=_FakeDataverse(),
    )
    svc = PluginDataService(plugin_id=seeded_plugin_row.id)
    record = await svc.get(
        db_session, entity_type="website",
        key=WEBSITE_DEPOSIT_KEY, entity_id=seeded_website.id,
    )
    assert record is not None
    assert record["alias"] == "custom-dv"
    assert record["file_count"] == 3  # dotfile excluded
    assert record["uploaded_as_zip"] is False
