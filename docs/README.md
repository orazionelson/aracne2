# Developer documentation

This directory holds the **developer-facing** documentation for
Aracne2 — reference material for anyone modifying the codebase,
operating an install, or writing a plugin. It lives in the repo
alongside the code and is read on GitHub, in VSCode, or on the
filesystem; it is **not** served by the running application.

## Contents

- `reference/` — per-subsystem reference docs (plugins, database
  schema, HTTP API shapes, TEI schemas, websites module, deposit
  integrations, etc.). Every non-trivial subsystem has one.
- `phases/` — historical implementation phases kept as a record.
  Not living docs; don't modify unless a phase is genuinely being
  re-done.
- `OPERATIONS.md` — runbook for admins / SRE: rotating credentials,
  reading logs, backup, troubleshooting port / DNS / bootstrap.
- `FUTURE_IDEAS.md` — speculative roadmap. Ideas that may or may not
  ship; when one ships, the entry is marked as such with a pointer
  to the canonical spec.
- `DEFERRED.md` — architectural decisions deferred for features that
  **are** in scope (different from `FUTURE_IDEAS.md`).
- `USER_MANUAL.md` — long-form editor / admin handbook, authored
  here for developer-side review. Its runtime counterpart is the
  in-app Help at `/help` (sourced from `backend/help_docs/`).
- `Security_review_YYYY-MM-DD.md` — one-shot security audit
  reports kept for trail.

## Two doc trees — why and how to keep them aligned

Aracne2 has **two** sets of markdown documentation, with different
audiences and different tones:

| | `docs/` (this directory) | `backend/help_docs/` |
|---|---|---|
| **Reader** | Developer / SRE — someone changing the codebase or operating the install | Editor, Designer, EiC, Admin — someone *using* the running Aracne2 |
| **Where read** | GitHub, VSCode, filesystem | In-browser at `/help` (the in-app Help drawer served by the Help plugin) |
| **Tone** | Reference: endpoints, schema, file:line anchors, architecture | Operational: "to do X go to Y and click Z" |
| **Scope** | Complete — every table, migration, field | Only what the user needs to act |
| **Canonical for** | Developer-facing material | User-facing flows |

They are **not** duplicates. A reference doc (e.g.
`reference/NON_NATIVE_PLUGINS.md`) lists every endpoint, every
column, every migration; the corresponding help page under
`backend/help_docs/` explains where the button lives and when it's
enabled. Overlap is natural but the two files should never be
identical.

### How to keep them aligned when a feature changes

1. **User-visible effect** (new button, new tab, new flow) → update
   **both** the relevant help page under `backend/help_docs/` **and**
   the corresponding reference doc under `reference/`.
2. **Purely internal change** (refactor, new internal table,
   migration that doesn't change behaviour) → update the reference
   doc only.
3. When a help page is a simplified / user-facing version of a
   reference doc, add a cross-link at the bottom:
   `Technical reference: docs/reference/<name>.md`. This makes the
   reference-vs-help split explicit.
4. There is **no CI enforcement** today. The convention lives on
   discipline + code review.

See [`backend/help_docs/README.md`](../backend/help_docs/README.md)
for the mirror view of this convention from the help-docs side.

## Language

Developer docs are in **English** — international convention, plus
it keeps this tree searchable by anyone arriving from the open-source
ecosystem. The in-app help is also in English today (see
`backend/help_docs/README.md`); localisation is a future enhancement.
