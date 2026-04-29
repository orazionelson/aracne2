# Aracne2 — Roadmap

The current planned sequence of work, organised in **three named
milestones** plus a backlog. Each milestone item points back to
the detailed entry in [`FUTURE_IDEAS.md`](FUTURE_IDEAS.md) or
[`DEFERRED.md`](DEFERRED.md) — this document is the *operational
plan*, not the design specs.

> "Milestone" instead of "sprint" because the latter implies a
> fixed timebox (Scrum-style), which Aracne2 doesn't run. A
> milestone is closed when its acceptance criteria are met,
> whatever the calendar says.

---

## Milestone 1 — Operationalisation

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

### Order of work inside the milestone

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

### Milestone 1 acceptance criteria

- A new admin can deploy Aracne2, generate a CLI export, restore it
  on a fresh instance, and recover the previous content history.
- An editor receives an email when their submitted collection is
  approved for publication.
- A visitor on the public site can ask a question in natural
  language and receive a TEI-grounded answer with citations.
- Every plugin in the platform that wants a public-facing surface
  can land its link via `public_navigation` without editing
  PublicHeader / PublicHomeSection / PublicFooter.

### CTS compliance deliverables — Milestone 1

Milestone 1 closes one CTS roadmap item directly and contributes
indirectly to others. The two template-style items originally
planned here (Storage Policy + Continuity Plan templates) are
**folded into the `policy_pages` plugin in Milestone 3** — see
[FUTURE_IDEAS §27](FUTURE_IDEAS.md). They are no longer Milestone 1
deliverables.

| CTS roadmap item | CTS requirement | Status before milestone | Status after milestone |
|---|---|---|---|
| GDPR self-service endpoints (`GET /users/me/export`, `DELETE /users/me`) | R4 — Confidentiality / Ethics | 🟡 partial | ✅ platform side complete; institutional DPIA still owed |

Indirect contributions:

- **Document versioning** (Milestone 1 core) → R7 — Data integrity
  and authenticity. Versioned TEI history is *evidence* of
  integrity ("show me the document as of date X"); it does not
  replace fixity (R7 → ✅ requires Milestone 2's fixity scheduler)
  but moves R7 closer.
- **Email / external notifications** → R12 — Workflows. Workflow
  state changes now leave the platform; the audit trail of
  notifications adds a verification surface a CTS reviewer can
  inspect.

**Milestone 1 close → CTS status table**: R4 ✅ platform side
complete; R3, R7, R9, R10, R16 unchanged (R3 / R9 / R10
declarations are deferred to Milestone 3 via `policy_pages`).

---

## Milestone 2 — Audit visibility + security debt

Goal: expose the audit trail to admins via a UI surface, ship the
fixity layer that closes the most visible CTS-reviewer gap, and
clean up the two security-debt items deferred since the
2026-04-29 review.

| Ref | Item | One-liner |
|---|---|---|
| FUTURE_IDEAS §20 | Admin view for the global audit log | UI surface for `audit_log` — filter by actor / action / resource, paginated table, export to CSV. Closes one of the most common "who did what" questions an admin gets |
| DEFERRED §15 | `pyasn1` 0.4.x → 0.6.x bump | Migrate JWT layer from `python-jose` to `PyJWT` (which doesn't depend on `pyasn1`); closes CVE-2026-30922 currently risk-accepted |
| DEFERRED §16 | `pytest` 8 → 9 bump | Coordinated triple bump with `pytest-asyncio` and `pytest-cov` once both ship 9-compatible versions; closes CVE-2025-71176 |

> **Note**: MCP Phase 2 (FUTURE_IDEAS §21) and MCP Phase 3
> (FUTURE_IDEAS §22) were originally planned here but moved to
> the [backlog](#backlog--to-define-after-milestone-1-2-and-3).
> Their value depends on real MCP usage signals from the editorial
> teams that will land between Milestones 1 and 3 — promoting them
> early, before that signal exists, risks designing the wrong
> consent UX (Phase 2) and the wrong identity model (Phase 3).

### Order of work inside the milestone

1. **DEFERRED §15 (PyJWT migration)** — closes a security-debt
   item; surfacing breaking changes early gives time to absorb
   them.
2. **DEFERRED §16 (pytest 9 bump)** — only land when
   `pytest-asyncio` and `pytest-cov` 9-compatible versions are
   out; if not, defer to Milestone 3. Trivial flip when the
   prerequisites are in place.
3. **FUTURE_IDEAS §20 (Audit log admin view)** — independent of
   the security-debt items; can land in parallel.

### Milestone 2 acceptance criteria

- An admin lands on `/admin/audit` and can answer "who deleted
  collection Y last week" from the UI alone, without `psql`.
- A `pip-audit` run on `requirements.txt` returns zero high or
  medium vulnerabilities, and the JWT layer no longer depends on
  the pinned-old-version `pyasn1`.

### CTS compliance deliverables — Milestone 2

Milestone 2 ships the single heaviest CTS platform item (fixity); the
self-assessment scaffold originally planned here is **folded into
the `policy_pages` plugin in Milestone 3** as one of its built-in
templates (`cts_self_assessment`). See
[FUTURE_IDEAS §27](FUTURE_IDEAS.md).

| CTS roadmap item | CTS requirement | Status before milestone | Status after milestone |
|---|---|---|---|
| Fixity layer — SHA-256 at deposit + scheduled re-check + drift report (`fixity_records` table, `apscheduler` job, `/admin/fixity` view) | R7 — Data integrity and authenticity | 🟡 partial | ✅ fully — the most visible CTS-reviewer gap closes |

Indirect contributions:

- **Admin view for the global audit log** (Milestone 2 core, FUTURE_IDEAS §20)
  → R7 + R16. The `audit_log` was always queryable via SQL; making
  it inspectable from the admin UI is the *evidence presentation*
  side of integrity / security that CTS reviewers expect.
- **PyJWT migration** (DEFERRED §15) → R16. Closes a residual
  risk-accepted security finding.

**Milestone 2 close → CTS status table**: R4 ✅ platform side,
**R7 ✅ fully**, R16 ✅ reinforced. R3, R9, R10 still pending the
institutional-declaration surface — delivered by Milestone 3 below.

---

## Milestone 3 — Institutional surface (`policy_pages` plugin)

Goal: deliver a single non-native plugin that turns every
institutional declaration the operator must produce — mission,
privacy / DPIA, storage policy, continuity plan, CTS
self-assessment, citation guide, editorial board, etc. — into
**live forms inside Aracne** with public rendering, versioning,
multi-locale support, PDF export, and a new capability role
(`PolicyManager`) for delegation.

Subsumes the four template-style deliverables originally planned
inside Milestones 1 / 2 + the cross-cutting CTS self-assessment
scaffold. See [FUTURE_IDEAS §27](FUTURE_IDEAS.md) for the full
design.

| Ref | Item | One-liner |
|---|---|---|
| FUTURE_IDEAS §27 | `policy_pages` plugin | Built-in 12-template engine with platform pre-fill + versioning + IT/EN locales + PDF export + `/policies/<slug>` public render |
| (within §27) | `PolicyManager` capability role | New orthogonal role admin can grant to any User-or-above to delegate policy editing without granting full Admin / EiC privileges |

### Order of work inside the milestone

1. **Plugin scaffold** + Alembic + base model + versioning ←
   foundation; everything else builds on it.
2. **`PolicyTemplate` / `Field` declarative engine** + 12
   built-in templates (mission, privacy_dpia, storage_policy,
   continuity_plan, cts_self_assessment, funding_staffing,
   expert_directory, appraisal_policy, preservation_plan,
   incident_response, citation_guide, editorial_board).
3. **Platform pre-fill mechanism** — lazy re-evaluation at render
   time so the published policy auto-refreshes when the deployment
   state changes (e.g. operator upgrades eXist-db).
4. **Admin form-editor UI** with multi-locale tabs (IT/EN side by
   side) and per-Field-type renderer.
5. **`PolicyManager` capability role** + admin role-management UI
   update.
6. **Public render** at `/policies/<slug>` + sitemap inclusion +
   JSON-LD; integrates with `public_navigation` (§24) for the
   footer "Policies" link.
7. **PDF export** via weasyprint.
8. **Tests + help doc**.

### Milestone 3 acceptance criteria

- An admin activates the `policy_pages` plugin, opens the Storage
  Policy template, sees the platform-filled fields populated with
  the deployment's current state, fills the operator-side
  declarations, and publishes — `/policies/storage-policy` is
  immediately reachable.
- The published Storage Policy page footer shows the version
  history (e.g. *"Version 2, published by Maria Bianchi on
  2026-09-15, supersedes v1 of 2026-Q1"*).
- The admin grants `PolicyManager` to user `alice@uni.example`;
  Alice (a regular User) can now log into the admin and edit
  policies without seeing any other admin surface.
- The published Mission page is available in IT and EN; switching
  language re-renders cleanly.
- Each policy can be exported as PDF with version metadata in the
  footer.

### CTS compliance deliverables — Milestone 3

Milestone 3 closes the institutional-declaration surface that
Milestones 1 / 2 deliberately deferred:

| Built-in template | CTS requirement | Status before milestone | Status after milestone |
|---|---|---|---|
| `storage_policy` | R9 — Documented storage procedures | 🟡 partial (architecture in OPERATIONS.md) | ✅ live form, public rendered, auto-refreshing platform fields |
| `continuity_plan` | R3 — Continuity of access | ✅ strong (deposit + static export shipped) | ✅ reinforced — operator's succession plan is now public, versioned, and signed by name |
| `preservation_plan` | R10 — Preservation plan | 🟡 partial | ✅ live form ready for the operator's declaration |
| `cts_self_assessment` | meta — operator's CTS application | — | ✅ scaffold pre-filled with the platform's per-requirement contribution; operator fills institutional half |
| `mission`, `privacy_dpia`, `funding_staffing`, `expert_directory`, `appraisal_policy`, `incident_response`, `citation_guide`, `editorial_board` | R1, R4, R5, R6, R8, R16, R14 + governance | varied | all gain a structured surface for the operator |

**Milestone 3 close → CTS status table**: every CTS requirement
either ✅ or has a **live form for the operator to declare against**.
The platform side is complete; the operator's job becomes
"fill the forms" instead of "write twelve documents from scratch
and host them somewhere".

---

## Backlog — to define after Milestone 1, 2, and 3

Everything else currently tracked across the three roadmap
documents, **to be re-prioritised after Milestone 3 closes** based on
real deployment feedback, contributor signals, and updated
priorities. Until then, items here are *not committed* — picking
one up before Milestone 3 ships should be a deliberate exception, not
the default.

### Notable items explicitly held in the backlog

- **FUTURE_IDEAS §21 — MCP Phase 2 (write tools)**. Was once
  planned for Milestone 2; deferred because the consent UX
  (per-call vs blanket per-corpus) needs real MCP usage data
  from Milestones 1 and 3 before it can be designed without
  guesswork. Likely candidate for Milestone 4.
- **FUTURE_IDEAS §22 — MCP Phase 3 (identity, members, audit)**.
  Was once planned for Milestone 2; deferred because personal
  tokens, `corpus_members`, and the audit-log surface only earn
  their cost when several editors are actually using MCP — which
  won't be observable until Milestone 1's NL search ships and
  external clients (Claude Desktop) are in active use. Likely
  candidate for Milestone 4 alongside §21.

### Sources to consult when re-prioritising

- [`FUTURE_IDEAS.md`](FUTURE_IDEAS.md) — every entry not in
  Milestone 1 / 2 / 3 above (≈ 19 items, including §21 and §22
  noted above, spread across 🔴 / 🟡 / 🟢 / 🔵 priority).
- [`DEFERRED.md`](DEFERRED.md) — every entry not in Milestone 1 / 2
  above (≈ 8 items, including the four ✅ Shipped that are kept
  for historical context).
- [`CTS_COMPLIANCE_ROADMAP.md`](CTS_COMPLIANCE_ROADMAP.md) — the
  five CTS-driven platform items, now scheduled across the three
  milestones above. Item 1 (fixity) lands in Milestone 2, item 2
  (GDPR endpoints) in Milestone 1, items 3 / 4 / 5 fold into the
  `policy_pages` plugin in Milestone 3.

---

## Conventions

- **Milestone** here means a coherent batch of work, not a fixed
  calendar window. Milestone lengths are open-ended; the goal is
  the acceptance criteria, not a deadline.
- **Re-prioritisation** is a deliberate operation: the backlog
  isn't promoted automatically. Adding a fourth milestone requires
  this document's update.
- **Dependencies** between items are noted in the order-of-work
  block, not in the table — readers picking up a single item
  should consult the corresponding `FUTURE_IDEAS` / `DEFERRED`
  entry for full context, not this file.

---

## Status tracking

This file is updated when:
- a milestone item is started → status note next to the row
- a milestone item is completed → strikethrough + commit reference
- a milestone closes → the milestone section moves to a "Completed
  milestones" section at the bottom

| Date | Change |
|---|---|
| 2026-04-29 | Initial roadmap — two named sprints + backlog. |
| 2026-04-29 | Added Sprint 3 (`policy_pages` plugin, FUTURE_IDEAS §27). Sprints 1 / 2 lose their template-style CTS deliverables — folded into the plugin's built-in templates. |
| 2026-04-29 | Renamed "sprint" → "milestone" (the latter doesn't carry the Scrum-fixed-timebox connotation, fitting Aracne's open-ended cadence). Moved FUTURE_IDEAS §21 (MCP Phase 2 write tools) and §22 (MCP Phase 3 identity) from Milestone 2 to the backlog — both depend on real MCP usage signals from Milestone 1's NL search before they can be designed without guesswork. |
