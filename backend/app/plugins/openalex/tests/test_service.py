"""OpenAlex search service — no network, httpx.MockTransport."""

from __future__ import annotations

import httpx
import pytest

from app.plugins.openalex.service import search


def _article_row() -> dict[str, object]:
    return {
        "id": "https://openalex.org/W2741809807",
        "doi": "https://doi.org/10.7717/peerj.4375",
        "title": "Tuning the activity of iron phthalocyanine",
        "publication_year": 2018,
        "type": "article",
        "authorships": [
            {
                "author": {
                    "display_name": "Jane Doe",
                    "orcid": "https://orcid.org/0000-0002-1825-0097",
                },
            },
            {"author": {"display_name": "John Smith"}},
        ],
        "primary_location": {
            "source": {
                "display_name": "PeerJ",
                "host_organization_name": "PeerJ Inc.",
            }
        },
    }


@pytest.mark.asyncio
async def test_search_parses_article_into_biblstruct() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        return httpx.Response(200, json={"results": [_article_row()]})

    hits = await search("peerj", rows=10, transport=httpx.MockTransport(handler))
    assert len(hits) == 1
    hit = hits[0]
    p = hit.preview
    assert p.openalex_id == "W2741809807"
    assert p.uri == "https://openalex.org/W2741809807"
    assert p.doi == "10.7717/peerj.4375"
    assert p.year == 2018
    assert p.type == "journalArticle"
    assert p.container == "PeerJ"
    assert p.publisher == "PeerJ Inc."
    assert p.authors == ["Jane Doe", "John Smith"]
    # xml:id uses first author's family name + year.
    assert hit.xml_id == "bib_doe_2018"
    # biblStruct contains the DOI, OpenAlex id, journal title and dates.
    xml = hit.biblstruct_xml
    assert 'xml:id="bib_doe_2018"' in xml
    assert 'type="journalArticle"' in xml
    assert "<title level=\"a\">Tuning the activity" in xml
    assert "<title level=\"j\">PeerJ</title>" in xml
    assert "<idno type=\"DOI\">10.7717/peerj.4375</idno>" in xml
    assert "<idno type=\"OpenAlex\">W2741809807</idno>" in xml
    assert "<surname>Doe</surname>" in xml
    assert "<forename>Jane</forename>" in xml
    # ORCID @ref on persName when present.
    assert 'ref="https://orcid.org/0000-0002-1825-0097"' in xml
    # Request hit the right endpoint with the search term.
    assert "api.openalex.org/works" in str(captured["url"])
    assert "search=peerj" in str(captured["url"])


@pytest.mark.asyncio
async def test_search_with_contact_email_adds_mailto() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        return httpx.Response(200, json={"results": []})

    await search(
        "x", contact_email="editor@example.org",
        transport=httpx.MockTransport(handler),
    )
    assert "mailto=editor%40example.org" in str(captured["url"])


@pytest.mark.asyncio
async def test_search_without_email_omits_mailto() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        return httpx.Response(200, json={"results": []})

    await search("x", transport=httpx.MockTransport(handler))
    assert "mailto=" not in str(captured["url"])


@pytest.mark.asyncio
async def test_search_handles_book_type() -> None:
    row: dict[str, object] = {
        "id": "https://openalex.org/W123",
        "title": "A monograph",
        "publication_year": 2020,
        "type": "book",
        "authorships": [{"author": {"display_name": "Alex Author"}}],
        "primary_location": {
            "source": {"display_name": "Cambridge University Press"}
        },
    }

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"results": [row]})

    hits = await search("x", transport=httpx.MockTransport(handler))
    assert hits[0].preview.type == "book"
    xml = hits[0].biblstruct_xml
    # Books put the title inside <monogr>, not <analytic>.
    assert '<title level="m">A monograph</title>' in xml


@pytest.mark.asyncio
async def test_search_handles_book_section() -> None:
    row: dict[str, object] = {
        "id": "https://openalex.org/W200",
        "title": "A chapter in a book",
        "publication_year": 2021,
        "type": "book-chapter",
        "authorships": [{"author": {"display_name": "Chapter Author"}}],
        "primary_location": {"source": {"display_name": "Host Book Title"}},
    }

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"results": [row]})

    hits = await search("x", transport=httpx.MockTransport(handler))
    assert hits[0].preview.type == "bookSection"
    xml = hits[0].biblstruct_xml
    # bookSection has analytic+monogr.
    assert '<title level="a">A chapter' in xml
    assert '<title level="m">Host Book Title</title>' in xml


@pytest.mark.asyncio
async def test_search_caps_rows() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        items = [
            {
                "id": f"https://openalex.org/W{1000 + i}",
                "title": f"Work {i}",
                "publication_year": 2020,
                "type": "article",
                "authorships": [{"author": {"display_name": "Author Nobody"}}],
            }
            for i in range(20)
        ]
        return httpx.Response(200, json={"results": items})

    hits = await search("x", rows=5, transport=httpx.MockTransport(handler))
    assert len(hits) == 5


@pytest.mark.asyncio
async def test_search_skips_rows_without_id_or_title() -> None:
    rows = [
        {"title": "No id"},
        {"id": "https://openalex.org/W111"},  # no title
        {"id": "https://example.com/X", "title": "Wrong host"},
        _article_row(),
    ]

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"results": rows})

    hits = await search("x", transport=httpx.MockTransport(handler))
    assert len(hits) == 1
    assert hits[0].preview.openalex_id == "W2741809807"


@pytest.mark.asyncio
async def test_search_xml_id_falls_back_when_no_author_or_title() -> None:
    row: dict[str, object] = {
        "id": "https://openalex.org/W300",
        "title": "Anonymous medieval treatise",
        "publication_year": 1400,
        "type": "book",
        "authorships": [],
    }

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"results": [row]})

    hits = await search("x", transport=httpx.MockTransport(handler))
    # Falls back to first 3 title words.
    assert hits[0].xml_id == "bib_anonymousmedievaltreatise_1400"


@pytest.mark.asyncio
async def test_search_fail_soft_on_http_error() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    hits = await search("x", transport=httpx.MockTransport(handler))
    assert hits == []


@pytest.mark.asyncio
async def test_search_fail_soft_on_network_error() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom")

    hits = await search("x", transport=httpx.MockTransport(handler))
    assert hits == []


@pytest.mark.asyncio
async def test_search_fail_soft_on_malformed_json() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, content=b"not-json",
            headers={"Content-Type": "application/json"},
        )

    hits = await search("x", transport=httpx.MockTransport(handler))
    assert hits == []


@pytest.mark.asyncio
async def test_split_name_last_comma_or_space() -> None:
    """Round-trip a couple of author-name shapes."""
    # "Doe, Jane" → family Doe, given Jane
    row1 = {
        "id": "https://openalex.org/W1",
        "title": "Test",
        "publication_year": 2020,
        "type": "article",
        "authorships": [{"author": {"display_name": "Doe, Jane"}}],
    }
    # "Jane Doe" → family Doe, given Jane
    row2 = {
        "id": "https://openalex.org/W2",
        "title": "Test",
        "publication_year": 2020,
        "type": "article",
        "authorships": [{"author": {"display_name": "Jane Doe"}}],
    }

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"results": [row1, row2]})

    hits = await search("x", transport=httpx.MockTransport(handler))
    for hit in hits:
        assert "<surname>Doe</surname>" in hit.biblstruct_xml
        assert "<forename>Jane</forename>" in hit.biblstruct_xml
