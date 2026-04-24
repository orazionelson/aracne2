# External reference lookups

When you tag a name, a place, an organisation, or a bibliographic
reference in a TEI document, the value is only as durable as the
authority it points to. Aracne2 ships a family of **external
reference lookup** plugins that turn a selection inside a TEI
element into an authoritative, citable `@ref` URL — or, for
bibliographic references, into a full `<biblStruct>` fragment.

Every lookup plugin follows the same shape:

1. The editor selects text inside a TEI element (or places the
   cursor inside one).
2. Clicks the service's **toolbar chip** at the top of the editor.
3. A **side panel** opens with a search box (or, for Trismegistos,
   an ID input).
4. Results appear as the editor types; clicking **Apply** writes
   the chosen URI to the enclosing tag's `@ref` attribute.

No free-text input makes it into the XML — only the canonical URI
returned by the authority. The XML stays clean and citable.

## Quick map: which authority for which tag

| TEI tag | What it encodes | Recommended plugins |
|---|---|---|
| `<persName>` | A person's name | **ORCID** (researchers), **VIAF**, **GND**, **Wikidata**, **CERL**, **Trismegistos** (ancient world) |
| `<placeName>` | A geographic name | **GeoNames**, **Wikidata**, **GND**, **Peripleo** (ancient), **CERL**, **Trismegistos** (ancient world) |
| `<orgName>` | An institution | **ROR** (academic), **Wikidata**, **GND**, **CERL** |
| `<term>` | A controlled term | **Getty AAT** (art, architecture, material culture), **Wikidata** |
| `<bibl>` / `<biblStruct>` | A bibliographic reference | **CrossRef** (paste DOI), **OpenAlex** (search papers/books), **Trismegistos** (ancient texts) |

Several plugins overlap deliberately — a `<persName>` can be
Wikidata OR VIAF OR ORCID depending on what the project prefers
for its vocabulary. Pick the one(s) your project wants to use and
leave the others deactivated for a cleaner toolbar.

## Opening the right panel

Each active plugin adds one chip to the editor toolbar, at the
top-right of the TEI editor. The chip shows the service's short
name (e.g. **WIKI**, **ORCID**, **ROR**). Only plugins that are
active on this deployment appear — if you don't see a chip, ask
the Admin to activate that plugin under `/admin/plugins`.

## The search-style flow (most plugins)

Used by Wikidata, ORCID, ROR, VIAF, GeoNames, GND, CERL, Peripleo,
Getty AAT, OpenAlex.

1. Place the cursor **inside** the TEI element you want to tag.
   The panel pre-fills the search box with your selection (or, when
   there's no selection, the text between the tag's opening and
   closing brackets).
2. Adjust the query if the pre-fill isn't quite right.
3. Results stream in as you type (debounced to ~400ms).
4. Each hit shows a label, a short disambiguating detail (dates,
   country, occupation…), the authority's ID, and a link to open
   the record in a new tab.
5. Click **Apply** on the right hit. The panel writes the URI as
   the `@ref` attribute on the enclosing tag and shows a
   confirmation "Linked <persName> to Q1067".

If the cursor isn't inside an eligible tag, the panel tells you so
without making any change to the XML.

## The paste-an-ID flow (Trismegistos only)

Trismegistos doesn't publish a free-text search API — only ID
resolvers. The Trismegistos panel is slightly different:

1. Pick the **kind**: Person / Place / Text.
2. For Text: pick the **source** — `trismegistos` (if you have a
   TM ID) or a partner project (DDBDP, HGV, PHI, EDH, EDCS, …) if
   you have an ID from that project and want TM to resolve it.
3. Paste the ID.
4. Click **Resolve**. The canonical TM URL and any partner-DB
   cross-references are shown.
5. **Apply** writes the URI to `@ref` on the enclosing
   `<persName>` / `<placeName>`. (Text records resolve to a URL
   too but the panel only applies the `@ref` on person/place tags.)

## The DOI-paste flow (CrossRef)

For bibliographic entries, CrossRef has a different UX:

1. Open the **CrossRef** panel.
2. Paste a DOI (with or without the `https://doi.org/` prefix).
3. Click **Resolve**. A TEI `<biblStruct>` fragment is generated
   from the CrossRef record.
4. Click **Insert**. The fragment is inserted at the cursor — as
   a *new* `<biblStruct>` element, not as a `@ref` on an existing
   one.

## The search-and-insert flow (OpenAlex)

OpenAlex works like CrossRef but starts from a free-text search
instead of a DOI:

1. Open the **OpenAlex** panel.
2. Type author name / title / keywords.
3. Pick a hit from the results.
4. Click **Insert**. A `<biblStruct>` for that work is inserted at
   the cursor.

OpenAlex is especially useful when you know a reference exists but
don't have its DOI handy, or for books and chapters that CrossRef
doesn't cover.

## Hover preview on the public site

Once a `@ref` is in place and the collection is published on a
website, readers see the name as a link. The Designer can
optionally enable a **hover preview**: passing the mouse over a
link opens a small popover that fetches label + description
(+ image when available) straight from the authority and shows
them inline.

Toggle it under **Sito** → the site's **Documento** tab →
*"Enable hover preview"*. Default is off.

**Scope at the moment:** Wikidata only. The Wikidata API allows
the browser to call it directly (no backend proxy needed), so the
feature costs nothing to the server. Other authorities (ORCID,
GeoNames, ROR, VIAF, GND, Getty AAT) block cross-origin browser
calls and will land in a later release via a backend proxy.

**Privacy note:** every hover fires an HTTP request to Wikidata.
Deployments that need to announce third-party data calls to their
visitors (GDPR-style cookie / data policy disclosures) should
leave the toggle off or update the site's policy before enabling.


## Troubleshooting

### "The enclosing element is `<p>`, not `<persName>`"

The lookup only applies `@ref` to the specific tags it's designed
for (see the table at the top). If the panel shows this message,
the cursor is inside the wrong tag — move it into the right one
(e.g. highlight the name and wrap it in `<persName>`) and retry.

### "No matching records"

Either the query really has no authority record (common for
obscure names, especially in Wikidata for pre-modern figures), or
the service is temporarily unreachable. The plugin fails soft — no
error pop-up — so try a different spelling, or switch to another
authority service for the same tag family.

### The chip I need isn't on the toolbar

The plugin is inactive on this deployment. Ask an Admin to open
`/admin/plugins`, switch to the **Estensioni** tab, activate the
plugin, and restart the backend. Then the chip appears the next
time you reload the editor.

### The authority URI I want isn't in the results

Some authorities (VIAF, GND) occasionally return only their most
popular matches. You can always open the authority's website in a
browser, find the right record, and paste its URI directly into
the `@ref` attribute — the XML editor doesn't stop you from
writing `@ref` by hand.

## See also

- [Extensions catalog](/help/page?path=05-reference/02-extensions-catalog)
  for the full per-plugin reference including authority vocabulary
  mapping and configuration requirements.
- [The TEI editor](/help/page?path=02-editing/03-tei-editor) for
  the general editor shortcuts and toolbar layout.
