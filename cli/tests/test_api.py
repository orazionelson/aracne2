"""Tests for the ApiClient envelope/header behaviour."""

from __future__ import annotations

import httpx
import pytest

from aracne_cli.api import ApiClient, ApiError


def test_get_unwraps_data_envelope(mock_backend) -> None:
    transport = mock_backend(
        {
            ("GET", "/api/v1/auth/me"): httpx.Response(
                status_code=200, json={"data": {"username": "alice"}}
            ),
        }
    )
    with ApiClient("http://h", "tok", transport=transport) as client:
        body = client.get("/auth/me")
    assert body == {"username": "alice"}


def test_get_injects_bearer_header(mock_backend) -> None:
    seen: list[str | None] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.headers.get("Authorization"))
        return httpx.Response(status_code=200, json={"data": {}})

    transport = mock_backend({("GET", "/api/v1/auth/me"): handler})
    with ApiClient("http://h", "aracne2_pat_xyz", transport=transport) as client:
        client.get("/auth/me")
    assert seen == ["Bearer aracne2_pat_xyz"]


def test_post_raises_apierror_on_4xx(mock_backend) -> None:
    transport = mock_backend(
        {
            ("POST", "/api/v1/x"): httpx.Response(
                status_code=409,
                json={
                    "error": {
                        "code": "DOCUMENT_BUSY",
                        "message": "Try again later",
                        "details": {},
                    }
                },
            ),
        }
    )
    with ApiClient("http://h", "tok", transport=transport) as client:
        with pytest.raises(ApiError) as excinfo:
            client.post("/x", json={})
    assert excinfo.value.code == "DOCUMENT_BUSY"
    assert excinfo.value.status_code == 409


def test_delete_returns_none_on_204(mock_backend) -> None:
    transport = mock_backend(
        {("DELETE", "/api/v1/x"): httpx.Response(status_code=204)}
    )
    with ApiClient("http://h", "tok", transport=transport) as client:
        result = client.delete("/x")
    assert result is None


def test_get_raw_returns_response(mock_backend) -> None:
    transport = mock_backend(
        {
            ("GET", "/api/v1/raw"): httpx.Response(
                status_code=200,
                content=b"<TEI/>",
                headers={"Content-Type": "application/xml"},
            ),
        }
    )
    with ApiClient("http://h", "tok", transport=transport) as client:
        response = client.get_raw("/raw")
    assert response.status_code == 200
    assert response.content == b"<TEI/>"
