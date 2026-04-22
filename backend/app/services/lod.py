"""Linked Open Data — RDF graph builders and HTTP content negotiation.

Pure functions (no DB, no FastAPI) that turn a small plain-Python
description of a collection / document into an rdflib ``Graph`` plus a
helper to serialise it in any of the three output formats Aracne2 exposes
(Turtle, RDF/XML, JSON-LD).

Design notes:

* **Vocabularies**: schema.org as the primary predicate set (broad
  consumer support — Google, Bing, generic aggregators) with Dublin
  Core terms mirrored whenever they carry a well-known equivalent
  (``dcterms:title``, ``dcterms:creator``, ``dcterms:publisher``,
  ``dcterms:issued``). Having both keeps LOD-library consumers and
  search-engine consumers happy from the same payload.

* **There is no single canonical TEI ontology**. The user picked
  "TEI Ontology, oppure prevedere export multipli" — we deliver the
  multiple-export part (Turtle / RDF/XML / JSON-LD) and let any
  future TEI-specific mapping bolt on as additional predicates in
  a separate pass.

* **URIs**: ``{base_url}/browse/{slug}`` for a collection,
  ``{base_url}/browse/{slug}/{filename}`` for a document — these are
  the same paths the SPA already renders for humans, so the LOD URI
  doubles as a browseable human URL (content-negotiation in the
  caller picks the right representation from the Accept header).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import TypedDict
from urllib.parse import quote

from rdflib import BNode, Graph, Literal, Namespace, URIRef
from rdflib.namespace import DCTERMS, RDF, XSD

SCHEMA = Namespace("https://schema.org/")


class _DocInput(TypedDict, total=False):
    filename: str  # required
    title: str | None
    author: str | None


def collection_uri(base_url: str, slug: str) -> URIRef:
    return URIRef(f"{base_url.rstrip('/')}/browse/{slug}")


def document_uri(base_url: str, slug: str, filename: str) -> URIRef:
    return URIRef(
        f"{base_url.rstrip('/')}/browse/{slug}/{quote(filename, safe='')}"
    )


def _bind_common(g: Graph) -> None:
    g.bind("schema", SCHEMA)
    g.bind("dcterms", DCTERMS)


def _add_person(g: Graph, subject: URIRef, name: str) -> None:
    """Attach a schema:Person (and a dcterms:creator literal) to *subject*."""
    person = BNode()
    g.add((person, RDF.type, SCHEMA.Person))
    g.add((person, SCHEMA.name, Literal(name)))
    g.add((subject, SCHEMA.author, person))
    g.add((subject, DCTERMS.creator, Literal(name)))


def _add_organization(g: Graph, subject: URIRef, name: str) -> None:
    org = BNode()
    g.add((org, RDF.type, SCHEMA.Organization))
    g.add((org, SCHEMA.name, Literal(name)))
    g.add((subject, SCHEMA.publisher, org))
    g.add((subject, DCTERMS.publisher, Literal(name)))


def collection_to_graph(
    *,
    base_url: str,
    slug: str,
    title: str,
    description: str | None = None,
    author: str | None = None,
    publisher: str | None = None,
    pub_year: int | None = None,
    documents: Iterable[Mapping[str, object]] | None = None,
) -> Graph:
    """Build an RDF graph describing a single collection and its documents.

    The *documents* iterable carries per-document mappings with the keys
    ``filename`` (required), ``title`` and ``author`` (both optional).
    Each document becomes a ``schema:CreativeWork`` linked to the parent
    collection via both ``schema:hasPart`` (collection → document) and
    ``schema:isPartOf`` (document → collection) so graph traversal works
    in either direction without a JOIN.
    """
    g = Graph()
    _bind_common(g)
    c = collection_uri(base_url, slug)

    g.add((c, RDF.type, SCHEMA.CreativeWork))
    g.add((c, SCHEMA.name, Literal(title)))
    g.add((c, DCTERMS.title, Literal(title)))
    g.add((c, SCHEMA.identifier, Literal(slug)))
    g.add((c, SCHEMA.url, c))

    if description:
        g.add((c, SCHEMA.description, Literal(description)))
        g.add((c, DCTERMS.description, Literal(description)))
    if author:
        _add_person(g, c, author)
    if publisher:
        _add_organization(g, c, publisher)
    if pub_year is not None:
        year_literal = Literal(str(pub_year), datatype=XSD.gYear)
        g.add((c, SCHEMA.datePublished, year_literal))
        g.add((c, DCTERMS.issued, year_literal))

    for doc in documents or []:
        filename = doc.get("filename")
        if not filename:
            continue
        assert isinstance(filename, str)
        d = document_uri(base_url, slug, filename)
        g.add((c, SCHEMA.hasPart, d))
        g.add((d, SCHEMA.isPartOf, c))
        g.add((d, RDF.type, SCHEMA.CreativeWork))
        doc_title = doc.get("title") or filename
        assert isinstance(doc_title, str)
        g.add((d, SCHEMA.name, Literal(doc_title)))
        g.add((d, DCTERMS.title, Literal(doc_title)))
        g.add((d, SCHEMA.identifier, Literal(filename)))
        g.add((d, SCHEMA.url, d))
        doc_author = doc.get("author")
        if isinstance(doc_author, str) and doc_author:
            _add_person(g, d, doc_author)

    return g


# ── Serialisation ─────────────────────────────────────────────────────────────

# Mapping from the Accept-header mime type Aracne2 publishes to the rdflib
# format identifier passed to ``Graph.serialize``.  Ordering matters: the
# content-negotiation helper returns the FIRST mime that appears in the
# Accept header string, and Turtle is listed first as our preferred default.
RDF_FORMAT_BY_MIME: tuple[tuple[str, str], ...] = (
    ("text/turtle", "turtle"),
    ("application/rdf+xml", "xml"),
    ("application/ld+json", "json-ld"),
)


def serialize_graph(graph: Graph, fmt: str) -> str:
    """Serialise *graph* as a ``str`` in the requested format.

    rdflib returns ``bytes`` for some formats with implicit encoding —
    we normalise to ``str`` so FastAPI's ``Response`` helper can ship it
    unchanged with the right Content-Type.
    """
    # auto_compact for JSON-LD keeps the output reasonably short and
    # readable (namespace prefixes inlined as a @context block).
    kwargs: dict[str, object] = {"format": fmt}
    if fmt == "json-ld":
        kwargs["auto_compact"] = True
    result = graph.serialize(**kwargs)  # type: ignore[arg-type]
    if isinstance(result, bytes):
        return result.decode("utf-8")
    return result


def negotiate_rdf(accept: str | None) -> tuple[str, str] | None:
    """Pick the first matching RDF format for an Accept header.

    Returns ``(rdflib_format, mime_type)`` when a match is found, or
    ``None`` when the header asks for something else (HTML, JSON, …).

    Q-values are intentionally ignored: in practice LOD harvesters send
    a single explicit mime type, and the few that sort-order multiple
    types pick our preferred one (Turtle) by the ordering of
    ``RDF_FORMAT_BY_MIME``.  The trade-off keeps the function small and
    the tests obvious.
    """
    if not accept:
        return None
    lowered = accept.lower()
    for mime, fmt in RDF_FORMAT_BY_MIME:
        if mime in lowered:
            return fmt, mime
    return None
