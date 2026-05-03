"""Tests for the ``document_versions`` table and the ``services.document_versions``
core helpers — Phase B.

Covers the data layer in isolation (no HTTP, no eXist-db round-trips beyond
the single mock byte stream): SHA-256 dedup behaviour, monotonic
``version_number`` allocation, gzip storage round-trip,
``get_last_publication`` selection, ``get_public_version`` rejecting
non-publication origins.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import VersionNotPublic
from app.models.collection import Collection, CollectionStatus
from app.models.document_version import DocumentVersion, VersionOrigin
from app.models.user import User
from app.services.document_versions import (
    create_version,
    get_last_publication,
    get_public_version,
    get_version,
    get_version_content,
    list_versions,
)
from app.tests.conftest import EIC_USERNAME


async def _make_collection(db: AsyncSession, slug: str) -> Collection:
    col = Collection(slug=slug, title="Test", status=CollectionStatus.assigned)
    db.add(col)
    await db.flush()
    return col


async def _eic_user(db: AsyncSession) -> User:
    return await db.scalar(
        # type: ignore[return-value]
        DocumentVersion.__table__.select()  # placeholder; not used
    ) or _user_by_username(db)


async def _user_by_username(db: AsyncSession, username: str = EIC_USERNAME) -> User:
    from sqlalchemy import select
    return await db.scalar(select(User).where(User.username == username))  # type: ignore[return-value]


@pytest.mark.asyncio
async def test_create_version_writes_row_and_compresses(
    db_session: AsyncSession,
    seeded_editorinchief: User,
) -> None:
    col = await _make_collection(db_session, "ver-1")
    body = b"<TEI><teiHeader/></TEI>"

    row = await create_version(
        db_session,
        collection=col,
        filename="doc1.xml",
        xml_bytes=body,
        origin=VersionOrigin.creation,
        actor=seeded_editorinchief,
    )

    assert row is not None
    assert row.version_number == 1
    assert row.size_bytes == len(body)
    assert len(row.content_sha256) == 64
    # Compressed payload differs from the source bytes; gunzip restores it.
    assert row.xml_content != body
    restored = await get_version_content(
        db_session,
        collection_id=col.id,
        filename="doc1.xml",
        version_number=1,
    )
    assert restored == body


@pytest.mark.asyncio
async def test_create_version_dedups_on_identical_sha256(
    db_session: AsyncSession,
    seeded_editorinchief: User,
) -> None:
    """A second create_version with the same content returns None and writes
    no new row — this is the contract the workflow auto-versioning depends
    on (publish on unchanged tree → 0 rows)."""
    col = await _make_collection(db_session, "ver-2")
    body = b"<TEI/>"

    first = await create_version(
        db_session,
        collection=col,
        filename="d.xml",
        xml_bytes=body,
        origin=VersionOrigin.creation,
        actor=seeded_editorinchief,
    )
    assert first is not None

    dup = await create_version(
        db_session,
        collection=col,
        filename="d.xml",
        xml_bytes=body,
        origin=VersionOrigin.publication,  # different origin, same content
        actor=seeded_editorinchief,
    )
    assert dup is None

    rows = await list_versions(
        db_session, collection_id=col.id, filename="d.xml"
    )
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_create_version_skip_dedup_always_writes(
    db_session: AsyncSession,
    seeded_editorinchief: User,
) -> None:
    """Manual saves and rollbacks pass skip_dedup=True so the editor's
    history always reflects their explicit action even on unchanged content."""
    col = await _make_collection(db_session, "ver-3")
    body = b"<TEI/>"

    a = await create_version(
        db_session,
        collection=col,
        filename="d.xml",
        xml_bytes=body,
        origin=VersionOrigin.creation,
        actor=seeded_editorinchief,
    )
    b = await create_version(
        db_session,
        collection=col,
        filename="d.xml",
        xml_bytes=body,
        origin=VersionOrigin.manual,
        actor=seeded_editorinchief,
        skip_dedup=True,
    )
    assert a is not None and b is not None
    assert b.version_number == a.version_number + 1


@pytest.mark.asyncio
async def test_version_numbers_are_monotonic_per_filename(
    db_session: AsyncSession,
    seeded_editorinchief: User,
) -> None:
    col = await _make_collection(db_session, "ver-4")

    for n in range(1, 4):
        row = await create_version(
            db_session,
            collection=col,
            filename="a.xml",
            xml_bytes=f"<TEI n='{n}'/>".encode(),
            origin=VersionOrigin.manual,
            actor=seeded_editorinchief,
            skip_dedup=True,
        )
        assert row is not None and row.version_number == n

    # A different filename starts its own counter.
    other = await create_version(
        db_session,
        collection=col,
        filename="b.xml",
        xml_bytes=b"<TEI/>",
        origin=VersionOrigin.creation,
        actor=seeded_editorinchief,
    )
    assert other is not None and other.version_number == 1


@pytest.mark.asyncio
async def test_get_last_publication_returns_only_publication_rows(
    db_session: AsyncSession,
    seeded_editorinchief: User,
) -> None:
    col = await _make_collection(db_session, "ver-5")

    await create_version(
        db_session,
        collection=col,
        filename="d.xml",
        xml_bytes=b"<TEI v='1'/>",
        origin=VersionOrigin.creation,
        actor=seeded_editorinchief,
    )
    pub1 = await create_version(
        db_session,
        collection=col,
        filename="d.xml",
        xml_bytes=b"<TEI v='2'/>",
        origin=VersionOrigin.publication,
        actor=seeded_editorinchief,
    )
    await create_version(
        db_session,
        collection=col,
        filename="d.xml",
        xml_bytes=b"<TEI v='3'/>",
        origin=VersionOrigin.manual,
        actor=seeded_editorinchief,
        skip_dedup=True,
    )

    last = await get_last_publication(
        db_session, collection_id=col.id, filename="d.xml"
    )
    assert last is not None
    assert pub1 is not None
    assert last.version_number == pub1.version_number


@pytest.mark.asyncio
async def test_get_public_version_rejects_non_publication(
    db_session: AsyncSession,
    seeded_editorinchief: User,
) -> None:
    col = await _make_collection(db_session, "ver-6")
    row = await create_version(
        db_session,
        collection=col,
        filename="d.xml",
        xml_bytes=b"<TEI/>",
        origin=VersionOrigin.manual,
        actor=seeded_editorinchief,
        skip_dedup=True,
    )
    assert row is not None

    with pytest.raises(VersionNotPublic):
        await get_public_version(
            db_session,
            collection_id=col.id,
            filename="d.xml",
            version_number=row.version_number,
        )


@pytest.mark.asyncio
async def test_list_versions_origin_filter(
    db_session: AsyncSession,
    seeded_editorinchief: User,
) -> None:
    col = await _make_collection(db_session, "ver-7")
    await create_version(
        db_session,
        collection=col,
        filename="d.xml",
        xml_bytes=b"<TEI v='1'/>",
        origin=VersionOrigin.creation,
        actor=seeded_editorinchief,
    )
    await create_version(
        db_session,
        collection=col,
        filename="d.xml",
        xml_bytes=b"<TEI v='2'/>",
        origin=VersionOrigin.publication,
        actor=seeded_editorinchief,
    )
    await create_version(
        db_session,
        collection=col,
        filename="d.xml",
        xml_bytes=b"<TEI v='3'/>",
        origin=VersionOrigin.manual,
        actor=seeded_editorinchief,
        skip_dedup=True,
    )

    only_pub = await list_versions(
        db_session,
        collection_id=col.id,
        filename="d.xml",
        origin=VersionOrigin.publication,
    )
    assert len(only_pub) == 1
    assert only_pub[0].origin is VersionOrigin.publication

    all_rows = await list_versions(
        db_session, collection_id=col.id, filename="d.xml"
    )
    assert len(all_rows) == 3


@pytest.mark.asyncio
async def test_get_version_404_when_missing(
    db_session: AsyncSession,
) -> None:
    from app.core.exceptions import NotFoundError

    col_id = uuid.uuid4()
    with pytest.raises(NotFoundError):
        await get_version(
            db_session,
            collection_id=col_id,
            filename="ghost.xml",
            version_number=1,
        )
