# Help docs — authoring notes

This directory is the **source** for the in-app Help plugin
(`backend/app/plugins/help/`). When the Help plugin is activated, every
`.md` file here is rendered on demand as sanitised HTML and served
under `/api/v1/plugins/help/`.

## Why it lives under `backend/`

Docker's build context for the backend container is `./backend/`, so
files outside of it cannot be COPY'd into the image. Placing the help
sources alongside `app/` keeps everything the backend serves in one
tree — production image ships them automatically, development sees
them via the same bind mount as the code.

## Directory layout rules

- One `.md` file per help page.
- Group related pages under sub-directories; the plugin walks the tree
  recursively.
- Sort order: alphabetical. Prefix filenames with `01-`, `02-`, … to
  force ordering (`01-introduction.md` sorts before `02-roles.md`).
- Titles are derived from the first `# Heading` in the file; the
  filename slug is the URL path.
- Images referenced by the pages go under `img/` and are fetched
  through `/plugins/help/assets/…` — only files ending in `.png .jpg
  .jpeg .svg .gif .webp` are served; path traversal is blocked.

## Content conventions

- Task-oriented prose — "how to do X", not reference documentation.
- ~100-300 words per page is a good target; longer pages should be
  split.
- Keep it in English. The plugin does not translate; if you need
  Italian content, add a localised version under a parallel `it/`
  tree (future enhancement).
- Code fences (`\`\`\``) are rendered with syntax highlighting by the
  frontend Prism bundle — no extra work needed here.
- Internal links: use `/help/page?path=<section>/<file>` (no `.md`
  extension) so the frontend router intercepts and renders in-app
  rather than round-tripping to the server.

## Two doc trees — why and how to keep them aligned

Aracne2 has **two** sets of markdown documentation, with different
audiences and different tones:

| | `docs/` (this repo's root) | `backend/help_docs/` (this directory) |
|---|---|---|
| **Reader** | Developer / SRE — someone changing the codebase or operating the install | Editor, Designer, EiC, Admin — someone *using* the running Aracne2 |
| **Where read** | GitHub, VSCode, filesystem | In-browser at `/help` (the in-app Help drawer) |
| **Tone** | Reference: endpoints, schema, file:line anchors, architecture | Operational: "to do X go to Y and click Z" |
| **Scope** | Complete — every table, migration, field | Only what the user needs to act |
| **Canonical for** | Developer-facing material | User-facing flows |

They are **not** duplicates. A doc page about the forge plugins under
`docs/reference/NON_NATIVE_PLUGINS.md` lists every endpoint, every
column, every migration; the help page about the same plugins under
`04-publishing/04-external-repositories.md` explains where the
"Deposit" button lives and when it's enabled. Overlap is natural
but the two files should never be identical.

**How to keep them aligned when a feature changes:**

1. If the feature has a **user-visible effect** (new button, new tab,
   new flow) → update the relevant help page under this directory
   **and** the corresponding reference doc under `docs/reference/`.
2. If the feature is **purely internal** (refactor, new internal
   table, migration that doesn't change behaviour) → update the
   reference doc only.
3. When the help page is a simplified / user-facing version of a
   reference doc, add a cross-link at the bottom:
   `Technical reference: docs/reference/<name>.md`. This makes it
   trivial for a curious admin to dig deeper and makes the
   reference-vs-help split explicit.
4. There is **no CI enforcement** today. The convention lives on
   discipline + code review.

See [`docs/README.md`](../../docs/README.md) for the mirror view of
this convention from the developer-docs side.
