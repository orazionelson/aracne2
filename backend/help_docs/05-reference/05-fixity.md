# Fixity

Aracne2 keeps a SHA-256 fingerprint of every published document.
On a regular schedule the platform re-hashes those documents and
compares the result against the recorded fingerprint; any
discrepancy ("drift") is surfaced in **Admin → Fixity** so an
Admin can investigate.

This page explains how to read the fixity dashboard, how to
adjust the schedule, and what to do when something drifts.

## Where it lives

In the sidebar under **Amministra**, near **Audit log**. The page
is Admin-gated; Editors and below do not see the link. The
dashboard is the only fixity surface in v1 — there is no
per-collection badge in the editor view.

## The four statuses

| Status | What it means |
|---|---|
| **OK** | The latest re-check matched the recorded SHA-256. The document is intact. |
| **Drifted** | The latest re-check returned a *different* SHA-256. The bytes have changed since the last publish — investigate. |
| **Missing** | The published version row is gone (e.g. the collection was unpublished). Drop the row from the table after the next publish. |
| **Error** | The platform could not read the body — corruption, unreadable gzip, or an environment fault. Often transient; the next re-check usually clears it. |

## Reading the dashboard

Four cards at the top show the current count per status. Click
any card to filter the table to just that status; click again to
clear.

When at least one row is non-OK a red banner reminds you how many
documents need attention.

The table itself is sorted **drift-first** by default (drifted →
missing → error → ok). Each row shows:

- the document filename,
- the **expected** hash (truncated; hover for the full value),
- the **observed** hash on the last re-check (highlighted in red
  on a drifted row),
- the publication version number,
- the time of the last check.

## Recheck now

The **Recheck now** button on the top right runs the full sweep
synchronously. The page refreshes when it returns with the new
counts. Useful as a spot-check after a deployment migration or
after restoring a backup; for routine integrity it is enough to
let the scheduled cadence handle it.

## Configuring the schedule

The cadence is governed by `fixity_recheck_cadence` in
**Admin → Settings**. Two values are supported:

- `weekly` (default) — Sunday 03:00 UTC.
- `daily` — every day at 03:00 UTC.

Change requires a backend restart to take effect — the scheduler
reads the cadence at boot. For most archives the default weekly
cadence is fine; flip to daily only if you want to detect a
tamper within 24 hours.

## When a row drifts

Drift is the platform telling you "the bytes published under
*filename* are no longer the bytes you originally published".
Aracne2 **does not** auto-quarantine the public render on drift —
that decision is yours. Two common scenarios:

### Intentional drift (you re-edited an already-published doc)

If you (or a colleague) re-published the collection after editing
the file, Aracne2 records the new hash on publish and the row
returns to **OK** automatically. If for some reason the row stayed
drifted, click **Recheck now** — that will pick up the new hash.

### Unintentional drift (incident)

If neither you nor any teammate edited the document, the row is
evidence of an incident — direct DB tampering, a backup-restore
gone wrong, or a corrupted blob. Steps:

1. **Look at the audit log**. The first time a row transitions
   into a drift state Aracne2 writes a `fixity.drift_detected`
   audit row; open **Admin → Audit log** and filter on
   `Action = fixity.drift_detected` to see the evidence
   (expected vs. observed hash, version number, timestamp).
2. **Cross-check with deposit backends**. If the collection has
   been deposited on Zenodo / Internet Archive / Codeberg / GH /
   GL / Dataverse, those copies are tamper-resistant — you can
   compare against them.
3. **Re-publish** once you have restored the canonical content;
   the fixity row returns to **OK** on the next re-check.

## What is in scope for the fixity layer

The platform re-hashes the **latest published version** of every
document. A drift in an older version (a manual save from six
months ago) is NOT detected by this layer — it is by design,
because:

- the public never sees an older manual save;
- re-hashing every gzipped blob in `document_versions` on a
  schedule would multiply storage I/O by 10–50× for little extra
  integrity value.

If you need full-history fixity for a CTS audit, ask the
maintainer — it's a separate project on the radar.

## Tips

- A row that flickers between OK and Error on consecutive
  re-checks usually points at a transient eXist-db /
  network-volume issue rather than tampering. Investigate
  storage health first.
- The **Recheck now** button is rate-limited (10/min per Admin)
  — if you click it repeatedly you'll see a 429 error.
- The fixity table only fills up after the first **publish** of
  each document. A fresh deployment shows an empty table until
  someone hits "Publish" the first time.

---

Technical reference: [`docs/reference/FIXITY.md`](../../docs/reference/FIXITY.md).

Related: [Audit log](/help/page?path=05-reference/04-audit-log).
