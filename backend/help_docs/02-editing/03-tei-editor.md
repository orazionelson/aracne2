# The TEI editor

Click any document filename to open the TEI editor. The editor occupies
most of the screen and is divided into two resizable areas — the XML
editor on the left, a side panel on the right.

## The toolbar

| Button | What it does |
|--------|-------------|
| Save | Saves the current content to the database. If a schema is attached, validation runs automatically after saving. |
| Format | Re-indents the XML for readability |
| Fold all | Collapses all XML elements so only the outermost structure is visible |
| Fullscreen (F11) | Expands the editor to fill the entire browser window |
| Add note (alpha) | Inserts an alphabetic note (a, b, c…) at the cursor |
| Add note (numeric) | Inserts a numeric note (1, 2, 3…) at the cursor |
| TEI help | Opens the help panel with element documentation |
| Media | Opens the facsimile/media panel |
| Zones | Opens the zone editor for text-image alignment |
| Validate | Opens the validation panel and runs the schema validator |
| AI | Opens the AI assistance panel |

## Autocomplete

If the collection has a TEI schema attached, the editor offers
intelligent autocomplete:

- Type `<` to see a list of elements valid at the current position
- Press space inside an opening tag to see valid attributes
- Press `=` after an attribute name to see valid values for that attribute
- Press `Ctrl+Space` to trigger autocomplete manually at any time

## Keyboard shortcuts

| Shortcut | Action |
|----------|--------|
| `Ctrl+J` | Jump to the matching closing/opening tag |
| `Ctrl+/` | Toggle XML comment on the selected line(s) |
| `F11` | Toggle fullscreen |
| `Esc` | Exit fullscreen |
| `Ctrl+Space` | Trigger autocomplete |

## External reference lookups

A family of optional buttons ("chips") appears in the toolbar when
the matching plugins are activated by your Admin. Each opens a
side-panel that resolves an external reference and inserts the
result directly into the document — either as a `@ref="…"` URI on
the enclosing tag, or as a new `<biblStruct>` for bibliographic
lookups.

The full per-plugin guide lives in
[External reference lookups](/help/page?path=03-advanced/05-external-reference-lookups).
Quick per-tag map:

| TEI tag | Lookups you can wire up |
|---|---|
| `<persName>` | **Wikidata**, **ORCID** (researchers), **VIAF**, **GND**, **CERL**, **Trismegistos** (ancient world) |
| `<placeName>` | **GeoNames**, **Wikidata**, **GND**, **Peripleo** (Pelagios, ancient), **CERL**, **Trismegistos** |
| `<orgName>` | **ROR** (academic), **Wikidata**, **GND**, **CERL** |
| `<term>` | **Getty AAT** (art / architecture / material culture), **Wikidata** |
| `<bibl>` / `<biblStruct>` | **CrossRef** (paste a DOI), **OpenAlex** (free-text search), **Trismegistos** (ancient texts) |

Each chip shows the authority's short name in the toolbar (e.g.
**WIKI**, **ORCID**, **ROR**). Every result is written as a
canonical URI — no free-text ever lands in the XML.

If a chip is missing, the matching plugin is not activated in
`/admin/plugins`. Plugin activation requires a backend restart to
take effect.
