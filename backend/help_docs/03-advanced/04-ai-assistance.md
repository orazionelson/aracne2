# AI assistance

Aracne2 integrates a first-class AI assistant throughout the
editorial workflow — in the TEI editor, in validation review, in
XSLT debugging, and in the Bibliobuilder. The goal is not to
replace the editor's judgement but to **shorten the distance
between free-text intent and clean TEI markup**: every AI response
is a proposal, always shown in preview, applied only on an
explicit user click.

The assistant is **opt-in at two levels**:

1. **Deployment** — an Admin activates the AI plugin and picks a
   provider (OpenAI / Anthropic / Gemini, or a local Ollama) +
   API key.
2. **Per action** — every AI feature is behind a button. Nothing
   is sent to the AI without the user's explicit click, and
   nothing is written to the document until the user accepts the
   proposal.

## Provider & privacy model

| Provider | Where the request goes | When to choose it |
|---|---|---|
| **Ollama** (local) | A container on the same host as Aracne2 | Privacy-sensitive editions; no external network call leaves the deployment |
| **OpenAI** (GPT-5, GPT-4.1, …) | api.openai.com | Default balance of quality / speed / cost |
| **Anthropic** (Claude) | api.anthropic.com | Best-in-class on long-context and reasoning |
| **Google Gemini** | generativelanguage.googleapis.com | Competitive on cost; large context |

Selection: Admin → `/admin/plugins/ai/config` → Provider dropdown.
Switching provider is hot — no restart needed — but any in-flight
stream completes on the old provider.

**Audit**: every AI call is logged in the `ai_request_logs` table
with the user, the prompt slug, a token count, and the request
duration. The full prompt and response are **not** logged by
default; an Admin can turn that on for debugging, with a clear
"retention in days" cap.

**What leaves the deployment** (cloud providers only): the
rendered prompt (template + your inputs + optional RAG context).
If your deployment sends prompts to a third-party API, treat any
content you send to the assistant as if you were sharing it with
that provider's terms of service.

## Where the assistant lives — the eight native features

Aracne2 ships eight native prompt templates. Each one is scoped to
one editorial task and is invoked from exactly one place in the
UI, so there's no ambiguity about what the AI will do.

### In the TEI editor — `DocumentEditView`

The AI sidebar on the right of the editor exposes four tools:

| Button | What it does |
|---|---|
| **Suggest improvements** | Reviews the selected XML and proposes a cleaner version. Typical fixes: balanced tags, canonical attribute names, corrected nesting. The response replaces the selection on Apply. |
| **Validate with AI** | Runs a fresh per-document validation against the editor buffer (not the saved file), then asks the AI to explain each error in plain language with a proposed fix. |
| **Extract entities** | Reads the selected prose and proposes `<persName>` / `<placeName>` / `<orgName>` wraps around the likely entities. Diff shown before apply. |
| **Free-text → `<biblStruct>`** | Converts a free-text citation ("Dante, Divina Commedia, ed. Petrocchi 1966–67") into a minimal well-formed `<biblStruct>`. Uses RAG over the TEI P5 Guidelines when enabled (see below). |

All four show a **diff preview** before writing anything. The
editor can accept, tweak, or discard — nothing is automatic.

### In the `<teiHeader>` — scaffolding

When a document has an empty or minimal `<teiHeader>`, the
**Scaffold teiHeader** button populates it from collection
metadata (title, authors, license, publication info) plus the
`<text>` body's top-level structure. Useful for retroactively
fitting a header to TEI files imported from non-TEI sources.

### In collection-wide validation — `CollectionDetailView`

After running **Validate all** on a collection, each per-document
error block has an **Analyze with AI** button that feeds the
errors to the assistant and returns a plain-language summary.
Useful for handing back a "please fix these" list to the assigned
Editor, in their first language.

### In the XSLT editor — `WebsiteEditView`

Two modes on the XSLT tab:

- **Debug** (single-shot): paste an error message (from a failed
  build or a runtime warning) into a dedicated textarea, click
  Debug; the AI explains the cause and proposes a corrected XSLT.
- **Discuss** (chat): open the XSLT in Discuss mode to have a
  back-and-forth with the AI about the stylesheet. Useful for
  exploration: "what does this template do?", "how would I add
  pagination to this loop?"

### In the Bibliobuilder — `CollectionBibliobuilderView`

When rebuilding the collection bibliography, the AI can normalise
common formatting inconsistencies before the final list is saved:
missing periods, "and" vs. "&", surname/forename order, ISO vs.
free-form dates. Preview-then-commit, like every other feature.

## Grounded on the TEI Guidelines — RAG

The AI plugin ships with an optional **retrieval-augmented
generation** layer: when an Admin ingests the TEI P5 Guidelines
(Admin → AI → Ingest RAG corpus), relevant Guideline excerpts are
retrieved at inference time and fed to the model as extra context.
Two effects:

1. **Less hallucination**: the model quotes the canonical schema
   instead of inventing attribute names.
2. **Schema-aligned output**: when asked to produce TEI, the
   result matches the conventions documented in the TEI P5 source
   of truth.

Visible signal in the UI: when a prompt uses RAG context, the AI
panel shows a small "📚 Using TEI Guidelines (12 passages)" line
below the response stream. Click it to see which passages were
retrieved.

RAG is on-demand per prompt. The four editor tools
(suggest / validate / entities / biblStruct) use it when
available; the XSLT and Bibliobuilder prompts don't need it.

## Custom prompts

Admin → `/admin/ai/prompts` exposes the full library. You can:

- **Clone** a native prompt and customise it (e.g. tweak the
  biblStruct template to match your project's `xml:id` convention).
- **Create** a new prompt from scratch, binding it to one of the
  existing UI surfaces (editor / validation / XSLT / bibliobuilder)
  via `target_context`.
- **Edit** a native prompt's label and template (but not its slug
  — the slug is referenced from frontend code).

Custom prompts appear alongside native ones in the right UI and
can be shared across the deployment.

## Rate limits

Two tiers protect the provider quota:

1. **Global rate limit** — the platform's shared slowapi limit
   (200 req/min default).
2. **Per-user AI cap** — configurable in AI plugin settings.
   Useful on multi-user deployments to prevent runaway usage.

When a user hits the cap, the UI shows a friendly "you've reached
your AI quota for today" banner; the editor stays usable without
AI.

## Cost management

Every call logs a token count (prompt + completion). Admin can
export a CSV of AI activity (Admin → AI → Usage) to invoice per
institution or per project. Most deployments settle at
€10–50 / month of API spend at the OpenAI rate — RAG adds maybe
20% overhead in tokens.

## Recommendation — when to use AI, when not

**Use it for**:
- Encoding tedious patterns (many similar passages to tag)
- Cleaning up TEI from non-expert contributors
- Explaining cryptic validation errors
- Generating repetitive boilerplate (`<teiHeader>` scaffolds,
  `<biblStruct>` from free text)
- Exploring XSLT stylesheets written by others

**Don't use it for**:
- Final scholarly decisions (disambiguation, emendation,
  critical apparatus choices) — always the editor's call.
- Anything that requires project-specific conventions the AI
  can't know about (encoding variants, custom entity schemes) —
  unless you've built a RAG corpus of your project's guidelines
  alongside the TEI P5 one.

The AI is a fast collaborator, not an authority. Keep it in the
preview-then-apply loop and it stays useful.

## See also

- [The TEI editor](/help/page?path=02-editing/03-tei-editor) for
  editor layout and where the AI sidebar sits.
- [Bibliography (Bibliobuilder)](/help/page?path=03-advanced/02-bibliography)
  for the Bibliobuilder workflow including the AI-normalise step.
