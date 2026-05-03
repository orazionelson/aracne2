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

| Tag | Meaning |
|---|---|
| 🔴 High | Clear value, ready for pickup |
| 🟡 Medium | Value confirmed but waiting on a trigger or sequencing |
| 🟢 Low | Niche, ship if specifically requested |
| 🔵 To discuss | Needs a design conversation before scoping |

Long design conversations from the original `FUTURE_IDEAS.md`
and `DEFERRED.md` files are preserved in git history; this file
is the operational backlog, not the design archive.

---

## 🔴 High

### 1. Automated bibliography enrichment via DOI / ISBN lookup

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

### 2. Public reader statistics and analytics

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

## 🟡 Medium

### 3. CI pipeline on GitHub Actions

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

### 4. Async task queue (Celery / ARQ / Dramatiq)

**Motivation.** Long-running operations today either block the
HTTP request or use `asyncio.create_task` (lost on restart).
"Big" publishes (corpus with hundreds of documents), Zenodo
deposits, ZIP exports, embedding rebuilds all suffer. An async
queue unblocks these AND prepares the ground for the PDF
sidecar (§19), HTR pipeline (§13), and batch bibliography
enrichment (§1).

**Scope.**
- Pick **ARQ** (Redis-only, leanest); Redis is the single new
  service.
- Wrap the existing long-running operations as ARQ tasks;
  callers `enqueue` and the SPA polls a job-status endpoint.
- Worker container in `docker-compose.yml` under a `worker`
  profile so deployments without long-running ops don't have
  to start it.

**Trigger.** First publish that times out, **or** any of the
items above (§13, §15, §17, §19) gets pickup.

**Effort.** ~2 days for the substrate + 1 day per migrated
operation.

---

### 5. Server-side PDF renderer — opt-in sidecar service

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

### 6. S3-compatible media backend (read + write, private buckets)

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

### 7. Collection ACL — multi-editor support

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

### 8. Full-collection validation — performance optimisation

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

### 9. TEI `<zone>` — word- / line-level alignment

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

**Effort.** ~3-4 days. Pairs with §13 (HTR pipeline) — most
naturally implemented together.

---

### 10. MCP server — Phase 2 (write tools)

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

**Effort.** ~5-7 days. Best paired with §11 (Phase 3) once
real usage data is available.

---

### 11. MCP server — Phase 3 (identity, members, audit)

**Motivation.** Per-user MCP tokens (instead of corpus-scoped),
`corpus_members` table, dedicated MCP audit-log surface. Earns
its cost only when several editors are actively using MCP.

**Trigger.** Multi-editor MCP usage signal.

**Effort.** ~4 days.

---

### 12. End-to-end AI evaluation harness

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

### 13. End-to-end HTR pipeline — large-corpus image-to-zone import

**Motivation.** A digitised manuscript collection where pages
are images today is a pain to ingest: HTR → zones → TEI is a
multi-step manual process. An end-to-end pipeline would
automate the most repetitive parts.

**Scope.** Adapter for Transkribus (existing API) + zone import
+ TEI scaffolding. Pairs with §9 (fine-grained zones).

**Trigger.** First manuscript-heavy project.

**Effort.** ~5 days.

---

### 14. Non-native plugin: GROBID — PDF → TEI import

**Motivation.** Operators with PDF-heavy bibliographies or
PDF-only critical apparatus can extract structured TEI via
GROBID. Sidecar deployment (compose profile `grobid`),
opt-in.

**Trigger.** First operator with a large PDF backlog.

**Effort.** ~3 days.

---

### 15. Non-native plugin: LEAF Turning Engine — TEI ↔ Markdown, Transkribus → TEI

**Motivation.** Wraps the LEAF-VRE Turning Engine REST microservice
for two adjacent workflows: a Markdown ↔ TEI bridge that lets
non-XML editors author content, and a Transkribus → TEI
converter that complements (and may eventually subsume) §13.

**Trigger.** Same as §13, plus operators with Markdown-only
authoring teams.

**Effort.** ~3 days.

---

### 16. TEI-specialised local model via LoRA fine-tuning

**Motivation.** A small (7B / 13B) open model fine-tuned on a
TEI corpus could match cloud models on TEI-specific tasks at a
fraction of the cost. Local-first, no per-token bill.

**Trigger.** A research group with GPU access willing to share
the trained weights.

**Effort.** ~10 days for the harness; the actual fine-tune is
the operator's compute time.

---

### 17. Gamification / contributor leaderboard

**Motivation.** Editorial teams sometimes ask for "who did
what" leaderboards as motivational tooling. Aggregate of
audit-log + version-row counts per user, displayed as an admin
dashboard.

**Trigger.** Specific editorial team request.

**Effort.** ~1.5 days.

---

## 🟢 Low

### 18. Plugin data table

**Motivation.** Plugins that need to persist their own state
write to `system_settings` (not ideal) or ad-hoc tables. A
generic `plugin_data` table (key/value/blob, scoped per plugin)
is cleaner.

**Trigger.** First plugin that genuinely needs it.

**Effort.** ~1 day.

---

### 19. WebSocket / Server-Sent Events for real-time notifications

**Motivation.** The notification dispatcher polls; a WS / SSE
push would be more responsive. Today's polling cadence is
adequate.

**Trigger.** Specifically asked for, **or** a heavy-traffic
deployment where polling becomes burdensome.

**Effort.** ~2 days.

---

### 20. Mobile companion app

**Motivation.** A read-only mobile reader for editors on the go.
Most institutions don't ask for it.

**Trigger.** Specifically asked for.

**Effort.** ~10+ days.

---

### 21. Collaborative real-time editing

**Motivation.** Google-Docs-style real-time co-edit on a single
TEI document. Conflicts with the workflow model (one Editor at
a time per document); not a natural fit.

**Trigger.** Specifically asked for; would need a substantial
data-model redesign.

**Effort.** ~weeks.

---

### 22. Secret management — beyond plain-text `.env`

**Motivation.** Today `.env` carries plaintext credentials.
Vault / SOPS / secrets-store-csi integrations would harden a
production deployment.

**Trigger.** Operator with security policy requiring it.

**Effort.** ~2 days per backend.

---

### 23. SPARQL endpoint over the published corpus

**Motivation.** The platform already emits RDF/Turtle via
content negotiation; a SPARQL endpoint completes the LOD story.
Apache Jena Fuselli sidecar + ETL pipeline.

**Trigger.** A research group with SPARQL-based discovery
needs.

**Effort.** ~3 days.

---

## 🔵 To discuss

These items need a design conversation before scoping —
priority will be reassessed when the conversation happens.

### 24. Glossary and index generation from named entities

Open question: where does the index live? Standalone HTML
page, document appendix, separate `/glossary` route? Curation
balance vs. autonomy.

### 25. TEI-to-DOCX export

Open question: same shape as §5 (PDF sidecar) — a pandoc
sidecar, or rely on the user's local pandoc?

### 26. Fuzzy string matching via Apache Commons Text in XQuery

Open question: who needs it? Without a concrete editorial
workflow this is over-engineering.

### 27. DataCite DOI minting

Open question: how many deployments have DataCite without
Zenodo? Today Zenodo (already shipped) covers most cases.

### 28. IIIF integration (+ Mirador / OpenSeadragon)

Open question: serve IIIF Image API ourselves or proxy from a
sidecar? Pairs with §9 (fine-grained zones) and §13 (HTR).

### 29. Matomo / Plausible analytics injector

Open question: ship as opt-in sidecar like the deposit plugins,
**or** roll our own inside §2 (public reader statistics)? Two
overlapping ways to get the same answer.

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
