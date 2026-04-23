# Named entities

Whenever a TEI document uses `<persName>`, `<placeName>`, or
`<orgName>`, Aracne2 tracks it as a **named entity occurrence**. The
entity index powers a browsable people / places / organisations page on
the public website and lets editors verify consistency across a
collection.

## What happens automatically

On every save, the backend re-extracts named entities from the document
and updates the index. No manual step is required.

- Entities with a `@ref` attribute (Wikidata, ORCID, VIAF, custom
  authority) are linked to that URI, so the same authority is counted
  once no matter how many times it appears or under how many
  surface-form variants.
- Entities without `@ref` are grouped by canonical form (the
  lower-cased, whitespace-collapsed inner text).

## Public entity browser

The public site exposes `/browse/<slug>/entities`, where readers can:

- Filter by entity type (person / place / organisation).
- Search by name fragment.
- Click an entity to see every occurrence with the surrounding context
  and a link to the exact document and location.

## Admin entity management (Admin)

`/admin/entities` lets an Admin manually merge entities that should be
considered the same, split ones that were accidentally merged, and
edit canonical forms. The audit log records every change.

## Configuring which tags to extract (EditorInChief+)

By default only `<persName>`, `<placeName>`, and `<orgName>` are
extracted. EditorInChief can extend this list from the collection
settings — for example to also extract `<name type="work">` or any
project-specific tag.
