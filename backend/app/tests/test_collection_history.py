"""Tests for the editorial workflow history endpoint.

``GET /api/v1/collections/{id}/history`` projects the ``audit_log``
rows that describe the collection's state transitions (assigned,
submitted, rejected / revisions-requested, published, unpublished).
The UI uses it for the timeline stepper on the Collection detail
page, for the "Latest revision request" in-panel note, and for the
SLA "stuck for N days" nudge. All three depend on the same
payload, so the shape must stay stable.

Happy path: EiC creates a collection, submits it, has it rejected
with a note — the returned list contains the expected actions in
order, surfaces the ``note``, and includes the actor's display
name + username.

Negative path: a user below EditorInChief gets 403 (the payload
can include revision-request notes addressed to the assigned
editor and so must not leak to Users / Editors).
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from httpx import AsyncClient

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
    assert res.status_code == 200
    return str(res.json()["data"]["access_token"])


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_history_returns_transitions_in_order(
    client_with_existdb: AsyncClient,
    seeded_editorinchief: object,
) -> None:
    """Creating → submitting → requesting revisions yields three entries,
    oldest first, with the reject note surfaced."""
    client = client_with_existdb
    eic_token = await _login(client, EIC_USERNAME, EIC_PASSWORD)

    # Create a collection. EiC is the actor; status starts as ``draft``.
    res = await client.post(
        "/api/v1/collections",
        json={"slug": "hist-test", "title": "History Test"},
        headers=_auth(eic_token),
    )
    assert res.status_code == 201, res.text
    col_id = res.json()["data"]["id"]

    # Assign is required before submit; reassign the EiC as the editor
    # of their own collection (a test shortcut — normally a separate
    # Editor would be assigned). The submit path requires that the
    # actor be the currently-assigned editor.
    eic_id = res.json()["data"]["owner_id"]
    res = await client.post(
        f"/api/v1/collections/{col_id}/assign",
        json={"user_id": eic_id, "note": "self-assign for test"},
        headers=_auth(eic_token),
    )
    assert res.status_code == 200, res.text

    # Submit for review.
    res = await client.post(
        f"/api/v1/collections/{col_id}/submit",
        json={"note": "ready"},
        headers=_auth(eic_token),
    )
    assert res.status_code == 200, res.text

    # Request revisions (backend path is still /reject for compat).
    res = await client.post(
        f"/api/v1/collections/{col_id}/reject",
        json={"note": "please fix the title casing"},
        headers=_auth(eic_token),
    )
    assert res.status_code == 200, res.text

    # Now fetch the history and verify ordering + content.
    res = await client.get(
        f"/api/v1/collections/{col_id}/history",
        headers=_auth(eic_token),
    )
    assert res.status_code == 200, res.text
    entries = res.json()["data"]
    actions = [e["action"] for e in entries]
    assert actions == [
        "collection.created",
        "collection.assigned",
        "collection.submitted",
        "collection.rejected",
    ], actions

    reject_entry = entries[-1]
    assert reject_entry["note"] == "please fix the title casing"
    assert reject_entry["actor_username"] == EIC_USERNAME
    # occurred_at is a serialised datetime — just assert presence + shape.
    assert isinstance(reject_entry["occurred_at"], str)
    assert "T" in reject_entry["occurred_at"]


@pytest.mark.asyncio
async def test_history_below_eic_returns_403(
    client_with_existdb: AsyncClient,
    seeded_editorinchief: object,
    seeded_user: object,
) -> None:
    """A regular user cannot read the workflow history — it could contain
    revision-request notes addressed privately to the assigned editor."""
    client = client_with_existdb
    eic_token = await _login(client, EIC_USERNAME, EIC_PASSWORD)
    user_token = await _login(client, TEST_USER_USERNAME, TEST_USER_PASSWORD)

    res = await client.post(
        "/api/v1/collections",
        json={"slug": "hist-403", "title": "History ACL"},
        headers=_auth(eic_token),
    )
    assert res.status_code == 201
    col_id = res.json()["data"]["id"]

    res = await client.get(
        f"/api/v1/collections/{col_id}/history",
        headers=_auth(user_token),
    )
    assert res.status_code == 403


@pytest.mark.asyncio
async def test_history_unknown_collection_returns_404(
    client_with_existdb: AsyncClient,
    seeded_editorinchief: object,
) -> None:
    """Unknown collection id → 404 even for authorised EiC, proving the
    endpoint reads the ``audit_log`` via the collection table (not a
    blind query that would leak 403/200 distinctions)."""
    client = client_with_existdb
    eic_token = await _login(client, EIC_USERNAME, EIC_PASSWORD)

    res = await client.get(
        "/api/v1/collections/no-such-slug/history",
        headers=_auth(eic_token),
    )
    assert res.status_code == 404
