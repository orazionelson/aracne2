# Your data and your rights

Aracne2 is a **scientific editorial platform**: the documents you
help publish here become part of an indexed, citable record. That
shapes the way the platform handles your personal data — some
rights are exercised with a single click, some require an Admin
to step in. This page explains what you can do, what you cannot,
and why.

## What you can do at any time

### Download a copy of your data

In **Profile → Privacy → Export my data** (or directly via the
`GET /users/me/export` endpoint), you can download a JSON file
containing every personal-metadata row the platform stores about
you:

- your profile (username, email, bio, ORCID, language, …);
- your active and revoked role grants;
- your sessions, with start / revoke timestamps;
- audit-log rows where you appear as actor or target;
- your notifications;
- your personal access tokens (labels and timestamps — never the
  token plaintexts);
- any GDPR requests you've submitted.

Things that are deliberately **not** in the export:

- your password hash;
- the SHA-256-hashed IP addresses (we hash on write — surfacing
  the hash adds nothing useful and would be a privacy cost
  without an investigative gain);
- bcrypt digests of any kind;
- document bodies — those are editorial content, not personal
  data.

### Edit your profile

Bio, ORCID, email, avatar, preferred language — all editable
from the Profile view. The platform does not gate any of these.

### Stop receiving workflow emails

In **Profile**, untick **Receive workflow email notifications**.
Submission / revisions-requested / publication notifications stop
arriving; you can still receive the password-reset email if you
ask for one.

### Revoke your sessions and tokens

In **Profile → API tokens** you can revoke any token you have
ever issued. Logging out from the navbar revokes the current
session.

## What requires Admin involvement

### Anonymising your account

If you want your **personally-identifying metadata removed** from
the platform — name, email, bio, ORCID, avatar, the actor name on
audit-log rows you authored — that is a separate process, because
it has effects beyond your account:

- Co-authored documents you helped publish stay published. Your
  contribution is part of the scientific record-of-work; it
  cannot be retracted unilaterally.
- Audit-log rows tied to your past actions stay; only the
  *actor name* gets rewritten to a generic placeholder.
- Sessions and API tokens are revoked. After anonymisation you
  can no longer log in with the original credentials.

The flow:

1. From **Profile → Privacy** click **Request anonymisation**
   (or call `POST /users/me/anonymise-request`). You can leave a
   short reason — useful when the request follows a specific
   external event like a court order or an institutional
   decision.
2. The platform creates a request row and notifies the platform's
   Admins. Your account is **not yet changed** — the request is
   in "submitted" state.
3. An Admin reviews the request. The institution's process kicks
   in here: court-order verification, sign-off, policy review,
   whatever applies.
4. If approved, the Admin runs the anonymisation. Your user row
   stays in the database (because other tables reference it for
   the auditability of the editorial record), but the
   identifying fields are replaced with stable placeholders
   (`deleted_user_<id>`).
5. If rejected, the Admin records the reasoning and you keep your
   account as-is.

You can submit one open request at a time; re-submitting while a
previous request is still under review returns a 409 error.

### Why anonymisation is not self-service

Two reasons.

**1. The legal ground is external.** A court order, a GDPR
officer's decision, an institutional sign-off — these are
authority external to the platform. Pressing a button to act on
them confuses the boundary between "I want this" and "this is
authorised". The Admin's review is where the platform records
that the external decision was applied.

**2. Decisions affect third parties.** Co-authors of joint
publications, the editor of record, downstream archives — none of
them are notified by your "Anonymise me" press, and none of them
have a place to push back. The institutional review is where
those concerns can be considered.

The cost is small (the request is queued, not lost); the
integrity gain is significant. Every serious scientific publisher
operates the same way.

## Why content stays after anonymisation

The platform makes a deliberate distinction:

- **Personal metadata** — your name, email, bio, the actor name
  on audit-log rows you authored. Anonymisation rewrites these to
  placeholders.
- **Editorial contribution** — the TEI documents you helped
  produce, your authorship in `<respStmt>`, citing references in
  third-party works. These survive anonymisation.

GDPR art. 17.3.d explicitly preserves processing necessary "for
archiving purposes in the public interest, scientific or
historical research purposes" — and edited scientific corpora
fall squarely inside that exception. A platform that scrubbed the
editorial record would be erasing a historical record other
people legitimately rely on; that is what the law specifically
guards against.

If an institution genuinely needs to retract a document — a
privacy decision about that document specifically, not about your
identity in general — that is an **editorial action**, performed
by the editor-of-record through the regular editorial workflow,
with its own audit trail. It is not what the GDPR anonymisation
machinery does.

## Tips

- The export endpoint is rate-limited; if you call it
  programmatically and get a 429, slow down to one request per
  minute.
- The audit log shows who anonymised whose data and when, with
  the placeholder ↔ original-name mapping in the
  `user.anonymised` row's payload — so a future audit can
  reconstruct the operation. This row exists only for legal-trail
  purposes; an operator NOT handling such an audit can leave it
  dormant.
- Your API tokens, password resets, and notifications appear in
  the export; this is intentional — we believe in showing you
  the complete picture.

---

Technical reference: [`docs/reference/GDPR_POSTURE.md`](../../docs/reference/GDPR_POSTURE.md).

Related: [Audit log](/help/page?path=05-reference/04-audit-log),
[Policy pages](/help/page?path=05-reference/06-policy-pages) (the
`privacy_dpia` template carries the deployment's specific
declaration).
