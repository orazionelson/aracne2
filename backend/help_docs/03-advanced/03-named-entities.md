# Named entities

A **named entity** is a person, place, organisation — or anything else
your project tags with a structured TEI element — that you want to
treat as a single, identifiable thing across the corpus, no matter
how often it appears or under how many surface-form variants.

Aracne2 keeps a live index of every such entity it sees in your
documents. The index powers a public people / places / organisations
browser, lets editors verify consistency at a glance, and gives the
platform a foothold for [external authority links](05-external-reference-lookups.md)
(Wikidata, VIAF, GeoNames, ORCID, …).

Nothing here requires manual upkeep in the day-to-day flow:
**you just write good TEI, the index follows.**

## The mental model: entity vs. occurrence

Two concepts are worth keeping straight:

- An **entity** is the abstract record — "Aldus Manutius",
  "Venezia", "Università di Napoli". It has a *type* (the TEI tag,
  e.g. `persName`), a *canonical form* (the display label), an
  optional *authority reference* (a Wikidata / VIAF / GeoNames /
  ORCID / … URI), and a global *occurrence count*.
- An **occurrence** is one specific mention inside one specific
  document. It carries the *raw form* as it appears in the XML
  (which may differ from the canonical form), a short *context
  excerpt* (the surrounding sentence), and a reference back to the
  collection + filename.

A single entity has many occurrences. Editors see and edit
occurrences (because that's where the markup lives); readers and
admins see entities (because that's the unit of reuse).

## What happens automatically

The index is maintained by the **Named Entity Index** native plugin,
which listens to document lifecycle events:

- **On document upload / save** — a small XQuery extracts every
  matching element from the saved file, the backend reconciles it
  against the existing index (case-insensitive lookup on
  canonical form + type), refreshes occurrence counts, and prunes
  any entity whose count has dropped to zero.
- **On document deletion** — all occurrences for that file are
  removed and the same orphan-pruning sweeps through.

Both flows run as background tasks (fire-and-forget) so the editor
never has to wait for indexing. If something goes wrong the failure
is logged but the document save itself is unaffected.

## Which TEI tags get indexed

By default the index extracts three TEI elements:

- `<persName>` — people
- `<placeName>` — places
- `<orgName>` — organisations

These are the names actually used; the platform's matching is
**namespace-agnostic** (it uses `local-name()` in XQuery), so the
extractor works whether or not your TEI declares the
`http://www.tei-c.org/ns/1.0` namespace.

EditorInChiefs (and Admins) can extend the list from the admin UI:

- `/admin/entities` → **Tag configuration** panel.
- Add / remove TEI element names — for example to also index
  `<objectName>` for material-culture editions, `<measure>` for
  metrology corpora, or `<rs>` if your project uses the generic
  "referencing string" tag.
- Save → from that moment on, every new save extracts the new tag
  list. **Existing index data is not refreshed automatically** —
  trigger a re-index per collection (see *Re-indexing* below).

The TEI tag name *is* the entity type stored in the DB. There's no
mapping layer to maintain.

## Authority references (`@ref`)

Whenever an element carries a `@ref` attribute pointing at an
external authority, Aracne2 captures it on the entity record:

```xml
<persName ref="https://www.wikidata.org/entity/Q104697">Aldus Manutius</persName>
<placeName ref="https://www.geonames.org/3164603">Venezia</placeName>
<orgName ref="https://ror.org/05290cv24">Università di Napoli Federico II</orgName>
```

What counts as a usable authority ref:

- Anything containing a colon — full URLs (`https://…`), CURIEs
  (`viaf:12345`, `wikidata:Q104697`), DOIs, etc.
- An entity that picks up an authority ref later "wins" — the
  first time any occurrence carries a `@ref`, the entity record
  is enriched. Subsequent occurrences without `@ref` still match
  the same entity (case-insensitive on the canonical form), so the
  link stays attached.

What's deliberately **not** treated as an authority ref:

- Internal document anchors (`@ref="#person1"`) — they refer to a
  `<listPerson>` within the same file, not an external authority,
  and pretending otherwise would pollute the index.
- Empty values — same logic.

If you don't have authority URIs yet, the index still works — entities
are grouped by canonical form alone. Adding `@ref` later only
strengthens the matching; it doesn't break anything.

The companion [External reference lookups](05-external-reference-lookups.md)
guide covers the toolbar plugins that turn a selection inside a TEI
element into an authoritative `@ref` URL without ever typing one by
hand.

## Public entity browser

Every published, public collection feeds into `/browse/<slug>/entities`,
where readers can:

- Filter by entity type (person / place / organisation / any custom
  tag your project added).
- Search by name fragment — case-insensitive substring match on the
  canonical form.
- Click an entity to see every occurrence in the corpus, with a
  short context excerpt and a direct link to the document at the
  exact position.

The browser only surfaces entities with at least one occurrence in
a published, public collection. Drafts and private collections feed
the index (so an Admin can clean up before publication) but stay
invisible to the public.

## Admin entity management

`/admin/entities` (Admin) is the cross-collection control surface.
The list shows every entity with its type, canonical form, authority
ref, and occurrence count. From there an Admin can:

- **Filter** — by type, by name fragment, or restricted to entities
  with no authority link yet (`unlinked`) — the natural start for an
  enrichment pass.
- **Edit canonical form** — when the first occurrence wasn't the
  one you'd want as the display label (e.g. an abbreviated form
  appeared first; you'd rather show the full one).
- **Edit authority ref** — paste a Wikidata / VIAF / GeoNames /
  GND / ORCID / ROR / Trismegistos / Getty AAT URI. This decouples
  enrichment from re-saving every document.
- **Merge** two entities into one — when the same real-world thing
  ended up split across two records ("Aldus Manutius" and
  "Aldo Manuzio", say). Pick a *source* and a *target*; every
  occurrence of the source is reassigned to the target, then the
  source row is deleted. The merge is irreversible — but always
  recoverable by re-indexing the affected collection if you change
  your mind.
- **Delete** an entity — useful when an entry slipped in by mistake
  (typo, OCR noise, stray tag). All its occurrences disappear with
  it; the source documents stay untouched.

Every admin action is recorded in the audit log.

## Re-indexing

The index keeps itself in sync as documents come and go, but a few
situations call for a full collection re-build:

- You **changed the tag configuration** (added or removed a TEI
  element from the extraction list) — existing data still reflects
  the old config until you re-index.
- You **bulk-imported** documents through a path that bypassed the
  editor (e.g. a one-off SQL migration, a restore from backup).
- An XQuery library in the platform was upgraded and you want to
  rebuild on the new extractor.

`/admin/entities` → **Re-index collection** runs the rebuild
end-to-end:

1. Wipes every existing occurrence for that collection.
2. Re-runs the extractor against every file in eXist-db, one
   document at a time, committing per-document so partial results
   survive a transient failure.
3. Refreshes counts and prunes orphans.

The operation is idempotent — running it twice in a row produces
the same result.

## Limits and conventions

A few rules worth knowing when you read the index later:

- **Canonical form is "first occurrence wins"**. Whatever raw text
  appeared in the first document indexed becomes the display label
  for the entity until an Admin overrides it.
- **Lookups are case-insensitive**, *display preserves case*. Two
  occurrences spelled "Aldus Manutius" and "ALDUS MANUTIUS" land
  on the same entity; the entity shows whichever form was indexed
  first.
- **Whitespace-collapsed text only**. The XQuery `normalize-space()`
  strips newlines and collapses runs of spaces — so a name split
  across lines in the source XML still matches the same entity.
- **Empty inner text is skipped**. An element with no readable
  content doesn't produce an occurrence even if it carries a
  `@ref`.
- **`raw_form`** is capped at 512 chars, **`context`** at 300.
  Anything longer is truncated. In practice neither limit ever
  bites — names that long are typos.
- **Internal `@ref="#…"` anchors are ignored** as authority refs
  (see above) but the occurrence is still indexed under its
  canonical form.

## Troubleshooting

> An entity I expected to see isn't in the public browser.

Two possibilities:
1. The collection isn't *published* + *public* yet — the public
   browser hides drafts and private collections by design. An
   Admin can confirm via `/admin/entities`, which sees everything.
2. The element's inner text was empty after `normalize-space()` —
   common with self-closing `<persName/>` placeholders.

> Two entities should be one.

Use **Merge** in `/admin/entities`. If the duplicates only exist
because of a mistyped `@ref`, fix the `@ref` in the affected
documents and re-index the collection — they'll converge naturally.

> The same entity should be two.

There's no "split" operation: the index is built bottom-up from
occurrences, so the right fix is to make the *occurrences*
distinguishable in the source — either by tagging different
elements (`persName` vs. `orgName`), by giving them distinct
authority refs, or by editing the names so the canonical forms
differ. Re-index the collection when done; the entity will split
on its own.

> I changed the tag config but `/browse/<slug>/entities` still shows
> the old tag set.

Re-index the affected collections from `/admin/entities`. The
config controls *future* extractions; existing rows aren't migrated.

> Indexing seems silently broken on a single document.

The plugin logs failures with key `named_entities_*_failed`
(check the backend container logs). The most common cause is
malformed XML that defusedxml refuses to parse — fix the document
in the editor and the next save re-indexes it cleanly.
