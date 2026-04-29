# CoreTrustSeal Compliance Roadmap

This document tracks Aracne2's progress towards full alignment with
the **CoreTrustSeal Requirements 2023–2025** (16 requirements, three
categories). It is **a roadmap in progress**, not a certification
claim. Two parallel work streams feed it:

1. **Platform work** — features Aracne2 must ship so an operating
   institution can demonstrate compliance technically. Tracked in
   the per-requirement gaps below and consolidated in
   §[Platform roadmap](#platform-roadmap).
2. **Institutional work** — declarations the operator must produce
   even when the platform fully supports the requirement. CTS
   certifies the *repository* (the institution that runs the
   software), not the software itself; some requirements can never
   be discharged purely by code. Tracked in
   §[Institutional declarations](#institutional-declarations).

When a deployment of Aracne2 wants to apply for CTS, both streams
must be complete. This document gives the operator a head start by
pre-filling the technical half and templating the institutional
half.

---

## Scoping note

CTS certifies repositories, not software. Aracne2 is a platform; the
institution running it (university, archive, consortium, foundation)
is the entity assessed. Three categories of requirement:

| Category | Where the work lives |
|---|---|
| Purely institutional | Operator's policy / governance documents |
| Mixed | Operator policy + platform primitives |
| Purely technical | Platform implementation |

The roadmap is structured around this split.

---

## Summary table

| # | Requirement | Category | Platform contribution | Status |
|---|---|---|---|---|
| R1  | Mission/Scope                  | Organizational     | None — neutral                                          | Institutional declaration owed |
| R2  | Licenses                       | Organizational     | License catalogue + per-collection assignment + LOD/OAI-PMH exposure | ✅ Strong |
| R3  | Continuity of access           | Organizational     | Multi-target deposit (Zenodo / IA / Codeberg / GH / GL / Dataverse) + static export + native backup | ✅ Strong |
| R4  | Confidentiality / Ethics       | Organizational     | GDPR primitives (PII fields, retention, IP hashing); export/delete endpoints planned | 🟡 Partial — endpoints to ship |
| R5  | Organizational infrastructure  | Organizational     | None — neutral                                          | Institutional declaration owed |
| R6  | Expert guidance                | Organizational     | None — neutral                                          | Institutional declaration owed |
| R7  | Data integrity and authenticity| Digital Object Mgmt| TEI validation + audit log + role gating + signed JWT; **fixity layer missing** | 🟡 Partial — fixity scheduler planned |
| R8  | Appraisal                      | Digital Object Mgmt| None — neutral                                          | Institutional declaration owed |
| R9  | Documented storage procedures  | Digital Object Mgmt| Storage architecture in OPERATIONS.md; per-deployment storage policy template missing | 🟡 Partial — template planned |
| R10 | Preservation plan              | Digital Object Mgmt| Format-as-preservation (TEI) + multi-deposit; migration plan template missing | 🟡 Partial — template planned |
| R11 | Data quality                   | Digital Object Mgmt| Schema validation + workflow review + entity normalisation + bibliography normaliser | ✅ Strong |
| R12 | Workflows                      | Digital Object Mgmt| Workflow states + audit log + deposit hooks + notifications | ✅ Strong |
| R13 | Discovery and identification   | Digital Object Mgmt| OAI-PMH + sitemap + JSON-LD + DOI via Zenodo + 12 authority lookups | ✅ Strong |
| R14 | Reuse                          | Digital Object Mgmt| License exposure + raw TEI + JSON-LD + DOI + embed widget + MCP server | ✅ Strong |
| R15 | Technical infrastructure       | Technology         | TEI / REST / OAI-PMH / JSON-LD / Docker; open source; monitoring | ✅ Strong |
| R16 | Security                       | Technology         | 5 security reviews + defusedxml + HSTS/CSP + bcrypt + Fernet + ACL + Dependabot | ✅ Strong |

**Counts**: 7 ✅ strong, 4 🟡 partial (with planned platform work), 5 ❌ purely
institutional. The 5 institutional-only items are inherent to CTS;
no platform can discharge them.

---

## Per-requirement assessment

### R1 — Mission/Scope ❌ Institutional

CTS expects a clear mission statement (*who we serve, what we
preserve, with what guarantees*).

**Platform**: neutral — Aracne2 doesn't constrain or shape the mission.

**Institution must declare**: a mission statement covering corpus
scope, target user community, durability commitment, and any opt-out
restrictions on what kinds of materials the repository will accept.

---

### R2 — Licenses ✅ Strong

**Platform provides**:
- `licenses` table with seedable catalogue (CC-BY, CC-BY-SA, CC0,
  CC-BY-NC, …) and a per-collection assignment (`license_id` on
  `collections`).
- License automatically exposed in JSON-LD (`schema:license`),
  OAI-PMH (`dc:rights`), the public collection HTML, and the Zenodo
  deposit metadata.
- Admin UI to add custom licenses for institutional or domain-
  specific terms (e.g. GFDL, Europeana Public Domain Mark).

**Institution must declare**: default license policy, exception
process, takedown / revocation procedure for licenses that turn
out to have been mis-assigned.

---

### R3 — Continuity of access ✅ Strong

**Platform provides**:
- **Six independent deposit backends** that mirror published
  collections to external archives:
  - Zenodo (DOI + long-term preservation guarantee from CERN)
  - Internet Archive Wayback (URL-level snapshot)
  - Codeberg / GitHub / GitLab (source-of-truth git repository)
  - Dataverse (any institutional dataverse)
- **Static site export** (HYBRID and STATIC website modes): a
  self-contained HTML+CSS+JS bundle servable from plain nginx,
  independent of the Aracne backend. A successor institution can
  serve the corpus indefinitely from a single static host.
- **Native backup plugin** with retention policies + offline target
  configuration (S3, NFS, rsync).
- **OAI-PMH harvest endpoint**: external aggregators (CLARIN,
  national research-infra harvesters) can re-ingest the corpus.

**Institution must declare**: a **succession plan** identifying:
- which deposit targets are mandatory at publish time;
- which institution(s) would inherit custodianship if the original
  ceases operations;
- the retention horizon for backups and the off-site location;
- the procedure for redirecting public DOIs to the successor's URL.

A template scaffold is planned — see §[Institutional declarations](#institutional-declarations).

---

### R4 — Confidentiality / Ethics 🟡 Partial

**Platform provides**:
- PII fields explicitly tagged in code: `users.email`, `sessions.ip_address`,
  `sessions.user_agent`, `audit_log.ip_address`, `audit_log.user_agent`,
  `audit_log.actor_username`.
- Retention configurable via `system_settings`:
  `audit_log_retention_days` (default 90),
  `expired_sessions_retention_days` (default 30).
- **IP hashing in production**: SHA-256 with salt = `JWT_SECRET`.
  The plaintext IP never reaches structured logs in production.
- **Response minimization**: `password_hash`, `ip_address`,
  `user_agent` never appear in any API response, including admin
  routes.

**Platform gaps (planned)**:
- `GET /users/me/export` (GDPR Art. 20 portability) — endpoint
  designed but not yet shipped.
- `DELETE /users/me` (GDPR Art. 17 erasure) with `audit_log`
  anonymisation — endpoint designed but not yet shipped.
- In-app **takedown request** form for third parties whose name
  appears in published TEI: today this happens via email to the
  admin; a structured form + ticket trail would close the gap.

**Institution must declare**:
- DPIA (Data Protection Impact Assessment) covering the PII fields
  the platform handles plus any project-specific PII inside TEI.
- Privacy notice URL exposed in the public footer.
- Process for handling takedown requests; SLA for response.
- Ethics review board membership and escalation path for sensitive
  content (living-persons mentions, contested historical claims).

---

### R5 — Organizational infrastructure ❌ Institutional

CTS asks about funding, staffing, succession of staff, and
organisational positioning.

**Platform**: neutral.

**Institution must declare**: funding sources and stability
horizon, staff roles (curator / engineer / IT support), succession
arrangements when key staff leave, position within a larger
governance hierarchy (department, university, consortium).

---

### R6 — Expert guidance ❌ Institutional

CTS expects identification of domain expertise — TEI specialists,
historians of the corpus, cataloguers, paleographers as relevant.

**Platform**: neutral.

**Institution must declare**: a list of designated experts (with
roles, contact information, project assignment), advisory board
composition, the procedure for consulting experts on edge cases.

---

### R7 — Data integrity and authenticity 🟡 Partial

**Platform provides**:
- TEI validation against RNG / DTD / XSD per schema, both live in
  the editor and as collection-wide reports.
- Audit log of every workflow transition and every mutation that
  affects collection state, signed implicitly by the actor's role
  context.
- Role gating: only Editor+ can write, only EditorInChief+ can
  publish, only Admin can change platform settings.
- Bcrypt password hashing + JWT signed with HMAC-SHA256 + Fernet
  encryption for sensitive settings.
- defusedxml on every XML parse path (XXE prevention; closed
  CVE-2026-41066 in Security review 2026-04-29).

**Platform gaps (planned)**:
- **Fixity layer**: no SHA-256 / SHA-512 is computed and stored at
  the moment of TEI deposit; no scheduled job re-checks file
  integrity; no drift report. *This is the single most visible gap
  to a CTS reviewer for R7.*
- **Version history of TEI**: today is last-write-wins. Git-based
  deposit (Codeberg / GitHub / GitLab) provides version history
  indirectly; native in-platform versioning is missing.
- **Provenance graph** (PROV-O / PREMIS): the audit log captures
  *who did what when*, but not in a Linked Data Provenance
  serialisation that downstream consumers can ingest.

**Institution must declare**:
- Integrity check frequency and the audit trail format.
- Procedure for handling integrity drift (notification, incident
  log, recovery from backup).

---

### R8 — Appraisal ❌ Institutional

CTS asks for a documented selection policy.

**Platform**: neutral — Aracne2 doesn't constrain what a
collection can contain.

**Institution must declare**: appraisal criteria (what we accept,
what we reject), submission review workflow, deaccessioning
procedure if a collection turns out to fall outside scope.

---

### R9 — Documented storage procedures 🟡 Partial

**Platform provides**:
- Storage architecture documented in [`OPERATIONS.md`](OPERATIONS.md)
  (where Postgres / eXist-db / media / backups live).
- Installation guide [`INSTALL_LINUX_SERVER.md`](INSTALL_LINUX_SERVER.md)
  with explicit Docker volumes and persistence mounts.
- Native backup plugin with retention.

**Platform gaps (planned)**:
- A **deployment-specific storage policy template** that the
  operator fills in: replication factor, RPO, RTO, where copies
  live, who has access, key custodians. Today the operator
  derives this manually from the existing docs.

**Institution must declare**: filled-in storage policy specific
to the institutional infrastructure.

---

### R10 — Preservation plan 🟡 Partial

**Platform provides**:
- TEI XML is itself a preservation-grade format: text-based,
  schema-validated, human-readable, decades-stable.
- Multi-target deposit makes copies independent of the platform.
- TEI ODD is stored and accessible — schema versioning lives with
  the corpus.

**Platform gaps (planned)**:
- No format-migration tooling for TEI P4 → P5 batch conversions
  (rarely needed today; flagged as a future facility).
- No "deprecated element alert" — Aracne does not warn the admin
  when a new TEI Council release deprecates an element heavily
  used in the corpus.

**Institution must declare**:
- Preservation horizon (how many years).
- Format migration plan (when do we revisit P5? what triggers a
  migration to a future P6?).
- Format normalisation policy (do we accept P4 imports?).

---

### R11 — Data quality ✅ Strong

**Platform provides**:
- Schema-aware TEI editor with autocomplete restricted to
  schema-allowed elements / attributes.
- Live validation + collection-wide validation reports.
- Editorial workflow draft → assigned → review → published with
  role gating, providing structural peer review.
- Named entities index with admin normalisation surface.
- Bibliography normaliser (Bibliobuilder) + CrossRef DOI
  resolution + Zotero import.
- AI-assisted markup, validation explanation, bibliography
  cleanup with optional RAG grounding to the TEI P5 Guidelines.

**Institution must declare**: editorial guidelines specific to
the corpus, peer review board (if any), quality metrics tracked
over time.

---

### R12 — Workflows ✅ Strong

**Platform provides**:
- Workflow states explicit in the data model.
- Audit log of all transitions.
- Hook system (`ON_COLLECTION_PUBLISHED`, `ON_COLLECTION_SUBMITTED`,
  `ON_DOCUMENT_UPLOADED`, `ON_USER_LOGIN`, …) wiring downstream
  actions like deposit, notification, webhook dispatch.
- Notification dispatcher for editor / EiC / admin.

**Institution must declare**: the implemented workflow (who can
move a collection from review to published; how long a draft
typically lives; review SLAs).

---

### R13 — Discovery and identification ✅ Strong

**Platform provides**:
- OAI-PMH provider native — six verbs, `oai_dc` metadata, set
  hierarchy, resumption tokens.
- `sitemap.xml` + `robots.txt` for the platform and per-website
  surfaces.
- JSON-LD content negotiation; RDF graph emission via
  `services/lod.py`.
- DOI persistente via Zenodo deposit; the badge surfaces on the
  collection page once the deposit completes.
- Authority URIs on entities — twelve authority lookups
  (Wikidata, ORCID, ROR, VIAF, GeoNames, GND, CERL Thesaurus,
  Peripleo, Getty AAT, OpenAlex, Trismegistos, CrossRef).
- Schema.org markup in the JSON-LD graph.
- MCP server for programmatic discovery via LLM clients.

This is the single strongest area lato CTS — a reviewer hits a
near-checklist of R13 expectations.

---

### R14 — Reuse ✅ Strong

**Platform provides**:
- License visible everywhere: HTML public, OAI-PMH, JSON-LD,
  Zenodo record.
- Raw TEI XML downloadable per document.
- JSON-LD + RDF/Turtle via content negotiation.
- DOI for citation.
- Embed search widget for inclusion in third-party sites with
  origin allowlisting.
- MCP server for programmatic access via LLM assistants
  (educational + research use cases).

**Institution must declare**: citation guidelines, suggested
citation format per collection, attribution expectations.

---

### R15 — Technical infrastructure ✅ Strong

**Platform provides**:
- Standards-aligned: TEI P5, REST + OpenAPI, JSON-LD, OAI-PMH,
  Docker-based deployment, embedded ALTO support designed (FUTURE_IDEAS),
  IIIF integration designed (FUTURE_IDEAS).
- 100% open-source stack: Python 3.12 / FastAPI / PostgreSQL /
  Vue 3 / Tailwind / eXist-db.
- End-to-end installation documentation: laptop
  ([quickstart.md](../quickstart.md)) and Linux server in test/dev
  + production
  ([INSTALL_LINUX_SERVER.md](INSTALL_LINUX_SERVER.md)).
- Test suite (~543 tests, of which 18 security-focused).
- Monitoring: `/api/v1/metrics` Prometheus endpoint + structlog
  JSON logs in production.

**Institution must declare**: uptime SLA, change-management
process, disaster-recovery rehearsal cadence.

---

### R16 — Security ✅ Strong

**Platform provides**:
- **Documented security review trail**: six security reviews
  ([`docs/Security_review_*.md`](.)), each finding tracked with
  the commit SHA that closed it.
- defusedxml on every XML parse path (XXE prevention); the lxml
  6.1.0 bump in `Security_review_2026-04-29` closed CVE-2026-41066.
- HSTS / CSP headers configurable in nginx (production).
- Bcrypt password hashing with configurable rounds.
- JWT with httpOnly + SameSite=Strict refresh cookie; access
  token in Pinia memory only.
- Rate limiting via slowapi (STRICT 10/min on auth, GLOBAL 200/min
  default, per-route overrides).
- Fernet encryption for sensitive settings (API keys, PATs, tokens).
- Role-based ACL explicit on every endpoint via
  `Depends(require_role(...))`.
- HTTPS guidance in [`INSTALL_LINUX_SERVER.md`](INSTALL_LINUX_SERVER.md).
- Dependabot alerts enabled on the public repository.

**Institution must declare**: incident response playbook, security
contact, disclosure policy (also lives in [SECURITY.md](../SECURITY.md)
with platform defaults).

---

## Platform roadmap

Five planned platform improvements that close the technical-side
gaps identified above. Each is a separate work item; once shipped,
the operator's CTS application becomes substantially easier.

These items are now **scheduled across three named milestones** in
[`Aracne_Roadmap.md`](Aracne_Roadmap.md):

- **Milestone 1** delivers item 2 (GDPR self-service endpoints).
- **Milestone 2** delivers item 1 (Fixity layer).
- **Milestone 3** delivers items 3, 4, and 5 — but **as built-in
  templates of the [`policy_pages`](FUTURE_IDEAS.md) plugin**,
  not as standalone Markdown templates. The plugin gives the
  operator a *live form* surface with platform pre-fill,
  versioning, IT/EN locales, public render, and PDF export —
  substantially more than three static Markdown files.

After Milestone 3, the platform-side contribution to CTS is
substantially complete: every requirement either ✅ flips to
"shipped" or has a **live form for the operator to declare
against**. The remaining work is purely institutional declaration
content, which the operator fills via the plugin's UI.

### 1. Fixity layer (R7) — ~1 week

A scheduler that computes and stores SHA-256 of every TEI file +
media at deposit time, periodically re-checks (default monthly),
and emits a drift report visible to admins. Closes the most visible
R7 gap. Reuses the `apscheduler` already in the stack.

Surface: a new `fixity_records` table (`object_id, sha256, computed_at,
last_verified_at, drift_count`); a new admin view `/admin/fixity`
showing the last-N drifts with timestamps.

### 2. GDPR self-service endpoints (R4) — ~3 days

Implement `GET /users/me/export` (Art. 20 portability) and
`DELETE /users/me` (Art. 17 erasure) with `audit_log`
anonymisation. Both are designed; only implementation remains.

Surface: a new admin help section + the two endpoints + frontend
buttons in `/profile`.

### 3, 4, 5 — Folded into the `policy_pages` plugin (Milestone 3)

The three items originally planned as standalone Markdown
templates — Storage Policy (R9), Continuity / Succession Plan
(R3), CTS self-assessment scaffold (cross-cutting) — are now
**built-in templates of the `policy_pages` plugin** delivered in
Milestone 3.

See [`FUTURE_IDEAS.md` §27](FUTURE_IDEAS.md) for the full design.
Headline differences vs. the original Markdown approach:

- **Live forms** the operator fills inside the platform admin,
  not Markdown files copied and edited externally.
- **Platform pre-fill**: Storage Policy auto-populates Postgres /
  eXist-db versions, Docker volumes, deposit-plugin status from
  the running deployment; Continuity Plan auto-populates active
  deposit targets; the published page re-evaluates these at
  render time, so policies stay accurate as the deployment
  evolves.
- **Versioning + audit trail** native — every save creates a
  versioned row, the public page renders the version history
  ("Version 3, published by Maria Bianchi on 2026-Q3, supersedes
  v2 of 2026-Q1") that CTS reviewers expect.
- **Public render** at `/policies/<slug>`, indexed in the sitemap,
  with JSON-LD metadata.
- **Multi-locale**: each operator field has IT and EN values; the
  visitor's `Accept-Language` picks the right render.
- **PDF export** for offline retention via weasyprint.
- **`PolicyManager` capability role** lets Admin delegate policy
  editing to a non-admin user without granting full Admin / EiC
  privileges.

The plugin also ships **9 additional templates** beyond the three
original CTS items (mission, privacy / DPIA, funding / staffing,
expert directory, appraisal policy, preservation plan, incident
response, citation guide, editorial board) — covering R1, R4, R5,
R6, R8, R10, R14, R16. The full institutional-declaration surface
sits in one place.

**Total**: ~14.5 days of focused work in Milestone 3, on top of the
~10 days for items 1+2 in Milestones 1+2. ~5 weeks of total CTS
platform work, with a far stronger operator-facing surface than
the original 5-template plan.

---

## Institutional declarations

For an operator running Aracne2 to apply for CTS, the following
declarations must exist as standalone documents in the
institution's documentation:

| Required declaration | Linked to | Suggested location |
|---|---|---|
| Mission statement                          | R1   | `https://<your-aracne>/about` |
| Privacy notice + DPIA                      | R4   | `https://<your-aracne>/privacy` |
| Funding & staffing statement               | R5   | Annual report / institutional handbook |
| Domain expert directory                    | R6   | Institutional handbook + footer link |
| Appraisal / selection policy               | R8   | Institutional handbook |
| Storage policy (filled template)           | R9   | Institutional internal docs |
| Preservation plan                          | R10  | Institutional internal docs |
| Workflow implementation guide              | R12  | Institutional internal docs |
| Citation & attribution guidelines          | R14  | `https://<your-aracne>/cite` |
| Uptime / change-mgmt / DR policy           | R15  | Institutional IT operations |
| Incident response playbook                 | R16  | Institutional security ops |
| Continuity / succession plan               | R3   | Institutional internal docs |

The five planned platform templates (§[Platform roadmap](#platform-roadmap))
will provide pre-filled scaffolds for the four most-detailed of
these (Storage / Continuity / Preservation / CTS self-assessment).

---

## Status tracking

This document is updated as platform work lands. Each completed
platform improvement (e.g. fixity layer) updates the relevant
requirement status from 🟡 to ✅ and removes the gap from the
roadmap section.

| Date | Change |
|---|---|
| 2026-04-29 | Initial roadmap drafted post-MCP / post-public-flip work. |

*Maintained by the platform maintainer; institutional declarations
are out of scope of this file but referenced where they belong.*
