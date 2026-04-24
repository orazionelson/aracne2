"""Tests for the website-archive flow.

Mirrors ``test_archive.py`` but exercises the website path: a
``Website`` row, the ``websites/{slug}`` URL pattern, and the
per-website plugin_data namespace ``website_archive``.
"""

from __future__ import annotations

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings as app_settings
from app.core.encryption import SENSITIVE_KEYS, encrypt_value
from app.models.plugin import Plugin, PluginStatus
from app.models.system_setting import SystemSetting
from app.models.website import BuildStatus, RenderingMode, Website
from app.plugins.internet_archive.archive import (
    WEBSITE_ARCHIVE_KEY,
    ArchiveSkipped,
    archive_website,
    refresh_website_status,
)
from app.plugins.internet_archive.service import (
    IAError,
    StatusResult,
    SubmitResult,
)
from app.services.plugin_data import PluginDataService


# ── Fixtures ────────────────────────────────────────────────────────────────


def _store(key: str, value: str) -> str:
    if value and key in SENSITIVE_KEYS:
        return encrypt_value(value, app_settings.jwt_secret)
    return value


async def _seed_settings(db: AsyncSession, **overrides: str) -> None:
    defaults: dict[str, tuple[str, str]] = {
        "internet_archive_access_key": ("ak-w", "string"),
        "internet_archive_secret_key": ("sk-w", "string"),
        "internet_archive_auto_archive": ("true", "bool"),
        "public_base_url": ("https://edition.example.org", "string"),
    }
    for key, (value, type_) in defaults.items():
        raw = overrides.get(key, value)
        db.add(SystemSetting(key=key, value=_store(key, raw), type=type_))
    await db.flush()


@pytest_asyncio.fixture
async def seeded_plugin_row(db_session: AsyncSession) -> Plugin:
    row = Plugin(
        name="internet_archive",
        display_name="Internet Archive",
        version="1.1.0",
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
        is_published=True,
    )
    db_session.add(site)
    await db_session.flush()
    return site


class _FakeIAClient:
    def __init__(
        self,
        *,
        job_id: str = "spn2-w",
        submit_raises: IAError | None = None,
        statuses: list[StatusResult] | None = None,
    ) -> None:
        self.job_id = job_id
        self.submit_raises = submit_raises
        self._statuses = list(statuses or [])
        self.submitted: list[str] = []
        self.polled: list[str] = []

    async def submit(self, url: str) -> SubmitResult:
        self.submitted.append(url)
        if self.submit_raises:
            raise self.submit_raises
        return SubmitResult(job_id=self.job_id, url=url)

    async def status(self, job_id: str) -> StatusResult:
        self.polled.append(job_id)
        if not self._statuses:
            return StatusResult(
                status="pending",
                timestamp=None,
                original_url=None,
                wayback_url=None,
                error=None,
            )
        return self._statuses.pop(0)


async def _no_sleep(_: float) -> None:
    return None


# ── Tests ───────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_archive_submits_sites_url_and_records_success(
    db_session: AsyncSession,
    seeded_plugin_row: Plugin,
    seeded_website: Website,
) -> None:
    await _seed_settings(db_session)
    fake = _FakeIAClient(
        statuses=[StatusResult(
            status="success", timestamp="2026-04-24",
            original_url="https://edition.example.org/sites/my-edition",
            wayback_url="https://web.archive.org/web/2026/edition.example.org/sites/my-edition",
            error=None,
        )],
    )
    data = await archive_website(
        db_session, seeded_website, ia_client=fake, sleep=_no_sleep,
    )
    # The submitted URL is exactly the website's canonical /sites/<slug>.
    assert fake.submitted == [
        "https://edition.example.org/sites/my-edition",
    ]
    assert data["status"] == "success"
    assert data["wayback_url"].startswith("https://web.archive.org/web/")
    # Persisted under the new key/entity_type so a collection archive on
    # the same project would coexist without overwriting.
    svc = PluginDataService(plugin_id=seeded_plugin_row.id)
    persisted = await svc.get(
        db_session, entity_type="website",
        key=WEBSITE_ARCHIVE_KEY, entity_id=seeded_website.id,
    )
    assert persisted is not None
    assert persisted["job_id"] == "spn2-w"


@pytest.mark.asyncio
async def test_archive_skips_when_credentials_missing(
    db_session: AsyncSession,
    seeded_plugin_row: Plugin,
    seeded_website: Website,
) -> None:
    await _seed_settings(
        db_session,
        internet_archive_access_key="",
        internet_archive_secret_key="",
    )
    with pytest.raises(ArchiveSkipped):
        await archive_website(
            db_session, seeded_website, ia_client=_FakeIAClient(),
            sleep=_no_sleep,
        )


@pytest.mark.asyncio
async def test_archive_skips_when_already_pending_or_success_without_force(
    db_session: AsyncSession,
    seeded_plugin_row: Plugin,
    seeded_website: Website,
) -> None:
    await _seed_settings(db_session)
    svc = PluginDataService(plugin_id=seeded_plugin_row.id)
    await svc.set(
        db_session, entity_type="website", key=WEBSITE_ARCHIVE_KEY,
        data={"status": "success", "wayback_url": "x"},
        entity_id=seeded_website.id,
    )
    await db_session.commit()

    with pytest.raises(ArchiveSkipped):
        await archive_website(
            db_session, seeded_website, ia_client=_FakeIAClient(),
            sleep=_no_sleep,
        )

    # Force overrides the guard.
    fake = _FakeIAClient(
        statuses=[StatusResult(
            status="success", timestamp=None,
            original_url=None, wayback_url=None, error=None,
        )],
    )
    await archive_website(
        db_session, seeded_website, ia_client=fake, force=True,
        sleep=_no_sleep,
    )
    assert fake.submitted  # SPN2 was hit


@pytest.mark.asyncio
async def test_archive_records_failed_when_submit_raises(
    db_session: AsyncSession,
    seeded_plugin_row: Plugin,
    seeded_website: Website,
) -> None:
    await _seed_settings(db_session)
    fake = _FakeIAClient(submit_raises=IAError("boom", status_code=503))
    with pytest.raises(IAError):
        await archive_website(
            db_session, seeded_website, ia_client=fake, sleep=_no_sleep,
        )
    svc = PluginDataService(plugin_id=seeded_plugin_row.id)
    persisted = await svc.get(
        db_session, entity_type="website",
        key=WEBSITE_ARCHIVE_KEY, entity_id=seeded_website.id,
    )
    assert persisted is not None
    assert persisted["status"] == "failed"
    assert persisted["http_status"] == 503


@pytest.mark.asyncio
async def test_archive_writes_pending_record_then_resolves_to_success(
    db_session: AsyncSession,
    seeded_plugin_row: Plugin,
    seeded_website: Website,
) -> None:
    """The pending stub is written before polling starts, so the UI
    has something to show even if the backend dies mid-poll."""
    await _seed_settings(db_session)
    fake = _FakeIAClient(
        statuses=[
            StatusResult(
                status="pending", timestamp=None,
                original_url=None, wayback_url=None, error=None,
            ),
            StatusResult(
                status="success", timestamp="t",
                original_url="u", wayback_url="w", error=None,
            ),
        ],
    )
    data = await archive_website(
        db_session, seeded_website, ia_client=fake, sleep=_no_sleep,
    )
    assert data["status"] == "success"
    assert len(fake.polled) == 2  # pending → success in two polls


@pytest.mark.asyncio
async def test_refresh_returns_existing_when_already_terminal(
    db_session: AsyncSession,
    seeded_plugin_row: Plugin,
    seeded_website: Website,
) -> None:
    await _seed_settings(db_session)
    svc = PluginDataService(plugin_id=seeded_plugin_row.id)
    await svc.set(
        db_session, entity_type="website", key=WEBSITE_ARCHIVE_KEY,
        data={"status": "success", "wayback_url": "w", "job_id": "j"},
        entity_id=seeded_website.id,
    )
    await db_session.commit()

    fake = _FakeIAClient()
    data = await refresh_website_status(
        db_session, seeded_website, ia_client=fake, sleep=_no_sleep,
    )
    # No SPN2 status calls — terminal records are returned as-is.
    assert fake.polled == []
    assert data["status"] == "success"


@pytest.mark.asyncio
async def test_refresh_polls_when_existing_is_pending(
    db_session: AsyncSession,
    seeded_plugin_row: Plugin,
    seeded_website: Website,
) -> None:
    await _seed_settings(db_session)
    svc = PluginDataService(plugin_id=seeded_plugin_row.id)
    await svc.set(
        db_session, entity_type="website", key=WEBSITE_ARCHIVE_KEY,
        data={
            "status": "pending", "job_id": "j-1",
            "original_url": "https://edition.example.org/sites/my-edition",
            "submitted_at": "2026-04-24T00:00:00+00:00",
            "error": None,
        },
        entity_id=seeded_website.id,
    )
    await db_session.commit()

    fake = _FakeIAClient(
        statuses=[StatusResult(
            status="success", timestamp="t",
            original_url=None, wayback_url="w", error=None,
        )],
    )
    data = await refresh_website_status(
        db_session, seeded_website, ia_client=fake, sleep=_no_sleep,
    )
    assert data["status"] == "success"
    assert fake.polled == ["j-1"]


@pytest.mark.asyncio
async def test_refresh_raises_skipped_when_no_record(
    db_session: AsyncSession,
    seeded_plugin_row: Plugin,
    seeded_website: Website,
) -> None:
    await _seed_settings(db_session)
    with pytest.raises(ArchiveSkipped):
        await refresh_website_status(
            db_session, seeded_website,
            ia_client=_FakeIAClient(), sleep=_no_sleep,
        )
