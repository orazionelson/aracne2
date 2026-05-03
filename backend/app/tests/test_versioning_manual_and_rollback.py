"""Tests for the manual-save + rollback paths in services.document_versions.

These exercise the service layer directly (no HTTP) because Phase B
intentionally stops at the service surface — the public REST API for
``/collections/{id}/documents/{filename}/versions/...`` lands in Phase C.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ManualVersionsLimitReached, NotFoundError
from app.db.existdb import ExistDBClient
from app.models.collection import Collection, CollectionStatus
from app.models.document_version import VersionOrigin
from app.models.system_setting import SystemSetting
from app.models.user import User
from app.services.document_versions import (
    create_version,
    list_versions,
    manual_save,
    rollback_to,
)


async def _make_collection(db: AsyncSession, slug: str) -> Collection:
    col = Collection(slug=slug, title="Test", status=CollectionStatus.assigned)
    db.add(col)
    await db.flush()
    return col


@pytest.mark.asyncio
async def test_manual_save_records_message(
    db_session: AsyncSession,
    seeded_editorinchief: User,
) -> None:
    col = await _make_collection(db_session, "man-1")
    row = await manual_save(
        db_session,
        collection=col,
        filename="d.xml",
        xml_bytes=b"<TEI/>",
        actor=seeded_editorinchief,
        audit_log_row=None,
        message="WIP — pre-coffee draft",
    )
    assert row.origin is VersionOrigin.manual
    assert row.message == "WIP — pre-coffee draft"
    assert row.created_by_id == seeded_editorinchief.id


@pytest.mark.asyncio
async def test_manual_save_writes_even_on_unchanged_content(
    db_session: AsyncSession,
    seeded_editorinchief: User,
) -> None:
    """Manual save bypasses dedup: pressing the button always produces a row
    so the editor's history is honest about their explicit actions."""
    col = await _make_collection(db_session, "man-2")
    body = b"<TEI/>"
    await create_version(
        db_session,
        collection=col,
        filename="d.xml",
        xml_bytes=body,
        origin=VersionOrigin.creation,
        actor=seeded_editorinchief,
    )
    row = await manual_save(
        db_session,
        collection=col,
        filename="d.xml",
        xml_bytes=body,
        actor=seeded_editorinchief,
        audit_log_row=None,
        message="checkpoint",
    )
    assert row.origin is VersionOrigin.manual

    rows = await list_versions(
        db_session, collection_id=col.id, filename="d.xml"
    )
    assert len(rows) == 2


@pytest.mark.asyncio
async def test_manual_save_enforces_soft_cap(
    db_session: AsyncSession,
    seeded_editorinchief: User,
) -> None:
    """The soft cap blocks the next manual save with 409 once
    document_manual_versions_max manual rows exist for the doc. Auto rows
    do not count against the cap."""
    cap = 3
    db_session.add(
        SystemSetting(
            key="document_manual_versions_max",
            value=str(cap),
            type="int",
        )
    )
    await db_session.flush()

    col = await _make_collection(db_session, "man-3")

    # Mix in some auto rows; they must NOT count against the cap.
    await create_version(
        db_session,
        collection=col,
        filename="d.xml",
        xml_bytes=b"<TEI v='auto1'/>",
        origin=VersionOrigin.creation,
        actor=seeded_editorinchief,
    )
    await create_version(
        db_session,
        collection=col,
        filename="d.xml",
        xml_bytes=b"<TEI v='auto2'/>",
        origin=VersionOrigin.publication,
        actor=seeded_editorinchief,
    )

    for n in range(cap):
        await manual_save(
            db_session,
            collection=col,
            filename="d.xml",
            xml_bytes=f"<TEI m='{n}'/>".encode(),
            actor=seeded_editorinchief,
            audit_log_row=None,
            message=f"manual {n}",
        )

    with pytest.raises(ManualVersionsLimitReached) as excinfo:
        await manual_save(
            db_session,
            collection=col,
            filename="d.xml",
            xml_bytes=b"<TEI m='last'/>",
            actor=seeded_editorinchief,
            audit_log_row=None,
            message="overflow",
        )
    assert excinfo.value.details["current"] == cap
    assert excinfo.value.details["limit"] == cap


@pytest.mark.asyncio
async def test_rollback_writes_rollback_row_and_pushes_to_existdb(
    db_session: AsyncSession,
    seeded_editorinchief: User,
) -> None:
    """Constructive rollback: working tree is rewritten with vN's content
    (via existdb.put_document) AND a new ``origin=rollback`` row is appended."""
    col = await _make_collection(db_session, "rb-1")

    target_body = b"<TEI v='target'/>"
    target = await create_version(
        db_session,
        collection=col,
        filename="d.xml",
        xml_bytes=target_body,
        origin=VersionOrigin.creation,
        actor=seeded_editorinchief,
    )
    assert target is not None

    # Subsequent manual save bumps the version counter.
    await manual_save(
        db_session,
        collection=col,
        filename="d.xml",
        xml_bytes=b"<TEI v='later'/>",
        actor=seeded_editorinchief,
        audit_log_row=None,
        message="later",
    )

    fake_existdb = AsyncMock(spec=ExistDBClient)
    fake_existdb.put_document = AsyncMock(return_value=None)

    rolled = await rollback_to(
        db_session,
        fake_existdb,
        collection=col,
        filename="d.xml",
        target_version_number=target.version_number,
        actor=seeded_editorinchief,
        audit_log_row=None,
    )
    assert rolled.origin is VersionOrigin.rollback
    assert rolled.message == f"Restored from version {target.version_number}"
    fake_existdb.put_document.assert_awaited_once_with(
        "rb-1", "d.xml", target_body
    )
    # The new row's content_sha256 matches the target's.
    assert rolled.content_sha256 == target.content_sha256


@pytest.mark.asyncio
async def test_rollback_to_unknown_version_raises_404(
    db_session: AsyncSession,
    seeded_editorinchief: User,
) -> None:
    col = await _make_collection(db_session, "rb-2")
    fake_existdb = AsyncMock(spec=ExistDBClient)

    with pytest.raises(NotFoundError):
        await rollback_to(
            db_session,
            fake_existdb,
            collection=col,
            filename="d.xml",
            target_version_number=42,
            actor=seeded_editorinchief,
            audit_log_row=None,
        )
    fake_existdb.put_document.assert_not_called()
