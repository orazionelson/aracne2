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


def _add_person(
    g: Graph,
    subject: URIRef,
    name: str,
    *,
    orcid_by_name: dict[str, str] | None = None,
) -> None:
    """Attach a schema:Person (and a dcterms:creator literal) to *subject*.

    When ``orcid_by_name`` contains a matching entry for *name*, the
    person node also carries a ``schema:sameAs`` edge to the ORCID URI
    so harvesters can round-trip to the canonical identity. Lookup is
    case-insensitive on the author name.
    """
    person = BNode()
    g.add((person, RDF.type, SCHEMA.Person))
    g.add((person, SCHEMA.name, Literal(name)))
    g.add((subject, SCHEMA.author, person))
    g.add((subject, DCTERMS.creator, Literal(name)))
    if orcid_by_name:
        orcid = orcid_by_name.get(name.casefold()) or orcid_by_name.get(name)
        if orcid:
            g.add((person, SCHEMA.sameAs, URIRef(f"https://orcid.org/{orcid}")))


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
    orcid_by_name: dict[str, str] | None = None,
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
    # Normalise the optional ORCID map once to a case-insensitive
    # lookup dict so the per-author _add_person call is O(1).
    ci_orcid = (
        {k.casefold(): v for k, v in orcid_by_name.items()}
        if orcid_by_name
        else None
    )

    if author:
        _add_person(g, c, author, orcid_by_name=ci_orcid)
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
            _add_person(g, d, doc_author, orcid_by_name=ci_orcid)

    return g


# ── Document-level graph ─────────────────────────────────────────────────────


# Mapping from the TEI local element name stored in NamedEntity.type to the
# schema.org class a consumer expects on a ``schema:mentions`` target. TEI
# names outside this map fall back to ``schema:Thing`` — correct-but-generic.
_ENTITY_TYPE_TO_SCHEMA: dict[str, URIRef] = {
    "persName": SCHEMA.Person,
    "placeName": SCHEMA.Place,
    "orgName": SCHEMA.Organization,
}


def document_to_graph(
    *,
    base_url: str,
    slug: str,
    filename: str,
    document_title: str | None = None,
    document_author: str | None = None,
    collection_title: str | None = None,
    collection_author: str | None = None,
    collection_publisher: str | None = None,
    collection_pub_year: int | None = None,
    entities: Iterable[Mapping[str, object]] | None = None,
    orcid_by_name: dict[str, str] | None = None,
) -> Graph:
    """Build an RDF graph for a single document.

    Includes a compact re-statement of the parent collection's metadata
    (``schema:isPartOf`` to a named CreativeWork, author/publisher/date
    inherited when the document itself does not override them) so the
    document graph is self-contained — a consumer that dereferences only
    the document URI still gets enough context to cite.

    *entities* iterates over mappings with keys ``type`` (TEI local name),
    ``canonical_form`` (display label) and ``authority_ref`` (URI or
    ``None``). Every entity becomes a blank-node ``schema:mentions``
    target: ``persName`` → Person, ``placeName`` → Place, ``orgName`` →
    Organization, anything else → Thing. When ``authority_ref`` is set —
    typically a Wikidata URI inserted via the editor's LOD.1c panel —
    it is attached as ``schema:sameAs`` so downstream harvesters can
    bridge to Wikidata / VIAF / GeoNames.
    """
    g = Graph()
    _bind_common(g)
    d = document_uri(base_url, slug, filename)
    c = collection_uri(base_url, slug)

    g.add((d, RDF.type, SCHEMA.CreativeWork))
    g.add((d, SCHEMA.identifier, Literal(filename)))
    g.add((d, SCHEMA.url, d))
    g.add((d, SCHEMA.isPartOf, c))

    doc_name = document_title or filename
    g.add((d, SCHEMA.name, Literal(doc_name)))
    g.add((d, DCTERMS.title, Literal(doc_name)))

    # Parent collection — keep minimal so the graph stays light; the full
    # collection is available at its own canonical URI for consumers who
    # want more.
    if collection_title:
        g.add((c, RDF.type, SCHEMA.CreativeWork))
        g.add((c, SCHEMA.name, Literal(collection_title)))
        g.add((c, DCTERMS.title, Literal(collection_title)))

    ci_orcid = (
        {k.casefold(): v for k, v in orcid_by_name.items()}
        if orcid_by_name
        else None
    )
    author = document_author or collection_author
    if author:
        _add_person(g, d, author, orcid_by_name=ci_orcid)
    if collection_publisher:
        _add_organization(g, d, collection_publisher)
    if collection_pub_year is not None:
        year_literal = Literal(str(collection_pub_year), datatype=XSD.gYear)
        g.add((d, SCHEMA.datePublished, year_literal))
        g.add((d, DCTERMS.issued, year_literal))

    for entity in entities or []:
        type_name = entity.get("type")
        canonical = entity.get("canonical_form")
        if not isinstance(type_name, str) or not isinstance(canonical, str):
            continue
        if not canonical:
            continue
        schema_class = _ENTITY_TYPE_TO_SCHEMA.get(type_name, SCHEMA.Thing)
        node = BNode()
        g.add((node, RDF.type, schema_class))
        g.add((node, SCHEMA.name, Literal(canonical)))
        authority_ref = entity.get("authority_ref")
        if isinstance(authority_ref, str) and authority_ref:
            # schema:sameAs is the canonical way to bridge a local entity
            # representation to its authority-file URI (Wikidata Qxxx,
            # VIAF, GeoNames, …). We intentionally keep the subject as a
            # blank node so we do not implicitly claim the external URI
            # as "our" entity.
            g.add((node, SCHEMA.sameAs, URIRef(authority_ref)))
        g.add((d, SCHEMA.mentions, node))

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
