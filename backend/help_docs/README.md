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
