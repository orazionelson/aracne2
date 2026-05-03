# Versioning

Every document carries a **version history**: a timeline of
snapshots that shows who changed it, when, and why. You can
review past states, compare two of them side by side, and roll
back to any of them in a single click.

## When a version is recorded

Aracne2 captures a snapshot at every editorially meaningful
moment, plus whenever you ask for one explicitly:

| Origin | Triggered by | Captured automatically? |
|---|---|---|
| Creation | The first time a document is uploaded | yes |
| Submission | You click **Submit for review** on the collection | yes, one per document |
| Revisions requested | EditorInChief sends the collection back | yes, one per document |
| Publication | EditorInChief publishes the collection | yes, one per document |
| Manual save | You click **Save version** in the editor | no — only when you press the button |
| Rollback | You restore a prior version | yes, one row recording the rollback |

Workflow snapshots are skipped when the content has not changed
since the last version (Aracne2 compares the SHA-256 fingerprint).
That way re-publishing an unchanged document does not bloat the
history.

## Opening the history panel

In the TEI editor, click the **History** button (clock icon) in
the toolbar. The drawer that opens lists every version of the
current document, newest first. Each row shows:

- the version number (`v3`, `v17`, …)
- the **origin** badge (creation, manual, submission, rejection,
  publication, rollback)
- the author and the timestamp
- the manual-save message if the row was a manual save

Toggle **Publication only** to filter to the snapshots the public
has seen — useful when you need to recall the state at a past
publication.

## Saving a version manually

Click **Save version** in the History drawer. A dialog asks for a
short message (mandatory) — think of it as a commit message:
*"sealed the apparatus of letter 12"*, *"merged Anna's
corrections"*. The current working tree is captured immediately
with that message attached.

Manual versions are the only ones you can later **delete** — auto
rows are append-only because they belong to the editorial integrity
record. The deployment caps the number of manual versions per
document (default 50); when you hit the limit you have to delete
an old manual save to make room.

## Comparing two versions

Click **Compare** on any row. The viewer shows a unified diff
between that version and the current document — additions in
green, removals in red. Selecting a different row at the top
switches the comparison without leaving the panel.

## Rolling back

Click **Roll back to this version** on any row. The working tree
is rewritten with that version's body and a new `rollback` row
captures the new state. Rollback is **constructive** — every
prior version stays in the history; nothing is deleted. The
collection's workflow state is unchanged: if it was published,
the public continues to see the last published snapshot until
EditorInChief explicitly re-publishes.

## What the public sees while you edit

Publishing a collection takes a snapshot of every document at
that moment. The public site keeps serving that snapshot — even
if you continue editing afterwards. Editing a published
collection is therefore **always safe**: nothing reaches the
public until EditorInChief re-publishes.

### Stable URLs to past versions

Every public document URL accepts a `?version=N` parameter that
serves the body of that exact publication. Only versions of
origin **publication** are reachable this way — manual saves and
rollbacks never leak to the public.

## Tips

- Use **Save version** as a "before I try something risky"
  checkpoint. The diff and rollback workflow makes recovery a
  one-click operation.
- The manual-save message is searchable in the audit log, so
  use clear wording: future-you (or your colleagues) will thank
  you.
- The **Publication only** filter is the fastest way to answer
  "what did the public see at the time?".
- If the **Save version** button is greyed out, you have hit the
  per-document soft cap — delete an obsolete manual row to make
  room.

---

Technical reference: [`docs/reference/DOCUMENT_VERSIONING.md`](../../docs/reference/DOCUMENT_VERSIONING.md).
