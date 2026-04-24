"""Dataverse REST client — no network, ``httpx.MockTransport``."""

from __future__ import annotations

import json

import httpx
import pytest

from app.plugins.dataverse_integration.service import (
    DataverseClient,
    DataverseError,
    _extract_bare_doi,
)


def _client(handler) -> DataverseClient:  # type: ignore[no-untyped-def]
    return DataverseClient(
        base_url="https://demo.dataverse.org",
        api_token="fake-token",
        transport=httpx.MockTransport(handler),
    )


# ── create_dataset ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_dataset_returns_persistent_id_and_landing_url() -> None:
    captured: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["auth"] = request.headers.get("x-dataverse-key", "")
        return httpx.Response(201, json={
            "data": {
                "id": 42,
                "persistentId": "doi:10.5072/FK2/AB12CD",
            },
        })

    client = _client(handler)
    draft = await client.create_dataset(
        "tei-editions",
        {"datasetVersion": {"metadataBlocks": {"citation": {"fields": []}}}},
    )
    assert draft.persistent_id == "doi:10.5072/FK2/AB12CD"
    assert draft.database_id == 42
    assert draft.landing_url == (
        "https://demo.dataverse.org/dataset.xhtml"
        "?persistentId=doi:10.5072/FK2/AB12CD"
    )
    assert "/api/dataverses/tei-editions/datasets" in captured["url"]
    assert captured["auth"] == "fake-token"


@pytest.mark.asyncio
async def test_create_dataset_raises_on_malformed_response() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(201, json={"data": {"id": 1}})  # no persistentId

    client = _client(handler)
    with pytest.raises(DataverseError, match="persistentId"):
        await client.create_dataset("tei", {"datasetVersion": {}})


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status,expect_msg",
    [
        (401, "401"),
        (403, "403"),
        (404, "404"),
        (400, "400"),
    ],
)
async def test_create_dataset_error_mapping(status: int, expect_msg: str) -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json={"message": "nope"})

    client = _client(handler)
    with pytest.raises(DataverseError) as exc:
        await client.create_dataset("tei", {})
    assert exc.value.status_code == status
    assert expect_msg in str(exc.value)


# ── upload_file ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_upload_file_sends_multipart_with_directory_label() -> None:
    captured: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["pid_param"] = request.url.params.get("persistentId", "")
        # The body is multipart — checking it parses cleanly is the key
        # assertion. Dataverse's add endpoint expects ``file`` + optional
        # ``jsonData``; both arrive as form parts.
        body = request.content.decode("latin-1", errors="replace")
        captured["has_jsondata"] = str("jsonData" in body)
        captured["has_directory_label"] = str("directoryLabel" in body)
        captured["has_filename"] = str("style.css" in body)
        return httpx.Response(200, json={"status": "OK"})

    client = _client(handler)
    await client.upload_file(
        "doi:10.5072/FK2/X",
        "style.css",
        b"body{}",
        directory_label="css",
    )
    assert "/api/datasets/:persistentId/add" in captured["url"]
    assert captured["pid_param"] == "doi:10.5072/FK2/X"
    assert captured["has_jsondata"] == "True"
    assert captured["has_directory_label"] == "True"
    assert captured["has_filename"] == "True"


@pytest.mark.asyncio
async def test_upload_file_without_directory_label_omits_jsondata() -> None:
    captured: dict[str, bool] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        body = request.content.decode("latin-1", errors="replace")
        captured["has_jsondata"] = "jsonData" in body
        return httpx.Response(200, json={"status": "OK"})

    client = _client(handler)
    await client.upload_file("doi:x", "doc.xml", b"<a/>")
    assert captured["has_jsondata"] is False


# ── publish ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_publish_returns_published_status_with_doi() -> None:
    captured: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["type"] = request.url.params.get("type", "")
        return httpx.Response(200, json={
            "data": {
                "persistentUrl": "https://doi.org/10.5072/FK2/AB12CD",
            },
        })

    client = _client(handler)
    result = await client.publish(
        "doi:10.5072/FK2/AB12CD", publish_type="major",
    )
    assert result.status == "published"
    assert result.doi == "10.5072/FK2/AB12CD"
    assert result.landing_url.startswith("https://demo.dataverse.org/dataset.xhtml")
    assert "/actions/:publish" in captured["url"]
    assert captured["type"] == "major"


# ── DOI extraction ─────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("doi:10.5072/FK2/AB12CD", "10.5072/FK2/AB12CD"),
        ("https://doi.org/10.5072/FK2/AB12CD", "10.5072/FK2/AB12CD"),
        ("10.5072/FK2/AB12CD", "10.5072/FK2/AB12CD"),
        ("not a doi", None),
        ("", None),
    ],
)
def test_extract_bare_doi(raw: str, expected: str | None) -> None:
    assert _extract_bare_doi(raw) == expected
