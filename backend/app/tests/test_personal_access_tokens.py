"""Tests for personal_access_tokens (Phase CLI-A).

Locks in the contract that drives the CLI:

- ``issue_pat`` returns plaintext exactly once with the
  ``aracne2_pat_`` prefix.
- ``resolve_pat`` finds the user for a valid plaintext, bumps
  ``last_used_at``, returns None for unknown / revoked / wrong-prefix
  tokens.
- ``revoke_pat`` is idempotent and scoped to the issuer.
- HTTP: GET/POST/DELETE on ``/users/me/tokens``.
- Auth integration: a request authenticated by PAT bearer reaches a
  protected route with the issuer's role.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.personal_access_token import PersonalAccessToken
from app.models.user import User
from app.services.personal_access_tokens import (
    PAT_PREFIX,
    issue_pat,
    list_pats,
    resolve_pat,
    revoke_pat,
)
from app.tests.conftest import (
    EIC_PASSWORD,
    EIC_USERNAME,
    TEST_USER_PASSWORD,
    TEST_USER_USERNAME,
)


async def _login(client: AsyncClient, username: str, password: str) -> str:
    res = await client.post(
        "/api/v1/auth/login",
        json={"username_or_email": username, "password": password},
    )
    assert res.status_code == 200, res.text
    return str(res.json()["data"]["access_token"])


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# ── Service-level tests ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_issue_pat_returns_plaintext_with_prefix(
    db_session: AsyncSession,
    seeded_editorinchief: User,
) -> None:
    row, plaintext = await issue_pat(
        db_session, user=seeded_editorinchief, label="my-laptop"
    )
    assert plaintext.startswith(PAT_PREFIX)
    # 32 url-safe random bytes → 43 base64 chars, plus the 12-char prefix.
    assert len(plaintext) == len(PAT_PREFIX) + 43
    assert row.user_id == seeded_editorinchief.id
    assert row.label == "my-laptop"
    assert row.revoked_at is None
    assert row.last_used_at is None
    # The bcrypt digest is in the row, not the plaintext.
    assert plaintext not in row.hashed_token


@pytest.mark.asyncio
async def test_issue_pat_rejects_empty_label(
    db_session: AsyncSession,
    seeded_editorinchief: User,
) -> None:
    from app.core.exceptions import DomainValidationError

    with pytest.raises(DomainValidationError):
        await issue_pat(db_session, user=seeded_editorinchief, label="   ")


@pytest.mark.asyncio
async def test_resolve_pat_returns_user_and_bumps_last_used(
    db_session: AsyncSession,
    seeded_editorinchief: User,
) -> None:
    _, plaintext = await issue_pat(
        db_session, user=seeded_editorinchief, label="cli"
    )
    found = await resolve_pat(db_session, plaintext)
    assert found is not None
    assert found.id == seeded_editorinchief.id
    # last_used_at bumped.
    rows = await list_pats(db_session, seeded_editorinchief)
    assert len(rows) == 1
    assert rows[0].last_used_at is not None


@pytest.mark.asyncio
async def test_resolve_pat_rejects_unknown_prefix(
    db_session: AsyncSession,
) -> None:
    """Bearers without the prefix never touch the DB."""
    found = await resolve_pat(db_session, "nope_not_an_aracne_pat")
    assert found is None


@pytest.mark.asyncio
async def test_resolve_pat_rejects_revoked(
    db_session: AsyncSession,
    seeded_editorinchief: User,
) -> None:
    row, plaintext = await issue_pat(
        db_session, user=seeded_editorinchief, label="cli"
    )
    await revoke_pat(
        db_session, user=seeded_editorinchief, token_id=row.id
    )
    found = await resolve_pat(db_session, plaintext)
    assert found is None


@pytest.mark.asyncio
async def test_revoke_pat_is_idempotent(
    db_session: AsyncSession,
    seeded_editorinchief: User,
) -> None:
    row, _ = await issue_pat(
        db_session, user=seeded_editorinchief, label="cli"
    )
    await revoke_pat(db_session, user=seeded_editorinchief, token_id=row.id)
    # Second call must not raise.
    await revoke_pat(db_session, user=seeded_editorinchief, token_id=row.id)


@pytest.mark.asyncio
async def test_revoke_pat_scoped_to_issuer(
    db_session: AsyncSession,
    seeded_user: User,
    seeded_editorinchief: User,
) -> None:
    """An editor cannot revoke another user's PAT by guessing the ID."""
    from app.core.exceptions import NotFoundError

    row, _ = await issue_pat(
        db_session, user=seeded_editorinchief, label="cli"
    )
    with pytest.raises(NotFoundError):
        await revoke_pat(db_session, user=seeded_user, token_id=row.id)


# ── HTTP-level tests ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_post_tokens_returns_plaintext_once(
    client_with_existdb: AsyncClient,
    seeded_editorinchief: User,
) -> None:
    token = await _login(
        client_with_existdb, EIC_USERNAME, EIC_PASSWORD
    )
    res = await client_with_existdb.post(
        "/api/v1/users/me/tokens",
        json={"label": "ci-pipeline"},
        headers=_auth(token),
    )
    assert res.status_code == 201, res.text
    body = res.json()["data"]
    assert body["label"] == "ci-pipeline"
    assert body["token"].startswith(PAT_PREFIX)


@pytest.mark.asyncio
async def test_get_tokens_excludes_plaintext(
    client_with_existdb: AsyncClient,
    db_session: AsyncSession,
    seeded_editorinchief: User,
) -> None:
    await issue_pat(
        db_session, user=seeded_editorinchief, label="round-trip"
    )
    token = await _login(
        client_with_existdb, EIC_USERNAME, EIC_PASSWORD
    )
    res = await client_with_existdb.get(
        "/api/v1/users/me/tokens", headers=_auth(token)
    )
    assert res.status_code == 200
    body = res.json()["data"]
    assert len(body) == 1
    assert "token" not in body[0]  # plaintext NEVER returned in list


@pytest.mark.asyncio
async def test_delete_token_revokes(
    client_with_existdb: AsyncClient,
    db_session: AsyncSession,
    seeded_editorinchief: User,
) -> None:
    row, plaintext = await issue_pat(
        db_session, user=seeded_editorinchief, label="will-be-revoked"
    )
    token = await _login(
        client_with_existdb, EIC_USERNAME, EIC_PASSWORD
    )
    res = await client_with_existdb.delete(
        f"/api/v1/users/me/tokens/{row.id}", headers=_auth(token)
    )
    assert res.status_code == 204
    # After revocation the plaintext is no longer accepted.
    found = await resolve_pat(db_session, plaintext)
    assert found is None


@pytest.mark.asyncio
async def test_users_below_editor_cannot_create_pats(
    client_with_existdb: AsyncClient,
    db_session: AsyncSession,
    seeded_roles: list[str],
) -> None:
    """Plain ``User`` (level 1) hits 403 — only Editor+ has CLI surface."""
    from sqlalchemy import select

    from app.core.password import hash_password
    from app.models.role import Role, UserRole

    plain = User(
        username="plain_test",
        email="plain@example.org",
        password_hash=hash_password("plainpass1"),
        is_active=True,
        is_verified=True,
    )
    db_session.add(plain)
    await db_session.flush()
    user_role = await db_session.scalar(
        select(Role).where(Role.name == "User")
    )
    assert user_role is not None
    db_session.add(UserRole(user_id=plain.id, role_id=user_role.id))
    await db_session.flush()

    token = await _login(client_with_existdb, "plain_test", "plainpass1")
    res = await client_with_existdb.post(
        "/api/v1/users/me/tokens",
        json={"label": "blocked"},
        headers=_auth(token),
    )
    assert res.status_code == 403


# ── Auth middleware integration ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_pat_bearer_authenticates_against_protected_route(
    client_with_existdb: AsyncClient,
    db_session: AsyncSession,
    seeded_editorinchief: User,
) -> None:
    """A request whose ``Authorization: Bearer`` carries a PAT
    plaintext authenticates against an arbitrary protected route, with
    the issuer's role applied."""
    _, plaintext = await issue_pat(
        db_session, user=seeded_editorinchief, label="cli"
    )
    res = await client_with_existdb.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {plaintext}"},
    )
    assert res.status_code == 200, res.text
    body = res.json()["data"]
    assert body["username"] == seeded_editorinchief.username
    assert body["role"] == "EditorInChief"


@pytest.mark.asyncio
async def test_revoked_pat_is_rejected_by_middleware(
    client_with_existdb: AsyncClient,
    db_session: AsyncSession,
    seeded_editorinchief: User,
) -> None:
    row, plaintext = await issue_pat(
        db_session, user=seeded_editorinchief, label="cli"
    )
    await revoke_pat(
        db_session, user=seeded_editorinchief, token_id=row.id
    )
    res = await client_with_existdb.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {plaintext}"},
    )
    assert res.status_code == 401
    assert res.json()["error"]["code"] == "INVALID_PAT"
