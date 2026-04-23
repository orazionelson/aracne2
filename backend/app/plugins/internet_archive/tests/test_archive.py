"""Integration tests for the archive orchestration.

Uses the conftest test engine (SQLite in-memory); the Internet Archive
HTTP client is faked so no network is touched. Exercise the full
submit → poll → record flow plus the refresh path.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings as app_settings
from app.core.encryption import SENSITIVE_KEYS, encrypt_value
from app.models.collection import Collection, CollectionStatus
from app.models.plugin import Plugin, PluginStatus
from app.models.system_setting import SystemSetting
from app.plugins.internet_archive.archive import (
    ARCHIVE_KEY,
    ArchiveSkipped,
    archive_collection,
    refresh_status,
)
from app.plugins.internet_archive.service import (
    IAError,
    StatusResult,
    SubmitResult,
)
from app.services.plugin_data import PluginDataService


# ── Fixtures ────────────────────────────────────────────────────────────────


def _store_value(key: str, value: str) -> str:
    if value and key in SENSITIVE_KEYS:
        return encrypt_value(value, app_settings.jwt_secret)
    return value


async def _seed_settings(db: AsyncSession, **overrides: str) -> None:
    defaults: dict[str, tuple[str, str]] = {
        "internet_archive_access_key": ("ak-123", "string"),
        "internet_archive_secret_key": ("sk-abc", "string"),
        "internet_archive_auto_archive": ("true", "bool"),
        "public_base_url": ("https://edition.example.org", "string"),
    }
    for key, (value, type_) in defaults.items():
        raw = overrides.get(key, value)
        db.add(SystemSetting(key=key, value=_store_value(key, raw), type=type_))
    await db.flush()


@pytest_asyncio.fixture
async def seeded_plugin_row(db_session: AsyncSession) -> Plugin:
    row = Plugin(
        name="internet_archive",
        display_name="Internet Archive",
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
        status=CollectionStatus.published,
    )
    db_session.add(col)
    await db_session.flush()
    return col


class _FakeIAClient:
    """Fake InternetArchiveClient with a configurable poll script.

    ``statuses`` is the queue of ``StatusResult``s returned by successive
    calls to ``.status()``. This lets a test assert "pending twice, then
    success" behaviour end-to-end without patching asyncio.sleep (the
    orchestration accepts an injected ``sleep`` for exactly that reason).
    """

    def __init__(
        self,
        *,
        job_id: str = "spn2-abc",
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
            # Default to pending when the test didn't queue enough entries.
            return StatusResult(
                status="pending",
                timestamp=None,
                original_url=None,
                wayback_url=None,
                error=None,
            )
        return self._statuses.pop(0)


async def _no_sleep(_: float) -> None:  # used to short-circuit the poll loop
    return None


# ── Tests ───────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_skipped_when_keys_missing(
    db_session: AsyncSession,
    seeded_plugin_row: Plugin,
    seeded_collection: Collection,
) -> None:
    await _seed_settings(db_session, internet_archive_access_key="")
    with pytest.raises(ArchiveSkipped):
        await archive_collection(
            db_session,
            seeded_collection,
            ia_client=_FakeIAClient(),  # type: ignore[arg-type]
        )


@pytest.mark.asyncio
async def test_skipped_when_public_base_url_missing(
    db_session: AsyncSession,
    seeded_plugin_row: Plugin,
    seeded_collection: Collection,
) -> None:
    await _seed_settings(db_session, public_base_url="")
    with pytest.raises(ArchiveSkipped):
        await archive_collection(
            db_session,
            seeded_collection,
            ia_client=_FakeIAClient(),  # type: ignore[arg-type]
        )


@pytest.mark.asyncio
async def test_skipped_when_already_archived(
    db_session: AsyncSession,
    seeded_plugin_row: Plugin,
    seeded_collection: Collection,
) -> None:
    await _seed_settings(db_session)
    svc = PluginDataService(plugin_id=seeded_plugin_row.id)
    await svc.set(
        db_session,
        entity_type="collection",
        key=ARCHIVE_KEY,
        entity_id=seeded_collection.id,
        data={"status": "success", "wayback_url": "https://web.archive.org/web/.../x"},
    )
    await db_session.commit()
    with pytest.raises(ArchiveSkipped):
        await archive_collection(
            db_session,
            seeded_collection,
            ia_client=_FakeIAClient(),  # type: ignore[arg-type]
        )


@pytest.mark.asyncio
async def test_submit_builds_public_url_from_config(
    db_session: AsyncSession,
    seeded_plugin_row: Plugin,
    seeded_collection: Collection,
) -> None:
    await _seed_settings(db_session)
    fake = _FakeIAClient(
        statuses=[
            StatusResult(
                status="success",
                timestamp="20260423120000",
                original_url="https://edition.example.org/browse/divina-commedia",
                wayback_url="https://web.archive.org/web/20260423120000/https://edition.example.org/browse/divina-commedia",
                error=None,
            )
        ]
    )
    await archive_collection(
        db_session,
        seeded_collection,
        ia_client=fake,  # type: ignore[arg-type]
        sleep=_no_sleep,
    )
    assert fake.submitted == ["https://edition.example.org/browse/divina-commedia"]


@pytest.mark.asyncio
async def test_happy_path_records_success(
    db_session: AsyncSession,
    seeded_plugin_row: Plugin,
    seeded_collection: Collection,
) -> None:
    await _seed_settings(db_session)
    fake = _FakeIAClient(
        statuses=[
            # One pending response, then terminal success — the poll loop
            # must keep going past the first non-terminal reply.
            StatusResult("pending", None, None, None, None),
            StatusResult(
                status="success",
                timestamp="20260423120000",
                original_url="https://edition.example.org/browse/divina-commedia",
                wayback_url="https://web.archive.org/web/20260423120000/https://edition.example.org/browse/divina-commedia",
                error=None,
            ),
        ]
    )
    data = await archive_collection(
        db_session,
        seeded_collection,
        ia_client=fake,  # type: ignore[arg-type]
        sleep=_no_sleep,
    )
    assert data["status"] == "success"
    assert data["wayback_url"].startswith("https://web.archive.org/web/")
    # plugin_data reflects the terminal state.
    svc = PluginDataService(plugin_id=seeded_plugin_row.id)
    stored = await svc.get(
        db_session,
        entity_type="collection",
        key=ARCHIVE_KEY,
        entity_id=seeded_collection.id,
    )
    assert stored is not None
    assert stored["status"] == "success"
    assert stored["job_id"] == "spn2-abc"


@pytest.mark.asyncio
async def test_timeout_leaves_pending_and_refresh_resolves(
    db_session: AsyncSession,
    seeded_plugin_row: Plugin,
    seeded_collection: Collection,
) -> None:
    """All 12 polls return pending → record stays pending; refresh then
    succeeds and the record is upgraded."""
    await _seed_settings(db_session)
    # 12 pending replies → the whole 60s budget runs out with no terminal.
    pending_bundle: list[StatusResult] = [
        StatusResult("pending", None, None, None, None) for _ in range(12)
    ]
    fake = _FakeIAClient(statuses=pending_bundle)
    data = await archive_collection(
        db_session,
        seeded_collection,
        ia_client=fake,  # type: ignore[arg-type]
        sleep=_no_sleep,
    )
    assert data["status"] == "pending"
    assert data["job_id"] == "spn2-abc"

    # Now refresh — queue a terminal success and verify the record upgrades.
    fake_refresh = _FakeIAClient(
        job_id="spn2-abc",
        statuses=[
            StatusResult(
                status="success",
                timestamp="20260423130000",
                original_url="https://edition.example.org/browse/divina-commedia",
                wayback_url="https://web.archive.org/web/20260423130000/https://edition.example.org/browse/divina-commedia",
                error=None,
            ),
        ],
    )
    refreshed = await refresh_status(
        db_session,
        seeded_collection,
        ia_client=fake_refresh,  # type: ignore[arg-type]
        sleep=_no_sleep,
    )
    assert refreshed["status"] == "success"
    assert "20260423130000" in refreshed["wayback_url"]


@pytest.mark.asyncio
async def test_submit_error_records_failed(
    db_session: AsyncSession,
    seeded_plugin_row: Plugin,
    seeded_collection: Collection,
) -> None:
    await _seed_settings(db_session)
    fake = _FakeIAClient(submit_raises=IAError("IA 401: Unauthorized", status_code=401))
    with pytest.raises(IAError):
        await archive_collection(
            db_session,
            seeded_collection,
            ia_client=fake,  # type: ignore[arg-type]
            sleep=_no_sleep,
        )
    svc = PluginDataService(plugin_id=seeded_plugin_row.id)
    stored = await svc.get(
        db_session,
        entity_type="collection",
        key=ARCHIVE_KEY,
        entity_id=seeded_collection.id,
    )
    assert stored is not None
    assert stored["status"] == "failed"
    assert stored["http_status"] == 401


@pytest.mark.asyncio
async def test_force_overrides_already_archived_guard(
    db_session: AsyncSession,
    seeded_plugin_row: Plugin,
    seeded_collection: Collection,
) -> None:
    await _seed_settings(db_session)
    svc = PluginDataService(plugin_id=seeded_plugin_row.id)
    await svc.set(
        db_session,
        entity_type="collection",
        key=ARCHIVE_KEY,
        entity_id=seeded_collection.id,
        data={"status": "success", "job_id": "spn2-old"},
    )
    await db_session.commit()

    fake = _FakeIAClient(
        job_id="spn2-new",
        statuses=[
            StatusResult(
                status="success",
                timestamp="20260423140000",
                original_url="https://edition.example.org/browse/divina-commedia",
                wayback_url="https://web.archive.org/web/20260423140000/https://edition.example.org/browse/divina-commedia",
                error=None,
            ),
        ],
    )
    data = await archive_collection(
        db_session,
        seeded_collection,
        ia_client=fake,  # type: ignore[arg-type]
        force=True,
        sleep=_no_sleep,
    )
    assert data["job_id"] == "spn2-new"


@pytest.mark.asyncio
async def test_refresh_is_noop_on_terminal_record(
    db_session: AsyncSession,
    seeded_plugin_row: Plugin,
    seeded_collection: Collection,
) -> None:
    """Refreshing a success/failed record returns it unchanged, without
    hitting SPN2 — the upstream would not re-open a completed job anyway."""
    await _seed_settings(db_session)
    svc = PluginDataService(plugin_id=seeded_plugin_row.id)
    terminal: dict[str, Any] = {
        "status": "success",
        "job_id": "spn2-done",
        "wayback_url": "https://web.archive.org/web/20260101000000/https://x",
        "submitted_at": "2026-04-23T10:00:00+00:00",
    }
    await svc.set(
        db_session,
        entity_type="collection",
        key=ARCHIVE_KEY,
        entity_id=seeded_collection.id,
        data=terminal,
    )
    await db_session.commit()

    fake = _FakeIAClient()  # would panic on pop if called
    returned = await refresh_status(
        db_session,
        seeded_collection,
        ia_client=fake,  # type: ignore[arg-type]
        sleep=_no_sleep,
    )
    assert returned["status"] == "success"
    assert fake.polled == []  # no network call
