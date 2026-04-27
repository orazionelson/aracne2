# AI prompts — built-in catalogue and where they live

Aracne2 ships with **nine built-in AI prompts**. They are seeded the
first time the platform boots and stay editable from
**Settings → AI** ([/admin/settings, AI tab](/admin/settings)). Each
prompt is a templated instruction that the platform sends to the
chosen provider together with the variables you fill in.

This page is the map: which prompt powers which button, what the
button does, where to find it in the UI, and what each prompt
expects as input.

## At a glance

| Slug | Label | Surface | Trigger | Output |
|---|---|---|---|---|
| `validate_errors_explain` | Explain validation errors | TEI editor + Collection detail | "Validate with AI" / Validate panel | Plain-language fix list |
| `document_edit_suggest`   | Suggest TEI encoding improvements | TEI editor | "Improve XML" button | Raw TEI XML (replace selection) |
| `document_discuss`        | Discuss document content | TEI editor | "Discuss" button | Multi-turn chat |
| `tei_bibl_inline`         | Normalize inline bibliography | TEI editor | "Biblio" button | Single `<biblStruct>` |
| `tei_extract_entities`    | Tag named entities | TEI editor | "Entities" button | Same text with `<persName>` / `<placeName>` / `<orgName>` wrapping |
| `tei_header_scaffold`     | Scaffold a teiHeader | TEI editor | "Header" button | Minimal `<teiHeader>` block |
| `xslt_debug`              | Debug XSLT stylesheet | Website editor (XSLT tab) | "Debug" button | Plain-language explanation + fix |
| `xslt_discuss`            | Discuss XSLT stylesheet | Website editor (XSLT tab) | "Discuss XSLT" button | Multi-turn chat |
| `bibliobuilder`           | Bibliography Normalizer | Bibliobuilder view | "Run Bibliobuilder" | Deduplicated `<listBibl>` |

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
- **The `target_context` field** (the violet badge — `editor`,
  `xslt`, `validation`) is a hint for future surface filtering. It
  doesn't gate visibility today; the call site picks a prompt by
  slug.

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

- a **slug** (snake_case, unique) — used by code if you ever wire
  it to a button;
- a **label** — what the user sees in the picker;
- an optional **description** — shown under the label;
- a **template** — your prompt text with `{variable}` placeholders.

The template lives untouched until you save. Custom prompts don't
gain a UI button automatically — that's a code change. They show
up everywhere a prompt picker is rendered (currently only Settings
→ AI; the editor's hard-coded buttons stay native).

Pattern that works: copy a native template (slug `xslt_discuss`,
say), tweak the persona / domain / examples, save with a new slug.
The infrastructure handles streaming, retries, history, applying —
your job is just the words.
