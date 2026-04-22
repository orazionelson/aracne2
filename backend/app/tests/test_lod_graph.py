"""Unit tests for the LOD graph builders in app.services.lod.

Pure-function tests — no DB, no HTTP, no FastAPI. They check that the
triples we promise in the public spec actually end up in the graph, that
the three output formats round-trip, and that content negotiation picks
the right rdflib format for each Accept header.
"""

from __future__ import annotations

import json
from rdflib import Graph, URIRef, Literal
from rdflib.namespace import DCTERMS, RDF, XSD

from app.services.lod import (
    SCHEMA,
    collection_to_graph,
    collection_uri,
    document_uri,
    negotiate_rdf,
    serialize_graph,
)


BASE = "https://example.org"


def test_collection_graph_has_creative_work_with_title_and_slug() -> None:
    g = collection_to_graph(base_url=BASE, slug="dante", title="Divina Commedia")
    c = collection_uri(BASE, "dante")
    assert (c, RDF.type, SCHEMA.CreativeWork) in g
    assert (c, SCHEMA.name, Literal("Divina Commedia")) in g
    assert (c, DCTERMS.title, Literal("Divina Commedia")) in g
    assert (c, SCHEMA.identifier, Literal("dante")) in g
    assert (c, SCHEMA.url, c) in g


def test_collection_graph_emits_author_and_publisher_as_nodes() -> None:
    g = collection_to_graph(
        base_url=BASE,
        slug="dante",
        title="Divina Commedia",
        author="Dante Alighieri",
        publisher="Società Dantesca Italiana",
    )
    c = collection_uri(BASE, "dante")
    # schema.org author/publisher are blank nodes with a typed name.
    authors = list(g.objects(c, SCHEMA.author))
    assert len(authors) == 1
    assert (authors[0], RDF.type, SCHEMA.Person) in g
    assert (authors[0], SCHEMA.name, Literal("Dante Alighieri")) in g

    pubs = list(g.objects(c, SCHEMA.publisher))
    assert len(pubs) == 1
    assert (pubs[0], RDF.type, SCHEMA.Organization) in g
    assert (pubs[0], SCHEMA.name, Literal("Società Dantesca Italiana")) in g

    # Dublin Core mirrors — plain literals for aggregator-friendly ingest.
    assert (c, DCTERMS.creator, Literal("Dante Alighieri")) in g
    assert (c, DCTERMS.publisher, Literal("Società Dantesca Italiana")) in g


def test_collection_graph_types_pub_year_as_xsd_gYear() -> None:
    g = collection_to_graph(base_url=BASE, slug="dante", title="Divina Commedia", pub_year=1321)
    c = collection_uri(BASE, "dante")
    expected = Literal("1321", datatype=XSD.gYear)
    assert (c, SCHEMA.datePublished, expected) in g
    assert (c, DCTERMS.issued, expected) in g


def test_collection_graph_links_documents_both_ways() -> None:
    g = collection_to_graph(
        base_url=BASE,
        slug="dante",
        title="Divina Commedia",
        documents=[
            {"filename": "inferno.xml", "title": "Inferno", "author": "Dante Alighieri"},
            {"filename": "purgatorio.xml"},  # title-less: falls back to filename
        ],
    )
    c = collection_uri(BASE, "dante")
    d1 = document_uri(BASE, "dante", "inferno.xml")
    d2 = document_uri(BASE, "dante", "purgatorio.xml")
    # hasPart from collection, isPartOf back from document — both sides.
    assert (c, SCHEMA.hasPart, d1) in g
    assert (d1, SCHEMA.isPartOf, c) in g
    assert (c, SCHEMA.hasPart, d2) in g
    assert (d2, SCHEMA.isPartOf, c) in g
    # Per-document metadata and identifier.
    assert (d1, RDF.type, SCHEMA.CreativeWork) in g
    assert (d1, SCHEMA.name, Literal("Inferno")) in g
    assert (d1, SCHEMA.identifier, Literal("inferno.xml")) in g
    # Fallback: filename is the name when title is missing.
    assert (d2, SCHEMA.name, Literal("purgatorio.xml")) in g


def test_document_uri_percent_encodes_filename() -> None:
    # Filenames with spaces or unicode should round-trip as a valid URI.
    uri = document_uri(BASE, "my-col", "carta d'amore.xml")
    assert "carta%20d%27amore.xml" in str(uri)


def test_collection_graph_skips_documents_without_filename() -> None:
    g = collection_to_graph(
        base_url=BASE,
        slug="dante",
        title="Divina Commedia",
        documents=[
            {"filename": "inferno.xml"},
            {"title": "Orphan"},  # no filename — must be ignored
        ],
    )
    c = collection_uri(BASE, "dante")
    has_parts = set(g.objects(c, SCHEMA.hasPart))
    assert has_parts == {document_uri(BASE, "dante", "inferno.xml")}


# ── Serialisation ─────────────────────────────────────────────────────────────


def _base_graph() -> Graph:
    return collection_to_graph(
        base_url=BASE,
        slug="dante",
        title="Divina Commedia",
        author="Dante Alighieri",
        pub_year=1321,
    )


def test_serialize_turtle_includes_schema_name_predicate() -> None:
    text = serialize_graph(_base_graph(), "turtle")
    assert isinstance(text, str)
    assert "schema:CreativeWork" in text or "CreativeWork" in text
    assert "Divina Commedia" in text


def test_serialize_xml_produces_rdf_document() -> None:
    text = serialize_graph(_base_graph(), "xml")
    assert isinstance(text, str)
    assert "<rdf:RDF" in text
    assert "Divina Commedia" in text


def test_serialize_json_ld_is_valid_json_with_context_or_graph() -> None:
    text = serialize_graph(_base_graph(), "json-ld")
    data = json.loads(text)
    # Compacted form returns either an object with @context or a list.
    assert data  # non-empty
    if isinstance(data, list):
        assert len(data) > 0
    else:
        assert "@context" in data or "@graph" in data


# ── Content negotiation ───────────────────────────────────────────────────────


def test_negotiate_returns_none_for_empty_or_html_accept() -> None:
    assert negotiate_rdf(None) is None
    assert negotiate_rdf("") is None
    assert negotiate_rdf("text/html") is None
    assert negotiate_rdf("application/json") is None


def test_negotiate_matches_turtle() -> None:
    assert negotiate_rdf("text/turtle") == ("turtle", "text/turtle")


def test_negotiate_matches_rdf_xml() -> None:
    assert negotiate_rdf("application/rdf+xml") == ("xml", "application/rdf+xml")


def test_negotiate_matches_json_ld() -> None:
    assert negotiate_rdf("application/ld+json") == ("json-ld", "application/ld+json")


def test_negotiate_picks_first_match_in_header() -> None:
    """When multiple types are listed, pick by our preferred order."""
    # Turtle is ordered first in RDF_FORMAT_BY_MIME so it wins.
    result = negotiate_rdf("application/rdf+xml, text/turtle")
    assert result == ("turtle", "text/turtle")


def test_negotiate_is_case_insensitive() -> None:
    assert negotiate_rdf("TEXT/TURTLE") == ("turtle", "text/turtle")
