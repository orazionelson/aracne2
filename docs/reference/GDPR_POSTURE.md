# GDPR posture for an editorial scientific platform

## Why this document exists

Aracne2 is a CMS for **published scientific work**: TEI documents
that, once approved by an EditorInChief and exposed at a public
URL, become part of the institution's record-of-work and are
citable, indexable, and frequently embedded in academic CVs,
ANVUR-style assessments, and downstream bibliographies.

This makes the platform's GDPR posture different from a B2C SaaS
in one specific way: **a contributor cannot unilaterally erase
their own contribution after publication**, because the
contribution is third-party-affecting (co-authors, the editor of
record, citing works). Self-service "delete my account → unpublish
all my contributions" — the pattern many social platforms ship —
is the wrong shape for a scientific editor.

This document explains what we ship instead, why it is GDPR-
compliant, and where the user's rights are honoured.

---

## The legal foundation in one paragraph

GDPR art. 17 ("right to erasure") is **not unconditional**. Para
17.3 enumerates exceptions; the two that apply here are:

- **17.3.b** — processing necessary for the *exercise of an
  official authority* or *the performance of a task carried out
  in the public interest*; and
- **17.3.d** — processing necessary "for archiving purposes in the
  public interest, scientific or historical research purposes…".

Edited scientific corpora — what Aracne2 hosts — fall squarely
inside **17.3.d**. A user's contribution to a published TEI
document is part of an archived, citable, peer-reviewed record;
its preservation is the legitimate ground that overrides the
art. 17 default of erasure on request.

This is the same legal foundation every serious scientific
publisher (Elsevier, Wiley, Oxford, Cambridge, the university
presses, the PMC archive, the institutional repositories) uses
to refuse self-service retraction.

---

## What this means in practice

### What the user CAN do at any time, self-service

| Right | How |
|---|---|
| **Art. 15 — access** | `GET /users/me/export` from the Profile view. Returns a JSON dump of every personal-metadata row across the platform: profile, role grants, sessions, audit_log rows where they're actor or target, notifications, PAT metadata, GDPR-request history. |
| **Art. 16 — rectification** | The Profile view's Edit form: bio, ORCID, email, language, avatar. |
| **Art. 18 — restriction** (limited) | The user can request `email_notifications_enabled=false` from Profile to stop receiving workflow emails — a partial restriction of processing. |
| **Art. 20 — portability** | The art. 15 export is in JSON, machine-readable, suitable for portability. |

The export endpoint **excludes** by design: `password_hash`, the
SHA-256-hashed IP address (privacy-cost without investigative
value), the bcrypt digests of any kind, document bodies (those are
editorial content, not personal data).

### What the user CANNOT do self-service, and why

**Hard-delete the account.** The platform does NOT ship a `DELETE
/users/me` self-service endpoint. The pattern was deliberately
removed in 2026-05-03 once it became clear that the editorial
context made it indefensible.

**Why**: deleting a contributor's user row would either:
- silently break the FK to `audit_log` / `document_versions` /
  `policy_page_versions` (auditability lost), or
- leave the editorial record intact while removing the personal
  metadata (which is what we ship — but it's not a *delete*, it's
  an *anonymise*, and it should be reviewed before it happens).

The right shape is the second: **anonymise on request, mediated**.

---

## The anonymisation request flow

```
   user                   platform              admin
   │                          │                    │
   │  POST /users/me/         │                    │
   │   anonymise-request      │                    │
   │  body: {reason?}         │                    │
   │ ─────────────────────────►│                    │
   │                          │  insert            │
   │                          │  gdpr_requests row │
   │                          │  audit:            │
   │                          │  user.anonymise_   │
   │                          │   requested        │
   │  202 Accepted            │                    │
   │ ◄─────────────────────────                    │
   │                          │                    │
   │                          │ ── review queue ──►│
   │                          │                    │  [external process:
   │                          │                    │   court order? clear
   │                          │                    │   institutional sign-off?
   │                          │                    │   …time passes]
   │                          │                    │
   │                          │  POST /admin/gdpr/ │
   │                          │   anonymise/{id}   │
   │                          │ ◄──────────────────│
   │                          │                    │
   │                          │  - replace user    │
   │                          │    fields with     │
   │                          │    placeholder     │
   │                          │  - rewrite         │
   │                          │    audit_log.      │
   │                          │    actor_username  │
   │                          │  - revoke sessions │
   │                          │  - revoke PATs     │
   │                          │  - is_active=false │
   │                          │  - emit            │
   │                          │    user.anonymised │
   │                          │    audit row       │
   │                          │                    │
   │                          │  200 OK            │
   │                          │ ──────────────────►│
   │                          │                    │
   │  next login              │                    │
   │ ─────────────────────────►│  401 (account     │
   │                          │      inactive)     │
   │ ◄─────────────────────────                    │
```

Status returned by the user-facing endpoint is **202 Accepted**,
which says exactly the right thing: *"we have received your
request but processing it is mediated, not immediate"*.

### What "anonymise" means concretely

After an Admin executes the action, the user row is **kept** but
its identifying fields are overwritten:

| Field | Before | After |
|---|---|---|
| `username` | `anna.bianchi` | `deleted_user_<uuid12>` |
| `email` | `anna@uni.example` | `deleted_user_<uuid12>@deleted.invalid` |
| `display_name` | `Anna Bianchi` | `null` |
| `bio` | (free text) | `null` |
| `orcid` | `0000-0001-…` | `null` |
| `avatar_url` | `…` | `null` |
| `is_active` | `true` | `false` |
| `deleted_at` | `null` | `now()` |

Why the row stays: every other table in the platform that FKs to
`users` (`audit_log.actor_id`, `document_versions.created_by_id`,
`policy_page_versions.saved_by_id`, etc.) needs the row to keep
existing so its `ON DELETE SET NULL` doesn't fire and break the
auditability of the editorial record.

Cross-table effects executed in the same transaction:

- `audit_log.actor_username` — for every row whose `actor_id` was
  the user, rewritten to the placeholder. The denormalised
  username column is what an audit-log search can read; rewriting
  it ensures no future `actor_username = 'anna.bianchi'` filter
  surfaces the original name.
- `audit_log.target_label` — every row targeting this user is
  rewritten the same way.
- `sessions` — every active session is revoked with reason
  `gdpr_anonymise`.
- `personal_access_tokens` — every active token revoked.
- `password_reset_tokens` — outstanding tokens deleted (they would
  be unusable anyway since the email has been invalidated).

The legal-trail audit row `user.anonymised` is the **only place**
that preserves the placeholder ↔ original-username mapping. It
sits in `audit_log.payload`:

```jsonc
{
  "request_id": "8c2b…",
  "placeholder": "deleted_user_3a2b1c4d5e6f",
  "original_user_id": "8c2b…",
  "original_username": "anna.bianchi",
  "review_notes": "Verified court order #ABC-2026-001."
}
```

This row is required for a future audit ("show me which past
users were anonymised, in case a court order needs to be unwound")
but lives only in `audit_log` — nowhere else in the platform.
Operators handling a CTS audit can produce it on demand;
operators NOT handling such an audit can leave it dormant.

---

## Editorial content survives the anonymise

These do **not** change when a user is anonymised:

- **Document version rows** authored by the user (`document_versions.created_by_id`) — the FK keeps pointing at the (now-anonymised) user row, so a reader can still see "this version was authored by deleted_user_3a2b1c4d5e6f at time T".
- **Audit-log payload** — JSONB bodies in old rows are not rewritten. If an old row carries a free-text mention of the user's name (rare; we audit metadata, not content), it survives. The platform's audit logger never includes the user's bio / display_name in payloads precisely so this concern is contained.
- **TEI document bodies** — `<respStmt>` / `<persName>` / contributor metadata inside the TEI stays untouched. These are part of the published scientific work; rewriting them would constitute a retraction, which is a separate editorial process the platform doesn't perform automatically.

If an institution receives a court order that *does* require
rewriting TEI bodies (e.g. a privacy-related judgment about a
specific document), that operation is done **at the document
level** through the editor view, by a person with editorial
authority, with the regular workflow audit trail. It is not
automated by GDPR machinery.

---

## What an Admin sees

`GET /api/v1/admin/gdpr/requests` returns the open queue:

```jsonc
{
  "data": [
    {
      "id": "…",
      "user_id": "…",
      "user_username": "anna.bianchi",
      "kind": "anonymise",
      "status": "submitted",
      "reason": "Court order #ABC-2026-001",
      "submitted_at": "2026-09-14T11:02:00Z",
      "reviewed_at": null,
      "review_notes": null
    }
  ]
}
```

The Admin reviews against whatever institutional process applies
(court order on file? GDPR officer sign-off? policy review?), then
either:

- `POST /api/v1/admin/gdpr/anonymise/{id}` — runs the anonymise
  action; payload `{review_notes: "…"}` records the rationale in
  the audit trail.
- `POST /api/v1/admin/gdpr/reject/{id}` — closes the request as
  rejected; payload `{review_notes: "…"}` carries the reason
  ("pending external legal review", "request out of scope", …).

The frontend admin UI for this queue is on the M3-follow-up
backlog — until then, an Admin uses curl or a small CLI snippet
against the JSON endpoints.

---

## What we tell a CTS reviewer

The `privacy_dpia` policy template (M3) carries this posture as a
field — when an Admin fills out the policy, the section "Lawful
basis for processing" should cite art. 17.3.d for editorial
content; the section "Subject rights handling" should describe
the export endpoint, the anonymise request flow, and the typical
review timeline.

A reviewer who reads the populated policy + this reference doc
gets:
- a clear statement that art. 15 (access) + art. 16
  (rectification) are honoured self-service;
- an explanation that art. 17 (erasure) is mediated, not
  self-service, with the legal foundation explicit;
- the implementation evidence: the table layout, the audit row
  contract, the anonymise placeholder shape, the cross-table
  effects.

This is exactly the shape every serious scientific publisher
publishes; Aracne2's posture matches Wiley, Elsevier, OUP, and
the institutional repositories.

---

## Why we did NOT ship a self-service anonymise endpoint

Even *anonymise*, not delete, the self-service form would be
wrong because:

1. **Court-order verification belongs to the institution, not the
   platform.** The Admin acts on legal grounds external to
   Aracne2; encoding that decision into a button the user can
   press would conflate the two. A user can request, an Admin
   acts; the surface keeps the boundary visible.
2. **The decision affects third parties** — co-authors of joint
   contributions, the institution-of-record. A self-service press
   of the button doesn't have a place to capture that the third
   parties were considered.
3. **Reviewability** — the audit row needs the Admin's review
   notes to be defensible. A self-service press has no such
   notes; the trail would be empty.

The cost of mediation is small (an email + a small queue review
in `/admin/gdpr/requests`); the integrity gain is significant.

---

## File map

```
backend/app/
├── alembic/versions/0082_gdpr_requests.py
├── models/gdpr_request.py        # GdprRequest + GdprRequestKind / Status enums
├── services/gdpr.py              # export_personal_data, submit_anonymise_request,
│                                 # anonymise_user_metadata, reject_anonymise_request
├── routers/users.py              # GET /users/me/export, POST /users/me/anonymise-request
└── routers/gdpr_admin.py         # GET /admin/gdpr/requests,
                                  # POST /admin/gdpr/anonymise/{id},
                                  # POST /admin/gdpr/reject/{id}
```

Tests:
[`backend/app/tests/test_gdpr_admin.py`](../../backend/app/tests/test_gdpr_admin.py),
[`backend/app/tests/test_users.py`](../../backend/app/tests/test_users.py).

---

## What is on the backlog (not blocking R4)

The three follow-ups originally listed here all shipped on
2026-05-03 alongside the docs:

- ✅ **Email notification to Admins** — wired through the
  ``ON_GDPR_REQUEST_SUBMITTED`` hook event; the
  ``email_dispatcher`` plugin's ``on_gdpr_request_submitted``
  listener fires a fire-and-forget task per active Admin with the
  ``gdpr_request_submitted`` template (EN/IT subject + html + text
  variants under ``app/email_templates/``).
- ✅ **Admin UI page** at ``/admin/gdpr`` — card-per-request queue
  with a review-notes textarea, Approve+Anonymise and Reject
  buttons. The reject path requires notes (UX guard); the
  approve path warns when notes are empty.
- ✅ **Frontend affordances on the Profile view** — a Privacy card
  with two buttons: **Export my data** (downloads the art. 15
  JSON dump as a file) and **Request anonymisation** (typed-
  confirm modal that explains the mediated flow + records the
  optional reason).

A still-deferred item: a structured **takedown form** for third
parties whose name appears in published TEI bodies. Today this is
handled out-of-band (email to the Admin); a structured form +
ticket trail would extend the GDPR coverage to people who don't
have an Aracne2 account. Tracked but not yet planned into a
milestone.
