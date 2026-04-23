# AI assistance

Aracne2 integrates a configurable AI assistant that can help with
specific, well-scoped editorial tasks. The assistant is opt-in at the
Admin level (activate the AI plugin + configure a provider and an API
key), and every feature is opt-in at the user level (you have to click
a button — nothing is sent to the AI without your action).

## In the TEI editor (Editor+)

Open the **AI** side-panel and pick one of the available prompts:

| Prompt | What it does |
|--------|--------------|
| Encode selection | Wraps the selected plain text in appropriate TEI tags |
| Clean up TEI | Fixes common mistakes (unbalanced tags, wrong attribute names) |
| Bibliographic `<bibl>` | Turns a free-text citation into a TEI `<biblStruct>` |
| Suggest named entities | Proposes `<persName>` / `<placeName>` wraps around likely entities |

The assistant always shows a diff of its proposed change before you
apply it. Nothing is written until you explicitly accept.

## Grounded on the TEI Guidelines (optional)

If the Admin has enabled the TEI Guidelines RAG option (pgvector-backed
retrieval), the assistant's prompts include the most relevant TEI P5
guideline excerpts as context. This significantly reduces hallucination
and lines the output up with the canonical schema.

## In collection-wide validation (EditorInChief+)

When validating every document in a collection, the AI can be asked to
produce a plain-language summary of the errors — useful for handing
back a "please fix these" list to the assigned Editor.

## In the Bibliobuilder (EditorInChief+)

When rebuilding the bibliography, the AI can normalise common formatting
inconsistencies (missing periods, "and" vs. "&", surname/forename
order) before the final list is saved.

## Privacy notice

Every AI call is logged in the audit trail with the user, the feature
used, and a token count. The actual prompt and response are not logged
by default (configurable). If your deployment sends prompts to a
third-party API (OpenAI, Anthropic, …), treat any content you send to
the assistant as if you were sharing it with that provider's terms of
service.

## Rate limits

AI calls share the platform's global rate limit plus an additional
per-user cap to prevent runaway usage. Your Admin can tighten these
limits in the AI plugin settings.
