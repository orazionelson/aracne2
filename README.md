# Aracne2

A modular, production-ready CMS for editing and publishing structured
TEI corpora. Built for philologists, historians, archivists and
scholarly editors who want to take a corpus from raw text to a
published, citable digital edition without also becoming sysadmins.

---

## Table of contents

- [How we got here](#how-we-got-here)
- [What Aracne2 is, in one paragraph](#what-aracne2-is-in-one-paragraph)
- [Who it's for](#who-its-for)
- [Architecture overview](#architecture-overview)
- [Synoptic feature overview](#synoptic-feature-overview)
  1. [Editorial workflow](#1-editorial-workflow)
  2. [The TEI editor](#2-the-tei-editor)
  3. [Collections, documents, and the working/published split](#3-collections-documents-and-the-workingpublished-split)
  4. [Validation and schema management](#4-validation-and-schema-management)
  5. [Facsimiles and zones](#5-facsimiles-and-zones)
  6. [Named entities and authority linking](#6-named-entities-and-authority-linking)
  7. [Bibliography](#7-bibliography)
  8. [AI assistance and RAG](#8-ai-assistance-and-rag)
  9. [Public websites and themes](#9-public-websites-and-themes)
  10. [Search — within, across, and natural-language](#10-search--within-across-and-natural-language)
  11. [Linked Open Data, OAI-PMH, and harvestability](#11-linked-open-data-oai-pmh-and-harvestability)
  12. [External deposit and archiving](#12-external-deposit-and-archiving)
  13. [Notifications, email, and password reset](#13-notifications-email-and-password-reset)
  14. [Webhooks and outbound integrations](#14-webhooks-and-outbound-integrations)
  15. [The MCP server — Aracne2 as an LLM tool host](#15-the-mcp-server--aracne2-as-an-llm-tool-host)
  16. [The `aracne` CLI and Personal Access Tokens](#16-the-aracne-cli-and-personal-access-tokens)
  17. [Audit log](#17-audit-log)
  18. [Fixity layer](#18-fixity-layer)
  19. [Policy pages, capability roles, and CTS posture](#19-policy-pages-capability-roles-and-cts-posture)
  20. [GDPR posture](#20-gdpr-posture)
  21. [Plugin architecture and auto-cabling](#21-plugin-architecture-and-auto-cabling)
  22. [Public-link toggles and admin surfaces](#22-public-link-toggles-and-admin-surfaces)
- [Technology stack](#technology-stack)
- [Quick start](#quick-start)
- [Project structure](#project-structure)
- [Role hierarchy](#role-hierarchy)
- [Security](#security)
- [Production deployment](#production-deployment)
- [Reference documentation](#reference-documentation)
- [License](#license)

---

## How we got here

Aracne2 is the third iteration of a tooling line that has spent
fifteen years asking the same question: **how do we turn a stream
of typed manuscript transcriptions into a citable, browsable,
machine-actionable digital edition without making the editor learn
to be an XML programmer?** Each iteration answered it differently,
and the constraints we hit each time shaped what came next.

### MaRa *(2008–2016)*

The starting point was the **Angevine Chancery Papers**, the
administrative output of the Angevin kings of Sicily and Naples
(13th–15th centuries). Their original registers were destroyed in
the 1943 fire that gutted the Naples State Archive; what survives
is a fragmentary reconstruction patched together by mid-20th-century
archivists from secondary witnesses, copies, and citations
scattered across European archives. Editing this corpus is a
philological detective story: every entry carries its own apparatus
of provenance notes, cross-references, and bibliographic citations
in idiosyncratic short-forms inherited from the manual edition.

**MaRa** (*Marcatore dei Registri Angioini*) was a set of PHP
scripts written to take that mass of typed text — produced by the
project's editors over years in plain txt documents — and lift it
into a custom XML encoding. The scripts handled three jobs that
nobody wanted to do by hand:

- **Tag insertion**: regular-expression passes that recognised
  recurring patterns (dates in Roman numerals, persName/placeName
  in capitalised forms, bibliographic short-forms) and proposed
  markup for the editor to accept or correct.
- **Bibliography harmonisation**: the editors used six different
  short-forms for the same source over the years; MaRa resolved
  them against a canonical bibliography file and rewrote them as
  consistent `<bibl>` references with `@xml:id` cross-pointers.
- **Validation and reporting**: per-document syntactic checks plus
  a corpus-wide report of unresolved short-forms, missing
  cross-references, and inconsistent date formats.

Around 2010 the scripts were wrapped in a CodeIgniter web UI so the
philologists on the project could run the pipeline themselves
instead of mailing batches to the developer. By the time MaRa was
published in 2018 (*Cosco, "Southern Italian Angevine Chancery
Papers in XML: the script MaRa v2.0"* —
[Zenodo](https://zenodo.org/records/1447195),
[Academia.edu](https://www.academia.edu/37523540/)) it had handled
several thousand documents and was the de-facto editorial
infrastructure for the project. But it was a **single-corpus,
single-server tool** without a publishing layer.

### Aracne *(2016–2026)*

The lesson from MaRa was clear: the editorial flow was generalisable,
the publication flow wasn't. **Aracne** was the first attempt to
turn the Angevine workflow into a platform — something other
philological projects could pick up without inheriting six years of
project-specific PHP. The bet was on the **eXist-db / XQuery
ecosystem**, which around 2015–2016 looked like the natural home
for an XML-native CMS: a single language (XQuery 3.1) for storage,
transformation, templating, and routing; a community of digital
humanists who already spoke it.

Aracne shipped a CodeMirror-based TEI editor with attribute
autocomplete, a draft → review → publish workflow with role gating,
a sitebuilder that produced static HTML editions, and a search
interface — all in XQuery on top of eXist-db. It worked, and
between 2018 and 2022 it backed several academic editions.

It also taught us where the XQuery-everywhere bet broke down:

- **Library ecosystem.** Anything beyond the TEI core — image
  cropping, OAuth, OAI-PMH, CrossRef, Zenodo, modern auth — meant
  either reimplementing primitives in XQuery or shelling out to
  external services with awkward bridges. The "everything in one
  language" claim was true only for plain TEI manipulation.
- **Debugging surface.** eXist-db's stack traces were terse and
  often pointed at the wrong place; performance tuning required
  reading the engine's internals; deploying to a production server
  was a per-host adventure.
- **Frontend stagnation.** The HTML5 + light-jQuery frontend aged
  badly; the rest of the web moved to component frameworks while
  Aracne stayed on hand-written templates.

By 2024 the friction-per-feature curve was steep enough that
adding a sixth integration cost more than re-architecting the
platform from scratch. Aracne is preserved as a reference at
[github.com/orazionelson/aracne](https://github.com/orazionelson/aracne)
— still useful as documentation of what an eXist-db-native CMS
looks like end to end.

### Aracne2 *(2026 →)*

The third iteration draws three lines from the previous two:

- **Keep eXist-db, but only as an XML store.** Aracne2 still uses
  eXist-db 6.4.1 to store TEI documents natively, run XQuery
  transformations, and serve full-text search — the things eXist-db
  is genuinely best at. Everything else (auth, ACL, workflow,
  plugins, settings, audit, AI integration, REST API) moves to a
  Python + FastAPI + PostgreSQL backend, a stack the digital-
  humanities community can hire and onboard for.
- **Clean separation between platform and corpus.** MaRa was a
  corpus tool that grew a UI; Aracne was a platform that grew a UI
  layer. Aracne2 is **two distinct data layers from day one**:
  PostgreSQL for platform state (users, roles, sessions, plugin
  registry, settings, audit), eXist-db for document state (TEI XML
  in per-collection databases). The two never bleed into each
  other. The platform is portable across corpora; the corpus is
  portable across platforms.
- **Modularity as the first-class concern.** Every integration that
  was a hand-coded special case in Aracne is a plugin in Aracne2:
  twelve authority lookups, six deposit backends, AI providers,
  the MCP server, the EVT viewer feed, the policy-pages declaration
  set, the natural-language search frontend. Activation hot-mounts
  a plugin's routes without restarting the backend. Capability
  tags (`inline_authority`, `collection_deposit`, `website_deposit`,
  `public_navigation`) let plugins auto-cable themselves into the
  SPA without anybody editing the SPA — see
  [§ Plugin architecture and auto-cabling](#21-plugin-architecture-and-auto-cabling).

---

## What Aracne2 is, in one paragraph

A web CMS with a separate frontend/backend architecture, inspired
by WordPress in its modularity: an agnostic core (authentication,
ACL, routing, hooks/plugins, rendering) on top of which domain
modules are added one at a time. Two distinct data layers
(PostgreSQL for platform state, eXist-db for TEI XML), a Vue 3
SPA that talks to the backend over REST/JSON/JWT only, and a
plugin system that hot-mounts third-party integrations without
restarting the backend or touching the SPA. AI assistance is a
peer tool inside the editor — not a chat widget — including
local-only RAG over the TEI P5 Guidelines for institutions that
cannot ship their corpus to a cloud LLM.

The platform reached **production-ready status across three
milestones**:

- **M1 — Operationalisation.** Document version history with
  working/published split, transactional email, password reset,
  natural-language search, the `aracne` CLI for bulk import/export,
  per-user Personal Access Tokens, plugin auto-cabling for public
  navigation. See [§§ 3, 13, 16, 21](#3-collections-documents-and-the-workingpublished-split).
- **M2 — Audit visibility & security debt.** Admin-facing audit log
  view, scheduled fixity layer with drift dashboard, full security
  review pipeline (PyJWT migration, dependency audit). See
  [§§ 17, 18](#17-audit-log).
- **M3 — Institutional surface.** `policy_pages` plugin (twelve
  CTS-aligned templates), capability roles via singleton
  `PolicyManager`, public `/policies` index, CoreTrustSeal posture
  documented end-to-end. See
  [§ 19](#19-policy-pages-capability-roles-and-cts-posture).

Day-to-day operations and deferred design decisions live in
[`docs/TO_DO.md`](docs/TO_DO.md); the per-CTS-requirement
self-assessment lives in
[`docs/reference/CTS_COMPLIANCE.md`](docs/reference/CTS_COMPLIANCE.md).

---

## Who it's for

Aracne2 fits **editorial teams** working on structured
corpora — university projects, critical editions, diplomatic-papers
archives, funded research groups. It is opt-in for plugins and
external services, so a deployment can stay minimal or grow into a
full publishing platform as the project does.

The audience is **invite-only by design**: the platform ships
without public registration, every user is created by an Admin or
EditorInChief, and the GDPR posture matches an editorial scientific
publisher's obligations rather than a B2C SaaS's
([§ 20](#20-gdpr-posture)). Suitable as the institutional repository
for a research group, the editorial backbone for a multi-volume
edition, or the operational platform for a project preparing for
CoreTrustSeal / nestor / ISO 16363 review
([§ 19](#19-policy-pages-capability-roles-and-cts-posture)).

---

## Architecture overview

```
┌─────────────────────────────────────────────────────────────────┐
│  Browser                                                        │
│  Vue 3 SPA · Pinia · Vue Router · Tailwind CSS                  │
└───────────────────────┬─────────────────────────────────────────┘
                        │  REST API · JSON · JWT Bearer
                        │  (httpOnly cookie for refresh token)
┌───────────────────────▼─────────────────────────────────────────┐
│  FastAPI backend  (Python 3.12 · async · Pydantic v2)           │
│                                                                 │
│  ┌─────────────┐  ┌──────────────┐  ┌────────────────────────┐ │
│  │   Routers   │  │   Services   │  │  Plugin system         │ │
│  │  + ACL/JWT  │→ │ + XQuery I/O │  │  hooks · native plugins│ │
│  │  + capab.   │  │ + fixity     │  │  + auto-cabling        │ │
│  └─────────────┘  └──────┬───────┘  └────────────────────────┘ │
└─────────────────────────┬┴───────────────────────────────────-──┘
              ┌───────────┴────────────┐
              │                        │
┌─────────────▼──────────┐  ┌──────────▼─────────────────────────┐
│  PostgreSQL 15          │  │  eXist-db 6.x                      │
│  Layer 1 — platform     │  │  Layer 2 — document data           │
│  users · roles          │  │  TEI XML collections               │
│  sessions · settings    │  │  queried via XQuery 3.1            │
│  audit · plugins        │  │  (REST API + .xq files)            │
│  named entities         │  │                                    │
│  schemas · websites     │  │                                    │
│  document_versions      │  │                                    │
│  policy_pages           │  │                                    │
│  pgvector (optional)    │  │                                    │
└─────────────────────────┘  └────────────────────────────────────┘
```

**Two distinct data layers:**

- **Layer 1 — Platform data** (PostgreSQL): users, roles
  (hierarchical + capability), sessions, system settings,
  `audit_log`, plugin registry, named entity index, TEI schemas,
  XSLT templates, websites, search engines, notifications,
  webhooks, **`document_versions`** (M1, see
  [§ 3](#3-collections-documents-and-the-workingpublished-split)),
  **`policy_pages`** + `policy_page_versions` (M3, see
  [§ 19](#19-policy-pages-capability-roles-and-cts-posture)),
  `gdpr_requests`, `personal_access_tokens`, `pgvector` (optional,
  RAG).
- **Layer 2 — Document data** (eXist-db): TEI XML documents stored
  natively in per-collection XML databases, queried and transformed
  via XQuery 3.1 files — never via inline query strings.

**Key architectural principles:**

- Frontend and backend communicate **exclusively via REST API +
  JSON + JWT** — the frontend never accesses any database directly.
- All XQuery is loaded from `.xq` / `.xqm` files on the
  filesystem — no inline query construction in Python code.
- The plugin system is **hook-based**: plugins register listeners
  on named events (`document.uploaded`, `collection.published`, …)
  rather than modifying core code.
- **Capabilities** declared in a plugin's `PluginMeta` auto-cable
  the plugin's UI into the SPA's iterators without per-plugin
  edits — see
  [§ 21](#21-plugin-architecture-and-auto-cabling).
- **Rate limiting** (slowapi) is applied at the router level; XML
  parsing always uses `defusedxml` to prevent XXE attacks.

---

## Synoptic feature overview

What follows is a long, deliberately exhaustive carrellata. Each
subsection points at the matching reference document; the
[`docs/reference/`](docs/reference/) tree carries the operational
detail.

### 1. Editorial workflow

A four-state workflow per collection — `draft → assigned → review
→ published` — with a soft "request revisions" loop back to
`assigned` and an Admin-only `unpublish` that reverts to draft.
Every transition is gated by role, audited, and emits both an
in-app notification and (when email is enabled) a transactional
email. EditorInChief+ can `direct-publish` a collection in one
step for bulk imports and projects that don't need formal review.

User manual: [§ 7](docs/USER_MANUAL.md#7-the-editorial-workflow).

### 2. The TEI editor

Schema-aware XML editor built on CodeMirror 5 with autocomplete
driven by a per-collection CM5 schema (auto-generated from RNG /
DTD / XSD, or hand-uploaded). Features:

- Element + attribute + attribute-value autocomplete keyed off the
  CM5 schema, with green **TEI P5** badge in the toolbar when the
  schema is loaded.
- `Save & Validate` shortcut — saves the document, then runs the
  validator on the saved content; the resizable error panel opens
  on failures and shows `line:col`, message, XPath, and a "Search
  on Google" link per row. Validation is non-blocking: malformed
  documents are still saved.
- Keyboard shortcuts (`Ctrl+J` jump-to-matching, `Ctrl+/` toggle
  comment, `F11` fullscreen, `Ctrl+Space` autocomplete trigger).
- Two note flavours (alpha / numeric) inserted as `<ref>`
  references with editable container content.
- **Authority lookup buttons** auto-cabled by the
  `inline_authority` plugin capability — Wikidata, ORCID, ROR,
  VIAF, GeoNames, GND, CERL Thesaurus, Peripleo, Getty AAT,
  OpenAlex, Trismegistos, CrossRef. Each opens a side panel,
  resolves the reference, and writes the canonical URI into the
  enclosing `@ref`.
- **AI side panel** — Validate explainer, Improve, Discuss, plus
  TEI-specific actions (normalise inline bibliography, tag named
  entities, scaffold teiHeader). See
  [§ 8](#8-ai-assistance-and-rag).
- **Version history panel** — every editorially meaningful event
  leaves an append-only row; explicit "Save version" and "Roll back
  to vN" available; SHA-256 fingerprint per row. See
  [§ 3](#3-collections-documents-and-the-workingpublished-split).

References:
[`COLLECTIONS.md`](docs/reference/COLLECTIONS.md) ·
[`TEI_SCHEMAS.md`](docs/reference/TEI_SCHEMAS.md) ·
[`PLUGINS.md`](docs/reference/PLUGINS.md) ·
[`AI_INTEGRATION.md`](docs/reference/AI_INTEGRATION.md) ·
[`DOCUMENT_VERSIONING.md`](docs/reference/DOCUMENT_VERSIONING.md).

### 3. Collections, documents, and the working/published split

Every TEI document belongs to exactly one collection. Documents
are uploaded individually or in batches (ZIP up to 500 files,
root-level XML only); the new-document wizard generates a TEI
skeleton populated from the collection's metadata.

The **document versioning** layer (M1, Alembic 0072) records
every change to every document on an append-only timeline:

| Origin | Triggered by |
|---|---|
| `creation` | New document created |
| `manual` | Editor clicks "Save version" |
| `submission` | Workflow → review |
| `revision` | Workflow → revisions requested (saves snapshot before reverting) |
| `publication` | Workflow → published |
| `rollback` | Editor clicks "Roll back to vN" |

Editors keep editing freely on a published collection — the
public website continues to serve the **last
`publication`-origin version per (collection, filename)** until
the next publish bumps it. `?version=N` permalinks on public
pages resolve only to publication-origin rows, so manual saves
and rollbacks never leak to anonymous visitors.

References:
[`COLLECTIONS.md`](docs/reference/COLLECTIONS.md) ·
[`DOCUMENT_VERSIONING.md`](docs/reference/DOCUMENT_VERSIONING.md) ·
[`BODY_TEMPLATES.md`](docs/reference/BODY_TEMPLATES.md).

### 4. Validation and schema management

Per-collection schema catalog: a schema entry can carry a
**validation file** (RNG / DTD / XSD), a **CM5 file** for the
editor, or both. Files arrive via upload or URL import (URL import
walks behind an SSRF guard that rejects private / loopback /
link-local / multicast addresses).

- **Per-document validation** — on demand from the toolbar; runs
  on the unsaved buffer, so errors are caught without writing to
  eXist-db. Automatic on save when a schema is attached.
- **Collection-wide validation** — EditorInChief+ runs the
  validator across every document; per-document error counts plus
  an "Explain errors (AI)" button that opens the AI panel
  pre-loaded with the failing document's error list.
- **Schema badge** — the editor shows a green **TEI P5** badge
  whenever a CM5 schema resolved.

References:
[`TEI_SCHEMAS.md`](docs/reference/TEI_SCHEMAS.md).

### 5. Facsimiles and zones

Manual TEI facsimile editor with two flavours:

- **Insert as figure** — embeds a `<figure><graphic url="…"/></figure>`
  inline, suitable for in-text illustrations.
- **Insert as card** — registers the image as a `<surface>` in the
  `<facsimile>` block and inserts a `<pb facs="#sN"/>` page-break
  in the transcription, linking the page boundary to the image.

The **zone editor** lets the editor draw rectangles on a page
image and link them to specific TEI elements (`<w>`, `<lb>`, …)
via `@facs="#zone_id"`. A thin HTTP entry point is reserved for
HTR pipeline output (full pipeline support is on the
[`docs/TO_DO.md`](docs/TO_DO.md) backlog).

References:
[`ZONES_FACSIMILE.md`](docs/reference/ZONES_FACSIMILE.md).

### 6. Named entities and authority linking

A background indexer scans every TEI document on upload / save and
extracts the configured tags (default: `persName`, `placeName`,
`orgName` — extensible per platform via System Settings).
Extracted entities feed:

- A **public entity browser** on every published collection,
  showing every passage where each entity appears.
- An **admin normalisation surface**: merge duplicates, set
  canonical forms, attach authority URIs (VIAF, GeoNames, …),
  re-index a collection after a config change.
- The **MCP server**'s `entity_search` tool (see
  [§ 15](#15-the-mcp-server--aracne2-as-an-llm-tool-host)).

The `inline_authority` capability auto-cables twelve authority
lookups into the editor toolbar (Wikidata, ORCID, ROR, VIAF,
GeoNames, GND, CERL Thesaurus, Peripleo, Getty AAT, OpenAlex,
Trismegistos, CrossRef) — each one resolves a name and writes the
canonical URI into the enclosing element's `@ref`.

References:
[`NAMED_ENTITIES.md`](docs/reference/NAMED_ENTITIES.md) ·
[`PLUGINS.md`](docs/reference/PLUGINS.md) ·
[`LOD_INTEGRATION.md`](docs/reference/LOD_INTEGRATION.md).

### 7. Bibliography

Per-collection bibliography editor (the **Bibliobuilder**) with
three ingestion paths — extracted from the documents'
`<bibl>` / `<biblStruct>` elements, imported from BibTeX / CSL-JSON,
or pulled from a **Zotero** group library. The AI normaliser
deduplicates and reformats inconsistent citations into a clean
`<listBibl>`.

Versioned: every Save creates a new numbered version. Exactly one
version can be marked **public** at a time, and the public
collection page surfaces it.

A **CrossRef DOI resolver** plugin lets the editor paste a DOI in
the inline-authority panel and receive a ready-to-use
`<biblStruct>` appended to the document's `<listBibl>` —
deterministic, no AI rewriting, suitable when the citation must
match a published record exactly.

References:
[`BIBLIOGRAPHY.md`](docs/reference/BIBLIOGRAPHY.md) ·
[`PLUGINS.md`](docs/reference/PLUGINS.md).

### 8. AI assistance and RAG

Aracne2 treats AI as a peer tool, not a chat widget. Five axes:

**In-editor assistance.** The TEI editor's AI panel runs three
modes — Validate (plain-language explanation of validator errors),
Improve (suggest edits to a selection), Discuss (free-form
conversation grounded in the document) — plus three TEI-specific
actions: normalise inline bibliography, tag named entities,
scaffold teiHeader. The **prompt library** is editable per
deployment; each prompt is scoped to a surface and the matching
toolbar button auto-cables itself.

**Bibliography automation.** Bibliobuilder normalisation, CrossRef
DOI resolver, Zotero import. See [§ 7](#7-bibliography).

**External assistant integration via MCP.** Aracne2 exposes a
Model Context Protocol endpoint; an editor working in Claude
Desktop, Cursor, or Claude Code can ask "in which documents does
the placeName 'Naples' occur?" and get answers grounded in real
TEI. Tokens are scoped by **corpus**, so heterogeneous projects
hosted on the same instance don't bleed into each other's
analyses. See [§ 15](#15-the-mcp-server--aracne2-as-an-llm-tool-host).

**Provider choice — bring your own model.**

- Cloud: **OpenAI**, **Anthropic Claude**, **Google Gemini** —
  paste the API key in `Settings → AI`, encrypted at rest.
- Local: **Ollama** profile bundled in the compose file — runs the
  model on your own hardware, no key needed, traffic stays on
  the host.

**Retrieval-augmented generation (RAG) over TEI.** The part most
generic AI tools cannot do. A `pgvector` store ingests the **TEI
P5 Guidelines** (the *living* spec — re-ingest on each TEI
Council release) and your own published collections. Each prompt
in the library has a `rag_enabled` toggle; relevant prompts pull
canonical Guidelines passages alongside the editor's selection.
The full pipeline (Postgres + pgvector + Ollama embeddings +
Ollama generation) runs in the `ai-local` Compose profile — no
data leaves the host. Fail-soft: if pgvector is offline, prompts
run unaugmented with a small structured note.

References:
[`AI_INTEGRATION.md`](docs/reference/AI_INTEGRATION.md) ·
[`MCP_SERVER.md`](docs/reference/MCP_SERVER.md) ·
[`NL_SEARCH.md`](docs/reference/NL_SEARCH.md).

### 9. Public websites and themes

A published collection can be turned into a navigable public
website managed by the **Designer** role. Three rendering modes —
**static** (HTML pre-built on demand), **dynamic** (every request
rendered live from eXist-db), **hybrid** (fixed pages pre-built;
documents on the fly) — all sharing the same XSLT pipeline.

The Designer can:

- Pick the bundled TEI XSLT template or write a custom one in the
  in-browser XSLT editor with live preview against any document
  in the collection.
- Define **custom indices** (e.g. an index of all `<persName key=…>`
  with a human-readable label).
- Add free-form Markdown / rich-text pages (introductions,
  methodology notes, credits).
- Apply a custom homepage CSS file and propagate it across the
  public document, entity, and bibliography pages.
- Build the site asynchronously and download the result as a ZIP
  for offline use or static-host deployment.

References:
[`WEB_SITES.md`](docs/reference/WEB_SITES.md) ·
[`XSLT_TEMPLATES.md`](docs/reference/XSLT_TEMPLATES.md) ·
[`PUBLIC_PAGES.md`](docs/reference/PUBLIC_PAGES.md) ·
[`EVT_INTEGRATION.md`](docs/reference/EVT_INTEGRATION.md) ·
[`SEO.md`](docs/reference/SEO.md).

### 10. Search — within, across, and natural-language

Three search surfaces, each with a different shape:

- **Within a collection** — full-text scan over the XML content
  on the collection detail page; results show filename and a
  context snippet.
- **Public cross-collection search** — single search bar on the
  public homepage that hits every published public collection.
- **Search Engine portals** — a Designer-managed object that
  bundles any subset of public collections into a standalone HTML
  page with its own URL, configurable theme, advanced filters
  (TEI element / attribute), server-side query cache, and an
  embeddable JS widget for external sites with per-origin access
  control.
- **Natural-language search** — the `nl_search` plugin (M1)
  exposes a public chat-style search at `/search-nl`. Visitors
  type a question; an LLM tool-use loop runs against the MCP read
  tools and streams an answer with citations to real TEI
  documents. The orchestrator refuses to emit an answer that
  doesn't cite at least one document — by design, to keep the
  output grounded.

References:
[`SEARCH_ENGINES.md`](docs/reference/SEARCH_ENGINES.md) ·
[`EMBED_WIDGET.md`](docs/reference/EMBED_WIDGET.md) ·
[`NL_SEARCH.md`](docs/reference/NL_SEARCH.md).

### 11. Linked Open Data, OAI-PMH, and harvestability

Public pages emit:

- **schema.org JSON-LD** in `<head>` for Google Dataset Search,
  Scholar, and other crawlers.
- **Content-negotiated RDF** on collection and document
  endpoints — Turtle, RDF/XML, JSON-LD via `Accept` header.
- **OAI-PMH 2.0** at `/api/v1/oai` (Dublin Core mapping from the
  TEI header), suitable for harvest by Europeana, OpenDOAR,
  national repositories, and institutional library catalogs.
- **Entity links** populated by the inline-authority capability
  (Wikidata QIDs, ORCID, VIAF, GeoNames, …) become
  `schema:sameAs` / `foaf:account` triples in the RDF output.

References:
[`LOD_INTEGRATION.md`](docs/reference/LOD_INTEGRATION.md) ·
[`OAI_PMH_PROVIDER.md`](docs/reference/OAI_PMH_PROVIDER.md) ·
[`SEO.md`](docs/reference/SEO.md).

### 12. External deposit and archiving

Six deposit backends, each opt-in at the deployment level (Admin
activates the plugin and pastes credentials) and per-action at the
editorial level:

| Plugin | Deposits | Returns |
|---|---|---|
| **Zenodo** | Collection TEI files and/or built website | DOI on publish, draft URL otherwise |
| **Internet Archive** | Public URL submitted to Save Page Now 2 | Wayback snapshot URL |
| **Dataverse** | Collection TEI files or website tree on any Dataverse instance (default `demo.dataverse.org`; per-deposit alias override) | DOI on dataset creation (resolves on publish) |
| **Codeberg / GitHub / GitLab** | Push every TEI file (collection) or rendered file (website) to a git repository in one commit per push | Commit SHA + Wayback link |

The git-forge plugins also support the **Initialize** flow
(forge → empty Aracne2 collection): a one-shot import of every
XML file from a repo into an empty collection. Once the
collection has any document, Initialize is permanently disabled —
the only allowed direction is push (Aracne2 → forge).

Self-hosted forges and Dataverses are supported via configurable
`base_url`. Per-link PAT and per-deposit alias overrides cover
multi-tenant institutional deployments.

References:
[`NON_NATIVE_PLUGINS.md`](docs/reference/NON_NATIVE_PLUGINS.md).

### 13. Notifications, email, and password reset

Two channels, both off by default at the platform level:

- **In-app notifications** — bell icon in the top nav, fed by the
  notification dispatcher plugin which hooks into every workflow
  event (assigned / submitted / revisions / published / new
  account / ZIP upload completed / …).
- **Transactional email** — sent through a **bundled Postfix
  container** that owns the queue, retries, and DKIM. The backend
  opens an unauthenticated SMTP connection on the docker network;
  the platform stores **no SMTP secrets** in the database. Per-user
  opt-out via the `email_notifications_enabled` profile toggle.

Three workflow events are wired through email today (collection
submitted, sent back for revisions, published) plus the
**self-service password reset** flow: `/forgot-password` →
single-use token (1h expiry) → `/reset-password/:token`.

References:
[`NOTIFICATIONS.md`](docs/reference/NOTIFICATIONS.md) ·
[`EMAIL_CHANNELS.md`](docs/reference/EMAIL_CHANNELS.md).

### 14. Webhooks and outbound integrations

Admin-managed HTTP webhook subscriptions on the platform's hook
events: `collection.submitted` / `published` / `unpublished`,
`document.uploaded` / `deleted`, `user.created`. Each endpoint
carries an optional HMAC signing secret for receiver-side
verification, the last delivery outcome (timestamp, HTTP status,
error message), a manual test button, and automatic retry up to
three times.

References:
[`WEBHOOKS.md`](docs/reference/WEBHOOKS.md).

### 15. The MCP server — Aracne2 as an LLM tool host

Aracne2 ships a built-in **Model Context Protocol** server that
exposes a curated set of read-only tools (`document_search`,
`entity_search`, `collection_metadata`, `document_content`, …) over
the MCP wire protocol.

- **Per-corpus token model.** A token is scoped to one corpus (a
  named subset of collections); a single Aracne2 install can host
  heterogeneous projects (a 13th-century chancery edition next to
  a 20th-century private archive) without their analyses bleeding
  into each other.
- **No write tools.** The MCP surface is intentionally read-only —
  no LLM agent can mutate TEI through MCP; edits go through the
  authenticated REST API, with audit log.
- **Powers** the `nl_search` plugin's public natural-language
  search ([§ 10](#10-search--within-across-and-natural-language)).

References:
[`MCP_SERVER.md`](docs/reference/MCP_SERVER.md) ·
[`NL_SEARCH.md`](docs/reference/NL_SEARCH.md).

### 16. The `aracne` CLI and Personal Access Tokens

A small Python package shipped at [`cli/`](cli/) (not on PyPI;
audience is invite-only). Headless tool that runs on an editor's
laptop and talks to the platform over HTTPS using a **Personal
Access Token (PAT)** the editor issues from the Profile view.

| Command | Purpose |
|---|---|
| `aracne login` | Capture a PAT and verify it against the host |
| `aracne whoami` | Print the user the PAT resolves to |
| `aracne import --collection SLUG --dir PATH` | Bulk-upload `*.xml` files |
| `aracne export --collection SLUG --output FILE.zip` | Download working tree as ZIP |
| `aracne export … --as-of YYYY-MM-DD` | Resolve every doc to its publication-origin state at that date |

PATs live in `personal_access_tokens` (parallel to `mcp_tokens`),
inherit the issuer's role at request time, are bcrypt-hashed at
rest, and can be revoked individually from the Profile card —
revocation invalidates the token on the next request. M1's
acceptance criterion ("a new admin can deploy Aracne2, generate
a CLI export, restore it on a fresh instance, and recover the
previous content history") rests on this command.

References:
[`CLI.md`](docs/reference/CLI.md).

### 17. Audit log

Every intentional, user-attributable action is recorded in the
`audit_log` table — auth events, document edits, plugin
activations, settings changes, role grants, GDPR requests, policy
publications, and so on. The table has been populated by the
platform since day one; **M2** added the admin-facing view at
`/admin/audit-log` so an Admin no longer needs `psql` to answer
"who deleted X last week".

The page supports free-text + action-prefix + actor + date-range
filters and a CSV export. Privacy posture: IP addresses are
already SHA-256-hashed in production; anonymised users surface
their placeholder identity. Retention is configurable
(`audit_log_retention_days`, default 90) — a nightly job prunes
older rows.

References:
[`AUDIT_LOG.md`](docs/reference/AUDIT_LOG.md).

### 18. Fixity layer

CTS R7's deliverable: per-document SHA-256 records that the
platform re-checks on a schedule and surfaces drift in
`/admin/fixity`. Aracne2 already wrote per-version SHA-256
fingerprints since M1 (Alembic 0072); **M2** added the routine
re-check.

The sweep targets the **latest publication-origin version per
(collection, filename)** — exactly what the public site serves.
Older versions and `manual`-origin rows are not re-hashed on the
schedule (their integrity check happens on read), keeping the
sweep cheap and meaningful. A **Recheck now** button runs the
sweep on demand, useful right after a backup restore or storage
swap.

References:
[`FIXITY.md`](docs/reference/FIXITY.md) ·
[`CTS_COMPLIANCE.md`](docs/reference/CTS_COMPLIANCE.md).

### 19. Policy pages, capability roles, and CTS posture

Trustworthy-repository assessments (CoreTrustSeal, nestor seal,
ISO 16363) ask a deployment to publish institutional declarations.
The **`policy_pages`** plugin (M3) turns these into live forms
inside Aracne2 with public rendering, multi-locale support
(IT / EN), and append-only versioning.

Twelve templates ship out of the box, each with a form, public
URL, and version history: `mission`, `privacy_dpia`,
`storage_policy`, `continuity_plan`, `preservation_plan`,
`appraisal_policy`, `incident_response`, `citation_guide`,
`editorial_board`, `funding_staffing`, `expert_directory`,
`cts_self_assessment`. Each ships with field-level guidance and a
"reference deployment" example, so a new operator can stand up
the page set in an afternoon.

Editing is delegated through **`PolicyManager`**, the first
**capability role** — orthogonal to the five hierarchical roles,
granted explicitly per user, singleton (at most one active
holder, with transactional transfer producing a single
`role.transferred` audit row). Granting it to user B while user A
holds it auto-revokes A in the same transaction.

The `cts_self_assessment` template's filled state lives at
[`docs/reference/CTS_COMPLIANCE.md`](docs/reference/CTS_COMPLIANCE.md) —
a per-requirement walk-through (16 of 16 strong) of CoreTrustSeal
alignment with explicit platform vs. institutional-declaration
split.

References:
[`POLICY_PAGES.md`](docs/reference/POLICY_PAGES.md) ·
[`CAPABILITY_ROLES.md`](docs/reference/CAPABILITY_ROLES.md) ·
[`CTS_COMPLIANCE.md`](docs/reference/CTS_COMPLIANCE.md).

### 20. GDPR posture

Aracne2 is a CMS for **published scientific work**. A
contribution that has been approved by an EditorInChief and
exposed at a public URL is part of the institution's
record-of-work; self-service "delete my account → unpublish all
my contributions" — the pattern many social platforms ship — is
the wrong shape for an editorial scientific platform.

GDPR art. 17.3.d permits this: erasure does not apply when
processing is necessary "for archiving purposes in the public
interest, scientific or historical research purposes". Edited
scientific corpora fall squarely inside that exception.

What Aracne2 ships:

| Right | Self-service surface |
|---|---|
| **Art. 15 — access** / **Art. 20 — portability** | `GET /users/me/export` from the Profile Privacy card → JSON dump of every personal-metadata row (excludes password hashes, hashed IPs, document bodies) |
| **Art. 16 — rectification** | The Profile edit form (bio, ORCID, email, language, avatar) |
| **Art. 18 — restriction (limited)** | `email_notifications_enabled=false` toggle |
| **Art. 17 — erasure** | **Mediated**: file an anonymisation request from Profile → Admin reviews under institutional sign-off → Admin executes, replacing user fields with a placeholder, rewriting `audit_log.actor_username`, revoking sessions and PATs, deactivating the account |

References:
[`GDPR_POSTURE.md`](docs/reference/GDPR_POSTURE.md).

### 21. Plugin architecture and auto-cabling

Hook-based plugin system (`PluginBase`, `PluginMeta`, the
HookRegistry) with **four UI auto-cabling capabilities**:

| Capability | Where it surfaces |
|---|---|
| `inline_authority` | TEI editor toolbar buttons (Wikidata, ORCID, ROR, …) — see [§ 6](#6-named-entities-and-authority-linking) |
| `collection_deposit` | Per-plugin section on the collection detail page (Zenodo / IA / Dataverse / forges) |
| `website_deposit` | Per-plugin section on the website edit page |
| `public_navigation` | Public header / home tile / footer link, gated by per-plugin admin toggle — see [§ 22](#22-public-link-toggles-and-admin-surfaces) |

Each capability is declared in the plugin's `meta.capabilities`
tuple plus a `ui_descriptor` block; the SPA's iterators consume
the descriptors over the existing `UiConfigResponse` channel. A
new public-facing plugin needs zero edits to `PublicHeader`,
`CollectionEdit`, `WebsiteEdit`, or any other shared component.

Native plugins (always active): audit logger, notification
dispatcher, AI provider adapters, OAI-PMH provider, EVT viewer
feed, MCP server, hooks framework. Non-native plugins
(activatable from `/admin/plugins`): twelve authority lookups,
six deposit backends, the `nl_search` and `policy_pages` plugins,
the Wayback "archive once" hook, the bundled MCP wrapper plugins
for downstream LLM tools.

References:
[`PLUGINS.md`](docs/reference/PLUGINS.md) ·
[`NON_NATIVE_PLUGINS.md`](docs/reference/NON_NATIVE_PLUGINS.md) ·
[`PUBLIC_NAVIGATION.md`](docs/reference/PUBLIC_NAVIGATION.md).

### 22. Public-link toggles and admin surfaces

A plugin that declares `public_navigation` does **not**
auto-publish its public surface. An Admin must consciously flip
the matching toggle in **Public Pages → Pagine → Plugin links**
(or in any user with the `PolicyManager` capability for
policy-related links). This guards against
"installed-but-not-yet-configured" surprises on the public site.

Admin-only surfaces shipped post-M0 (besides the existing
`/admin/users`, `/admin/plugins`, `/admin/settings`):

| Page | Purpose |
|---|---|
| `/admin/audit-log` | Browse / filter / export the audit log ([§ 17](#17-audit-log)) |
| `/admin/fixity` | Per-collection fixity dashboard + recheck ([§ 18](#18-fixity-layer)) |
| `/admin/policies` | Edit / publish institutional declarations ([§ 19](#19-policy-pages-capability-roles-and-cts-posture)) |
| `/admin/gdpr` | Review queue for anonymisation requests ([§ 20](#20-gdpr-posture)) |

References:
[`PUBLIC_NAVIGATION.md`](docs/reference/PUBLIC_NAVIGATION.md) ·
[`SYSTEM_SETTINGS.md`](docs/reference/SYSTEM_SETTINGS.md).

---

## Technology stack

| Layer | Technology |
|-------|-----------|
| Backend runtime | Python 3.12 · FastAPI · SQLAlchemy 2 async · Alembic · Pydantic v2 |
| Auth | **PyJWT** (migrated from python-jose 2026-05-03) · **bcrypt directly** (no passlib) · httpOnly refresh cookie |
| Databases | PostgreSQL 15 · eXist-db 6.x · pgvector (optional, RAG) |
| XML | defusedxml (XXE prevention) · XQuery 3.1 · lxml |
| Email | bundled Postfix container — no SMTP secrets in DB |
| Scheduling | APScheduler (fixity sweep, audit-log retention prune) |
| Frontend | Vue 3 · Vite 5 · Pinia · Vue Router 4 · vue-i18n 9 · Tailwind CSS 3 |
| Sanitisation | bleach (Markdown rendering on policy pages) |
| Testing | pytest-asyncio · SQLite in-memory · Vitest |
| Infrastructure | Docker · docker-compose · nginx |
| CLI | `cli/aracne_cli` — typer + httpx + rich |

---

## Quick start

The full, dummy-friendly walk-through — prerequisites, first-time
configuration, default credentials, daily-workflow targets, and a
troubleshooting section — lives in [quickstart.md](quickstart.md).

The bare-minimum sequence, for the impatient:

```bash
git clone <repo-url> && cd aracne2
cp .env.example .env       # then fill JWT_SECRET, POSTGRES_PASSWORD; leave EXIST_PASSWORD empty
make up
make migrate
make seed
```

Frontend at http://localhost:5173 — login `admin` / `changeme_admin`
(unless you changed `ADMIN_PASSWORD` in `.env`).

For a server-side install (test/dev or production) see
[`docs/reference/INSTALL_LINUX_SERVER.md`](docs/reference/INSTALL_LINUX_SERVER.md);
for day-to-day operations (rotating credentials, troubleshooting,
backup) see
[`docs/reference/OPERATIONS.md`](docs/reference/OPERATIONS.md).

---

## Project structure

```
/
├── backend/
│   ├── app/
│   │   ├── main.py            # FastAPI entrypoint + lifespan
│   │   ├── config.py          # Pydantic Settings
│   │   ├── core/              # exceptions, hooks, plugin_loader, password
│   │   ├── db/                # postgres, existdb, seed
│   │   ├── middleware/        # ACL, capabilities, CORS, rate limiter
│   │   ├── models/            # SQLAlchemy ORM models (Layer 1)
│   │   ├── routers/           # FastAPI routers (one per domain)
│   │   ├── schemas/           # Pydantic schemas
│   │   ├── services/          # business logic
│   │   ├── plugins/           # built-in + non-native plugin packages
│   │   ├── xqueries/          # XQuery files (never inline)
│   │   ├── email_templates/   # transactional email templates
│   │   ├── help_docs/         # in-app help (Markdown)
│   │   └── tests/
│   ├── alembic/               # migrations (latest: 0081_capability_roles)
│   └── requirements.txt
├── frontend/
│   └── src/
│       ├── services/api.ts    # axios + token refresh interceptor
│       ├── stores/            # Pinia stores
│       ├── router/            # Vue Router + navigation guards
│       ├── views/             # page components
│       ├── components/        # reusable components
│       └── locales/           # i18n (en, it)
├── cli/                       # aracne-cli — bulk import/export tool
│   └── aracne_cli/            # commands: login, whoami, import, export
├── docs/
│   ├── USER_MANUAL.md         # non-developer end-to-end guide
│   ├── TO_DO.md               # operational backlog (priority-ordered)
│   └── reference/             # per-feature reference documents
├── docker-compose.yml
├── docker-compose.prod.yml
├── nginx.conf
├── Makefile
└── .env.example
```

---

## Role hierarchy

Editor and Designer are **lateral roles** at the same level —
orthogonal domains, same person or different people.

```
                Admin
                  │
            EditorInChief
             ╱          ╲
        Editor          Designer
             ╲          ╱
                User
```

| Role | Level | Domain |
|------|-------|--------|
| User | 1 | Read-only access to published content |
| Editor | 2 | Creates and edits documents |
| Designer | 2 | Manages XSLT templates and CSS themes |
| EditorInChief | 3 | Manages collections and publication workflow |
| Admin | 4 | Full platform access |

A separate **capability role** mechanism layers on top, granted
per user and orthogonal to the hierarchy. The first concrete
capability is `PolicyManager`
([§ 19](#19-policy-pages-capability-roles-and-cts-posture));
future capabilities like `Translator` or `Annotator` would land
as additional values of the `RoleName` enum without API changes.

---

## Security

- `access_token`: stored in Pinia memory only — never in
  localStorage / sessionStorage.
- `refresh_token`: httpOnly + SameSite=Strict + Secure cookie —
  the SPA never reads it; silent refresh on boot via `POST
  /auth/refresh`.
- **PyJWT** for token signing (migrated from python-jose
  2026-05-03 to close the unmaintained-dep risk and shed the
  transitive pyasn1 attack surface) + **bcrypt directly** for
  password hashing (no passlib — unmaintained since 2020).
- **Rate limiting**: 10 req/min on auth + MCP endpoints, 200
  req/min global; lookup-plugin routes carry their own
  intermediate limit tuned to the upstream's quota.
- **XML parsing** via `defusedxml` (XXE prevention) end-to-end
  — including the validator, the OAI-PMH provider, and every
  authority-lookup adapter that consumes upstream XML.
- **Markdown sanitisation** via `bleach` on every policy-page
  render — XSS-safe by construction.
- **CORS**: validated at startup — no `*` wildcard, every
  origin must be `http://` or `https://`, non-localhost
  `http://` rejected in production.
- **CSP, X-Frame-Options, HSTS** configured in `nginx.conf` —
  HSTS commented and ready to uncomment when HTTPS is active.
- **Audit log** ([§ 17](#17-audit-log)) and **fixity layer**
  ([§ 18](#18-fixity-layer)) provide the operational
  counterpart to the security posture.
- **Manual security review cadence** — local Claude-driven
  reviews are persisted in `docs/Security_review_*.md` (latest:
  `2026-05-03`); not run from CI by design.

---

## Production deployment

```bash
# Build production images
make build-prod

# Start production stack (nginx serves the built SPA, 4 uvicorn workers)
make up-prod
```

Before going to production:

- Set `ENVIRONMENT=production` in `.env`.
- Generate a strong `JWT_SECRET`
  (`python -c "import secrets; print(secrets.token_hex(64))"`).
- Uncomment the HSTS header in `nginx.conf` once HTTPS is active.
- Change all default passwords in `.env`.
- Restrict `.env` permissions so only the deploy user can read it:
  ```bash
  chmod 600 .env
  chown <deploy-user>:<deploy-user> .env
  ```
  `.env` is already excluded from git via `.gitignore`. The
  `chmod 600` ensures other OS users on the same server cannot
  read the file in plain text. `docker compose` reads it
  correctly regardless of these permissions as long as it runs
  as the same user.

The full operations runbook (rotating credentials, port / DNS /
bootstrap troubleshooting, backup, log access, queue flush)
lives in
[`docs/reference/OPERATIONS.md`](docs/reference/OPERATIONS.md).

---

## Reference documentation

The detailed reference tree lives in
[`docs/reference/`](docs/reference/). Cross-document index:

### Architecture & contracts

| Document | Topic |
|---|---|
| [API_FORMAT.md](docs/reference/API_FORMAT.md) | Standard JSON envelope, pagination, error format |
| [DB_SCHEMA.md](docs/reference/DB_SCHEMA.md) | PostgreSQL platform schema (Layer 1) |
| [SYSTEM_SETTINGS.md](docs/reference/SYSTEM_SETTINGS.md) | All `system_settings` keys, types, defaults |
| [HEALTH_CHECK.md](docs/reference/HEALTH_CHECK.md) | Health-check endpoint contract |
| [EXISTDB_SETUP.md](docs/reference/EXISTDB_SETUP.md) | eXist-db user model, bootstrap, env vars |

### Editorial domain

| Document | Topic |
|---|---|
| [COLLECTIONS.md](docs/reference/COLLECTIONS.md) | Collections & TEI editor — data model, endpoints |
| [DOCUMENT_VERSIONING.md](docs/reference/DOCUMENT_VERSIONING.md) | Working/published split, `document_versions` schema |
| [TEI_SCHEMAS.md](docs/reference/TEI_SCHEMAS.md) | Schema catalog (RNG / DTD / XSD / CM5) |
| [BODY_TEMPLATES.md](docs/reference/BODY_TEMPLATES.md) | Body templates for new-document creation |
| [ZONES_FACSIMILE.md](docs/reference/ZONES_FACSIMILE.md) | Text-image alignment via TEI `<zone>` / `facs` |
| [NAMED_ENTITIES.md](docs/reference/NAMED_ENTITIES.md) | Named entity index, normalisation, authority linking |
| [BIBLIOGRAPHY.md](docs/reference/BIBLIOGRAPHY.md) | Bibliographic entries, BibTeX/CSL-JSON, Bibliobuilder |

### Publication

| Document | Topic |
|---|---|
| [WEB_SITES.md](docs/reference/WEB_SITES.md) | Website generator — static / dynamic / hybrid |
| [XSLT_TEMPLATES.md](docs/reference/XSLT_TEMPLATES.md) | XSLT template catalog |
| [PUBLIC_PAGES.md](docs/reference/PUBLIC_PAGES.md) | Public-page CSS classes |
| [SEO.md](docs/reference/SEO.md) | Schema.org / Dublin Core surface |
| [SEARCH_ENGINES.md](docs/reference/SEARCH_ENGINES.md) | Search Engine portals |
| [EMBED_WIDGET.md](docs/reference/EMBED_WIDGET.md) | Embeddable JS search widget |
| [EVT_INTEGRATION.md](docs/reference/EVT_INTEGRATION.md) | EVT 2 viewer integration |

### Cross-platform integration

| Document | Topic |
|---|---|
| [LOD_INTEGRATION.md](docs/reference/LOD_INTEGRATION.md) | Wikidata, ORCID, JSON-LD, RDF content negotiation |
| [OAI_PMH_PROVIDER.md](docs/reference/OAI_PMH_PROVIDER.md) | OAI-PMH 2.0 metadata provider |
| [WEBHOOKS.md](docs/reference/WEBHOOKS.md) | Webhook dispatcher — events, signing, retries |
| [NOTIFICATIONS.md](docs/reference/NOTIFICATIONS.md) | In-app notification system |
| [EMAIL_CHANNELS.md](docs/reference/EMAIL_CHANNELS.md) | Postfix-based transactional email + password reset |

### AI surface

| Document | Topic |
|---|---|
| [AI_INTEGRATION.md](docs/reference/AI_INTEGRATION.md) | Provider adapters, prompt library, RAG, streaming |
| [MCP_SERVER.md](docs/reference/MCP_SERVER.md) | Model Context Protocol — tools, corpora, token model |
| [NL_SEARCH.md](docs/reference/NL_SEARCH.md) | Public natural-language search plugin |

### Plugins, capabilities, public navigation

| Document | Topic |
|---|---|
| [PLUGINS.md](docs/reference/PLUGINS.md) | Plugin architecture, native plugins, hooks |
| [NON_NATIVE_PLUGINS.md](docs/reference/NON_NATIVE_PLUGINS.md) | Authority lookups + deposit backends |
| [PUBLIC_NAVIGATION.md](docs/reference/PUBLIC_NAVIGATION.md) | `public_navigation` capability + admin toggles |
| [CAPABILITY_ROLES.md](docs/reference/CAPABILITY_ROLES.md) | Capability roles + singleton semantics |
| [POLICY_PAGES.md](docs/reference/POLICY_PAGES.md) | Institutional declarations as live forms |

### Tooling, posture, governance

| Document | Topic |
|---|---|
| [CLI.md](docs/reference/CLI.md) | `aracne` CLI + Personal Access Tokens |
| [AUDIT_LOG.md](docs/reference/AUDIT_LOG.md) | Audit log schema + admin dashboard |
| [FIXITY.md](docs/reference/FIXITY.md) | Fixity layer — schedule, drift surface |
| [GDPR_POSTURE.md](docs/reference/GDPR_POSTURE.md) | GDPR for an editorial scientific platform |
| [CTS_COMPLIANCE.md](docs/reference/CTS_COMPLIANCE.md) | Per-requirement CoreTrustSeal self-assessment |

### Operations & install

| Document | Topic |
|---|---|
| [INSTALL_LINUX_SERVER.md](docs/reference/INSTALL_LINUX_SERVER.md) | Server-side install (test / dev / production) |
| [OPERATIONS.md](docs/reference/OPERATIONS.md) | Day-to-day operations runbook |
| [BRAND.md](docs/reference/BRAND.md) | Aracne icon set — sigla → path mapping |

### Out-of-tree planning

| Document | Topic |
|---|---|
| [docs/USER_MANUAL.md](docs/USER_MANUAL.md) | End-to-end manual for non-developer users |
| [docs/TO_DO.md](docs/TO_DO.md) | Operational backlog, priority-ordered |

---

## License

See [LICENSE](LICENSE).
