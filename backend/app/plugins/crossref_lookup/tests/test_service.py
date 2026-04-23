"""Tests for the CrossRef DOI resolver.

Covers the pure mapping layer (``crossref_to_biblstruct``) directly, plus
``resolve_doi`` end-to-end using ``httpx.MockTransport`` so no network is
needed. The HTTP endpoint test validates the ACL + error mapping only —
we do not re-exercise the mapping through the router.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from typing import Any

import httpx
import pytest

from app.core.exceptions import ExternalServiceError, NotFoundError
from app.plugins.crossref_lookup import service as crossref
from app.plugins.crossref_lookup.service import (
    crossref_to_biblstruct,
    looks_like_doi,
    resolve_doi,
)


# ── looks_like_doi ──────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "candidate,expected",
    [
        ("10.1234/xyz", True),
        ("10.1016/j.jhist.2020.05.001", True),
        ("10.5281/zenodo.42", True),
        ("https://doi.org/10.1234/xyz", False),  # the resolver strips the prefix first
        ("not-a-doi", False),
        ("", False),
        ("10.12/ab(cd)", True),  # parentheses allowed in DOI path
    ],
)
def test_looks_like_doi(candidate: str, expected: bool) -> None:
    assert looks_like_doi(candidate) is expected


# ── crossref_to_biblstruct — pure mapping ───────────────────────────────────


def _parse(xml: str) -> ET.Element:
    return ET.fromstring(xml)


def test_mapping_journal_article_happy_path() -> None:
    message: dict[str, Any] = {
        "type": "journal-article",
        "DOI": "10.1234/xyz",
        "title": ["The Rise of X"],
        "author": [
            {"given": "John", "family": "Smith", "sequence": "first"},
            {"given": "A.", "family": "Doe"},
        ],
        "container-title": ["Journal of Y"],
        "publisher": "Springer",
        "publisher-location": "Berlin",
        "volume": "12",
        "issue": "3",
        "page": "45-67",
        "issued": {"date-parts": [[1998, 6, 15]]},
    }
    result = crossref_to_biblstruct(message)
    root = _parse(result.biblstruct_xml)

    assert root.get("type") == "journalArticle"
    # ET parses xml:id into the reserved XML namespace; re-reading via the
    # literal key returns None. Either query by Clark name, or check the raw
    # XML string — we do both to pin down the expected serialisation.
    assert root.get("{http://www.w3.org/XML/1998/namespace}id") == "bib_smith_1998"
    assert 'xml:id="bib_smith_1998"' in result.biblstruct_xml
    assert result.xml_id == "bib_smith_1998"

    analytic = root.find("analytic")
    assert analytic is not None
    authors = analytic.findall("author")
    assert len(authors) == 2
    assert authors[0].find("persName/surname").text == "Smith"  # type: ignore[union-attr]
    assert authors[0].find("persName/forename").text == "John"  # type: ignore[union-attr]
    a_title = analytic.find("title")
    assert a_title is not None and a_title.get("level") == "a"
    assert a_title.text == "The Rise of X"

    monogr = root.find("monogr")
    assert monogr is not None
    j_title = monogr.find("title")
    assert j_title is not None and j_title.get("level") == "j"
    assert j_title.text == "Journal of Y"

    imprint = monogr.find("imprint")
    assert imprint is not None
    assert imprint.find("pubPlace").text == "Berlin"  # type: ignore[union-attr]
    assert imprint.find("publisher").text == "Springer"  # type: ignore[union-attr]
    assert imprint.find("date").get("when") == "1998"  # type: ignore[union-attr]

    scopes = {s.get("unit"): s.text for s in monogr.findall("biblScope")}
    assert scopes == {"volume": "12", "issue": "3", "page": "45-67"}

    idnos = {idno.get("type"): idno.text for idno in root.findall("idno")}
    assert idnos == {"DOI": "10.1234/xyz"}

    assert result.preview.title == "The Rise of X"
    assert result.preview.authors == ["John Smith", "A. Doe"]
    assert result.preview.year == 1998
    assert result.preview.container == "Journal of Y"


def test_mapping_book_places_author_on_monogr() -> None:
    message: dict[str, Any] = {
        "type": "book",
        "DOI": "10.1000/bookdoi",
        "title": ["Book Title"],
        "author": [{"given": "J.", "family": "Smith"}],
        "publisher": "Routledge",
        "publisher-location": "London",
        "issued": {"date-parts": [[2000]]},
        "ISBN": ["978-0-00-000000-0"],
    }
    result = crossref_to_biblstruct(message)
    root = _parse(result.biblstruct_xml)

    assert root.get("type") == "book"
    assert root.find("analytic") is None  # no analytic for book

    monogr = root.find("monogr")
    assert monogr is not None
    # Author directly under monogr, not analytic.
    assert monogr.find("author/persName/surname").text == "Smith"  # type: ignore[union-attr]
    # Title level="m".
    t = monogr.find("title")
    assert t is not None and t.get("level") == "m"
    assert t.text == "Book Title"

    idnos = {idno.get("type"): idno.text for idno in root.findall("idno")}
    assert idnos["DOI"] == "10.1000/bookdoi"
    assert idnos["ISBN"] == "978-0-00-000000-0"


def test_mapping_book_chapter_has_analytic_plus_host() -> None:
    message: dict[str, Any] = {
        "type": "book-chapter",
        "DOI": "10.2000/chap",
        "title": ["Chapter Title"],
        "author": [{"given": "A.", "family": "Author"}],
        "container-title": ["Host Book"],
        "publisher": "Cambridge UP",
        "issued": {"date-parts": [[2005]]},
        "page": "100-120",
    }
    result = crossref_to_biblstruct(message)
    root = _parse(result.biblstruct_xml)

    assert root.get("type") == "bookSection"
    assert root.find("analytic") is not None
    assert root.find("analytic/title").get("level") == "a"  # type: ignore[union-attr]

    monogr = root.find("monogr")
    assert monogr is not None
    host_title = monogr.find("title")
    assert host_title is not None
    assert host_title.get("level") == "m"
    assert host_title.text == "Host Book"
    scope = monogr.find("biblScope[@unit='page']")
    assert scope is not None and scope.text == "100-120"


def test_mapping_unknown_type_falls_back_to_other() -> None:
    message: dict[str, Any] = {
        "type": "posted-content",
        "DOI": "10.1/preprint",
        "title": ["A Preprint"],
        "author": [{"given": "X.", "family": "Y"}],
        "issued": {"date-parts": [[2023]]},
    }
    result = crossref_to_biblstruct(message)
    root = _parse(result.biblstruct_xml)
    assert root.get("type") == "other"
    # No analytic — the "other" type follows the book layout.
    assert root.find("analytic") is None
    assert root.find("monogr/title").get("level") == "m"  # type: ignore[union-attr]


def test_mapping_prefers_published_print_over_issued() -> None:
    message: dict[str, Any] = {
        "type": "journal-article",
        "title": ["x"],
        "author": [{"family": "Smith"}],
        "issued": {"date-parts": [[1990]]},
        "published-print": {"date-parts": [[1992, 3]]},
    }
    result = crossref_to_biblstruct(message)
    assert result.preview.year == 1992


def test_mapping_xml_id_falls_back_to_title_words_when_no_author() -> None:
    message: dict[str, Any] = {
        "type": "book",
        "title": ["Grammar of Old Occitan"],
        "issued": {"date-parts": [[1975]]},
    }
    result = crossref_to_biblstruct(message)
    # First three words ("Grammar", "of", "Old") joined, lowercased, ASCII-slugged.
    # "Occitan" is dropped because we cap at 3 tokens to keep ids short.
    assert result.xml_id == "bib_grammarofold_1975"


def test_mapping_empty_author_list_is_tolerated() -> None:
    message: dict[str, Any] = {
        "type": "journal-article",
        "title": ["x"],
        "author": [],
        "issued": {"date-parts": [[2001]]},
    }
    result = crossref_to_biblstruct(message)
    root = _parse(result.biblstruct_xml)
    # Analytic still present but without <author> children.
    assert root.find("analytic") is not None
    assert root.find("analytic/author") is None


def test_mapping_unicode_surname_is_ascii_slugged() -> None:
    message: dict[str, Any] = {
        "type": "book",
        "title": ["x"],
        "author": [{"family": "Büchi", "given": "Rémy"}],
        "issued": {"date-parts": [[2019]]},
    }
    result = crossref_to_biblstruct(message)
    assert result.xml_id == "bib_buchi_2019"


# ── resolve_doi — httpx.MockTransport ───────────────────────────────────────


def _mock_client(handler: httpx.MockTransport) -> None:
    """Patch the module-level httpx.AsyncClient to use *handler*."""
    # resolve_doi opens a fresh AsyncClient each call; we swap the
    # AsyncClient class on the service module so the call picks up the
    # test transport without any public API change.


@pytest.mark.asyncio
async def test_resolve_doi_success(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/works/10.1234/xyz"
        assert "Aracne2" in request.headers["User-Agent"]
        assert "mailto:ops@example.org" in request.headers["User-Agent"]
        return httpx.Response(
            200,
            json={
                "message": {
                    "type": "journal-article",
                    "DOI": "10.1234/xyz",
                    "title": ["T"],
                    "author": [{"given": "A", "family": "B"}],
                    "issued": {"date-parts": [[2020]]},
                }
            },
        )

    transport = httpx.MockTransport(handler)
    _install_transport(monkeypatch, transport)

    result = await resolve_doi("10.1234/xyz", contact_email="ops@example.org")
    assert result.preview.doi == "10.1234/xyz"
    assert result.preview.year == 2020


@pytest.mark.asyncio
async def test_resolve_doi_404_raises_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(404, text="Resource not found.")

    _install_transport(monkeypatch, httpx.MockTransport(handler))
    with pytest.raises(NotFoundError):
        await resolve_doi("10.1234/xyz")


@pytest.mark.asyncio
async def test_resolve_doi_5xx_raises_external_service_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="Service unavailable.")

    _install_transport(monkeypatch, httpx.MockTransport(handler))
    with pytest.raises(ExternalServiceError):
        await resolve_doi("10.1234/xyz")


@pytest.mark.asyncio
async def test_resolve_doi_strips_doi_prefix(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        return httpx.Response(
            200,
            json={
                "message": {
                    "type": "book",
                    "DOI": "10.9/abc",
                    "title": ["x"],
                    "author": [{"family": "Z"}],
                    "issued": {"date-parts": [[1900]]},
                }
            },
        )

    _install_transport(monkeypatch, httpx.MockTransport(handler))
    await resolve_doi("https://doi.org/10.9/abc")
    assert captured["path"] == "/works/10.9/abc"


@pytest.mark.asyncio
async def test_resolve_doi_rejects_malformed_input() -> None:
    with pytest.raises(ExternalServiceError):
        await resolve_doi("not-a-doi")


# ── Test helper ─────────────────────────────────────────────────────────────


def _install_transport(
    monkeypatch: pytest.MonkeyPatch, transport: httpx.MockTransport
) -> None:
    """Make the service module open AsyncClients backed by *transport*.

    We replace ``httpx.AsyncClient`` inside the service module with a
    thin factory that forwards every kwarg but forces the transport —
    keeps the production call signature untouched.
    """
    real_cls = crossref.httpx.AsyncClient

    def factory(*args: object, **kwargs: object) -> httpx.AsyncClient:
        kwargs["transport"] = transport
        return real_cls(*args, **kwargs)

    monkeypatch.setattr(crossref.httpx, "AsyncClient", factory)
