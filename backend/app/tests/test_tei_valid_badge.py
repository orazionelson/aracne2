"""Tests for the ``_tei_valid_badge_html`` footer helper.

The helper decides whether a public website should show the green
"TEI valid" shield in its footer. The rules — all in one place here
so they are easy to audit:

- ``public_tei_valid_badge_enabled`` system setting must be ``"true"``.
- The collection must have at least one ``CollectionValidationRun``
  with ``status='done'`` AND ``error_count=0``.
- If there are multiple done runs, the **latest** one wins, so a
  previously-green run followed by a red one correctly suppresses
  the badge.
- ``collection_validation_runs`` rows in states other than ``done``
  (pending / running / cancelled / failed) never count.
- When the badge renders, its HTML carries ``id="tei-valid-badge"``
  (the stable hook documented for per-site CSS overrides) and a
  ``title="Validated on YYYY-MM-DD"`` derived from ``completed_at``.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.collection import Collection, CollectionStatus
from app.models.collection_validation_run import (
    CollectionValidationRun,
    ValidationRunStatus,
)
from app.models.system_setting import SystemSetting
from app.services.websites import _tei_valid_badge_html


async def _make_collection(db: AsyncSession, slug: str = "badge-test") -> Collection:
    col = Collection(
        slug=slug,
        title="Badge Test",
        status=CollectionStatus.published,
        is_public=True,
    )
    db.add(col)
    await db.flush()
    return col


async def _set_enabled(db: AsyncSession, value: str) -> None:
    existing = await db.get(SystemSetting, "public_tei_valid_badge_enabled")
    if existing is None:
        db.add(
            SystemSetting(
                key="public_tei_valid_badge_enabled",
                value=value,
                type="bool",
            )
        )
    else:
        existing.value = value
    await db.flush()


@pytest.mark.asyncio
async def test_no_collection_no_badge(db_session: AsyncSession) -> None:
    """A website with no linked collection never shows the badge."""
    html = await _tei_valid_badge_html(db_session, None)
    assert html == ""


@pytest.mark.asyncio
async def test_no_validation_run_no_badge(db_session: AsyncSession) -> None:
    col = await _make_collection(db_session)
    await _set_enabled(db_session, "true")
    html = await _tei_valid_badge_html(db_session, col)
    assert html == ""


@pytest.mark.asyncio
async def test_green_run_produces_badge(db_session: AsyncSession) -> None:
    col = await _make_collection(db_session)
    await _set_enabled(db_session, "true")
    run = CollectionValidationRun(
        collection_id=col.id,
        started_by=None,
        schema_id=None,
        status=ValidationRunStatus.done,
        doc_count=3,
        validated_count=3,
        error_count=0,
        completed_at=datetime(2026, 4, 24, tzinfo=UTC),
    )
    db_session.add(run)
    await db_session.flush()

    html = await _tei_valid_badge_html(db_session, col)
    assert 'id="tei-valid-badge"' in html
    assert 'title="Validated on 2026-04-24"' in html
    assert "TEI valid" in html


@pytest.mark.asyncio
async def test_red_run_suppresses_badge(db_session: AsyncSession) -> None:
    """A done run with errors counts as red — no badge."""
    col = await _make_collection(db_session)
    await _set_enabled(db_session, "true")
    db_session.add(
        CollectionValidationRun(
            collection_id=col.id,
            status=ValidationRunStatus.done,
            doc_count=3,
            validated_count=3,
            error_count=2,
            completed_at=datetime.now(UTC),
        )
    )
    await db_session.flush()

    html = await _tei_valid_badge_html(db_session, col)
    assert html == ""


@pytest.mark.asyncio
async def test_latest_run_wins(db_session: AsyncSession) -> None:
    """A green run superseded by a red run loses the badge."""
    col = await _make_collection(db_session)
    await _set_enabled(db_session, "true")
    earlier = datetime(2026, 4, 1, tzinfo=UTC)
    later = earlier + timedelta(days=5)
    db_session.add_all(
        [
            CollectionValidationRun(
                collection_id=col.id,
                status=ValidationRunStatus.done,
                doc_count=3,
                validated_count=3,
                error_count=0,
                completed_at=earlier,
            ),
            CollectionValidationRun(
                collection_id=col.id,
                status=ValidationRunStatus.done,
                doc_count=3,
                validated_count=3,
                error_count=1,
                completed_at=later,
            ),
        ]
    )
    await db_session.flush()

    html = await _tei_valid_badge_html(db_session, col)
    assert html == ""


@pytest.mark.asyncio
async def test_setting_disabled_suppresses_badge(
    db_session: AsyncSession,
) -> None:
    """Even with a green run on record, the global kill-switch wins."""
    col = await _make_collection(db_session)
    await _set_enabled(db_session, "false")
    db_session.add(
        CollectionValidationRun(
            collection_id=col.id,
            status=ValidationRunStatus.done,
            doc_count=3,
            validated_count=3,
            error_count=0,
            completed_at=datetime.now(UTC),
        )
    )
    await db_session.flush()

    html = await _tei_valid_badge_html(db_session, col)
    assert html == ""


@pytest.mark.asyncio
async def test_non_done_runs_never_count(db_session: AsyncSession) -> None:
    """Pending / running / cancelled / failed runs never produce a badge."""
    col = await _make_collection(db_session)
    await _set_enabled(db_session, "true")
    for st in (
        ValidationRunStatus.pending,
        ValidationRunStatus.running,
        ValidationRunStatus.cancelled,
        ValidationRunStatus.failed,
    ):
        db_session.add(
            CollectionValidationRun(
                collection_id=col.id,
                status=st,
                doc_count=3,
                validated_count=3 if st != ValidationRunStatus.pending else 0,
                error_count=0,
                completed_at=datetime.now(UTC) if st != ValidationRunStatus.pending else None,
            )
        )
    await db_session.flush()

    html = await _tei_valid_badge_html(db_session, col)
    assert html == ""
