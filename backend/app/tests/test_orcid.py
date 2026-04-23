"""Tests for the ORCID validator + the /auth/me PATCH endpoint."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from app.core.orcid import is_valid_orcid, normalise_orcid


# ── pure validator ─────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "value,expected",
    [
        ("0000-0002-1825-0097", True),   # Stephen Hawking, known-valid
        ("0000-0003-1415-9269", True),   # well-formed, checksum ok
        # Bad checksum, right shape:
        ("0000-0002-1825-0099", False),
        # Wrong shape:
        ("0000000218250097", False),
        ("0000-0002-1825", False),
        # Lowercase X is allowed by the regex, upper-cased on normalise:
        ("0000-0002-1825-009x", False),   # lowercase x plus bad checksum
    ],
)
def test_is_valid_orcid_shape_and_checksum(value: str, expected: bool) -> None:
    assert is_valid_orcid(value) is expected


def test_normalise_strips_https_prefix() -> None:
    assert normalise_orcid("https://orcid.org/0000-0002-1825-0097") == "0000-0002-1825-0097"


def test_normalise_strips_doi_style_prefix() -> None:
    assert normalise_orcid("orcid:0000-0002-1825-0097") == "0000-0002-1825-0097"


def test_normalise_uppercases_checksum_x() -> None:
    # Upper-casing is correct — ORCID's Mod 11-2 uses capital X for value 10.
    assert normalise_orcid("0000-0003-1415-926x") == "0000-0003-1415-926X"


# ── PATCH /auth/me ─────────────────────────────────────────────────────────


async def _login_and_get_token(client: AsyncClient, username: str, password: str) -> str:
    resp = await client.post(
        "/api/v1/auth/login",
        json={"username_or_email": username, "password": password},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]["access_token"]


@pytest.mark.asyncio
async def test_patch_me_sets_and_clears_orcid(client, seeded_user) -> None:
    token = await _login_and_get_token(client, "testuser", "testpassword1")

    # Set a valid ORCID.
    resp = await client.patch(
        "/api/v1/auth/me",
        json={"orcid": "0000-0002-1825-0097"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["orcid"] == "0000-0002-1825-0097"

    # Clear by sending empty string.
    resp = await client.patch(
        "/api/v1/auth/me",
        json={"orcid": ""},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["orcid"] is None


@pytest.mark.asyncio
async def test_patch_me_rejects_bad_checksum(client, seeded_user) -> None:
    token = await _login_and_get_token(client, "testuser", "testpassword1")
    resp = await client.patch(
        "/api/v1/auth/me",
        json={"orcid": "0000-0002-1825-0099"},  # bad checksum
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_patch_me_strips_orcid_url_prefix(client, seeded_user) -> None:
    token = await _login_and_get_token(client, "testuser", "testpassword1")
    resp = await client.patch(
        "/api/v1/auth/me",
        json={"orcid": "https://orcid.org/0000-0002-1825-0097"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["orcid"] == "0000-0002-1825-0097"
