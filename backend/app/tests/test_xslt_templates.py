import uuid

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.models.xslt_template import XsltTemplate
from app.tests.conftest import (
    ADMIN_PASSWORD,
    ADMIN_USERNAME,
    DESIGNER_PASSWORD,
    DESIGNER_USERNAME,
    TEST_USER_PASSWORD,
    TEST_USER_USERNAME,
)

_MINIMAL_XSLT = (
    '<?xml version="1.0"?>'
    '<xsl:stylesheet xmlns:xsl="http://www.w3.org/1999/XSL/Transform" version="1.0">'
    "<xsl:template match=\"/\"><html/></xsl:template>"
    "</xsl:stylesheet>"
)


# ── Helpers ───────────────────────────────────────────────────────────────────


async def _login_as(client: AsyncClient, username: str, password: str) -> str:
    res = await client.post(
        "/api/v1/auth/login",
        json={"username_or_email": username, "password": password},
    )
    assert res.status_code == 200
    return str(res.json()["data"]["access_token"])


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def seeded_xslt_template(db_session: AsyncSession) -> XsltTemplate:
    tpl = XsltTemplate(
        name="Test XSLT",
        content=_MINIMAL_XSLT,
        processor="lxml",
        tags=[],
    )
    db_session.add(tpl)
    await db_session.flush()
    return tpl


# ── List ──────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_xslt_templates_as_designer(
    client: AsyncClient,
    seeded_designer: User,
    seeded_xslt_template: XsltTemplate,
) -> None:
    """Designer can list XSLT templates."""
    token = await _login_as(client, DESIGNER_USERNAME, DESIGNER_PASSWORD)
    res = await client.get("/api/v1/xslt-templates", headers=_auth(token))
    assert res.status_code == 200
    names = [t["name"] for t in res.json()["data"]]
    assert "Test XSLT" in names


@pytest.mark.asyncio
async def test_list_xslt_templates_as_admin(
    client: AsyncClient, seeded_admin: User, seeded_xslt_template: XsltTemplate
) -> None:
    """Admin can also list XSLT templates."""
    token = await _login_as(client, ADMIN_USERNAME, ADMIN_PASSWORD)
    res = await client.get("/api/v1/xslt-templates", headers=_auth(token))
    assert res.status_code == 200


@pytest.mark.asyncio
async def test_list_xslt_templates_as_editor_returns_403(
    client: AsyncClient, seeded_user: User
) -> None:
    """Editor (no Designer role) is denied access."""
    token = await _login_as(client, TEST_USER_USERNAME, TEST_USER_PASSWORD)
    res = await client.get("/api/v1/xslt-templates", headers=_auth(token))
    assert res.status_code == 403


# ── Get detail ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_xslt_template_as_designer(
    client: AsyncClient,
    seeded_designer: User,
    seeded_xslt_template: XsltTemplate,
) -> None:
    token = await _login_as(client, DESIGNER_USERNAME, DESIGNER_PASSWORD)
    res = await client.get(
        f"/api/v1/xslt-templates/{seeded_xslt_template.id}", headers=_auth(token)
    )
    assert res.status_code == 200
    assert res.json()["data"]["name"] == "Test XSLT"


@pytest.mark.asyncio
async def test_get_nonexistent_xslt_template_returns_404(
    client: AsyncClient, seeded_designer: User
) -> None:
    token = await _login_as(client, DESIGNER_USERNAME, DESIGNER_PASSWORD)
    res = await client.get(
        f"/api/v1/xslt-templates/{uuid.uuid4()}", headers=_auth(token)
    )
    assert res.status_code == 404


# ── Create ────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_xslt_template_as_designer(
    client: AsyncClient, seeded_designer: User
) -> None:
    """Designer can create a new XSLT template."""
    token = await _login_as(client, DESIGNER_USERNAME, DESIGNER_PASSWORD)
    res = await client.post(
        "/api/v1/xslt-templates",
        headers=_auth(token),
        json={"name": "New Template", "content": _MINIMAL_XSLT},
    )
    assert res.status_code == 201
    assert res.json()["data"]["name"] == "New Template"


@pytest.mark.asyncio
async def test_create_xslt_template_as_editor_returns_403(
    client: AsyncClient, seeded_user: User
) -> None:
    """Editor cannot create XSLT templates."""
    token = await _login_as(client, TEST_USER_USERNAME, TEST_USER_PASSWORD)
    res = await client.post(
        "/api/v1/xslt-templates",
        headers=_auth(token),
        json={"name": "Forbidden", "content": _MINIMAL_XSLT},
    )
    assert res.status_code == 403


# ── Update ────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_update_xslt_template_as_designer(
    client: AsyncClient,
    seeded_designer: User,
    seeded_xslt_template: XsltTemplate,
) -> None:
    token = await _login_as(client, DESIGNER_USERNAME, DESIGNER_PASSWORD)
    res = await client.patch(
        f"/api/v1/xslt-templates/{seeded_xslt_template.id}",
        headers=_auth(token),
        json={"name": "Updated XSLT"},
    )
    assert res.status_code == 200
    assert res.json()["data"]["name"] == "Updated XSLT"


# ── Delete ────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_delete_xslt_template_as_designer(
    client: AsyncClient,
    seeded_designer: User,
    seeded_xslt_template: XsltTemplate,
) -> None:
    """Designer can delete an XSLT template."""
    token = await _login_as(client, DESIGNER_USERNAME, DESIGNER_PASSWORD)
    res = await client.delete(
        f"/api/v1/xslt-templates/{seeded_xslt_template.id}", headers=_auth(token)
    )
    assert res.status_code == 204
