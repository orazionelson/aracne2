# To-do — Aracne2 backlog

Single consolidated backlog. Replaces the previous
`DEFERRED.md` + `FUTURE_IDEAS.md` split — the distinction
("decision deferred" vs. "future feature") was operational, and
the split stopped earning its keep once the three milestones
closed and the M1-residual GDPR work shipped.

Items are grouped by **priority**; within each group, ordered by
where I'd recommend picking next based on value × readiness ×
unblocking-effect on other items.

## Priority legend

| Tag | Code prefix | Meaning |
|---|---|---|
| 🔴 High | `H` | Clear value, ready for pickup |
| 🟡 Medium | `M` | Value confirmed but waiting on a trigger or sequencing |
| 🟢 Low | `L` | Niche, ship if specifically requested |
| 🔵 To discuss | `T` | Needs a design conversation before scoping |

Each entry is identified by `<prefix><n>` (e.g. `H1`, `M3`,
`T7`). New entries are appended within their priority section
without renumbering the others; cross-references stay stable.

Long design conversations from the original `FUTURE_IDEAS.md`
and `DEFERRED.md` files are preserved in git history; this file
is the operational backlog, not the design archive.

---

## 🔴 High

### H1. Automated bibliography enrichment via DOI / ISBN lookup

**Motivation.** Manual entry of bibliographic metadata is
error-prone and time-consuming. The platform already has
single-shot CrossRef / OpenAlex lookup plugins; what's missing
is the **batch path** — "enrich every empty `<biblStruct>` in
this collection at once".

**Scope.**
- Backend: a service that walks a collection's bibliography,
  identifies entries with a DOI / ISBN but missing structured
  fields, calls the existing lookup plugins per entry, and
  writes back the resolved metadata.
- Frontend: an "Enrich bibliography" button on
  `CollectionDetailView` with a progress + results panel.
- Caching: lookups already cache in PostgreSQL via
  `search_engine_query_cache` pattern; same approach here to
  avoid burning the CrossRef rate limit.

**Trigger.** A real corpus on a deployment with hundreds of
unstructured citations.

**Effort.** ~2-3 days.

---

### H2. Public reader statistics and analytics

**Motivation.** Scholarly editors and funders need evidence of
readership; today the platform has zero analytics. Basic counts
(views per document, search frequency, geographic aggregate)
justify project resources without third-party tracking.

**Scope.**
- New `view_stats` table aggregating daily counts per document.
- Hashed-IP geographic aggregation (no individual tracking).
- Bot-filter heuristic (User-Agent + rate-based).
- Admin dashboard at `/admin/stats` showing top documents, views
  over time, popular searches.

**Privacy invariants** — same as the audit log: no individual-
level tracking, hashed IPs only, configurable retention via
`system_settings.view_stats_retention_days` (default 12 months).

**Trigger.** First public deployment with real traffic, **or** a
funder asking for usage evidence.

**Effort.** ~3-4 days.

---

### H3. Document the collection-import ZIP layout requirement

**Motivation.** Importing a collection requires the XML files at
the **root** of the ZIP, no enclosing folder. This is
counter-intuitive: most users right-click a folder and "Compress",
producing a ZIP with a single top-level directory — which today
fails (or imports silently nothing). Recurring user-feedback item.

**Scope (docs only, no server-side behaviour change).**
- `USER_MANUAL.md` — short section under collection import with
  a worked example for Linux / macOS (`zip -j out.zip *.xml`) and
  Windows ("Select all files inside the folder, then Send to →
  Compressed folder"). Show both a ✅ and a ❌ tree.
- In-app help (`backend/help_docs/02-editing/...`) — same example,
  same screenshots if any.
- The ZIP upload panel in the Collections page — an inline info
  box ("Files at the ZIP root, no enclosing folder") next to the
  file picker, with a link to the help page.
- Backend: make the existing error message explicit when the ZIP
  contains a single top-level directory and no XML at the root
  ("The ZIP contains a folder `<name>/` but no XML at the root.
  Re-zip selecting the files, not the folder.").

**Trigger.** User feedback (recurring).

**Effort.** ~0.5 days.

**See also.** Item §T7 explores the alternative server-side fix
(accept any layout, flatten on import); it's a UX call that needs
discussion first. This entry is the no-regret first move.

---

### H4. Non-native plugin: TEI editor tag/snippet toolbar buttons

**Motivation.** TEI exposes ~1500 tags, but real editorial projects
mark content with under a dozen of them. The old Aracne wired
fixed buttons (`[persName]`, `[placeName]`, …) into CodeMirror so
editors could one-click insert an empty tag at the cursor or
wrap a selection with it. In Aracne2 the same idea needs to be
**dynamic and per-collection**, because two corpora on the same
instance carry different tagsets.

**Scope.**

- **Plugin** (non-native, opt-in from `/admin/plugins`). Reuses
  the same plugin-discovery pattern as the authority chips
  (Wikidata, ORCID, ROR, …) — the TEI editor auto-cables the
  buttons declared by the plugin via a new capability
  `inline_snippet`, sibling of `inline_authority`.
- **Per-collection configuration**, surfaced as a panel on the
  Collection detail page, **below the deposit-providers section**.
  The list of buttons lives on the Collection (single source of
  truth per corpus).
- **Two-mode "Add" UI**:
  - *Add tag button* — input that takes a single tag name (e.g.
    `persName`); the plugin synthesises the snippet
    `<persName>${SEL}</persName>` under the hood.
  - *Add snippet button* — textarea that takes a full snippet
    (e.g. `<bibl><author></author><title>${SEL}</title></bibl>`),
    with placeholder syntax `${SEL}` (active selection or empty)
    and `${1}`, `${2}`, … (tab-stops à la VS Code, handled by
    CodeMirror 6's `@codemirror/autocomplete` snippet API).
- **Unified data model.** Internally a button is always a
  snippet — the "Add tag" mode is sugar that produces the wrapper.
  A small *Promote to snippet* action lets an editor convert a
  tag entry into a full snippet later, without re-adding it.
- **Well-formed XML validation before save.** Required on both
  ends:
  - Substitute the known placeholders (`${SEL}`, `${1}`, …) with
    a literal (`x`), wrap the result in a synthetic root, and
    parse.
  - Backend: `defusedxml.ElementTree.fromstring(...)` —
    mandatory per project rules.
  - Frontend: `new DOMParser().parseFromString(..., "application/xml")`
    + check for `<parsererror>` — for immediate feedback.
  - A failing parse blocks save with the error position.
- **CRUD + UX**.
  - Add / edit / remove (with `confirm` on remove).
  - Drag-to-reorder, or up/down arrows
    (`@vueuse/integrations` exports `useSortable`). The toolbar
    in the editor honours the configured order.
  - Optional **`label`** field (defaults to the tag name) so the
    toolbar can read "Person" instead of `persName`.
  - Optional **keyboard shortcut** field, restricted to
    `Ctrl+1`…`Ctrl+9`, with anti-collision validation across the
    collection's buttons.

**Trigger.** Recurring editor feedback; the productivity gap vs.
the old Aracne is felt in the first hour of any new project.

**Effort.** ~3-4 days.

---

### H5. Designer-controlled CSS for generated websites — download default, upload override, live preview

**Motivation.** Each generated website ships a baked-in default
stylesheet (`_STATIC_CSS`) that covers all page types out of the
box. Designers can already tweak palette / font via the structured
`theme_config` and add additive overrides via the existing
`custom_css` textarea. What's missing is the natural *"fork the
default"* workflow — download the resolved default, edit it
locally, upload back as a full replacement — plus a live preview
so iteration is *edit → see* rather than *edit → save → rebuild
→ reload*. Mirrors the existing pattern of
`/admin/public-pages → Foglio di stile personalizzato`.

**Scope.**

- **Data model.** New field on the `websites` model:
  `override_css: Text | None`. Trivial migration.
- **Build-time cascade** (refactor `_style_block` in
  `backend/app/services/websites.py`):
  1. `:root{--primary…}` from `theme_config` — *always* emitted,
     regardless of mode. The color picker / font selector keep
     working in override mode.
  2. either `_STATIC_CSS` *or* `website.override_css` when set —
     mutually exclusive.
  3. `website.custom_css` — *always* emitted last, the existing
     "last-mile" additive textarea. Survives override mode as
     the last resort for patches the uploaded sheet didn't
     cover.
- **UI** — mirror the `/admin/public-pages → Foglio di stile
  personalizzato` card, surfaced in the website edit page's
  CSS/JS section:
  - Status pill (*"Nessun CSS personalizzato"* /
    *"CSS personalizzato attivo"*).
  - File input + *"Carica"* button to upload the override.
  - *"Reset to default"* button (clears `override_css`).
  - *"Scarica CSS"* link in the footer: downloads the current
    `_STATIC_CSS` with the website's resolved `:root{…}`
    prepended — ready as a starting point for a fork.
- **Validation** on upload:
  - Strip `</style>` from the file before save (same defence
    used today on `custom_css`).
  - Reject non-`text/css` MIME and files over a configurable
    cap (e.g. 256 KB).
- **Live preview** (the E component):
  - New tab *"Anteprima"* in the website CSS/JS edit panel.
  - Backend endpoint `GET /websites/{id}/sample-html?page_type=
    home|collection|document|search` returns the website's
    most-recently-built HTML for that page type, stripped of
    its `<style>` block.
  - Frontend renders the result in an `<iframe srcdoc>` and
    injects the *work-in-progress* CSS (default-or-override +
    `custom_css`) into a fresh `<style>` block. Re-renders on
    a 300 ms debounce after textarea changes or after a
    successful upload.
  - Fallback when the site has never been built: a hardcoded
    skeleton HTML covering the four page types, so the
    preview is usable from day one.

**Trigger.** Recurring Designer feedback on the need to
"really" customise the look beyond the structured theme.

**Effort.** ~3-4 days for the upload/override + ~2 days for the
live preview = ~5-6 days total. Done as one feature because
upload/override and preview share the same panel and the same
CSS-resolution code.

---

## 🟡 Medium

### M1. CI pipeline on GitHub Actions

**Motivation.** Today the maintainer runs `pytest` locally. CI
gives external contributors a green-check signal on PRs and
makes the project safer to receive contributions for.

**Scope.**
- `.github/workflows/ci.yml` — matrix run on push + PR:
  - Backend: `pip install -r requirements.txt && pytest -q`
  - Frontend: `npm install && vue-tsc --noEmit && vitest run`
  - Lint: `ruff check`, `mypy --strict app/`
- Optional: Dependabot config (already alerting on the public
  repo without a config file; an explicit one tightens cadence).

**Trigger.** First external contributor PR, **or** a slot of
admin time.

**Effort.** ~1-1.5 days.

---

### M2. Async task queue (Celery / ARQ / Dramatiq)

**Motivation.** Long-running operations today either block the
HTTP request or use `asyncio.create_task` (lost on restart).
"Big" publishes (corpus with hundreds of documents), Zenodo
deposits, ZIP exports, embedding rebuilds all suffer. An async
queue unblocks these AND prepares the ground for the PDF
sidecar (§L1), HTR pipeline (§M11), and batch bibliography
enrichment (§H1).

**Scope.**
- Pick **ARQ** (Redis-only, leanest); Redis is the single new
  service.
- Wrap the existing long-running operations as ARQ tasks;
  callers `enqueue` and the SPA polls a job-status endpoint.
- Worker container in `docker-compose.yml` under a `worker`
  profile so deployments without long-running ops don't have
  to start it.

**Trigger.** First publish that times out, **or** any of the
items above (§M11, §M13, §M15, §L1) gets pickup.

**Effort.** ~2 days for the substrate + 1 day per migrated
operation.

---

### M3. Server-side PDF renderer — opt-in sidecar service

**Motivation.** Browser-print covers 80% of the PDF use case
today. The 20% — byte-deterministic policy PDFs for CTS reviewers,
deposit pipelines that want the PDF attached server-side,
nightly export jobs — need a server renderer. Weasyprint pulls
~80 MB of system libs (cairo, pango, gdk-pixbuf), so a sidecar
container with `pdf` compose profile keeps the cost opt-in.

**Scope.**
- New `sidecars/pdf/` container with FastAPI + weasyprint.
- Backend `services/pdf_renderer.py` httpx wrapper; returns
  `None` if the sidecar URL is unreachable so the caller falls
  back to browser-print.
- Two parallel UX paths on every PDF-producing surface (TEI
  documents, bibliography, entities pages, policies, audit-log
  export): browser-print button always present; "Official PDF"
  link only when the sidecar is reachable.
- Static-website export keeps browser-print only — no backend
  at runtime.

**Trigger.** A CTS reviewer asking for byte-deterministic PDFs,
**or** a deposit pipeline that wants PDF attached server-side.

**Effort.** ~3-4 days.

---

### M4. S3-compatible media backend (read + write, private buckets)

**Motivation.** Today media (avatars, homepage assets, website
images, TEI media) lives on the local filesystem. A multi-replica
deployment, a backup-friendly setup, or an S3-only institutional
storage requires an S3 backend. Pure read+write, with private
bucket support (signed URLs).

**Scope.**
- New `app/services/media_storage.py` interface; pluggable
  backends `local` (existing) and `s3`.
- `system_settings.media_storage_backend` toggle.
- Migration tool to move local files to S3 (one-shot).
- Signed-URL generation for private buckets; CDN-friendly cache
  headers for public ones.

**Trigger.** Operator with S3 / MinIO infrastructure asking for
this, **or** a multi-replica deployment.

**Effort.** ~3 days.

---

### M5. Collection ACL — multi-editor support

**Motivation.** Currently one Editor is assigned per collection;
collaborative editing on a single collection requires escalation
to EditorInChief or hand-off. Multi-editor would let two or more
Editors share write access to the same collection without
EiC-level rights.

**Scope.**
- Repurpose the existing `collection_permissions` table (already
  shipped, currently single-FK) to a many-to-many.
- Update `require_collection_write` to allow any user with an
  active permission row.
- Frontend: collection detail "Editors" list with add/remove.

**Trigger.** First deployment with co-edited collections.

**Effort.** ~1.5 days.

---

### M6. Full-collection validation — performance optimisation

**Motivation.** Schema-validation runs per-document today. A
collection-wide report walks every document sequentially and
becomes slow on collections >500 documents.

**Scope.**
- Parallelise per-document validation (asyncio gather + a small
  semaphore).
- Cache validation results keyed on `document_versions.content_sha256`
  so unchanged versions are not re-validated on the next sweep.
- Surface a progress bar in the UI.

**Trigger.** First report >30s, **or** a deployment regularly
running collection-wide validation.

**Effort.** ~1.5 days.

---

### M7. TEI `<zone>` — word- / line-level alignment

**Motivation.** Today zones are page-level (one `<surface>` per
image). For HTR / IIIF / OCR-correction workflows, fine-grained
zones (line-level, word-level) are needed.

**Scope.**
- Extend `<zone>` editor with a finer click-and-draw mode.
- Backend stores additional `zone_type` (page / line / word)
  and `text_content` ref to the surrounding TEI element.
- Image overlay viewer shows the right zone level for the
  active TEI selection.

**Trigger.** First HTR project, **or** a IIIF integration that
needs line-anchored text.

**Effort.** ~3-4 days. Pairs with §M11 (HTR pipeline) — most
naturally implemented together.

---

### M8. MCP server — Phase 2 (write tools)

**Motivation.** Phase 1 ships read-only MCP tools (the editor's
LLM client can browse + cite the corpus). Phase 2 would add
**write** tools — ask Claude Desktop to apply a TEI markup
suggestion directly. Significantly more useful but requires a
consent UX so the editor approves each change.

**Scope.** Per-call approval modal in the SPA, signed by an
audit-log entry; tool list extends with `update_document_source`
+ `apply_tei_fragment` + `tag_entity_occurrence`.

**Trigger.** Real signal from the existing read-only Phase 1
usage telling us which write operations are actually wanted.

**Effort.** ~5-7 days. Best paired with §M9 (Phase 3) once
real usage data is available.

---

### M9. MCP server — Phase 3 (identity, members, audit)

**Motivation.** Per-user MCP tokens (instead of corpus-scoped),
`corpus_members` table, dedicated MCP audit-log surface. Earns
its cost only when several editors are actively using MCP.

**Trigger.** Multi-editor MCP usage signal.

**Effort.** ~4 days.

---

### M10. End-to-end AI evaluation harness

**Motivation.** Today AI provider switching (Anthropic / OpenAI /
Ollama) is operator's instinct. A harness that runs a fixed
benchmark suite (TEI-tagging, validation explanation,
bibliography normalisation, NL search recall) against every
configured provider gives a defensible answer to "which provider
serves my corpus best".

**Scope.**
- Frozen benchmark dataset committed to the repo.
- CLI runner (`aracne-cli ai eval`) that calls each provider
  against each task and reports accuracy, latency, cost.
- Markdown report output suitable for committing to a deployment's
  policy archive.

**Trigger.** When a second provider is contributed or an
institution asks for an explicit comparison report.

**Effort.** ~3 days.

---

### M11. End-to-end HTR pipeline — large-corpus image-to-zone import

**Motivation.** A digitised manuscript collection where pages
are images today is a pain to ingest: HTR → zones → TEI is a
multi-step manual process. An end-to-end pipeline would
automate the most repetitive parts.

**Scope.** Adapter for Transkribus (existing API) + zone import
+ TEI scaffolding. Pairs with §M7 (fine-grained zones).

**Trigger.** First manuscript-heavy project.

**Effort.** ~5 days.

---

### M12. Non-native plugin: GROBID — PDF → TEI import

**Motivation.** Operators with PDF-heavy bibliographies or
PDF-only critical apparatus can extract structured TEI via
GROBID. Sidecar deployment (compose profile `grobid`),
opt-in.

**Trigger.** First operator with a large PDF backlog.

**Effort.** ~3 days.

---

### M13. Non-native plugin: LEAF Turning Engine — TEI ↔ Markdown, Transkribus → TEI

**Motivation.** Wraps the LEAF-VRE Turning Engine REST microservice
for two adjacent workflows: a Markdown ↔ TEI bridge that lets
non-XML editors author content, and a Transkribus → TEI
converter that complements (and may eventually subsume) §M11.

**Trigger.** Same as §M11, plus operators with Markdown-only
authoring teams.

**Effort.** ~3 days.

---

### M14. Non-native plugin: nodegoat as authority provider

**Motivation.** Many DH projects already maintain their
prosopography (and increasingly their geography and
event-network) inside a **[nodegoat](https://nodegoat.net/)**
instance. Surfacing that instance as an `inline_authority`
provider lets editors pick from their own project registry
instead of (or alongside) Wikidata, and writes the canonical
nodegoat object URL as `@ref` on `<persName>` / `<placeName>` /
`<orgName>`. Same shape as the existing eleven authority
plugins; the platform's "modular catalogue of connectors"
covers exactly this case.

**Scope.**
- Admin config: `nodegoat_base_url`, `nodegoat_api_key`
  (Fernet-encrypted, added to `SENSITIVE_KEYS`), and
  per-tag Type mapping (`<persName>` → Type "Person",
  `<placeName>` → Type "Place", `<orgName>` → Type
  "Organisation"). All from `/admin/plugins/nodegoat_authority/config`.
- Backend: a `search` endpoint that proxies to nodegoat's
  REST API and returns hits in the editor's standard chip
  shape (label, sub-label, canonical URL).
- Editor: chips `NODE-PER`, `NODE-PLA`, `NODE-ORG` appear
  in the toolbar when the current tag matches; on Apply
  the picker writes `@ref="<base>/object/<id>"`.
- Tests: `httpx.MockTransport` for the proxy + a manual
  smoke test against a real nodegoat instance.

**Trigger.** First operator already running a nodegoat
instance for their prosopography.

**Effort.** ~3-4 days, reusing the wikidata / ror / orcid
plugin scaffold.

---

### M15. TEI-specialised local model via LoRA fine-tuning

**Motivation.** A small (7B / 13B) open model fine-tuned on a
TEI corpus could match cloud models on TEI-specific tasks at a
fraction of the cost. Local-first, no per-token bill.

**Trigger.** A research group with GPU access willing to share
the trained weights.

**Effort.** ~10 days for the harness; the actual fine-tune is
the operator's compute time.

---

### M16. Gamification / contributor leaderboard

**Motivation.** Editorial teams sometimes ask for "who did
what" leaderboards as motivational tooling. Aggregate of
audit-log + version-row counts per user, displayed as an admin
dashboard.

**Trigger.** Specific editorial team request.

**Effort.** ~1.5 days.

---

## 🟢 Low

### L1. Plugin data table

**Motivation.** Plugins that need to persist their own state
write to `system_settings` (not ideal) or ad-hoc tables. A
generic `plugin_data` table (key/value/blob, scoped per plugin)
is cleaner.

**Trigger.** First plugin that genuinely needs it.

**Effort.** ~1 day.

---

### L2. WebSocket / Server-Sent Events for real-time notifications

**Motivation.** The notification dispatcher polls; a WS / SSE
push would be more responsive. Today's polling cadence is
adequate.

**Trigger.** Specifically asked for, **or** a heavy-traffic
deployment where polling becomes burdensome.

**Effort.** ~2 days.

---

### L3. Mobile companion app

**Motivation.** A read-only mobile reader for editors on the go.
Most institutions don't ask for it.

**Trigger.** Specifically asked for.

**Effort.** ~10+ days.

---

### L4. Collaborative real-time editing

**Motivation.** Google-Docs-style real-time co-edit on a single
TEI document. Conflicts with the workflow model (one Editor at
a time per document); not a natural fit.

**Trigger.** Specifically asked for; would need a substantial
data-model redesign.

**Effort.** ~weeks.

---

### L5. Secret management — beyond plain-text `.env`

**Motivation.** Today `.env` carries plaintext credentials.
Vault / SOPS / secrets-store-csi integrations would harden a
production deployment.

**Trigger.** Operator with security policy requiring it.

**Effort.** ~2 days per backend.

---

### L6. SPARQL endpoint over the published corpus

**Motivation.** The platform already emits RDF/Turtle via
content negotiation; a SPARQL endpoint completes the LOD story.
Apache Jena Fuselli sidecar + ETL pipeline.

**Trigger.** A research group with SPARQL-based discovery
needs.

**Effort.** ~3 days.

---

### L7. AI assistant for CSS editing — debug & discuss scopes

**Motivation.** The AI scope infrastructure (`xslt.debug`,
`xslt.discuss`) already supports per-surface AI panels. Designers
who aren't CSS-fluent — common in DH projects — benefit from a
peer assistant that can debug rules ("why isn't this matching?"),
suggest simplifications, or explain existing styles in plain
language. Natural sibling of the XSLT helpers, surfaced in the
same website CSS/JS edit panel.

**Scope.**

- New AI scopes **`css.debug`** and **`css.discuss`** (siblings
  of `xslt.debug` / `xslt.discuss`).
- Prompt context: the website's currently effective CSS (default
  or override + `custom_css`), the resolved `theme_config`
  variables, optionally an HTML fragment the Designer pastes to
  ground the question.
- Three native prompts seeded at boot:
  - **`css_debug`** — paste a failing selector + the HTML it
    should match; the AI explains why it isn't applying
    (specificity, cascade order, missing CSS variable, typo).
  - **`css_simplify`** — AI rewrites a complex rule with less
    specificity / duplication.
  - **`css_discuss`** — open chat scoped to the current
    stylesheet, for explanations or "make this look more X"
    prompts.
- UI: AI sidebar inside the website CSS/JS edit panel, same
  chrome as the existing XSLT AI panel.

**Trigger.** After §H5 lands and there's a real population of
Designers editing CSS through the panel; the assistant has more
to chew on once the override-mode workflow is in production.

**Effort.** ~1.5 days, reusing the existing AI-scope scaffolding
(`backend/app/plugins/_native/ai/`) and the XSLT AI panel as a
Vue template.

---

## 🔵 To discuss

These items need a design conversation before scoping —
priority will be reassessed when the conversation happens.

### T1. Glossary and index generation from named entities

Open question: where does the index live? Standalone HTML
page, document appendix, separate `/glossary` route? Curation
balance vs. autonomy.

### T2. TEI-to-DOCX export

Open question: same shape as §M3 (PDF sidecar) — a pandoc
sidecar, or rely on the user's local pandoc?

### T3. Fuzzy string matching via Apache Commons Text in XQuery

Open question: who needs it? Without a concrete editorial
workflow this is over-engineering.

### T4. DataCite DOI minting

Open question: how many deployments have DataCite without
Zenodo? Today Zenodo (already shipped) covers most cases.

### T5. IIIF integration (+ Mirador / OpenSeadragon)

Open question: serve IIIF Image API ourselves or proxy from a
sidecar? Pairs with §M7 (fine-grained zones) and §M11 (HTR).

### T6. Matomo / Plausible analytics injector

Open question: ship as opt-in sidecar like the deposit plugins,
**or** roll our own inside §H2 (public reader statistics)? Two
overlapping ways to get the same answer.

---

### T7. Server-side auto-flatten of the collection-import ZIP

**Motivation.** Sibling of §H3: instead of (only) documenting the
"files at root, no folder" rule, accept **any** ZIP layout and
flatten it server-side before handing the XML files to eXist.
Removes the most common source of failed first imports.

**Open questions.**
- What if the ZIP contains **multiple top-level folders** (e.g.
  `documents/`, `media/`, `assets/`)? Flatten only the XML tree
  and route media elsewhere? Reject? Pick the largest folder?
- **Name collisions** when two folders contain a file with the
  same basename (`cap1/intro.xml` and `cap2/intro.xml`): reject,
  prefix with the folder path, prefix with a counter, ask the
  user?
- **Non-XML files** unexpectedly present (PDFs, JPEGs, READMEs):
  silently skip, warn but proceed, treat as media, reject?
- **Pathological archives** — deeply nested directory trees,
  thousands of entries, zip-slip-style paths (`../../etc/passwd`):
  what's the safe enumeration limit, how do we validate paths
  before extraction?
- Does the change break the **inverse operation** (export
  collection as ZIP) — should export now produce a flat ZIP too
  for symmetry, or keep the folder structure that operators rely
  on for offline review?

**Trigger.** Decision on the UX stance (strict vs. permissive)
and on each of the open questions above.

**Effort.** ~1.5-2 days of code once the policy questions are
settled; the policy work itself is the gating item.

---

## What recently shipped (no longer on the backlog)

For reference; full details in commit history:

- **M1** (2026-05-02 → 2026-05-03) — Document versioning, email
  channels, CLI/PAT, public_navigation, NL search.
- **M2** (2026-05-03) — PyJWT migration, audit-log admin UI,
  fixity layer, pytest 9 bump.
- **M3** (2026-05-03) — `policy_pages` plugin (12 templates),
  PolicyManager singleton capability role, `/admin/policies`
  admin UI, public render.
- **M1 residual** (2026-05-03) — GDPR posture rework
  (mediated anonymisation flow, art. 15 export, three follow-up
  affordances).
- **PolicyManager UI** (2026-05-03) — Admin Assign / Change /
  Revoke buttons on `/admin/policies`, with a user-picker modal
  wired to the existing `transferPolicyManager` /
  `revokePolicyManager` store actions.
- **Postgres 15 → 17** (2026-05-03) — major upgrade of the
  platform DB and the optional pgvector RAG store. Runbook in
  [`reference/OPERATIONS.md`](reference/OPERATIONS.md#postgres-major-version-upgrade).
- **Earlier** — GitHub integration plugin, plugin hot-reload,
  TEI schema validation, XSLT template management + AI sidebar,
  full-text search, production hardening, security debt
  (`pyasn1`, `pytest 9`).

The CTS-compliance posture is documented separately in
[`reference/CTS_COMPLIANCE.md`](reference/CTS_COMPLIANCE.md).
