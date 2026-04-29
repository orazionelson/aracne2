# Aracne2 — Roadmap

The current planned sequence of work, organised in **two named
sprints** plus a backlog. Each sprint item points back to the
detailed entry in [`FUTURE_IDEAS.md`](FUTURE_IDEAS.md) or
[`DEFERRED.md`](DEFERRED.md) — this document is the *operational
plan*, not the design specs.

---

## Sprint 1 — Operationalisation

Goal: bring the platform from "demo-ready" to "deployment-ready" by
adding the surfaces that a real editorial team needs from day one
(versioning, email notifications, batch CLI), plus the first
public-facing AI feature (NL search).

| Ref | Item | One-liner |
|---|---|---|
| FUTURE_IDEAS §1 | CLI import/export tool | Standalone command-line tool to ingest / export collections in batch — outside the SPA, scriptable in CI / cron / migration contexts |
| FUTURE_IDEAS §24 | `public_navigation` capability | Auto-cabling primitive: plugins declare a public-page link; admin toggles surface them in header / home / footer (mirrors `inline_authority` / `collection_deposit` / `website_deposit`) |
| FUTURE_IDEAS §25 | Natural-language search plugin | Public-facing chat-style search at `/search-nl`, MCP-tool-grounded, abuse-mitigated (budget cap, auth gate, per-IP limit). **Depends on §24** for the public-pages link toggle |
| DEFERRED §7 | Document versioning | Versioned history of TEI documents — rollback, diff, "this is the version of this date" recoverable in-app |
| DEFERRED §11 | Email / external notification channels | SMTP integration + templates so password resets, publication approvals, and account verification can leave the platform |

### Order of work inside the sprint

1. **DEFERRED §7 (Document versioning)** — touches the core data
   model; landing first lets every later feature assume a versioned
   document store.
2. **DEFERRED §11 (Email channels)** — independent of versioning;
   can land in parallel with the versioning work after the model
   change settles.
3. **FUTURE_IDEAS §1 (CLI tool)** — depends on stable import /
   export surface; benefits from versioning being in place
   (so `aracne export --as-of 2026-03-01` is meaningful).
4. **FUTURE_IDEAS §24 (`public_navigation` primitive)** — small
   footprint (~2.5 days). Lands before §25 because the toggle is a
   §25 prerequisite.
5. **FUTURE_IDEAS §25 (NL search plugin)** — last, because it
   consumes §24 and is the largest item (~5 days).

### Sprint 1 acceptance criteria

- A new admin can deploy Aracne2, generate a CLI export, restore it
  on a fresh instance, and recover the previous content history.
- An editor receives an email when their submitted collection is
  approved for publication.
- A visitor on the public site can ask a question in natural
  language and receive a TEI-grounded answer with citations.
- Every plugin in the platform that wants a public-facing surface
  can land its link via `public_navigation` without editing
  PublicHeader / PublicHomeSection / PublicFooter.

### CTS compliance deliverables — Sprint 1

Sprint 1 also closes the smaller, doc-heavy half of the platform
roadmap in [`CTS_COMPLIANCE_ROADMAP.md`](CTS_COMPLIANCE_ROADMAP.md).
At sprint close, three roadmap items move from "planned" to
"shipped" and three CTS requirements update their status:

| CTS roadmap item | CTS requirement | Status before sprint | Status after sprint |
|---|---|---|---|
| GDPR self-service endpoints (`GET /users/me/export`, `DELETE /users/me`) | R4 — Confidentiality / Ethics | 🟡 partial | ✅ platform side complete; institutional DPIA still owed |
| `docs/templates/STORAGE_POLICY.md` | R9 — Documented storage procedures | 🟡 partial | ✅ template available; operator fills it per deployment |
| `docs/templates/CONTINUITY_PLAN.md` | R3 — Continuity of access | ✅ strong (deposit + static export already shipped) | ✅ reinforced — scaffold for the operator's succession plan |

Indirect contributions (sprint items that *strengthen* a CTS
requirement without being its primary deliverable):

- **Document versioning** (Sprint 1 core) → R7 — Data integrity
  and authenticity. Versioned TEI history is a *form* of integrity
  evidence ("show me the document as of date X"). It does not by
  itself replace fixity (R7 → ✅ requires Sprint 2's fixity
  scheduler) but moves R7 closer.
- **Email / external notifications** → R12 — Workflows. Workflow
  state changes now leave the platform; the audit trail of
  notifications adds a verification surface a CTS reviewer can
  inspect.

**Sprint 1 close → CTS status table**: R3 ✅ reinforced, R4 ✅
platform side, R9 ✅ template available; R7, R10, R16 unchanged.

---

## Sprint 2 — Programmatic surface + security debt

Goal: deepen the MCP integration into a real agentic platform
(write tools, identity, audit), expose the audit trail to admins,
and clean up the two security-debt items deferred since the
2026-04-29 review.

| Ref | Item | One-liner |
|---|---|---|
| FUTURE_IDEAS §20 | Admin view for the global audit log | UI surface for `audit_log` — filter by actor / action / resource, paginated table, export to CSV. Closes one of the most common "who did what" questions an admin gets |
| FUTURE_IDEAS §21 | MCP server — Phase 2 (write tools) | Add `crossref_to_tei`, `crossref_lookup`, `zotero_import_to_collection`, `start_collection_validation` tools with per-corpus consent toggle (`mcp_allow_writes`). Output-only tools land first; DB-mutating ones gate behind explicit consent |
| FUTURE_IDEAS §22 | MCP server — Phase 3 (identity, members, audit) | Personal MCP tokens (per-user, generated from `/profile/mcp-tokens`), `corpus_members` table, `mcp_audit_log` with retention sweeper, per-corpus rate-limit override |
| DEFERRED §15 | `pyasn1` 0.4.x → 0.6.x bump | Migrate JWT layer from `python-jose` to `PyJWT` (which doesn't depend on `pyasn1`); closes CVE-2026-30922 currently risk-accepted |
| DEFERRED §16 | `pytest` 8 → 9 bump | Coordinated triple bump with `pytest-asyncio` and `pytest-cov` once both ship 9-compatible versions; closes CVE-2025-71176 |

### Order of work inside the sprint

1. **DEFERRED §15 (PyJWT migration)** — independent of MCP work,
   closes a security-debt item, and could surface unexpected
   breaking changes early in the sprint when there's time to
   absorb them.
2. **DEFERRED §16 (pytest 9 bump)** — only land when `pytest-asyncio`
   and `pytest-cov` 9-compatible versions are out; if not, defer
   to Sprint 3. Trivial flip when the prerequisites are in place.
3. **FUTURE_IDEAS §22 (MCP Phase 3)** — adds the `corpus_members`
   table that Phase 2's audit attribution wants; lands before §21.
4. **FUTURE_IDEAS §21 (MCP Phase 2 write tools)** — builds on the
   identity model from §22 for proper audit attribution.
5. **FUTURE_IDEAS §20 (Audit log admin view)** — last, so it can
   render the new `mcp_audit_log` table from §22 alongside the
   existing `audit_log`.

### Sprint 2 acceptance criteria

- An editor running Claude Desktop can ask Claude to "import these
  30 DOIs as bibliography for collection X" and the platform
  carries out the operation under per-corpus consent, with the
  result attributed in the audit log to a specific user.
- An admin lands on `/admin/audit` and can answer "who deleted
  collection Y last week" from the UI alone, without `psql`.
- A `pip-audit` run on `requirements.txt` returns zero high or
  medium vulnerabilities.

### CTS compliance deliverables — Sprint 2

Sprint 2 closes the heavier half of the CTS platform roadmap — the
two items that demand real implementation work, not just a
template:

| CTS roadmap item | CTS requirement | Status before sprint | Status after sprint |
|---|---|---|---|
| Fixity layer — SHA-256 at deposit + scheduled re-check + drift report (`fixity_records` table, `apscheduler` job, `/admin/fixity` view) | R7 — Data integrity and authenticity | 🟡 partial | ✅ fully — the most visible CTS-reviewer gap closes |
| `docs/templates/CTS_SELF_ASSESSMENT.md` (cross-cutting scaffold pre-filling the platform's contribution per requirement) | meta — discharges the operator's writing burden | — | ✅ scaffold available |

Indirect contributions:

- **Admin view for the global audit log** (Sprint 2 core, FUTURE_IDEAS §20)
  → R7 + R16. The `audit_log` was always queryable via SQL; making
  it inspectable from the admin UI is the *evidence presentation*
  side of integrity / security that CTS reviewers expect.
- **MCP Phase 3 `mcp_audit_log`** (FUTURE_IDEAS §22) → R7 + R16.
  Per-call audit trail of programmatic access is exactly the
  granularity a careful R7 review wants.
- **PyJWT migration** (DEFERRED §15) → R16. Closes a residual
  risk-accepted security finding.

**Sprint 2 close → CTS status table**: R3 ✅, R4 ✅ platform side,
**R7 ✅ fully**, R9 ✅ template, R16 ✅ reinforced.

After Sprint 2: the platform-side contribution to CTS is
**substantially complete**. R10 (preservation plan) remains 🟡
because its missing piece is purely an institutional declaration
the operator must write — no platform work would close it. The
self-assessment scaffold delivered in this sprint is the right
artefact to drive that institutional writing.

---

## Backlog — to define after Sprint 1 and 2

Everything else currently tracked across the three roadmap
documents, **to be re-prioritised after Sprint 2 closes** based on
real deployment feedback, contributor signals, and updated
priorities. Until then, items here are *not committed* — picking
one up before Sprint 2 ships should be a deliberate exception, not
the default.

Sources to consult when re-prioritising:

- [`FUTURE_IDEAS.md`](FUTURE_IDEAS.md) — every entry not in
  Sprint 1 / Sprint 2 above (≈ 18 items spread across 🔴 / 🟡 /
  🟢 / 🔵 priority).
- [`DEFERRED.md`](DEFERRED.md) — every entry not in Sprint 1 /
  Sprint 2 above (≈ 8 items, including the four ✅ Shipped that
  are kept for historical context).
- [`CTS_COMPLIANCE_ROADMAP.md`](CTS_COMPLIANCE_ROADMAP.md) — the
  five CTS-driven platform items (fixity scheduler, GDPR
  self-service endpoints, two policy templates, self-assessment
  scaffold). These are out-of-band of FUTURE_IDEAS / DEFERRED;
  consider promoting one or more into Sprint 3 if any institution
  asks for CTS evaluation.

---

## Conventions

- **Sprint** here means a coherent batch of work, not a fixed
  calendar window. Sprint 1 / Sprint 2 lengths are open-ended;
  the goal is the acceptance criteria, not a deadline.
- **Re-prioritisation** is a deliberate operation: the backlog
  isn't promoted automatically. Adding a third sprint requires
  this document's update.
- **Dependencies** between items are noted in the order-of-work
  block, not in the table — readers picking up a single item
  should consult the corresponding `FUTURE_IDEAS` / `DEFERRED`
  entry for full context, not this file.

---

## Status tracking

This file is updated when:
- a sprint item is started → status note next to the row
- a sprint item is completed → strikethrough + commit reference
- a sprint closes → the sprint section moves to a "Completed
  sprints" section at the bottom

| Date | Change |
|---|---|
| 2026-04-29 | Initial roadmap — Sprint 1 and Sprint 2 defined; backlog framed as the rest of the corpus of tracked items. |
