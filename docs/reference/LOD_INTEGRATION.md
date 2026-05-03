# Linked Open Data — Technical Reference

Aracne2 ships LOD as a track of incremental features. This page is the
single reference for what is wired, what the vocabularies are, and how a
consumer (search engine, aggregator, research harvester) dereferences
the public corpus.

Roadmap and status:

| Step  | Feature                                     | Status       |
|-------|---------------------------------------------|--------------|
| LOD.1 | Inbound entity linking (Wikidata → `@ref`)  | ✅ shipped    |
| LOD.2 | JSON-LD schema.org in public SPA pages      | ✅ shipped    |
| LOD.3 | RDF export with content negotiation         | ✅ shipped    |
| LOD.4 | SPARQL endpoint                             | 🟢 deferred — see [TO_DO.md](../TO_DO.md) |

---

## LOD.1 — Inbound entity linking

Editor-driven. In the TEI editor (`DocumentEditView.vue`) a **globe-icon
sidebar** lets the editor put the cursor inside a `<persName>`,
`<placeName>` or `<orgName>`, search Wikidata and apply a canonical URI
as the `@ref` attribute in one click.

Backend: `GET /api/v1/wikidata/search?q=&lang=&limit=` — authenticated
proxy over the public `wbsearchentities` API, rate-limited, fail-soft.
Returns structured `WikidataHit(qid, label, description, uri)` where
`uri` is the Wikidata `concepturi` (`http://www.wikidata.org/entity/Qxxx`)
— paste-ready for `@ref`.

Storage: the existing `named_entities` plugin already ingests the `@ref`
attribute at reindex time and stores it on `NamedEntity.authority_ref`
(pre-provisioned from the VIAF/GeoNames work, the Wikidata URI shape
fits through the same pipeline without migrations).

See:
- [`backend/app/routers/wikidata.py`](../../backend/app/routers/wikidata.py)
- [`frontend/src/components/ui/WikidataLinkPanel.vue`](../../frontend/src/components/ui/WikidataLinkPanel.vue)
- [`frontend/src/composables/useCodeMirror.ts`](../../frontend/src/composables/useCodeMirror.ts) § `insertEntityRef`

---

## LOD.2 — schema.org JSON-LD in public SPA pages

Every public route emits one `<script type="application/ld+json"
id="aracne-jsonld">` block in `<head>`. Re-used across routes via the
`useJsonLd(source)` composable so navigation overwrites cleanly with no
stacking.

| Route              | schema.org type     | Key fields                                      |
|--------------------|---------------------|-------------------------------------------------|
| `/`                | `WebSite`           | `name`, `url`                                    |
| `/browse/:slug`    | `CreativeWork`      | `name`, `description`, `author`, `publisher`, `datePublished`, `hasPart[]` |
| `/browse/:slug/:f` | `CreativeWork`      | `name`, `isPartOf`, `author` (doc or collection), `datePublished` |

`CreativeWork` is the base type rather than `Book` / `ScholarlyArticle`
because TEI corpora range across genres and the superclass never
mis-classifies.

Implementation: [`frontend/src/composables/useJsonLd.ts`](../../frontend/src/composables/useJsonLd.ts).

---

## LOD.3 — RDF export with content negotiation

The same public URLs double as dereferenceable LOD resources. An HTTP
client sets the `Accept` header and the backend returns the appropriate
RDF serialisation — no separate `/rdf` endpoint, no file-extension dance.

### Endpoints and Accept values

| Endpoint                                              | Accept             | Returns                                                                 |
|-------------------------------------------------------|--------------------|-------------------------------------------------------------------------|
| `GET /api/v1/public/collections/{slug}`               | `text/turtle`      | Turtle RDF describing the collection + its documents                    |
|                                                       | `application/rdf+xml` | RDF/XML, same graph                                                  |
|                                                       | `application/ld+json` | JSON-LD (auto-compacted), same graph                                 |
|                                                       | `application/json` / `*/*` / missing | Existing SPA envelope `{"data": PublicCollectionDetail}` |
| `GET /api/v1/public/collections/{slug}/documents/{file}` | `text/turtle`      | Turtle RDF for the document incl. `schema:mentions` with Wikidata sameAs |
|                                                       | `application/rdf+xml` | RDF/XML                                                              |
|                                                       | `application/ld+json` | JSON-LD                                                              |
|                                                       | anything else      | Existing XSLT-rendered HTML                                             |

Negotiation: `services.lod.negotiate_rdf()` — simple greedy match; Turtle
wins when multiple RDF types are listed (Q-values intentionally ignored,
trade-off documented in the module).

### Vocabularies

Two vocabularies emitted together so both search-engine and
library-aggregator consumers get what they expect:

- **schema.org** as the primary predicate set (consumer-facing,
  Google / Bing understand it natively).
- **Dublin Core terms** mirrored where a well-known DC equivalent exists
  (`dcterms:title`, `dcterms:creator`, `dcterms:publisher`,
  `dcterms:issued`, `dcterms:description`).

### URI shape

- Collection URI: `{origin}/browse/{slug}`
- Document URI: `{origin}/browse/{slug}/{filename}` (filename
  percent-encoded)
- Entity subjects: **blank nodes** carrying `schema:name` +
  `schema:sameAs` → authority URI. Not using the Wikidata URI directly
  as the subject avoids implicitly claiming Wikidata entities as "our"
  entities; `sameAs` is the idiomatic bridge.

`{origin}` is derived from the request (`request.url.scheme` +
`request.url.netloc`). Production behind a reverse proxy with
`X-Forwarded-*` headers resolves to the real canonical public URL;
in local dev the backend port leaks in — LOD consumers testing
locally understand that.

### Example — Turtle for a collection

```turtle
@prefix schema: <https://schema.org/> .
@prefix dcterms: <http://purl.org/dc/terms/> .
@prefix xsd:    <http://www.w3.org/2001/XMLSchema#> .

<https://example.org/browse/dante> a schema:CreativeWork ;
    schema:name "Divina Commedia" ;
    dcterms:title "Divina Commedia" ;
    schema:identifier "dante" ;
    schema:author [ a schema:Person ; schema:name "Dante Alighieri" ] ;
    dcterms:creator "Dante Alighieri" ;
    schema:datePublished "1321"^^xsd:gYear ;
    dcterms:issued      "1321"^^xsd:gYear ;
    schema:hasPart <https://example.org/browse/dante/inferno.xml> .
```

### Example — Turtle for a document with a linked entity

```turtle
<https://example.org/browse/dante/inferno.xml> a schema:CreativeWork ;
    schema:name "Inferno" ;
    schema:identifier "inferno.xml" ;
    schema:isPartOf <https://example.org/browse/dante> ;
    schema:mentions [
        a schema:Person ;
        schema:name "Dante Alighieri" ;
        schema:sameAs <http://www.wikidata.org/entity/Q1067>
    ] .
```

### Quick consumer checks

```bash
# Turtle, collection
curl -H "Accept: text/turtle" https://example.org/api/v1/public/collections/dante

# JSON-LD, document
curl -H "Accept: application/ld+json" \
  https://example.org/api/v1/public/collections/dante/documents/inferno.xml

# Default still JSON (SPA behaviour preserved)
curl https://example.org/api/v1/public/collections/dante
```

### Implementation

- [`backend/app/services/lod.py`](../../backend/app/services/lod.py) —
  pure functions: `collection_to_graph`, `document_to_graph`,
  `serialize_graph`, `negotiate_rdf`. No FastAPI, no DB — trivial to
  unit-test.
- [`backend/app/routers/public_view.py`](../../backend/app/routers/public_view.py) —
  `public_collection_detail` and `public_document_render` branch on the
  Accept header.
- Tests: `backend/app/tests/test_lod_graph.py` (21 cases) +
  `backend/app/tests/test_public_view.py` (6 content-neg cases).

### Out of scope for v1

- **Content negotiation on the SPA URL** `/browse/{slug}`: would need
  nginx or an SSR layer to route by Accept. Today the LOD URLs live
  under `/api/v1/public/...`; a reverse-proxy rule can later map the
  two together so the "canonical URL" truly resolves to both HTML and
  RDF from the same path.
- **TEI-specific ontology** beyond schema.org + DC. There is no single
  canonical TEI ontology; the project ships the multiple-export path
  (Turtle/RDF-XML/JSON-LD) so any downstream CIDOC-CRM / TEI-Ontology
  mapping can bolt on as an additional graph builder without touching
  the endpoint.
- **SPARQL**: see [TO_DO.md](../TO_DO.md).
