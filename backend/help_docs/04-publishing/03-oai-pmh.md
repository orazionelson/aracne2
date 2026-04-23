# OAI-PMH — making your data harvestable

OAI-PMH (Open Archives Initiative Protocol for Metadata Harvesting) is
the standard mechanism library catalogues, aggregators, and digital
humanities registries use to pull metadata from content providers.
When Aracne2 exposes its collections via OAI-PMH, third-party
harvesters can pick up your editions automatically.

## What is exposed

Aracne2 ships with a native OAI-PMH provider (the `oai_pmh` plugin,
always active). It speaks OAI-PMH 2.0 and implements all six verbs:

- `Identify` — basic provider information
- `ListMetadataFormats` — supported metadata formats (currently `oai_dc`)
- `ListSets` — the collections, exposed as OAI sets
- `ListIdentifiers` — paginated list of record identifiers
- `ListRecords` — paginated list of full records with metadata
- `GetRecord` — a single record by identifier

Each **published** collection is an OAI set. Each **published**
document is an OAI record. Draft and review-stage content is never
exposed.

## What you need to do

Nothing special — the OAI-PMH endpoint lives at `/api/v1/oai` and is
active out of the box. Give a harvester this URL and they can start
pulling immediately.

Aracne2 extracts Dublin Core metadata from the TEI `<teiHeader>`
automatically (title, creator, subject, publisher, date, language,
identifier, type). If a document is missing a field, the corresponding
DC element is omitted rather than emitted empty.

## Related identifiers

Set the collection's **Identifier URL** (DOI, Handle, URN, or
alternative) in the collection settings. This value becomes the
`dc:identifier` for every record in that set, giving harvesters a
stable citation target.

## Future metadata formats

The current release exposes only `oai_dc`. Richer formats (`mods`,
`tei`) are tracked in the project's future-ideas list and can be
enabled as separate plugins when they ship.
