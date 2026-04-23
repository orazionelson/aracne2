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

Three optional buttons appear in the toolbar when the matching plugin
is activated by your Admin. Each opens a side-panel that resolves an
external reference and inserts the result directly into the document.

| Button | What it does |
|--------|-------------|
| Wikidata | Searches Wikidata by name; writes `@ref="https://www.wikidata.org/entity/Q…"` on `<persName>`, `<placeName>`, or `<orgName>` |
| ORCID | Searches the public ORCID registry by researcher name; writes `@ref="https://orcid.org/0000-…"` on `<persName>` |
| DOI | Resolves a pasted DOI via CrossRef and appends the resulting TEI `<biblStruct>` to the document's `<listBibl>` |

If a button is missing, the plugin is not activated in
`/admin/plugins`. Plugin activation requires a backend restart to take
effect.
