"""Tests for the website-deposit flow.

Mirrors ``test_deposit.py`` for collections but exercises the website
path: a ``Website`` row, a rendered tree on disk under ``tmp_path``
(used as the websites_root override), and a stubbed Zenodo client
that records the call sequence.
"""

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
from app.plugins.zenodo_deposit.deposit import (
    WEBSITE_DEPOSIT_KEY,
    DepositSkipped,
    deposit_website,
)
from app.plugins.zenodo_deposit.service import (
    DepositDraft,
    DepositResult,
    ZenodoError,
)
from app.services.plugin_data import PluginDataService


# ── Helpers ────────────────────────────────────────────────────────────────


def _store(key: str, value: str) -> str:
    if value and key in SENSITIVE_KEYS:
        return encrypt_value(value, app_settings.jwt_secret)
    return value


async def _seed_settings(db: AsyncSession, **overrides: str) -> None:
    defaults: dict[str, tuple[str, str]] = {
        "zenodo_api_token": ("token-xyz", "string"),
        "zenodo_base_url": ("https://sandbox.zenodo.org", "string"),
        "zenodo_default_community": ("", "string"),
        "zenodo_auto_publish": ("false", "bool"),
        "zenodo_access": ("open", "string"),
        "zenodo_resource_type": ("publication-other", "string"),
        "public_base_url": ("https://edition.example.org", "string"),
    }
    for key, (value, type_) in defaults.items():
        raw = overrides.get(key, value)
        db.add(SystemSetting(key=key, value=_store(key, raw), type=type_))
    await db.flush()


@pytest_asyncio.fixture
async def seeded_plugin_row(db_session: AsyncSession) -> Plugin:
    row = Plugin(
        name="zenodo_deposit",
        display_name="Zenodo Deposit",
        version="2.0.0",
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
        description="Static-rendered TEI.",
        rendering_mode=RenderingMode.STATIC,
        build_status=BuildStatus.done,
    )
    db_session.add(site)
    await db_session.flush()
    return site


def _write_rendered_tree(root: Path) -> None:
    """Lay out a small but representative rendered-site tree."""
    root.mkdir(parents=True, exist_ok=True)
    (root / "index.html").write_bytes(b"<html>home</html>")
    (root / "browse.html").write_bytes(b"<html>browse</html>")
    css = root / "css"
    css.mkdir()
    (css / "theme.css").write_bytes(b"body{font-family:serif}")
    docs = root / "docs"
    docs.mkdir()
    (docs / "doc1.html").write_bytes(b"<html>doc1</html>")
    # Dotfile that the collector must skip.
    (root / ".DS_Store").write_bytes(b"junk")


class _FakeZenodo:
    def __init__(
        self, *, draft_id: str = "site-abc", doi: str | None = "10.5281/zenodo.99",
    ) -> None:
        self.draft_id = draft_id
        self.doi = doi
        self.calls: list[tuple[str, Any]] = []
        self.last_payload: dict[str, Any] | None = None

    async def create_draft(self, payload: dict[str, Any]) -> DepositDraft:
        self.calls.append(("create_draft", payload))
        self.last_payload = payload
        return DepositDraft(
            id=self.draft_id,
            record_url=f"https://sandbox.zenodo.org/uploads/{self.draft_id}",
        )

    async def upload_file(self, draft_id: str, filename: str, content: bytes) -> None:
        self.calls.append(("upload_file", filename, len(content)))

    async def publish(self, deposit_id: str) -> DepositResult:
        self.calls.append(("publish", deposit_id))
        return DepositResult(
            id=deposit_id,
            doi=self.doi,
            record_url=f"https://sandbox.zenodo.org/records/{deposit_id}",
            status="published",
        )


# ── Tests ──────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_zip_mode_uploads_one_archive_skipping_dotfiles(
    db_session: AsyncSession,
    tmp_path: Path,
    seeded_plugin_row: Plugin,
    seeded_website: Website,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(app_settings, "websites_root", tmp_path)
    _write_rendered_tree(tmp_path / seeded_website.slug)
    await _seed_settings(db_session)

    fake = _FakeZenodo()
    result = await deposit_website(
        db_session, seeded_website, upload_as_zip=True, zenodo_client=fake,
    )
    assert result.status == "draft"  # auto_publish=false in defaults
    # Exactly one upload, named ``{slug}.zip``.
    upload_calls = [c for c in fake.calls if c[0] == "upload_file"]
    assert len(upload_calls) == 1
    assert upload_calls[0][1] == "my-edition.zip"
    # The zip must contain four files (no .DS_Store).
    zip_bytes = upload_calls[0]
    # Decode the zip we receive: rebuild from a fresh upload to inspect.
    fake2 = _FakeZenodo()
    captured: dict[str, bytes] = {}

    async def capture_upload(draft_id: str, filename: str, content: bytes) -> None:
        captured[filename] = content

    fake2.upload_file = capture_upload  # type: ignore[assignment]
    await deposit_website(
        db_session, seeded_website, upload_as_zip=True, force=True,
        zenodo_client=fake2,
    )
    assert "my-edition.zip" in captured
    with zipfile.ZipFile(io.BytesIO(captured["my-edition.zip"])) as zf:
        names = sorted(zf.namelist())
    assert names == [
        "browse.html", "css/theme.css", "docs/doc1.html", "index.html",
    ]


@pytest.mark.asyncio
async def test_file_by_file_mode_uploads_each_file_individually(
    db_session: AsyncSession,
    tmp_path: Path,
    seeded_plugin_row: Plugin,
    seeded_website: Website,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(app_settings, "websites_root", tmp_path)
    _write_rendered_tree(tmp_path / seeded_website.slug)
    await _seed_settings(db_session)

    fake = _FakeZenodo()
    await deposit_website(
        db_session, seeded_website, upload_as_zip=False, zenodo_client=fake,
    )
    uploaded = sorted(c[1] for c in fake.calls if c[0] == "upload_file")
    assert uploaded == [
        "browse.html", "css/theme.css", "docs/doc1.html", "index.html",
    ]


@pytest.mark.asyncio
async def test_dynamic_mode_refuses_with_skipped(
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
    _write_rendered_tree(tmp_path / site.slug)

    with pytest.raises(DepositSkipped):
        await deposit_website(
            db_session, site, zenodo_client=_FakeZenodo(),
        )


@pytest.mark.asyncio
async def test_unbuilt_website_refuses_with_skipped(
    db_session: AsyncSession,
    tmp_path: Path,
    seeded_plugin_row: Plugin,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(app_settings, "websites_root", tmp_path)
    site = Website(
        slug="unbuilt",
        title="Unbuilt",
        rendering_mode=RenderingMode.STATIC,
        build_status=BuildStatus.idle,
    )
    db_session.add(site)
    await db_session.flush()
    await _seed_settings(db_session)

    with pytest.raises(DepositSkipped):
        await deposit_website(
            db_session, site, zenodo_client=_FakeZenodo(),
        )


@pytest.mark.asyncio
async def test_missing_render_dir_refuses_with_skipped(
    db_session: AsyncSession,
    tmp_path: Path,
    seeded_plugin_row: Plugin,
    seeded_website: Website,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(app_settings, "websites_root", tmp_path)
    # Note: no _write_rendered_tree call → directory missing.
    await _seed_settings(db_session)
    with pytest.raises(DepositSkipped):
        await deposit_website(
            db_session, seeded_website, zenodo_client=_FakeZenodo(),
        )


@pytest.mark.asyncio
async def test_missing_token_refuses_with_skipped(
    db_session: AsyncSession,
    tmp_path: Path,
    seeded_plugin_row: Plugin,
    seeded_website: Website,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(app_settings, "websites_root", tmp_path)
    _write_rendered_tree(tmp_path / seeded_website.slug)
    await _seed_settings(db_session, zenodo_api_token="")
    with pytest.raises(DepositSkipped):
        await deposit_website(
            db_session, seeded_website, zenodo_client=_FakeZenodo(),
        )


@pytest.mark.asyncio
async def test_already_deposited_blocks_unless_force(
    db_session: AsyncSession,
    tmp_path: Path,
    seeded_plugin_row: Plugin,
    seeded_website: Website,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(app_settings, "websites_root", tmp_path)
    _write_rendered_tree(tmp_path / seeded_website.slug)
    await _seed_settings(db_session)

    # First deposit succeeds.
    await deposit_website(
        db_session, seeded_website, zenodo_client=_FakeZenodo(),
    )

    # Second without force refuses.
    with pytest.raises(DepositSkipped):
        await deposit_website(
            db_session, seeded_website, zenodo_client=_FakeZenodo(),
        )

    # With force it goes through again.
    await deposit_website(
        db_session, seeded_website, force=True, zenodo_client=_FakeZenodo(),
    )


@pytest.mark.asyncio
async def test_zenodo_error_records_failed_status(
    db_session: AsyncSession,
    tmp_path: Path,
    seeded_plugin_row: Plugin,
    seeded_website: Website,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(app_settings, "websites_root", tmp_path)
    _write_rendered_tree(tmp_path / seeded_website.slug)
    await _seed_settings(db_session)

    class _Failing(_FakeZenodo):
        async def create_draft(self, payload: dict[str, Any]) -> DepositDraft:
            raise ZenodoError("nope", status_code=503)

    with pytest.raises(ZenodoError):
        await deposit_website(
            db_session, seeded_website, zenodo_client=_Failing(),
        )
    # The failure is persisted under the website-deposit key.
    svc = PluginDataService(plugin_id=seeded_plugin_row.id)
    data = await svc.get(
        db_session, entity_type="website",
        key=WEBSITE_DEPOSIT_KEY, entity_id=seeded_website.id,
    )
    assert data is not None
    assert data["status"] == "failed"
    assert data["http_status"] == 503


@pytest.mark.asyncio
async def test_success_records_metadata_with_file_count_and_zip_flag(
    db_session: AsyncSession,
    tmp_path: Path,
    seeded_plugin_row: Plugin,
    seeded_website: Website,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(app_settings, "websites_root", tmp_path)
    _write_rendered_tree(tmp_path / seeded_website.slug)
    await _seed_settings(db_session)

    await deposit_website(
        db_session, seeded_website, upload_as_zip=False,
        zenodo_client=_FakeZenodo(),
    )
    svc = PluginDataService(plugin_id=seeded_plugin_row.id)
    data = await svc.get(
        db_session, entity_type="website",
        key=WEBSITE_DEPOSIT_KEY, entity_id=seeded_website.id,
    )
    assert data is not None
    assert data["uploaded_as_zip"] is False
    assert data["file_count"] == 4
    assert data["status"] == "draft"
