"""Fixity layer tests — record at deposit, re-check, drift transitions.

Eight concerns:

1. ``record_publication`` upserts a row with status=ok on first
   publish.
2. Re-publishing the same content refreshes the row (drifted reset).
3. ``recheck_one`` keeps status=ok when the version body is intact.
4. A tampered body transitions ok → drifted, stamps drifted_at,
   and emits a fixity.drift_detected audit row.
5. A missing version row transitions to status=missing.
6. Subsequent re-checks while still drifted do not re-emit the
   audit row.
7. /admin/fixity list endpoint surfaces drift first.
8. /admin/fixity/recheck synchronous endpoint returns a per-status
   tally.
"""

from __future__ import annotations

import gzip
import hashlib
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditLog
from app.models.collection import Collection, CollectionStatus
from app.models.document_version import DocumentVersion, VersionOrigin
from app.models.fixity_record import FixityRecord, FixityStatus
from app.models.user import User
from app.services.fixity import (
    list_records,
    record_publication,
    recheck_all,
    recheck_one,
    status_summary,
)
from app.tests.conftest import ADMIN_PASSWORD, ADMIN_USERNAME


def _sha256(blob: bytes) -> str:
    return hashlib.sha256(blob).hexdigest()


async def _make_collection(db: AsyncSession, slug: str = "fix-test") -> Collection:
    col = Collection(
        title="Fixity Test",
        slug=slug,
        status=CollectionStatus.published,
    )
    db.add(col)
    await db.flush()
    return col


async def _seed_publication_version(
    db: AsyncSession, *, collection: Collection, filename: str, body: bytes,
    version_number: int = 1,
) -> DocumentVersion:
    digest = _sha256(body)
    row = DocumentVersion(
        collection_id=collection.id,
        document_filename=filename,
        version_number=version_number,
        xml_content=gzip.compress(body),
        content_sha256=digest,
        size_bytes=len(body),
        origin=VersionOrigin.publication,
    )
    db.add(row)
    await db.flush()
    return row


# ── Service-level ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_record_publication_creates_row(db_session: AsyncSession) -> None:
    col = await _make_collection(db_session)
    body = b"<TEI/>"
    digest = _sha256(body)

    row = await record_publication(
        db_session,
        collection=col,
        filename="a.xml",
        expected_sha256=digest,
        version_number=1,
        size_bytes=len(body),
    )
    assert row.status == FixityStatus.ok
    assert row.expected_sha256 == digest
    assert row.last_seen_sha256 == digest
    assert row.last_checked_at is not None


@pytest.mark.asyncio
async def test_record_publication_refreshes_existing_row(
    db_session: AsyncSession,
) -> None:
    col = await _make_collection(db_session)

    # Plant a drifted row first.
    drifted = FixityRecord(
        collection_id=col.id,
        document_filename="a.xml",
        expected_sha256="deadbeef" * 8,
        last_seen_sha256="cafebabe" * 8,
        version_number=1,
        size_bytes=10,
        status=FixityStatus.drifted,
        drifted_at=datetime.now(UTC),
    )
    db_session.add(drifted)
    await db_session.flush()

    new_body = b"<TEI><refresh/></TEI>"
    new_digest = _sha256(new_body)
    refreshed = await record_publication(
        db_session,
        collection=col,
        filename="a.xml",
        expected_sha256=new_digest,
        version_number=2,
        size_bytes=len(new_body),
    )
    assert refreshed.id == drifted.id
    assert refreshed.status == FixityStatus.ok
    assert refreshed.drifted_at is None
    assert refreshed.expected_sha256 == new_digest


@pytest.mark.asyncio
async def test_recheck_one_keeps_ok_on_match(db_session: AsyncSession) -> None:
    col = await _make_collection(db_session)
    body = b"<TEI><stable/></TEI>"
    await _seed_publication_version(db_session, collection=col, filename="a.xml", body=body)
    digest = _sha256(body)

    rec = await record_publication(
        db_session,
        collection=col,
        filename="a.xml",
        expected_sha256=digest,
        version_number=1,
        size_bytes=len(body),
    )
    out = await recheck_one(db_session, record=rec)
    assert out.status == FixityStatus.ok
    assert out.last_seen_sha256 == digest


@pytest.mark.asyncio
async def test_recheck_one_drifts_on_tamper(db_session: AsyncSession) -> None:
    col = await _make_collection(db_session)
    real = b"<TEI><real/></TEI>"
    fake = b"<TEI><tampered/></TEI>"
    # Stored body is FAKE; expected is REAL → mismatch on re-check.
    await _seed_publication_version(db_session, collection=col, filename="a.xml", body=fake)

    rec = await record_publication(
        db_session,
        collection=col,
        filename="a.xml",
        expected_sha256=_sha256(real),
        version_number=1,
        size_bytes=len(real),
    )
    out = await recheck_one(db_session, record=rec)
    assert out.status == FixityStatus.drifted
    assert out.last_seen_sha256 == _sha256(fake)
    assert out.drifted_at is not None

    audits = list(
        await db_session.scalars(
            select(AuditLog).where(AuditLog.action == "fixity.drift_detected")
        )
    )
    assert len(audits) == 1


@pytest.mark.asyncio
async def test_recheck_one_missing_when_version_gone(
    db_session: AsyncSession,
) -> None:
    col = await _make_collection(db_session)
    rec = await record_publication(
        db_session,
        collection=col,
        filename="ghost.xml",
        expected_sha256=_sha256(b"x"),
        version_number=99,  # no DocumentVersion row exists for this
        size_bytes=1,
    )
    out = await recheck_one(db_session, record=rec)
    assert out.status == FixityStatus.missing
    assert out.last_seen_sha256 is None


@pytest.mark.asyncio
async def test_repeat_recheck_does_not_double_audit(
    db_session: AsyncSession,
) -> None:
    col = await _make_collection(db_session)
    real = b"<TEI><real/></TEI>"
    fake = b"<TEI><tampered/></TEI>"
    await _seed_publication_version(db_session, collection=col, filename="a.xml", body=fake)

    rec = await record_publication(
        db_session,
        collection=col,
        filename="a.xml",
        expected_sha256=_sha256(real),
        version_number=1,
        size_bytes=len(real),
    )
    await recheck_one(db_session, record=rec)
    await recheck_one(db_session, record=rec)
    await recheck_one(db_session, record=rec)
    audits = list(
        await db_session.scalars(
            select(AuditLog).where(AuditLog.action == "fixity.drift_detected")
        )
    )
    assert len(audits) == 1


# ── Endpoint level ────────────────────────────────────────────────────────────


async def _login(client: AsyncClient, username: str, password: str) -> str:
    res = await client.post(
        "/api/v1/auth/login",
        json={"username_or_email": username, "password": password},
    )
    assert res.status_code == 200, res.text
    return str(res.json()["data"]["access_token"])


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_admin_list_endpoint_drift_first(
    client: AsyncClient,
    db_session: AsyncSession,
    seeded_admin: User,
) -> None:
    col = await _make_collection(db_session, slug="endpoint-test")
    # One ok row, one drifted row.
    db_session.add_all(
        [
            FixityRecord(
                collection_id=col.id,
                document_filename="ok.xml",
                expected_sha256="a" * 64,
                last_seen_sha256="a" * 64,
                version_number=1,
                size_bytes=10,
                status=FixityStatus.ok,
                last_checked_at=datetime.now(UTC),
            ),
            FixityRecord(
                collection_id=col.id,
                document_filename="drift.xml",
                expected_sha256="b" * 64,
                last_seen_sha256="c" * 64,
                version_number=1,
                size_bytes=10,
                status=FixityStatus.drifted,
                drifted_at=datetime.now(UTC),
                last_checked_at=datetime.now(UTC),
            ),
        ]
    )
    await db_session.flush()

    token = await _login(client, ADMIN_USERNAME, ADMIN_PASSWORD)
    res = await client.get("/api/v1/fixity", headers=_auth(token))
    assert res.status_code == 200
    items = res.json()["data"]
    assert items[0]["document_filename"] == "drift.xml"


@pytest.mark.asyncio
async def test_admin_recheck_endpoint_returns_tally(
    client: AsyncClient,
    db_session: AsyncSession,
    seeded_admin: User,
) -> None:
    col = await _make_collection(db_session, slug="recheck-test")
    body = b"<x/>"
    await _seed_publication_version(
        db_session, collection=col, filename="a.xml", body=body
    )
    db_session.add(
        FixityRecord(
            collection_id=col.id,
            document_filename="a.xml",
            expected_sha256=_sha256(body),
            last_seen_sha256=None,
            version_number=1,
            size_bytes=len(body),
            status=FixityStatus.ok,
        )
    )
    await db_session.flush()

    token = await _login(client, ADMIN_USERNAME, ADMIN_PASSWORD)
    res = await client.post("/api/v1/fixity/recheck", headers=_auth(token))
    assert res.status_code == 200
    data = res.json()["data"]
    assert data["total"] >= 1
    assert data["ok"] >= 1
