"""Tests for the native Backup plugin (/backup/*).

All endpoints are Admin-only.  The in-memory job registry (_jobs dict) is
cleared before every test via the `clean_backup_jobs` autouse fixture so tests
are fully isolated without touching the database.

Background tasks (_run_backup) are patched to a no-op coroutine in most tests;
the download test manually injects a DONE job with a real ZIP file.
"""

from __future__ import annotations

import zipfile
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
import pytest_asyncio
from httpx import AsyncClient

from app.models.user import User
from app.plugins._native.backup import service as backup_service
from app.plugins._native.backup.schemas import BackupJobOut, BackupJobStatus
from app.tests.conftest import (
    ADMIN_PASSWORD,
    ADMIN_USERNAME,
    TEST_USER_PASSWORD,
    TEST_USER_USERNAME,
)


# ── Helpers ────────────────────────────────────────────────────────────────────


async def _login_as(client: AsyncClient, username: str, password: str) -> str:
    res = await client.post(
        "/api/v1/auth/login",
        json={"username_or_email": username, "password": password},
    )
    assert res.status_code == 200
    return str(res.json()["data"]["access_token"])


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# ── Fixtures ───────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def clean_backup_jobs() -> None:
    """Clear the in-memory job registry before every test."""
    backup_service._jobs.clear()


@pytest.fixture
def done_job(tmp_path: Path) -> BackupJobOut:
    """Inject a completed backup job with a real (empty) ZIP file into the registry."""
    job_id = uuid4()
    zip_filename = f"backup_test_{job_id.hex[:8]}.zip"
    zip_path = tmp_path / zip_filename
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("manifest.json", '{"test": true}')
    job = BackupJobOut(
        id=job_id,
        label="test done job",
        scopes=["database"],
        status=BackupJobStatus.DONE,
        started_at=datetime.now(UTC),
        finished_at=datetime.now(UTC),
        error=None,
        filename=zip_filename,
        size_bytes=zip_path.stat().st_size,
    )
    backup_service._jobs[job_id] = job
    # Patch backup_root so the router resolves the file from tmp_path.
    with patch("app.plugins._native.backup.router.settings") as mock_cfg:
        mock_cfg.backup_root = tmp_path
        yield job


# ── ACL: non-Admin is rejected ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_backup_as_non_admin_returns_403(
    client: AsyncClient, seeded_user: User
) -> None:
    """Editor cannot trigger a backup."""
    token = await _login_as(client, TEST_USER_USERNAME, TEST_USER_PASSWORD)
    res = await client.post(
        "/api/v1/backup/jobs",
        headers=_auth(token),
        json={"scopes": ["database"], "label": ""},
    )
    assert res.status_code == 403


@pytest.mark.asyncio
async def test_list_jobs_as_non_admin_returns_403(
    client: AsyncClient, seeded_user: User
) -> None:
    token = await _login_as(client, TEST_USER_USERNAME, TEST_USER_PASSWORD)
    res = await client.get("/api/v1/backup/jobs", headers=_auth(token))
    assert res.status_code == 403


# ── POST /backup/jobs ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_backup_returns_202(
    client: AsyncClient, seeded_admin: User
) -> None:
    """Admin can trigger a backup; returns 202 with a PENDING job."""
    token = await _login_as(client, ADMIN_USERNAME, ADMIN_PASSWORD)
    # Patch the background task so it doesn't actually run.
    async def _noop(*_a: object, **_k: object) -> None:
        pass

    with patch("app.plugins._native.backup.service._run_backup", new=_noop):
        res = await client.post(
            "/api/v1/backup/jobs",
            headers=_auth(token),
            json={"scopes": ["database", "collections"], "label": "my-label"},
        )
    assert res.status_code == 202
    data = res.json()["data"]
    assert data["status"] == "pending"
    assert data["label"] == "my-label"
    assert set(data["scopes"]) == {"database", "collections"}
    assert "id" in data


@pytest.mark.asyncio
async def test_create_backup_default_scopes(
    client: AsyncClient, seeded_admin: User
) -> None:
    """Omitting scopes triggers the default (all three)."""
    token = await _login_as(client, ADMIN_USERNAME, ADMIN_PASSWORD)

    async def _noop(*_a: object, **_k: object) -> None:
        pass

    with patch("app.plugins._native.backup.service._run_backup", new=_noop):
        res = await client.post(
            "/api/v1/backup/jobs",
            headers=_auth(token),
            json={},
        )
    assert res.status_code == 202
    scopes = set(res.json()["data"]["scopes"])
    assert scopes == {"database", "collections", "media"}


# ── GET /backup/jobs ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_jobs_empty(client: AsyncClient, seeded_admin: User) -> None:
    """List is empty when no jobs have been created."""
    token = await _login_as(client, ADMIN_USERNAME, ADMIN_PASSWORD)
    res = await client.get("/api/v1/backup/jobs", headers=_auth(token))
    assert res.status_code == 200
    assert res.json()["data"] == []


@pytest.mark.asyncio
async def test_list_jobs_shows_created_job(
    client: AsyncClient, seeded_admin: User
) -> None:
    token = await _login_as(client, ADMIN_USERNAME, ADMIN_PASSWORD)

    async def _noop(*_a: object, **_k: object) -> None:
        pass

    with patch("app.plugins._native.backup.service._run_backup", new=_noop):
        await client.post(
            "/api/v1/backup/jobs",
            headers=_auth(token),
            json={"label": "test"},
        )
    res = await client.get("/api/v1/backup/jobs", headers=_auth(token))
    assert res.status_code == 200
    assert len(res.json()["data"]) == 1
    assert res.json()["data"][0]["label"] == "test"


# ── GET /backup/jobs/{id} ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_job_status(client: AsyncClient, seeded_admin: User) -> None:
    token = await _login_as(client, ADMIN_USERNAME, ADMIN_PASSWORD)

    async def _noop(*_a: object, **_k: object) -> None:
        pass

    with patch("app.plugins._native.backup.service._run_backup", new=_noop):
        create_res = await client.post(
            "/api/v1/backup/jobs",
            headers=_auth(token),
            json={"label": "status-check"},
        )
    job_id = create_res.json()["data"]["id"]

    res = await client.get(f"/api/v1/backup/jobs/{job_id}", headers=_auth(token))
    assert res.status_code == 200
    assert res.json()["data"]["id"] == job_id


@pytest.mark.asyncio
async def test_get_nonexistent_job_returns_404(
    client: AsyncClient, seeded_admin: User
) -> None:
    token = await _login_as(client, ADMIN_USERNAME, ADMIN_PASSWORD)
    fake_id = str(uuid4())
    res = await client.get(f"/api/v1/backup/jobs/{fake_id}", headers=_auth(token))
    assert res.status_code == 404


# ── DELETE /backup/jobs/{id} ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_delete_job_returns_204(
    client: AsyncClient, seeded_admin: User
) -> None:
    token = await _login_as(client, ADMIN_USERNAME, ADMIN_PASSWORD)

    async def _noop(*_a: object, **_k: object) -> None:
        pass

    with patch("app.plugins._native.backup.service._run_backup", new=_noop):
        create_res = await client.post(
            "/api/v1/backup/jobs",
            headers=_auth(token),
            json={},
        )
    job_id = create_res.json()["data"]["id"]

    del_res = await client.delete(
        f"/api/v1/backup/jobs/{job_id}", headers=_auth(token)
    )
    assert del_res.status_code == 204

    # Confirm it's gone.
    get_res = await client.get(
        f"/api/v1/backup/jobs/{job_id}", headers=_auth(token)
    )
    assert get_res.status_code == 404


@pytest.mark.asyncio
async def test_delete_nonexistent_job_returns_404(
    client: AsyncClient, seeded_admin: User
) -> None:
    token = await _login_as(client, ADMIN_USERNAME, ADMIN_PASSWORD)
    res = await client.delete(
        f"/api/v1/backup/jobs/{uuid4()}", headers=_auth(token)
    )
    assert res.status_code == 404


# ── GET /backup/jobs/{id}/download ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_download_pending_job_returns_404(
    client: AsyncClient, seeded_admin: User
) -> None:
    """Downloading a job that hasn't finished yet returns 404."""
    token = await _login_as(client, ADMIN_USERNAME, ADMIN_PASSWORD)

    async def _noop(*_a: object, **_k: object) -> None:
        pass

    with patch("app.plugins._native.backup.service._run_backup", new=_noop):
        create_res = await client.post(
            "/api/v1/backup/jobs",
            headers=_auth(token),
            json={},
        )
    job_id = create_res.json()["data"]["id"]

    res = await client.get(
        f"/api/v1/backup/jobs/{job_id}/download", headers=_auth(token)
    )
    assert res.status_code == 404


@pytest.mark.asyncio
async def test_download_done_job_returns_zip(
    client: AsyncClient, seeded_admin: User, done_job: BackupJobOut
) -> None:
    """A completed backup job can be downloaded as a ZIP archive."""
    token = await _login_as(client, ADMIN_USERNAME, ADMIN_PASSWORD)
    res = await client.get(
        f"/api/v1/backup/jobs/{done_job.id}/download", headers=_auth(token)
    )
    assert res.status_code == 200
    assert res.headers["content-type"] == "application/zip"
