# CoreTrustSeal compliance — operational reference

This document is the **operational** view of how Aracne2 supports
the **CoreTrustSeal Requirements 2023–2025** (16 requirements,
three categories) for an institution preparing a CTS application.
It is not a roadmap — every platform-side deliverable that the
roadmap once tracked has shipped. It tells the operator, per
requirement: what the platform provides, where to find the
evidence, and what the institution still has to declare on its
own.

CTS certifies the **repository** (the institution running the
software), not the software itself. Aracne2 is the platform that
makes the technical half of the application straightforward and
templates the institutional half through the
[`policy_pages`](POLICY_PAGES.md) plugin.

---

## Summary table

| # | Requirement | Category | What Aracne2 contributes | Status |
|---|---|---|---|---|
| R1  | Mission/Scope                  | Organizational     | `mission` policy template (live form, IT/EN, versioned, public render) | ✅ Strong (form surface) |
| R2  | Licenses                       | Organizational     | License catalogue + per-collection assignment + LOD/OAI-PMH exposure | ✅ Strong |
| R3  | Continuity of access           | Organizational     | Six deposit backends + static export + native backup + `aracne-cli export --as-of` + `continuity_plan` policy template | ✅ Strong |
| R4  | Confidentiality / Ethics       | Organizational     | GDPR primitives + `privacy_dpia` template + art. 15 self-service export + mediated anonymisation flow ([`GDPR_POSTURE.md`](GDPR_POSTURE.md)) | ✅ Strong (editorial-platform posture) |
| R5  | Organizational infrastructure  | Organizational     | `funding_staffing` policy template | ✅ Strong (form surface) |
| R6  | Expert guidance                | Organizational     | `expert_directory` policy template (multi-row table) | ✅ Strong (form surface) |
| R7  | Data integrity and authenticity| Digital Object Mgmt| TEI validation + `document_versions` history with SHA-256 + fixity layer ([`FIXITY.md`](FIXITY.md)) + admin audit-log UI ([`AUDIT_LOG.md`](AUDIT_LOG.md)) | ✅ Strong |
| R8  | Appraisal                      | Digital Object Mgmt| `appraisal_policy` policy template | ✅ Strong (form surface) |
| R9  | Documented storage procedures  | Digital Object Mgmt| Storage architecture in [`OPERATIONS.md`](OPERATIONS.md) + `storage_policy` template with platform-resolved engine versions | ✅ Strong |
| R10 | Preservation plan              | Digital Object Mgmt| TEI as preservation-grade format + multi-deposit + `preservation_plan` template | ✅ Strong |
| R11 | Data quality                   | Digital Object Mgmt| Schema validation + workflow review + entity normalisation + bibliography normaliser | ✅ Strong |
| R12 | Workflows                      | Digital Object Mgmt| Workflow states + audit log + email dispatcher + in-app notifications ([`EMAIL_CHANNELS.md`](EMAIL_CHANNELS.md), [`NOTIFICATIONS.md`](NOTIFICATIONS.md)) | ✅ Strong |
| R13 | Discovery and identification   | Digital Object Mgmt| OAI-PMH + sitemap + JSON-LD + DOI via Zenodo + 12 authority lookups + MCP server | ✅ Strong |
| R14 | Reuse                          | Digital Object Mgmt| License exposure + raw TEI + JSON-LD + DOI + embed widget + MCP server + `citation_guide` template | ✅ Strong |
| R15 | Technical infrastructure       | Technology         | Standards-aligned stack, open source, Docker, monitoring | ✅ Strong |
| R16 | Security                       | Technology         | Seven security reviews + defusedxml + HSTS/CSP + bcrypt + Fernet + ACL + Dependabot + PATs + password-reset flow + `incident_response` template | ✅ Strong |

**Counts**: 16 ✅ Strong / 0 🟡 / 0 ❌. Every requirement either
ships natively or has a *live form* the operator fills in via
[`/admin/policies`](POLICY_PAGES.md). The "(form surface)" marker
means the platform provides a structured place for the
institution to make the declaration; the declaration text itself
is still operator-supplied.

---

## How an operator uses this document

1. **Read the per-requirement assessment below** for the
   requirement you're documenting against.
2. **Follow the linked reference doc** for the technical surface
   the platform provides — every requirement points at one or
   more files under [`reference/`](.) where the implementation,
   data model, and REST endpoints are described.
3. **Open the matching `policy_pages` template** in
   [`/admin/policies`](POLICY_PAGES.md) and fill the operator
   fields. The platform-resolved fields (versions, deposit
   targets, retention defaults, …) are pre-filled; you only
   write the institutional half.
4. **Publish the policy** — the rendered page becomes part of
   your CTS evidence, with version history, IT/EN locales, and a
   stable URL at `/policies/<slug>`.

---

## Per-requirement assessment

### R1 — Mission/Scope ✅ Strong (form surface)

**Platform:** the [`mission`](POLICY_PAGES.md) policy template
captures mission statement, scope, target community, durability
commitment. Multi-locale (IT/EN), versioned, rendered at
`/policies/mission`.

**Institution declares:** the actual mission text — who the
repository serves, what it preserves, with what guarantees.

---

### R2 — Licenses ✅ Strong

**Platform:**
- `licenses` table with seedable catalogue (CC-BY, CC-BY-SA, CC0,
  CC-BY-NC, …); per-collection `license_id` on `collections`.
- License automatically exposed in JSON-LD (`schema:license`),
  OAI-PMH (`dc:rights`), public collection HTML, Zenodo deposit
  metadata.
- Admin UI to add custom licenses for institutional or domain-
  specific terms.

**Institution declares:** default license policy, exception
process, takedown / revocation procedure for licenses that turn
out to have been mis-assigned.

---

### R3 — Continuity of access ✅ Strong

**Platform:**
- **Six independent deposit backends** mirror published
  collections to external archives: Zenodo (DOI from CERN),
  Internet Archive Wayback (URL snapshot), Codeberg / GitHub /
  GitLab (source-of-truth git repository), Dataverse.
- **Static site export** (HYBRID and STATIC website modes): a
  self-contained HTML+CSS+JS bundle servable from plain nginx.
- **Native backup plugin** with retention + offline target (S3,
  NFS, rsync).
- **OAI-PMH provider** for external aggregator harvest.
- **Headless CLI** (`aracne-cli export --as-of YYYY-MM-DD`) — see
  [`CLI.md`](CLI.md).
- **`continuity_plan`** policy template that auto-populates the
  active deposit-target list and the OAI-PMH endpoint from the
  running deployment.

**Institution declares (in the template):** designated successor
institution, DOI redirection procedure, communication plan,
succession horizon.

---

### R4 — Confidentiality / Ethics ✅ Strong (editorial-platform posture)

**Platform:**
- **PII inventory** in code: `users.email`, `sessions.ip_address`,
  `sessions.user_agent`, `audit_log.ip_address`, `audit_log.user_agent`,
  `audit_log.actor_username`.
- **Retention** configurable in `system_settings`:
  `audit_log_retention_days` (default 90),
  `expired_sessions_retention_days` (default 30).
- **IP hashing in production**: SHA-256 with `JWT_SECRET` salt;
  the plaintext IP never reaches the table.
- **Response minimisation**: `password_hash`, `ip_address`, raw
  `user_agent` never appear in any API response.
- **Art. 15 self-service export** at `GET /users/me/export`.
- **Art. 17 mediated anonymisation flow**: user submits via
  `POST /users/me/anonymise-request`; Admin reviews and executes
  via `/admin/gdpr/anonymise/{id}`. Anonymisation rewrites
  identifying user fields with `deleted_user_<uuid12>`
  placeholders, rewrites every `audit_log.actor_username` for
  that user, revokes sessions / PATs, and stamps the user
  inactive — the editorial record (authorship of published
  documents) is preserved. Legal foundation: GDPR art. 17.3.d
  (scientific-research / public-interest archiving). Full posture
  in [`GDPR_POSTURE.md`](GDPR_POSTURE.md).
- **`privacy_dpia`** policy template for the DPIA declaration.

**Institution declares (in the template):** DPIA covering the
PII fields the platform handles plus any project-specific PII
inside TEI; data controller; DPO contact; lawful basis (cite
art. 17.3.d for the editorial corpus + the institution's basis
for user accounts); takedown SLA.

**Open follow-up (not blocking):** structured takedown form for
third parties whose name appears in published TEI bodies (today
out-of-band via email).

---

### R5 — Organizational infrastructure ✅ Strong (form surface)

**Platform:** [`funding_staffing`](POLICY_PAGES.md) policy
template (multi-row staff table + funding sources + succession
arrangements + budget horizon).

**Institution declares (in the template):** funding sources and
stability horizon, staff roles with incumbents, succession
arrangements, position within the institutional hierarchy.

---

### R6 — Expert guidance ✅ Strong (form surface)

**Platform:** [`expert_directory`](POLICY_PAGES.md) policy
template — multi-row table for named experts (name, role,
expertise area, contact, ORCID).

**Institution declares (in the template):** the expert list,
advisory committee, review cadence.

---

### R7 — Data integrity and authenticity ✅ Strong

**Platform:**
- **TEI validation** (RNG / DTD / XSD) — live in editor + collection-
  wide reports. See [`TEI_SCHEMAS.md`](TEI_SCHEMAS.md).
- **Audit log** of every workflow transition + admin UI at
  `/admin/audit-log` with structured + free-text filters and CSV
  export. See [`AUDIT_LOG.md`](AUDIT_LOG.md).
- **Role gating** explicit on every endpoint via `require_role`.
- **Cryptography**: bcrypt password hashing, JWT HMAC-SHA256,
  Fernet for sensitive settings.
- **defusedxml** on every XML parse path (XXE prevention).
- **`document_versions`** native version history with gzip-
  compressed body + SHA-256 fingerprint of uncompressed XML; the
  working/published storage split in eXist-db means editor edits
  never leak to the public until a re-publish. See
  [`DOCUMENT_VERSIONING.md`](DOCUMENT_VERSIONING.md).
- **Audit-log → version-row back-pointer**: every
  `document_versions` row carries the `audit_log.id` that
  originated it.
- **Fixity layer** (`fixity_records` + scheduled re-check + drift
  report at `/admin/fixity`). Cadence configurable (`daily` |
  `weekly`, default Sun 03:00 UTC). First drift transition
  emits `fixity.drift_detected` audit row. Drift is record-only
  by design. See [`FIXITY.md`](FIXITY.md).

**Institution declares:** integrity-check frequency (or accept
the configurable default), procedure for handling drift
(notification, incident log, recovery from backup).

**Open backlog:** Linked-Data provenance graph (PROV-O / PREMIS)
serialisation of the audit trail — tracked in [`TO_DO.md`](../TO_DO.md).

---

### R8 — Appraisal ✅ Strong (form surface)

**Platform:** [`appraisal_policy`](POLICY_PAGES.md) policy
template — acceptance criteria, rejection criteria,
deaccessioning procedure.

**Institution declares (in the template):** what we accept, what
we reject, how we deaccession a previously-published item.

---

### R9 — Documented storage procedures ✅ Strong

**Platform:**
- Storage architecture in [`OPERATIONS.md`](OPERATIONS.md) (where
  Postgres / eXist-db / media / backups live, with explicit
  Docker volumes).
- Installation guide [`INSTALL_LINUX_SERVER.md`](INSTALL_LINUX_SERVER.md).
- Native backup plugin with retention.
- **`storage_policy`** policy template with platform-resolved
  PostgreSQL / eXist-db versions and backup-plugin status.

**Institution declares (in the template):** off-site target,
RPO / RTO, key custodian, restore-rehearsal cadence,
encryption-at-rest details.

---

### R10 — Preservation plan ✅ Strong

**Platform:**
- TEI XML is preservation-grade (text-based, schema-validated).
- Multi-deposit makes copies independent of the platform.
- TEI ODD stored and accessible.
- **`preservation_plan`** policy template with platform-resolved
  TEI format declaration + schema catalogue + deposit-target list.

**Institution declares (in the template):** preservation horizon,
format-migration plan (P5 → future P6), format-normalisation
policy, media-format policy.

---

### R11 — Data quality ✅ Strong

**Platform:**
- Schema-aware TEI editor with autocomplete restricted to
  schema-allowed elements / attributes.
- Live validation + collection-wide validation reports.
- Editorial workflow draft → assigned → review → published with
  role gating (structural peer review).
- Named entities index with admin normalisation surface
  ([`NAMED_ENTITIES.md`](NAMED_ENTITIES.md)).
- Bibliography normaliser + CrossRef DOI resolution + Zotero
  import ([`BIBLIOGRAPHY.md`](BIBLIOGRAPHY.md)).
- AI-assisted markup, validation explanation, bibliography
  cleanup with optional RAG grounding to TEI P5 Guidelines
  ([`AI_INTEGRATION.md`](AI_INTEGRATION.md)).

**Institution declares:** corpus-specific editorial guidelines,
peer review board (if any), quality metrics tracked over time.

---

### R12 — Workflows ✅ Strong

**Platform:**
- Workflow states explicit in the data model.
- Audit log of all transitions.
- Hook system (`ON_COLLECTION_PUBLISHED`, `ON_COLLECTION_SUBMITTED`,
  `ON_COLLECTION_REJECTED`, `ON_DOCUMENT_UPLOADED`,
  `ON_GDPR_REQUEST_SUBMITTED`, …) wiring downstream actions.
- In-app notification dispatcher
  ([`NOTIFICATIONS.md`](NOTIFICATIONS.md)).
- Email dispatcher (Postfix-mediated SMTP via local container)
  for the workflow events that leave the platform — submitted →
  EiC, rejected → editor, published → editor, GDPR-request → all
  Admins. Per-user opt-out via `users.email_notifications_enabled`,
  fire-and-forget so an SMTP failure never blocks the workflow.
  See [`EMAIL_CHANNELS.md`](EMAIL_CHANNELS.md).

**Institution declares:** workflow specifics — who can publish,
typical draft lifetime, review SLAs.

---

### R13 — Discovery and identification ✅ Strong

**Platform:**
- **OAI-PMH provider** native (six verbs, `oai_dc` metadata, set
  hierarchy, resumption tokens). See [`OAI_PMH_PROVIDER.md`](OAI_PMH_PROVIDER.md).
- `sitemap.xml` + `robots.txt` for the platform and per-website
  surfaces. See [`SEO.md`](SEO.md).
- **JSON-LD** content negotiation; RDF graph emission via
  [`LOD_INTEGRATION.md`](LOD_INTEGRATION.md).
- **DOI** via Zenodo deposit; the badge surfaces on the
  collection page once the deposit completes.
- **Authority URIs** on entities — twelve authority lookups
  (Wikidata, ORCID, ROR, VIAF, GeoNames, GND, CERL Thesaurus,
  Peripleo, Getty AAT, OpenAlex, Trismegistos, CrossRef). See
  [`NAMED_ENTITIES.md`](NAMED_ENTITIES.md).
- **Schema.org** markup in the JSON-LD graph.
- **MCP server** for programmatic discovery via LLM clients. See
  [`MCP_SERVER.md`](MCP_SERVER.md).

This is the strongest area to a CTS reviewer — a near-checklist
of R13 expectations.

---

### R14 — Reuse ✅ Strong

**Platform:**
- License visible everywhere (HTML public, OAI-PMH, JSON-LD,
  Zenodo).
- Raw TEI XML downloadable per document.
- JSON-LD + RDF/Turtle via content negotiation.
- DOI for citation.
- Embed search widget for inclusion in third-party sites with
  origin allowlisting ([`EMBED_WIDGET.md`](EMBED_WIDGET.md)).
- MCP server for programmatic access via LLM assistants.
- **`citation_guide`** policy template with platform-detected
  DOI-badge presence and JSON-LD markup status.

**Institution declares (in the template):** suggested citation
format per collection, attribution expectations, citation
examples.

---

### R15 — Technical infrastructure ✅ Strong

**Platform:**
- Standards-aligned: TEI P5, REST + OpenAPI, JSON-LD, OAI-PMH,
  Docker.
- 100% open-source stack: Python 3.12 / FastAPI / PostgreSQL /
  Vue 3 / Tailwind / eXist-db.
- End-to-end installation documentation: laptop / Linux server /
  production ([`INSTALL_LINUX_SERVER.md`](INSTALL_LINUX_SERVER.md)).
- Test suite (~720 backend + ~24 CLI tests).
- Monitoring: `/api/v1/metrics` Prometheus endpoint + structlog
  JSON logs.

**Institution declares:** uptime SLA, change-management process,
disaster-recovery rehearsal cadence.

---

### R16 — Security ✅ Strong

**Platform:**
- **Documented security review trail**: seven reviews
  (`docs/Security_review_*.md`), each finding tracked with the
  commit SHA that closed it.
- defusedxml on every XML parse path; the lxml 6.1.0 bump in
  Security_review_2026-04-29 closed CVE-2026-41066.
- HSTS / CSP headers configurable in nginx.
- Bcrypt password hashing with configurable rounds.
- JWT with httpOnly + SameSite=Strict refresh cookie; access
  token in Pinia memory only.
- **Personal Access Tokens** (bcrypt-hashed `aracne2_pat_…`
  bearers) for headless clients ([`CLI.md`](CLI.md)).
- **Password reset flow** with single-use SHA-256-hashed tokens,
  24h TTL, all-sessions-revoke on confirm
  ([`EMAIL_CHANNELS.md`](EMAIL_CHANNELS.md)).
- **Capability roles** orthogonal to the hierarchy
  ([`CAPABILITY_ROLES.md`](CAPABILITY_ROLES.md)) — first concrete
  capability is the singleton `PolicyManager`.
- Rate limiting via slowapi.
- Fernet encryption for sensitive settings.
- Role-based ACL explicit on every endpoint via
  `Depends(require_role(...))` / `Depends(require_capability(...))`.
- HTTPS guidance in [`INSTALL_LINUX_SERVER.md`](INSTALL_LINUX_SERVER.md).
- Dependabot alerts on the public repository.
- **`incident_response`** policy template with platform-resolved
  list of security-review files + Dependabot status.

**Institution declares (in the template):** incident contacts,
escalation ladder, disclosure timeline, post-mortem policy.

---

## Institutional declarations — where each one lives

For an operator running Aracne2 to apply for CTS, the following
declarations must exist as published, versioned policy pages.
Every one of them ships as a [`policy_pages`](POLICY_PAGES.md)
template the operator fills in via `/admin/policies`:

| Declaration | Linked CTS req | Template slug | Public URL once published |
|---|---|---|---|
| Mission statement                        | R1   | `mission` | `/policies/mission` |
| Privacy notice + DPIA                    | R4   | `privacy_dpia` | `/policies/privacy-dpia` |
| Funding & staffing statement             | R5   | `funding_staffing` | `/policies/funding-staffing` |
| Domain expert directory                  | R6   | `expert_directory` | `/policies/expert-directory` |
| Appraisal / selection policy             | R8   | `appraisal_policy` | `/policies/appraisal-policy` |
| Storage policy                           | R9   | `storage_policy` | `/policies/storage-policy` |
| Preservation plan                        | R10  | `preservation_plan` | `/policies/preservation-plan` |
| Citation & attribution guidelines        | R14  | `citation_guide` | `/policies/citation-guide` |
| Incident response playbook               | R16  | `incident_response` | `/policies/incident-response` |
| Continuity / succession plan             | R3   | `continuity_plan` | `/policies/continuity-plan` |
| Editorial board                          | governance | `editorial_board` | `/policies/editorial-board` |
| CTS self-assessment scaffold             | meta | `cts_self_assessment` | `/policies/cts-self-assessment` |

The `cts_self_assessment` template pre-fills the platform's
contribution per R-requirement (the same data this document
carries) so the operator only writes the institutional half. It
is the document the operator submits to a CTS reviewer.

---

## Status tracking

This document was previously a *roadmap* (`CTS_COMPLIANCE_ROADMAP.md`).
It became operational reference on 2026-05-03 once every
platform-side deliverable shipped:

| Date | Change |
|---|---|
| 2026-05-02 | Milestone 1 — versioning, email, CLI/PAT shipped (3 / 5). |
| 2026-05-03 | Milestone 1 closes (`public_navigation` + `nl_search` ship). |
| 2026-05-03 | Milestone 2 closes — PyJWT migration, audit-log admin UI, **fixity layer** (R7 → ✅ Strong), pytest 9 bump. |
| 2026-05-03 | Milestone 3 closes — `policy_pages` plugin with 12 templates (R1, R3, R4, R5, R6, R8, R9, R10, R14, R16 reinforced). |
| 2026-05-03 | R4 GDPR posture rework closes the M1 residual deliverable — **R4 → ✅ Strong**. Final counts: **16 ✅ / 0 🟡 / 0 ❌**. |
| 2026-05-03 | Document repurposed: `CTS_COMPLIANCE_ROADMAP.md` → [`reference/CTS_COMPLIANCE.md`](.). The original roadmap moved to `docs/archived/`. |

Future entries belong in the matching policy templates (every
substantive change to the institution's CTS posture happens
through a `policy_pages` save → publish cycle), not here.

*Maintained by the platform maintainer; institutional
declarations live in [`/admin/policies`](POLICY_PAGES.md), not
here.*
