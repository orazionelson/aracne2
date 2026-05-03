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
| R1  | Mission/Scope                  | Organizational     | `policy_pages` plugin ships a `mission` template the operator fills in; published at `/policies/mission` with version history | ✅ Strong (form surface) |
| R2  | Licenses                       | Organizational     | License catalogue + per-collection assignment + LOD/OAI-PMH exposure | ✅ Strong |
| R3  | Continuity of access           | Organizational     | Multi-target deposit (Zenodo / IA / Codeberg / GH / GL / Dataverse) + static export + native backup + headless `aracne-cli export --as-of <date>` + **`continuity_plan` policy template (M3)** | ✅ Strong |
| R4  | Confidentiality / Ethics       | Organizational     | GDPR primitives (PII fields, retention, IP hashing) + **`privacy_dpia` policy template (M3)** + **art. 15 self-service export at `GET /users/me/export`** + **mediated anonymisation request flow (`POST /users/me/anonymise-request` → Admin review at `/admin/gdpr/*`)**, posture documented in [`GDPR_POSTURE.md`](reference/GDPR_POSTURE.md) | ✅ Strong (editorial-platform posture) |
| R5  | Organizational infrastructure  | Organizational     | `funding_staffing` policy template (M3) | ✅ Strong (form surface) |
| R6  | Expert guidance                | Organizational     | `expert_directory` policy template (M3) — multi-row table | ✅ Strong (form surface) |
| R7  | Data integrity and authenticity| Digital Object Mgmt| TEI validation + audit log + role gating + signed JWT + **`document_versions` history with SHA-256 fingerprints (Alembic 0072)** + **fixity layer with scheduled re-check + drift report (`fixity_records`, Alembic 0079)** + **Admin audit-log UI (`/admin/audit-log`)** | ✅ Strong |
| R8  | Appraisal                      | Digital Object Mgmt| `appraisal_policy` policy template (M3) | ✅ Strong (form surface) |
| R9  | Documented storage procedures  | Digital Object Mgmt| Storage architecture in OPERATIONS.md + **`storage_policy` policy template (M3)** with platform-resolved engine versions | ✅ Strong |
| R10 | Preservation plan              | Digital Object Mgmt| Format-as-preservation (TEI) + multi-deposit + **`preservation_plan` policy template (M3)** | ✅ Strong |
| R11 | Data quality                   | Digital Object Mgmt| Schema validation + workflow review + entity normalisation + bibliography normaliser | ✅ Strong |
| R12 | Workflows                      | Digital Object Mgmt| Workflow states + audit log + deposit hooks + in-app notifications + **email dispatcher (Postfix-mediated SMTP) for submitted/rejected/published events** | ✅ Strong |
| R13 | Discovery and identification   | Digital Object Mgmt| OAI-PMH + sitemap + JSON-LD + DOI via Zenodo + 12 authority lookups | ✅ Strong |
| R14 | Reuse                          | Digital Object Mgmt| License exposure + raw TEI + JSON-LD + DOI + embed widget + MCP server | ✅ Strong |
| R15 | Technical infrastructure       | Technology         | TEI / REST / OAI-PMH / JSON-LD / Docker; open source; monitoring | ✅ Strong |
| R16 | Security                       | Technology         | 6 security reviews + defusedxml + HSTS/CSP + bcrypt + Fernet + ACL + Dependabot + **bcrypt-hashed Personal Access Tokens for headless clients (revocable, role-scoped)** + **password reset flow with single-use SHA-256-hashed tokens, 24h TTL, all-sessions-revoke on confirm** | ✅ Strong |

**Counts after M3 + GDPR-rework**: 16 ✅ strong, 0 🟡 partial,
0 institutional-only items the platform doesn't help with. ✅ rows
tagged "(form surface)" mean the platform provides a structured
place for the institution to make the declaration; the declaration
text itself is still operator-supplied.

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
- **Headless CLI export** (``aracne-cli export``): an editor armed
  with a Personal Access Token can pull the corpus to disk as a
  ZIP archive (manifest + per-doc files) from any terminal,
  outside the SPA. ``--as-of YYYY-MM-DD`` resolves each document
  to its ``publication``-origin row at or before the date so a
  successor institution can snapshot the corpus exactly as it
  appeared on a specific day, without server-side cooperation.

**Institution must declare**: a **succession plan** identifying:
- which deposit targets are mandatory at publish time;
- which institution(s) would inherit custodianship if the original
  ceases operations;
- the retention horizon for backups and the off-site location;
- the procedure for redirecting public DOIs to the successor's URL.

A template scaffold is planned — see §[Institutional declarations](#institutional-declarations).

---

### R4 — Confidentiality / Ethics ✅ Strong

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
- **Art. 15 self-service export** at `GET /users/me/export` —
  every personal-metadata row across the platform's admin tables
  serialised as JSON. Excludes hashes / digests / document bodies.
- **Art. 17 anonymisation request flow** — user submits via
  `POST /users/me/anonymise-request`; an Admin reviews and
  executes via `/admin/gdpr/anonymise/{id}`. The B2C-style
  hard-delete pattern was deliberately removed in 2026-05-03 once
  the editorial-platform context (third-party-affecting
  contributions) was acknowledged. Anonymisation rewrites
  identifying user fields with `deleted_user_<uuid12>`
  placeholders, rewrites every `audit_log.actor_username`
  referencing the user, revokes sessions / PATs, and stamps the
  user inactive — without deleting the row (so the editorial
  record survives). Legal foundation: GDPR art. 17.3.d
  (scientific-research / public-interest archiving).
- **Posture document** at [`GDPR_POSTURE.md`](reference/GDPR_POSTURE.md)
  describing the legal foundation, the anonymisation flow, and
  the cross-table effects in detail. The `privacy_dpia` policy
  template (M3) is where the operator's specific declaration goes.

**Platform gaps (small, non-blocking)**:
- Email notification to Admins when a new GDPR request lands —
  plumbing is in place via `email_dispatcher`; needs an
  `ON_GDPR_REQUEST_SUBMITTED` hook event wired.
- Frontend "Request anonymisation" button on the Profile view —
  endpoint exists; UI affordance not yet shipped.
- Admin UI page at `/admin/gdpr` mirroring `/admin/audit-log`'s
  shape — until then the JSON endpoints are the canonical surface.
- In-app **takedown request** form for third parties whose name
  appears in published TEI: today this happens via email to the
  admin; a structured form + ticket trail would extend coverage.

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

### R7 — Data integrity and authenticity ✅ Fully

**Platform provides**:
- TEI validation against RNG / DTD / XSD per schema, both live in
  the editor and as collection-wide reports.
- Audit log of every workflow transition and every mutation that
  affects collection state, signed implicitly by the actor's role
  context. **Admin-facing UI** at ``/admin/audit-log`` (M2 §20)
  with structured + free-text filters and CSV export.
- Role gating: only Editor+ can write, only EditorInChief+ can
  publish, only Admin can change platform settings.
- Bcrypt password hashing + JWT signed with HMAC-SHA256 + Fernet
  encryption for sensitive settings.
- defusedxml on every XML parse path (XXE prevention; closed
  CVE-2026-41066 in Security review 2026-04-29).
- **Native version history of TEI** (Alembic 0072 ``document_versions``):
  every workflow event (submission, rejection, publication,
  rollback) and every editor "Save version" action snapshots the
  document body, gzip-compressed, with a SHA-256 fingerprint of the
  uncompressed XML. The history is queryable via REST + a
  per-collection working/published storage split in eXist-db means
  editor edits never leak to the public until a re-publish.
- **Audit-log → version-row back-pointer**: every
  ``document_versions`` row carries the ``audit_log.id`` that
  originated it, so a CTS reviewer can navigate "this row was
  written when EiC X clicked Approve at time T" in O(1).
- **Fixity layer** (M2 CTS R7 deliverable, Alembic 0079
  ``fixity_records``): one row per (collection, filename) records
  the SHA-256 of the latest publication-origin version at deposit
  time; an ``apscheduler`` ``fixity_recheck`` job (configurable
  cadence, default weekly Sun 03:00 UTC) re-hashes every row and
  transitions ``ok → drifted | missing | error`` on mismatch. First
  drift transition stamps ``drifted_at`` and emits an
  ``fixity.drift_detected`` audit_log row. Drift surfaces in
  ``/admin/fixity`` with an Admin "Recheck now" button. Drift is
  record-only; the platform never auto-quarantines a public render
  on a hash mismatch.

**Platform gaps (planned)**:
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
  `ON_COLLECTION_REJECTED`, `ON_DOCUMENT_UPLOADED`, `ON_USER_LOGIN`,
  …) wiring downstream actions like deposit, notification, email
  dispatch, webhook dispatch.
- In-app notification dispatcher for editor / EiC / admin.
- **Email dispatcher** (Postfix-mediated SMTP via local container)
  for the three workflow events that leave the platform: submitted
  → all active EiCs; rejected/revisions-requested → assigned editor;
  published → assigned editor. Templates in ``en`` + ``it``,
  per-user opt-out via ``users.email_notifications_enabled``,
  fire-and-forget so an SMTP failure never blocks the workflow op.

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
- Test suite (~726 backend tests, of which ~25 security-focused, plus
  ~24 tests for the standalone `aracne-cli` package in `cli/`).
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
- **Personal Access Tokens** (Alembic 0075) for headless clients:
  bcrypt-hashed plaintext (``aracne2_pat_`` prefix +
  ``secrets.token_urlsafe(32)``), prefix-detected in
  ``app/middleware/acl.py`` ahead of the JWT decode path,
  inherits the issuer's currently-active role, soft-revoke via
  ``revoked_at``. Self-service issue/revoke from the user's own
  Profile page.
- **Password reset flow** with single-use SHA-256-hashed tokens
  (Alembic 0074), 24h TTL, ``used_at`` enforces single use; the
  confirm endpoint revokes every active session of the user before
  applying the new password (mirrors ``change_password``).
  ``/auth/password/reset/request`` always returns 204 (no
  account enumeration); ``/auth/password/reset/confirm`` collapses
  every failure mode to ``INVALID_RESET_TOKEN``.
- Rate limiting via slowapi (STRICT 10/min on auth + reset
  endpoints, GLOBAL 200/min default, per-route overrides).
- Fernet encryption for sensitive settings (API keys, deposit
  tokens). PATs are bcrypt-hashed (one-way) so even if the DB
  leaks an attacker cannot reconstruct the plaintext.
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
| 2026-05-02 | Milestone 1 — three of five items shipped. Document versioning + email channels + CLI/PAT all landed; GDPR self-service endpoints (the only direct CTS deliverable in M1) still pending. R7 partial bullet "Version history of TEI" closes; R12 reinforced with email; R3 reinforced with `aracne-cli export --as-of`; R16 reinforced with PATs and password-reset flow. Test suite count refreshed (~543 → ~726 backend + ~24 CLI). |
| 2026-05-03 | Milestone 1 — items 4 / 5 of 5 shipped (`public_navigation` capability + `nl_search` plugin). Public layout iterators surface plugin links via three slots (header / home_quick_links / footer). Closes M1. |
| 2026-05-03 | Milestone 2 — all four items shipped. PyJWT migration (drop `python-jose`+`pyasn1`, closes CVE-2026-30922); admin `/admin/audit-log` view with structured + free-text filters and CSV export (FUTURE_IDEAS §20); **fixity layer with `fixity_records` table + `apscheduler` re-check job + `/admin/fixity` view** — closes the heaviest CTS R7 reviewer gap, **R7 transitions 🟡 → ✅ Strong**; pytest 9 triple bump (CVE-2025-71176). |
| 2026-05-03 | Milestone 3 — `policy_pages` plugin shipped. 12 built-in templates as live forms with platform pre-fill, IT/EN locales, append-only versioning, Save / Publish split, browser-print PDF; new `PolicyManager` singleton capability role with the orthogonal `kind`+`singleton` schema on `roles`; new `require_capability` middleware. **Six CTS rows transition 🟡 / "institutional declaration owed" → ✅ Strong (form surface)**: R1 mission, R5 funding/staffing, R6 expert directory, R8 appraisal, R9 storage policy, R10 preservation plan. R3 + R4 reinforced (continuity_plan + privacy_dpia templates). Counts now: **15 ✅ / 1 🟡 (R4 pending GDPR endpoints) / 0 ❌**. |
| 2026-05-03 | **R4 GDPR posture rework ✅ Closed** — the M1 residual deliverable. New `gdpr_requests` table (Alembic 0082); `services/gdpr.py` with rich `export_personal_data` (art. 15) + mediated `submit_anonymise_request` + Admin-side `anonymise_user_metadata` / `reject_anonymise_request`. The B2C-style `DELETE /users/me` hard-delete was *removed* — it's the wrong shape for an editorial scientific platform where contributions to published documents are third-party-affecting. Replacement: user submits a request, Admin reviews under whatever institutional/legal process applies, anonymisation rewrites identifying user fields + `audit_log.actor_username` rows to `deleted_user_<uuid12>` placeholders while preserving the editorial record (legal foundation: art. 17.3.d). Documented in [`GDPR_POSTURE.md`](reference/GDPR_POSTURE.md). **R4 transitions 🟡 Partial → ✅ Strong**. Counts now: **16 ✅ / 0 🟡 / 0 ❌**. |

*Maintained by the platform maintainer; institutional declarations
are out of scope of this file but referenced where they belong.*
