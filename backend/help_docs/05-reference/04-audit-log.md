# Audit log

Aracne2 records every intentional, user-attributable action it
performs — logins, password changes, document edits, workflow
transitions, plugin activations, settings changes, and so on. The
table is populated by the platform automatically; an Admin can
inspect it at any time from **Admin → Audit log**.

The view answers questions like *"who deleted X last week?"*,
*"when was this document last modified?"*, *"did anyone change
this setting in the last 24 hours?"* — without ever opening a
database shell.

## Where it lives

In the sidebar under **Amministra**, between **Backup** and
**Plugin links**. The page is Admin-gated; Editors and below do
not see the link.

## What you'll see

A filter bar at the top, a paginated table in the middle, and an
**Export CSV** button on the top right.

The table columns:

| Column | What it shows |
|---|---|
| **Time** | When the action happened (your browser's local time) |
| **Action** | A short dotted label, e.g. `collection.published` |
| **Actor** | The username of who did it |
| **Target** | A `type/label` pair pointing at what was acted on |

Click any row to open a side panel with the full payload — a
free-form JSON object the platform attaches to most actions
(e.g. `{"role": "Editor"}` on a login; `{"note": "release 1.2"}`
on a publish).

## Filtering

The view ships with two complementary filter shapes — use either,
or both at the same time:

### Free-text search

The wide **Search** box at the top matches your text against
**actor username**, **action**, and **target label** at the same
time (an OR across the three columns). Useful when you don't
quite remember which field carries the value you remember:

> Search: `manzoni` → matches `target_label="Manzoni"` (a
> collection title) and any action whose own name contains
> "manzoni".

### Structured filters

Below the free-text box, five drop-downs / inputs let you narrow
the query by exact field:

- **Action** — pick one from the curated drop-down list. The list
  is hand-maintained, so you'll never see a typo of an existing
  action; if a value you expect is missing, ask the maintainer to
  add it to the curated list.
- **Actor** — partial match on username.
- **Target type** — exact match (e.g. `collection`, `user`,
  `document`, `media`, `plugin`).
- **From** / **To** — date+time range (your browser's local time;
  converted to UTC server-side).

The structured filters and the free-text **Search** box compose:
they are ANDed together. So *Search="anna" + Action="collection.created"*
returns every collection-created action attributed to a user
whose username contains "anna".

Click **Apply** to run the query (or just press Enter inside the
search box). **Clear** resets every filter and returns to the
default view.

## Exporting

The **Export CSV** button on the top right downloads the **same
filtered query** you currently see, with no pagination — useful
for spreadsheets, audits, or for a one-off "send the last week's
publishes to my colleague" share. Filename is `audit-log.csv`.

The CSV columns:
`id, occurred_at, action, actor_username, target_type, target_id, target_label`.

## Privacy and what is NOT shown

A few fields are deliberately hidden from this view:

- The **IP address** is hashed before it ever reaches the
  database (with the platform's `JWT_SECRET` as salt), so the
  Admin sees neither the raw nor the hash. This is by design —
  the hash adds no investigative value while paying a privacy
  cost.
- Document **bodies** are never recorded in the audit log. The
  payload only carries metadata: who, when, what changed, the
  role they held, the note they typed.

## Retention

Rows older than **`audit_log_retention_days`** (default `90`,
configurable in **Admin → Settings**) are deleted by a nightly
job at 02:00 UTC. The view always shows what is currently in the
table; once a row is purged, it is gone.

## Tips

- For a "live" feel, just refresh the page after an action you
  want to verify — the table is paginated so rows added since
  the last query show up immediately when you reload.
- The **side panel** is your friend when an action looks
  surprising: the JSONB payload often carries the actual `before`
  / `after` values and the EditorInChief's note.
- Filter by **target_type=user** to see every action that touched
  a user account — useful for "who deactivated this account?".
- The filter dropdown for Action is curated to match the canonical
  vocabulary, so the values you see are the values the platform
  actually emits.

---

Technical reference: [`docs/reference/AUDIT_LOG.md`](../../docs/reference/AUDIT_LOG.md).
