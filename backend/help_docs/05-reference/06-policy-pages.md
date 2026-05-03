# Policy pages

The **Policy pages** plugin turns institutional declarations
(mission, privacy / DPIA, storage policy, continuity plan,
CTS self-assessment, citation guide, editorial board, etc.) into
**live forms inside Aracne2**. You fill the forms; the platform
renders the public pages at `/policies/<slug>` with the version
metadata in the footer.

The plugin is **off by default**. An Admin must:

1. Activate it from **Admin → Plugins**.
2. Assign a **PolicyManager** (the user with read+write access).
3. (Optional) flip the **Public Pages → Pagine → Plugin links**
   toggle for `policy_pages` to surface a single "Policies" link
   in the public footer.

The page lives at **Admin → Policies**.

---

## Two roles, two surfaces

### PolicyManager (write access)

A **capability role**. Singleton: only one user holds it at any
moment. Granted by an Admin via the card at the top of
**Admin → Policies**: pick a user, click Change, the previous
holder is automatically revoked. The audit log records the
transfer as one event.

Admin always has write access; granting `PolicyManager` to
someone else lets that user edit policies *without* getting any
other admin privilege. Useful when the institutional-relations
team owns the policies but should not be able to manage users,
plugins, or the platform's infrastructure.

### Editor / Designer / EditorInChief (read access)

Anyone at Editor or above sees the form **read-only**, including
drafts. No save / publish buttons, but they can:

- review draft text before it becomes public;
- print a draft for offline review (browser **Print** button);
- read the version history with timestamps and authors.

Per the editorial process: the platform does **not** ship a
review workflow. Drafts are reviewed by humans (in email,
meetings, paper); when consensus is reached, the PolicyManager
edits + publishes.

---

## How the editing flow works

1. **Pick a template** from the left rail. The 12 built-in
   templates are grouped by category (`core`, `cts:R*`).
2. **Fill the operator fields**. Multi-locale fields (mission
   statement, lawful basis, etc.) show side-by-side IT / EN
   tabs — fill both, or just one and leave the other empty if
   your audience is monolingual.
3. **Greyed-out fields** are *platform-resolved*: the platform
   reads them live from the running deployment (PostgreSQL
   version, active deposit plugins, schema catalogue, …) so the
   published policy stays in sync without you copy-pasting. They
   appear as read-only badges in the form.
4. **Save** writes a new version. The form is now a *draft*; the
   public site shows nothing yet.
5. The team reviews the draft through whatever channel the
   institution uses.
6. When approved, the PolicyManager comes back to **Admin →
   Policies**, opens the same template, and clicks **Publish**.
   The platform points the public URL `/policies/<slug>` at the
   chosen version.

Save and Publish are deliberately separate. **Saving never
publishes anything.** Publishing never silently saves changes —
if you have unsaved edits, save them first.

---

## Field types

The form mixes six field shapes:

- **Text / textarea** — single line / paragraph. Localizable
  (IT / EN tabs) where the template marks them so.
- **Integer** — bounded number (e.g. RPO hours, takedown SLA
  days).
- **Drop-down** — pick one from a fixed set (e.g. restore
  rehearsal cadence: monthly / quarterly / annually).
- **Rows table** — repeating sub-form for things like editorial
  board members or named experts. Click "Add row" to append;
  trash icon to remove.
- **Platform-resolved** — read-only, amber-tagged. Reflects the
  current deployment state at every public render.

A field marked with `*` is **required** before the form will save.

---

## Versioning

Every Save creates a new version row. The version number is
monotonic per policy; the history panel at the bottom of the
form shows them with the timestamp and the saver's username.
Optionally fill the **Save message** field to leave a note (like
a commit message) for future-you or for the team reviewer.

You can publish a version that is not the latest one — useful
when you need to roll back. Open the version history, click
**Publish this** next to the version you want public, confirm.

Versions are append-only. The platform does not delete them; CTS
auditors expect the trail to be complete.

---

## Publishing and unpublishing

- **Publish latest** — promote the most-recent saved version.
  Most common path.
- **Publish this** (per-version) — pick a specific version. Use
  for rollbacks.
- **Unpublish** — clear the public pointer. The public URL
  `/policies/<slug>` returns 404; drafts remain saved. Use when
  a policy needs to come down for revision without losing the
  edit history.

A confirmation dialog protects each of these actions.

---

## The 12 built-in templates

| Template | What it asks for |
|---|---|
| **Mission** | Why the corpus exists; durability commitment |
| **Privacy / DPIA** | Data controller, DPO contact, lawful basis, takedown SLA |
| **Storage policy** | RPO/RTO, off-site target, restore rehearsal cadence |
| **Continuity plan** | Successor institution, communication plan, succession horizon |
| **Preservation plan** | Format-migration plan, preservation horizon |
| **Appraisal policy** | Acceptance / rejection / deaccessioning rules |
| **Incident response** | Contacts, escalation ladder, disclosure timeline |
| **Citation guide** | Suggested citation format, attribution expectations |
| **Editorial board** | Members table (name, role, ORCID) |
| **Funding & staffing** | Funding sources, staff roles, succession |
| **Expert directory** | Subject-matter advisors table |
| **CTS self-assessment** | One operator declaration per R1–R16 (the heaviest one — pursue only when applying for CTS) |

Operators that don't pursue CTS use the templates tagged `core`
(mission, privacy_dpia, citation_guide, editorial_board,
funding_staffing, expert_directory) and ignore the `cts:*` ones.

---

## Public visibility

Each policy you publish becomes available at
`/policies/<url-slug>` (e.g. `/policies/mission`,
`/policies/storage-policy`). The visitor sees:

- the policy body, rendered from your filled fields;
- the platform-resolved fields evaluated at the time they hit
  the page (so an upgraded deployment auto-updates without you
  re-publishing);
- a footer like *"Version 3 — published 2026-09-15 by Maria
  Bianchi"* — exactly the audit trail a CTS reviewer expects;
- a **Print** button that uses the browser's native Save-as-PDF.

A single **Policies** link can be added to the public footer via
**Admin → Public Pages → Pagine → Plugin links** — flip the
`policy_pages` toggle on. The `/policies` index page lists every
currently-published policy.

---

## What the platform does NOT do

- **No internal review workflow.** Drafts don't have "submitted /
  needs-review / approved" states. The platform trusts the
  external review process and just transcribes.
- **No automated PDF beyond browser-print** in v1. The Print
  button uses your browser's PDF engine; the printed output
  carries the version footer because it's part of the body.
  Server-rendered byte-deterministic PDFs are tracked as a
  future feature.
- **No per-policy ACL beyond the role split.** Every Editor+
  reads every draft of every policy. If a confidential field
  needs to stay invisible to non-PolicyManagers, don't put it in
  a policy — use Admin Settings instead.

---

Technical reference: [`docs/reference/POLICY_PAGES.md`](../../docs/reference/POLICY_PAGES.md), [`docs/reference/CAPABILITY_ROLES.md`](../../docs/reference/CAPABILITY_ROLES.md).
