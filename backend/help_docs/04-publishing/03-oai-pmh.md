# OAI-PMH — making your data harvestable

OAI-PMH (Open Archives Initiative Protocol for Metadata Harvesting,
v2.0) is the long-standing standard that library catalogues,
digital-humanities aggregators, and discovery services use to pull
metadata from content providers. When Aracne2 exposes its
published collections via OAI-PMH, harvesters discover your
editions automatically and keep their indexes fresh without human
coordination.

## The endpoint

Every Aracne2 deployment exposes a single OAI-PMH endpoint:

```
https://<your-host>/api/v1/oai
```

This is live out of the box — the `oai_pmh` plugin is native (always
active) and requires no configuration. You give a harvester this URL
and they can start pulling immediately.

## Who typically harvests

Known harvesters / aggregators that consume OAI-PMH endpoints for
digital-humanities content:

- **Europeana** — pan-European digital cultural heritage aggregator.
- **OpenAIRE** — aggregator of European scholarly outputs.
- **CLARIN Virtual Language Observatory** — linguistic-resource
  discovery.
- **DARIAH / DH-Italia / AIUCD registries** — DH-specific resource
  catalogues.
- **National library union catalogues** — in Italy, SBN
  (Servizio Bibliotecario Nazionale) and its regional aggregators.
- **Google Scholar** — parses `oai_dc` when indexing DH editions.
- **Institutional repositories** — when two institutions share
  editorial work, one can harvest the other's Aracne2.

## What is exposed

Every **published** collection becomes an **OAI set**; every
published document inside it becomes an **OAI record**. Draft,
assigned, and review-stage content is never exposed — OAI-PMH is
strictly public. Unpublishing a collection also removes it from
the harvester's next crawl.

Metadata is extracted from each document's TEI `<teiHeader>` and
mapped to Dublin Core elements (the `oai_dc` format). Mapping:

| OAI-DC element | TEI source |
|---|---|
| `dc:title` | `titleStmt/title` |
| `dc:creator` | `titleStmt/author`, `respStmt/persName` |
| `dc:subject` | `profileDesc/textClass/keywords/term` |
| `dc:publisher` | `publicationStmt/publisher` |
| `dc:date` | `publicationStmt/date` |
| `dc:language` | `profileDesc/langUsage/language/@ident` |
| `dc:identifier` | Collection's identifier URL (DOI / Handle / URN) — see [Related identifiers](#related-identifiers) below |
| `dc:type` | Static: "text" |
| `dc:rights` | Collection's assigned license |

Missing fields are **omitted** (not emitted empty). Multiple values
(e.g. several creators) become repeated elements.

## The six OAI-PMH verbs — with URL examples

All examples assume your host is `edition.example.org`.

### 1. `Identify` — basic provider info

```
https://edition.example.org/api/v1/oai?verb=Identify
```

Returns repository name, base URL, protocol version, admin email,
earliest datestamp, deletion policy. Harvesters call this first to
confirm compatibility.

### 2. `ListMetadataFormats` — supported formats

```
https://edition.example.org/api/v1/oai?verb=ListMetadataFormats
```

Currently returns only `oai_dc` (Dublin Core, mandatory for
OAI-PMH 2.0). Richer formats (`mods`, `tei`) are on the roadmap.

### 3. `ListSets` — the collections

```
https://edition.example.org/api/v1/oai?verb=ListSets
```

Returns one `<set>` per published collection with its slug as
`setSpec` and its title as `setName`. Example excerpt:

```xml
<ListSets>
  <set>
    <setSpec>divina-commedia</setSpec>
    <setName>Divina Commedia — edizione Petrocchi</setName>
  </set>
  <set>
    <setSpec>papyri-oxyrhynchus</setSpec>
    <setName>Oxyrhynchus Papyri (vol. I–III)</setName>
  </set>
</ListSets>
```

### 4. `ListIdentifiers` — paginated record IDs

```
https://edition.example.org/api/v1/oai?verb=ListIdentifiers&metadataPrefix=oai_dc
```

Scope the list to a single collection by adding `&set=<slug>`:

```
https://edition.example.org/api/v1/oai?verb=ListIdentifiers&metadataPrefix=oai_dc&set=divina-commedia
```

Filter by date range (ISO 8601):

```
…&from=2026-01-01&until=2026-04-30
```

Returns a list of `<header>` blocks (identifier + datestamp + set
memberships). Use this when you only need to know *what* changed,
not the full metadata.

### 5. `ListRecords` — paginated full records

```
https://edition.example.org/api/v1/oai?verb=ListRecords&metadataPrefix=oai_dc
```

Same filters as `ListIdentifiers` (`set`, `from`, `until`) plus
the full Dublin Core metadata for each record. This is what
harvesters call for bulk syncs.

Example record in the response:

```xml
<record>
  <header>
    <identifier>oai:edition.example.org:divina-commedia:inferno-canto-i</identifier>
    <datestamp>2026-03-14T10:23:45Z</datestamp>
    <setSpec>divina-commedia</setSpec>
  </header>
  <metadata>
    <oai_dc:dc xmlns:oai_dc="http://www.openarchives.org/OAI/2.0/oai_dc/"
               xmlns:dc="http://purl.org/dc/elements/1.1/">
      <dc:title>Inferno — Canto I</dc:title>
      <dc:creator>Dante Alighieri</dc:creator>
      <dc:date>1320</dc:date>
      <dc:language>it</dc:language>
      <dc:type>text</dc:type>
      <dc:publisher>Aracne2 Editions</dc:publisher>
      <dc:identifier>https://doi.org/10.5281/zenodo.123456</dc:identifier>
    </oai_dc:dc>
  </metadata>
</record>
```

### 6. `GetRecord` — a single record by identifier

```
https://edition.example.org/api/v1/oai?verb=GetRecord&identifier=oai:edition.example.org:divina-commedia:inferno-canto-i&metadataPrefix=oai_dc
```

Use this to fetch one specific record without paginating.

## Pagination — the resumption token

OAI-PMH uses **resumption tokens** for pagination: the response to
`ListIdentifiers` / `ListRecords` includes a `<resumptionToken>`
element when more results are available. Pass it back in the next
request to get the next page:

```
https://edition.example.org/api/v1/oai?verb=ListRecords&resumptionToken=<token>
```

Aracne2 paginates at 100 records per page. Well-behaved harvesters
handle this transparently.

## Related identifiers — wiring OAI-DC to DOIs

To make `dc:identifier` a useful citation target rather than a
random URL, set your collection's **Identifier URL** in the
collection edit form. Recommended values:

- The DOI minted by the Zenodo plugin (`https://doi.org/10.5281/zenodo.<n>`)
- The DOI minted by the Dataverse plugin (after publish)
- A Handle (`https://hdl.handle.net/...`)
- An Archival Resource Key (ARK)
- A URN (e.g. `urn:nbn:it:<n>`)

The same value propagates to every record in the set, so harvesters
can deduplicate and cross-reference against DOI providers.

## Testing your endpoint before sharing it

The cleanest third-party validator is the OpenArchives-provided one:

- **OAI-PMH Validator**: http://oval.base-search.net/
  — Paste your `…/api/v1/oai` URL, hit Validate, read the report.

Alternatively, the command line:

```bash
# Check the Identify verb
curl -s "https://edition.example.org/api/v1/oai?verb=Identify" | head -20

# Count published collections
curl -s "https://edition.example.org/api/v1/oai?verb=ListSets" \
  | grep -c '<setSpec>'

# Fetch the first 100 records
curl -s "https://edition.example.org/api/v1/oai?verb=ListRecords&metadataPrefix=oai_dc" \
  | xmllint --format -
```

## Incremental harvesting — the `from` parameter

Well-behaved harvesters remember the datestamp of their last
successful run and on the next crawl pass it as `from=` so they
only pick up *new* or *changed* records:

```
https://edition.example.org/api/v1/oai?verb=ListRecords&metadataPrefix=oai_dc&from=2026-03-14T00:00:00Z
```

Aracne2 sets a record's `datestamp` to the document's last-saved
timestamp, so an unchanged document doesn't appear in incremental
crawls.

## What if I don't want a collection to be harvested?

Either:

- Leave the collection as **Draft** / **Review** — unpublished
  content is never exposed via OAI-PMH, full stop.
- Mark the collection as **private** in its settings — private
  collections are invisible to both the public website *and* the
  OAI-PMH endpoint.

Harvest-blocking more granularly (e.g. hide a specific document
from a public collection) is not supported — OAI-PMH's philosophy
is "public-or-not" per record, not per-field access control.

## Submitting your endpoint to aggregators

Once the endpoint validates:

- **OpenAIRE**: submit at https://provide.openaire.eu/ — requires
  a free operator account.
- **Europeana**: submission flows through an accredited
  aggregator for your country (in Italy, CulturaItalia).
- **CLARIN VLO**: send a one-time request to the CLARIN centre
  that coordinates your national node.

The submission typically amounts to pasting your endpoint URL,
accepting the aggregator's terms, and waiting for the next crawl
(most run daily to weekly).

## Roadmap

- **Richer metadata formats** (`mods`, `tei`) — tracked in
  `docs/TO_DO.md`. When they ship, harvesters that request
  those prefixes will get them alongside the mandatory `oai_dc`.
- **Set hierarchies** — currently each collection is one flat
  set; a future enhancement can expose nested sets mapping to a
  project-level grouping.

## See also

- [Websites — publishing to the web](/help/page?path=04-publishing/01-websites)
  for the public-facing presentation layer (OAI-PMH is pure
  metadata; the website is the human-facing interface to the same
  content).
- [Depositing on external repositories](/help/page?path=04-publishing/04-external-repositories)
  for how to mint the DOIs that populate `dc:identifier`.
