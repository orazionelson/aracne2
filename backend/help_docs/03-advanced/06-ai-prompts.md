# AI prompts — catalogue, scopes and where they live

Aracne2 ships with **nine built-in AI prompts**. They are seeded
the first time the platform boots and stay editable from
**Settings → AI** ([/admin/settings, AI tab](/admin/settings)). Each
prompt is a templated instruction that the platform sends to the
chosen provider together with the variables you fill in.

The platform is **scope-driven**: every prompt declares a *scope*,
and the editor surfaces auto-render a button (or a picker entry)
for each prompt whose scope matches their context. Custom prompts
inherit this for free — give your new prompt one of the eight
recognised scopes and it appears in the matching toolbar without a
single line of frontend code.

## The eight scopes

| Scope | Where it appears | Input variables | Output |
|---|---|---|---|
| `editor.selection`  | TEI editor toolbar — one button per prompt | `filename`, `collection_slug`, `selection` (active editor selection, or whole document if nothing selected) | XML — read-only viewer + Apply button |
| `editor.document`   | TEI editor toolbar — one button per prompt | same shape; `selection` filled with the entire document | XML — read-only viewer + Apply button |
| `editor.validation` | TEI editor — Validate button | `filename`, `schema`, `errors` (the validator's error list) | Plain-language explanation, no Apply |
| `editor.discuss`    | TEI editor — Discuss button | `filename`, `collection_slug`, `selection` | Multi-turn chat |
| `xslt.debug`        | Website editor → XSLT tab — Debug button | `xslt_source`, optional `error_msg` | Plain text |
| `xslt.discuss`      | Website editor → XSLT tab — Discuss button | `xslt_source` | Multi-turn chat |
| `bibliobuilder`     | Bibliobuilder view — Modality dropdown above the Run button | none (the bundle of `<bibl>` / `<biblStruct>` is sent as the user-message body) | Deduplicated `<listBibl>` |
| _empty_ (orphan)    | **Nowhere.** Visible only in Settings → AI. | — | — |

The orphan state is the deliberate "I'm drafting, don't ship me yet"
mode — leave the scope blank when creating a custom prompt and no
editor will surface it until you pick one.

## Native prompts at a glance

| Slug | Label | Scope | What it does |
|---|---|---|---|
| `validate_errors_explain` | Explain validation errors | `editor.validation` | Walks the user through the schema validator's output |
| `document_edit_suggest`   | Suggest TEI encoding improvements | `editor.selection` | Cleans up the selected XML fragment |
| `document_discuss`        | Discuss document content | `editor.discuss` | Open chat about the selected fragment |
| `tei_bibl_inline`         | Normalize inline bibliography | `editor.selection` | Free-text bib note → `<biblStruct>` |
| `tei_extract_entities`    | Tag named entities | `editor.selection` | Wraps `persName` / `placeName` / `orgName` |
| `tei_header_scaffold`     | Scaffold a teiHeader | `editor.document` | Builds a minimal `<teiHeader>` from free-text metadata |
| `xslt_debug`              | Debug XSLT stylesheet | `xslt.debug` | Explains a build error against the stylesheet |
| `xslt_discuss`            | Discuss XSLT stylesheet | `xslt.discuss` | Open chat about an XSLT |
| `bibliobuilder`           | Bibliography Normalizer | `bibliobuilder` | Deduplicates and structures the corpus' raw bib entries |

The "★" badge in **Settings → AI** marks the seeded ones — you can
edit them, but native prompts cannot be deleted (the system would
re-seed them on the next boot anyway). Custom prompts you author
yourself **can** be deleted.

## TEI editor — six prompts

The richest surface. Open a document, click the "AI" sidebar button.
The header of the AI panel exposes:

### Validate with AI — `validate_errors_explain`

Runs the document through the active TEI schema, then sends the
list of validation errors plus the file metadata to the AI. The
response is a plain-language explanation of each error and how to
fix it. Doesn't modify the document.

**Inputs the platform fills in for you**

- `filename` — the active document file.
- `schema` — the schema label currently selected.
- `errors` — the validator's output, line/col annotated.

Use it when the validator complains and the message is opaque.

### Improve XML — `document_edit_suggest`

Sends the **current selection** (or the whole document, if no
selection is active) and asks the AI to return a cleaner TEI
encoding. The response renders in a read-only XML viewer; the
**Apply** button replaces the selection (or the whole document)
with the AI's version. Stripping of stray markdown fences is
automatic.

**Inputs**

- `filename`, `collection_slug`
- `selection` — what's selected in the editor; the whole document
  if no selection.

Use it for cleanup passes — converting inline notes to `<note>`
elements, fixing namespace declarations, normalising attribute
ordering. Always preview before applying.

### Discuss — `document_discuss`

Multi-turn chat about the selected fragment. Unlike Improve, this
prompt is open-ended: the AI explains, suggests, asks questions —
your call which parts of the conversation to act on.

**Inputs**: same as Improve (`filename`, `collection_slug`,
`selection`). The full chat history is sent on every follow-up so
the AI keeps context.

Use it when you don't yet know what the right encoding looks like
and want a second opinion.

### Biblio — `tei_bibl_inline`

Converts a free-text bibliographic note in the selection into a
single `<biblStruct>` element with structured `<analytic>` /
`<monogr>` / `<imprint>` / `<idno>` children. Generates a stable
`xml:id` of the form `bib_<surname>_<year>`.

**Inputs**: `filename`, `collection_slug`, `selection` (the
free-text bibliographic note).

The output is a valid `<biblStruct>` ready to drop into a
`<listBibl>` or referenced via `<ref target="#bib_...">`. Pairs
naturally with the **CrossRef** lookup plugin for free-text
references that carry a DOI.

### Entities — `tei_extract_entities`

Wraps every `persName` / `placeName` / `orgName` in the selection
with the right inline tag. Doesn't rewrite the text, only adds
markup. Ambiguous mentions (e.g. "Cambridge" — place or
institution?) are wrapped with the most likely tag plus
`@cert="medium"` so you can review.

**Inputs**: `filename`, `collection_slug`, `selection`.

Faster than the manual taxonomy walk, especially on long passages.
Always followed by a manual review pass — the model is good but
not infallible at disambiguation.

### Header — `tei_header_scaffold`

Builds a minimal `<teiHeader>` block from free-text metadata in the
selection. Expects something like *"Title: Divina Commedia. Author:
Dante Alighieri. Edited by: M. Rossi. Year: 2026. License: CC-BY
4.0."* and produces the full `<fileDesc>` skeleton, with empty
elements omitted.

**Inputs**: `filename`, `collection_slug`, `selection`.

Best on a freshly created document where the TEI header is still
empty. Doesn't replace careful manual encoding — the AI fills in
what it can derive, you fill in the rest.

## Website editor — XSLT prompts

Open a website and switch to the XSLT tab.

### Debug — `xslt_debug`

When a build fails or a stylesheet produces unexpected output, paste
the error message and the AI walks through the stylesheet looking
for the cause. Returns the suspected line(s) and a suggested patch.

**Inputs**

- `error_msg` — the lxml/Saxon error text (optional but helpful).
- `xslt_source` — the full XSLT.

### Discuss XSLT — `xslt_discuss`

Multi-turn chat about a stylesheet. Useful when you want to
*understand* a template you didn't write — the AI explains what
each match block is doing in plain prose, with snippets when
helpful.

**Inputs**: `xslt_source`.

## Collection-wide — `bibliobuilder`

The Bibliobuilder view (`/collections/<slug>/bibliobuilder`)
extracts every `<bibl>` and `<biblStruct>` across the collection's
documents into a single XML envelope, then sends the whole batch to
the `bibliobuilder` prompt. The AI returns a deduplicated, sorted
`<listBibl>` ready to be saved as a public bibliography.

This is the heaviest prompt by input size — typical runs ship
100k+ characters in a single user turn (700+ entries are common).
It enforces strict structural rules so the output XML drops into
the project's existing schema without reshaping.

## Editing a prompt

In **Settings → AI**, click a prompt in the left list and the
right panel switches to its detail. **Modifica** on a native prompt
edits the current row; the next platform boot will not overwrite
your edit unless you Reset (delete + restart, which re-seeds the
canonical version).

Two things to keep in mind:

- **Variable placeholders** like `{filename}` and `{selection}` are
  substituted at request time. Edit the surrounding prose freely;
  don't rename the placeholders or the call sites stop being able
  to fill them in.
- **The `scope` field** (the violet badge in the prompt detail) is
  the load-bearing connection between a prompt and a UI surface.
  Edit it to move a prompt to a different surface; clear it to take
  a prompt out of circulation without deleting it. The eight allowed
  values are listed in the table at the top of this page.

## Privacy posture

Every prompt sends the variables you see listed in the table above
to the configured provider. Nothing else — no audit-log rows, no
session metadata, no IP. When the deployment runs against a
remote provider (OpenAI / Anthropic / Gemini) the document content
is the price of admission. To keep editorial content fully local,
switch the provider to **Ollama** under Settings → AI.

The "Privacy warning" toggle in the AI settings makes the editor
display a one-shot reminder before the first AI call of a session
— useful for shared deployments where editors might not realise
which provider is in use.

## Adding a custom prompt

Hit **+ Nuovo prompt** in the AI tab. The form takes:

- a **slug** (snake_case, unique) — the platform's internal handle;
- a **label** — what the user sees on the button or in the picker;
- an optional **description** — shown under the label and as the
  button's tooltip;
- a **scope** — pick from the eight recognised values (or leave
  blank to keep the prompt in draft mode, visible only here);
- a **template** — your prompt text with `{variable}` placeholders.

**Scope is what wires the prompt to a button.** A new
`editor.selection`-scoped prompt appears as a button in the TEI
editor next to Improve XML / Biblio / Entities / Header on the very
next page reload. A new `xslt.debug`-scoped prompt overrides the
existing Debug button (or, when there are multiple, the
alphabetically first one wins; the others are reachable only via
direct edit). A `bibliobuilder`-scoped prompt joins the modality
dropdown in the Bibliobuilder workflow.

**Variable placeholders** like `{filename}` and `{selection}` must
match the scope's contract — see the table at the top of this page.
The platform fills them in at request time; if your template
references `{foo}` and `foo` isn't in the scope's input variables,
the run fails with a clear error.

Pattern that works: copy a native template (slug `xslt_discuss`,
say), tweak the persona / domain / examples, give it a new slug
and the same scope, save. The infrastructure handles streaming,
retries, chat history and Apply — your job is just the words.
