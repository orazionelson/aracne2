# OAI-PMH Provider — Reference Documentation

## Overview

The OAI-PMH Provider is a native Aracne2 plugin that exposes published collections
as a standard **OAI-PMH 2.0** (Open Archives Initiative Protocol for Metadata
Harvesting) repository. This makes the platform's content machine-harvestable by
external aggregators such as OpenDOAR, BASE, Europeana, DART, and national
cultural heritage portals.

The plugin adds a single public HTTP endpoint:

```
GET /api/v1/oai?verb=<Verb>[&param=value…]
```

No authentication is required. The endpoint always returns `application/xml`.

---

## Source files

| File | Purpose |
|------|---------|
| `backend/app/plugins/_native/oai_pmh/plugin.py` | Plugin class registered with the plugin loader |
| `backend/app/plugins/_native/oai_pmh/router.py` | FastAPI router — single GET endpoint, parameter parsing |
| `backend/app/plugins/_native/oai_pmh/service.py` | All OAI-PMH logic — XML builder, verb handlers, DC mapping |
| `backend/app/xqueries/oai_pmh/get_dc_meta.xq`   | XQuery that extracts Dublin Core fields from a TEI document |

---

## Protocol summary

OAI-PMH is a lightweight HTTP protocol. Every request is a `GET` to the repository
base URL with a mandatory `verb` parameter. The server always responds with a
well-formed XML document in the `http://www.openarchives.org/OAI/2.0/` namespace.

### Data model concepts

| OAI-PMH concept | Aracne2 equivalent |
|-----------------|--------------------|
| Repository      | The Aracne2 installation |
| Set             | One published public Collection (`status=published`, `is_public=true`) |
| Record          | One XML document stored in eXist-db |
| Identifier      | `oai:{hostname}:{slug}/{filename}` |
| Datestamp       | `collection.updated_at` of the containing collection |
| Metadata format | `oai_dc` (Dublin Core) — the only supported format |

### Supported verbs

| Verb | Required params | Optional params |
|------|-----------------|-----------------|
| `Identify` | — | — |
| `ListMetadataFormats` | — | `identifier` |
| `ListSets` | — | — |
| `ListIdentifiers` | `metadataPrefix` | `set`, `from`, `until`, `resumptionToken`* |
| `ListRecords` | `metadataPrefix` | `set`, `from`, `until`, `resumptionToken`* |
| `GetRecord` | `identifier`, `metadataPrefix` | — |

\* `resumptionToken` is mutually exclusive with all selective harvesting parameters
(`set`, `from`, `until`). When a token is present the other parameters are ignored.

---

## Request / Response examples

### Identify

```
GET /api/v1/oai?verb=Identify
```

```xml
<?xml version="1.0" encoding="UTF-8"?>
<OAI-PMH xmlns="http://www.openarchives.org/OAI/2.0/"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://www.openarchives.org/OAI/2.0/ http://www.openarchives.org/OAI/2.0/OAI-PMH.xsd">
  <responseDate>2026-04-09T10:00:00Z</responseDate>
  <request verb="Identify">https://example.com/api/v1/oai</request>
  <Identify>
    <repositoryName>Aracne2 OAI-PMH Repository</repositoryName>
    <baseURL>https://example.com/api/v1/oai</baseURL>
    <protocolVersion>2.0</protocolVersion>
    <adminEmail>admin@example.com</adminEmail>
    <earliestDatestamp>2026-01-15T09:30:00Z</earliestDatestamp>
    <deletedRecord>no</deletedRecord>
    <granularity>YYYY-MM-DDThh:mm:ssZ</granularity>
  </Identify>
</OAI-PMH>
```

`repositoryName` is `{PLATFORM_NAME} OAI-PMH Repository` where `PLATFORM_NAME`
comes from `settings.platform_name` (env var). `adminEmail` comes from
`settings.admin_email`. `earliestDatestamp` is computed as
`MIN(collection.published_at)` across all published public collections.

---

### ListSets

```
GET /api/v1/oai?verb=ListSets
```

Returns one `<set>` per collection with `status=published` and `is_public=true`.
Sets are ordered by `published_at` ascending.

```xml
<ListSets>
  <set>
    <setSpec>dante</setSpec>
    <setName>Opere di Dante Alighieri</setName>
    <setDescription>
      <oai_dc:dc xmlns:oai_dc="http://www.openarchives.org/OAI/2.0/oai_dc/"
                 xmlns:dc="http://purl.org/dc/elements/1.1/">
        <dc:description>Critical edition of Dante's complete works</dc:description>
      </oai_dc:dc>
    </setDescription>
  </set>
</ListSets>
```

`setSpec` is the collection slug. `setDescription` is only emitted when the
collection has a non-empty description field.

Error returned if no published public collections exist: `noSetHierarchy`.

---

### ListMetadataFormats

```
GET /api/v1/oai?verb=ListMetadataFormats
GET /api/v1/oai?verb=ListMetadataFormats&identifier=oai:example.com:dante/inferno.xml
```

Currently returns only `oai_dc`. When `identifier` is provided the syntax is
validated; if invalid, `idDoesNotExist` is returned. The format list is the same
regardless of which record is queried because `oai_dc` is supported for all
records.

```xml
<ListMetadataFormats>
  <metadataFormat>
    <metadataPrefix>oai_dc</metadataPrefix>
    <schema>http://www.openarchives.org/OAI/2.0/oai_dc.xsd</schema>
    <metadataNamespace>http://www.openarchives.org/OAI/2.0/oai_dc/</metadataNamespace>
  </metadataFormat>
</ListMetadataFormats>
```

---

### ListIdentifiers

```
GET /api/v1/oai?verb=ListIdentifiers&metadataPrefix=oai_dc
GET /api/v1/oai?verb=ListIdentifiers&metadataPrefix=oai_dc&set=dante
GET /api/v1/oai?verb=ListIdentifiers&metadataPrefix=oai_dc&from=2026-01-01&until=2026-04-09
```

Returns record headers only (no metadata). Each `<header>` contains:

- `<identifier>` — the OAI identifier for the record
- `<datestamp>` — `collection.updated_at` formatted as `YYYY-MM-DDThh:mm:ssZ`
- `<setSpec>` — the collection slug

```xml
<ListIdentifiers>
  <header>
    <identifier>oai:example.com:dante/inferno.xml</identifier>
    <datestamp>2026-03-22T14:05:00Z</datestamp>
    <setSpec>dante</setSpec>
  </header>
  <header>
    <identifier>oai:example.com:dante/purgatorio.xml</identifier>
    <datestamp>2026-03-22T14:05:00Z</datestamp>
    <setSpec>dante</setSpec>
  </header>
  <resumptionToken completeListSize="2" cursor="0"/>
</ListIdentifiers>
```

The empty `<resumptionToken>` on the last page signals that the list is complete
(required by the OAI-PMH spec even when there is no continuation).

---

### ListRecords

```
GET /api/v1/oai?verb=ListRecords&metadataPrefix=oai_dc
GET /api/v1/oai?verb=ListRecords&metadataPrefix=oai_dc&set=dante&from=2026-01-01
```

Same as `ListIdentifiers` but each `<record>` also contains a `<metadata>` child
with the Dublin Core element. Each record's DC metadata is assembled by merging
two data sources in priority order (see "Dublin Core metadata" section below).

```xml
<ListRecords>
  <record>
    <header>
      <identifier>oai:example.com:dante/inferno.xml</identifier>
      <datestamp>2026-03-22T14:05:00Z</datestamp>
      <setSpec>dante</setSpec>
    </header>
    <metadata>
      <oai_dc:dc xmlns:oai_dc="http://www.openarchives.org/OAI/2.0/oai_dc/"
                 xmlns:dc="http://purl.org/dc/elements/1.1/"
                 xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
                 xsi:schemaLocation="http://www.openarchives.org/OAI/2.0/oai_dc/ http://www.openarchives.org/OAI/2.0/oai_dc.xsd">
        <dc:title>Inferno</dc:title>
        <dc:creator>Dante Alighieri</dc:creator>
        <dc:publisher>Aracne2 Project</dc:publisher>
        <dc:date>1308</dc:date>
        <dc:description>Prima cantica della Divina Commedia</dc:description>
        <dc:language>it</dc:language>
        <dc:type>Text</dc:type>
        <dc:format>application/xml</dc:format>
        <dc:identifier>oai:example.com:dante/inferno.xml</dc:identifier>
        <dc:source>Firenze, 1308</dc:source>
      </oai_dc:dc>
    </metadata>
  </record>
  <resumptionToken completeListSize="2" cursor="0"/>
</ListRecords>
```

---

### GetRecord

```
GET /api/v1/oai?verb=GetRecord&identifier=oai:example.com:dante/inferno.xml&metadataPrefix=oai_dc
```

Returns a single record. Validates:
1. Identifier syntax (`oai:{host}:{slug}/{filename}`)
2. Collection exists, is published, and is public
3. Document file exists in eXist-db

Returns `idDoesNotExist` if any check fails.

---

## OAI identifier scheme

```
oai:{hostname}:{collection_slug}/{filename}
```

- `hostname` is extracted from the OAI base URL at request time via `urlparse`.
- `collection_slug` is the collection's unique slug (e.g. `dante`).
- `filename` is the XML document filename as stored in eXist-db (e.g. `inferno.xml`).

Examples:

```
oai:aracne2.example.com:dante/inferno.xml
oai:aracne2.example.com:vasari/vite.xml
```

**Stability**: identifiers are stable as long as the hostname, collection slug,
and filename do not change. Renaming a collection slug or moving a file will
break existing harvested identifiers — harvesters will treat the new identifier
as a new record.

---

## Dublin Core metadata — assembly logic

For each record, Dublin Core metadata is assembled by merging two data sources.
TEI header values always take priority over PostgreSQL collection-level metadata.

### Data source 1 — TEI header (via XQuery)

The XQuery `oai_pmh/get_dc_meta.xq` is executed against the document in
eXist-db and extracts:

| XQuery output tag | TEI path (local-name matching, namespace-agnostic) |
|-------------------|----------------------------------------------------|
| `title`           | `teiHeader/fileDesc/titleStmt/title[1]` |
| `creator`         | `teiHeader/fileDesc/titleStmt/author` (all instances) |
| `publisher`       | `teiHeader/fileDesc/publicationStmt/publisher[1]` |
| `date`            | `teiHeader/fileDesc/publicationStmt/date/@when` (or element text) |
| `language`        | `teiHeader/profileDesc/langUsage/language/@ident[1]` |
| `description`     | `teiHeader/profileDesc/abstract[1]` |

The XQuery uses `local-name()` matching so it works regardless of whether the
document declares the TEI namespace (`http://www.tei-c.org/ns/1.0`) or not.
For `date`, it prefers the machine-readable `@when` attribute over the text
content of the element.

If the XQuery call fails for any reason (document not well-formed, eXist-db
unavailable, timeout), the service falls back silently to source 2 and logs a
`WARNING` event `oai_pmh_tei_dc_failed`.

### Data source 2 — PostgreSQL collection metadata (fallback)

When a TEI field is absent or the XQuery fails, the corresponding value is taken
from the collection row in PostgreSQL:

| DC field | Collection column | Notes |
|----------|-------------------|-------|
| `title` | `collection.title` | Always present |
| `creator` | `collection.author` | Optional |
| `contributor` | `collection.resp_stmts` (JSONB array) | Each entry: `{name, resp}` |
| `publisher` | `collection.publisher` | Optional |
| `date` | `collection.pub_year` → `collection.published_at` | Cascading fallback |
| `description` | `collection.description` | Optional |
| `language` | — | No fallback; omitted if not in TEI |
| `source` | `collection.pub_place + collection.pub_year` | Omitted if both absent |

### Fixed DC fields

These fields are always present regardless of the document content:

| DC field | Value |
|----------|-------|
| `dc:type` | `Text` |
| `dc:format` | `application/xml` |
| `dc:identifier` | The full OAI identifier of the record |

---

## Pagination — resumption tokens

`ListIdentifiers` and `ListRecords` paginate results in pages of 100 records
(`PAGE_SIZE = 100`).

### Token format

A resumption token is a **base64url-encoded JSON object** with the following fields:

```json
{
  "metadataPrefix": "oai_dc",
  "offset": 100,
  "set": "dante",
  "from": "2026-01-01T00:00:00Z",
  "until": "2026-12-31T23:59:59Z"
}
```

`set`, `from`, and `until` are included only when those filters were active in
the original request. `metadataPrefix` is always stored so subsequent pages
use the same format.

### Token lifecycle

1. **First request**: `offset=0`, no token. After processing page 0, if more
   records remain, a token with `offset=100` is embedded in the response.
2. **Subsequent requests**: harvester sends `resumptionToken=<token>`. Other
   params are ignored. The handler decodes the token, re-runs the full query with
   stored filters, and slices from the stored offset.
3. **Final page**: response includes an empty `<resumptionToken>` element
   (no text content) with `completeListSize` and `cursor` attributes. This
   signals that the list is complete, as required by the OAI-PMH spec.

### Re-query on each page

Each page request re-queries both PostgreSQL (for collections) and eXist-db (for
filenames). This ensures consistency: if a document was added or removed between
page requests, the re-query reflects the current state. The trade-off is that
there is no server-side session state, but the results may be slightly
inconsistent across pages if the repository changes during harvesting. This is
standard behaviour for stateless OAI-PMH repositories.

---

## Date filtering — `from` / `until`

Date parameters support both granularities:

- Date: `YYYY-MM-DD` (e.g. `2026-01-15`)
- DateTime: `YYYY-MM-DDThh:mm:ssZ` (e.g. `2026-01-15T09:30:00Z`)

Filtering is applied at the **collection level** using `collection.updated_at`.
All documents in a collection share the same datestamp. This means:

- A collection updated on `2026-03-22` will have all its documents matched by
  `from=2026-03-22`, even if individual documents were not changed.
- This is a deliberate trade-off: Aracne2 does not track per-document
  modification timestamps in PostgreSQL. Collection-level granularity is
  sufficient for OAI-PMH selective harvesting and is explicitly disclosed via
  the `granularity` field in `Identify`.

---

## Error codes

| Code | Meaning | When returned |
|------|---------|---------------|
| `badVerb` | Verb missing or not recognized | `verb` param absent or not in the valid set |
| `badArgument` | Required argument missing | `metadataPrefix` absent for ListIdentifiers/ListRecords; `identifier` or `metadataPrefix` absent for GetRecord |
| `cannotDisseminateFormat` | Requested format not supported | Any `metadataPrefix` other than `oai_dc` |
| `idDoesNotExist` | Identifier unknown | Invalid syntax, non-published collection, or file absent from eXist-db |
| `noRecordsMatch` | Query returns empty result set | No published public collection (or documents) match the criteria |
| `noSetHierarchy` | No sets defined | No published public collections exist (ListSets only) |
| `badResumptionToken` | Token invalid | Token cannot be base64-decoded or parsed as JSON |

Per the OAI-PMH spec, `badVerb` errors do NOT include the `verb` attribute on
the `<request>` element.

---

## Architecture and data flow

### Plugin loading

The plugin is discovered at startup by `PluginLoader.discover()`, which scans
`backend/app/plugins/_native/`. It is always active (`native=True`) and its
router is mounted at `/api/v1` prefix, making the endpoint `/api/v1/oai`.

### Request path (ListRecords example)

```
HTTP GET /api/v1/oai?verb=ListRecords&metadataPrefix=oai_dc&set=dante
          │
          ▼
  router.oai_endpoint()
    │  parses query params (FastAPI aliases: "from" → from_date, "set" → set_spec,
    │  "metadataPrefix" → metadata_prefix, "resumptionToken" → resumption_token)
    │  extracts base_url = request.url without query string
    ▼
  service.dispatch()
    │  validates verb → "ListRecords"
    │  validates metadataPrefix → "oai_dc" ✓
    │  no resumptionToken → offset = 0
    ▼
  service._list_records(offset=0)
    │
    ├─► _collect_docs()
    │     ├─► PostgreSQL: SELECT collections WHERE status=published AND is_public=true
    │     │               AND slug='dante' ORDER BY published_at
    │     └─► eXist-db:   list_collection('dante') → ['inferno.xml', 'purgatorio.xml']
    │         Returns: [(col_dante, 'inferno.xml'), (col_dante, 'purgatorio.xml')]
    │
    ├─► page = docs[0:100]  (all 2 records fit in one page)
    │
    ├─► for each (col, filename):
    │     ├─► _fetch_tei_dc(existdb, 'dante', 'inferno.xml')
    │     │     → xquery('oai_pmh/get_dc_meta.xq', {doc_path: '/db/aracne2/collections/dante/inferno.xml'})
    │     │     → parse XML result with defusedxml
    │     │     → {'title': ['Inferno'], 'creator': ['Dante Alighieri'], 'date': ['1308']}
    │     │
    │     └─► _build_dc_element(col, 'inferno.xml', 'oai:example.com:dante/inferno.xml', tei_dict)
    │           → <oai_dc:dc> with merged TEI + PostgreSQL metadata
    │
    ├─► _append_record() × 2  → adds <record> children to <ListRecords>
    │
    └─► len(docs)=2 ≤ PAGE_SIZE → emit empty <resumptionToken> (end of list)
          │
          ▼
        _to_xml(root) → ET.indent() + ET.tostring() → UTF-8 XML string
          │
          ▼
      Response(content=xml, media_type="application/xml; charset=UTF-8")
```

### XML generation

All XML is built with Python's stdlib `xml.etree.ElementTree`. Namespace prefixes
are registered once at module import time via `ET.register_namespace()`:

| Prefix | Namespace URI |
|--------|--------------|
| _(default)_ | `http://www.openarchives.org/OAI/2.0/` |
| `oai_dc` | `http://www.openarchives.org/OAI/2.0/oai_dc/` |
| `dc` | `http://purl.org/dc/elements/1.1/` |
| `xsi` | `http://www.w3.org/2001/XMLSchema-instance` |

`ET.indent()` (Python ≥ 3.9) adds human-readable indentation before
serialization. The output always starts with `<?xml version="1.0" encoding="UTF-8"?>`.

### XQuery execution

`_fetch_tei_dc()` calls `ExistDBClient.xquery()` which:
1. Loads `backend/app/xqueries/oai_pmh/get_dc_meta.xq` from disk.
2. Inlines the `$doc_path` variable by replacing the `external` declaration with
   a literal assignment (eXist-db REST external variable binding is unreliable).
3. POSTs the query to eXist-db REST endpoint `/exist/rest/db`.
4. Returns the raw response bytes.

The result is then parsed with `defusedxml.ElementTree.fromstring()` (XXE-safe)
and iterated to build the `dict[str, list[str]]` used by `_build_dc_element()`.

---

## Deployment considerations

### Base URL and hostname

The OAI identifier's hostname component is derived at request time from the URL
that reaches the FastAPI process. In a Docker / nginx setup, ensure that the
`Host` header (or `X-Forwarded-Host`) is forwarded correctly so the identifiers
reflect the public domain name and not `localhost` or a container name.

If nginx terminates TLS and proxies to the backend, add to the nginx location block:

```nginx
proxy_set_header Host $host;
proxy_set_header X-Forwarded-Proto $scheme;
```

And in FastAPI (if behind a proxy), configure `root_path` or use a
`ProxyHeadersMiddleware` so that `request.url` reflects the public URL.

### Performance

| Verb | PostgreSQL queries | eXist-db calls |
|------|--------------------|----------------|
| Identify | 1 (MIN aggregate) | 0 |
| ListSets | 1 | 0 |
| ListMetadataFormats | 0 | 0 |
| ListIdentifiers | 1 + N (list_collection per collection) | N |
| ListRecords (page of K docs) | 1 + N | N + K (get_dc_meta per doc) |
| GetRecord | 1 | 2 (list_collection + get_dc_meta) |

For `ListRecords`, the dominant cost is the K sequential XQuery calls to extract
TEI metadata. With a page size of 100 and a 10 ms average XQuery call, a full
page takes ~1 second. This is acceptable for batch harvesters that are not
latency-sensitive. If performance becomes a bottleneck, a multi-document
XQuery that processes an entire collection in one call can replace the per-file
approach.

### Deleted records

The repository declares `<deletedRecord>no</deletedRecord>`. Aracne2 does not
expose tombstone records. When a document is deleted or a collection is
unpublished, it simply disappears from future harvests. Harvesters configured
for `deletedRecord=no` must perform their own comparison with previous harvests
to detect removals.

---

## Known limitations and future extensions

| Limitation | Notes |
|------------|-------|
| Single metadata format | Only `oai_dc` is supported. Adding `oai_qdc` (Qualified DC) or TEI-based formats would require additional XQuery and `_build_*` functions. |
| Collection-granularity datestamps | All documents share `collection.updated_at`. Per-document timestamps would require a new `documents` table in PostgreSQL or an eXist-db property query. |
| No set hierarchy | OAI-PMH supports nested sets (e.g. `dante:lyric`). The current implementation uses flat sets only. |
| No resumption token expiry | Tokens do not expire. The OAI-PMH spec recommends expiring tokens after a reasonable interval. |
| Re-query on each page | Each page re-queries DB and eXist-db. A cache (Redis or in-process) could improve throughput for large repositories. |
| Repository name and email | Currently read from `settings.platform_name` and `settings.admin_email` (environment variables). Could be made configurable per-installation via system_settings keys `oai_pmh_repository_name` and `oai_pmh_admin_email`. |
