# Aracne2 — `gh-pages` branch

This branch is the source for the project's GitHub Pages site at
**https://orazionelson.github.io/aracne2/**.

It is an **orphan branch**: it shares no history with `main`. It contains only
the static landing page and its assets — no source code, no documentation, no
Python or Node dependencies.

## How to update

```bash
git checkout gh-pages
# edit index.html, style.css, drop screenshots into img/screenshots/, etc.
git add -A
git commit -m "site: …"
git push
git checkout main      # or whichever branch you were working on
```

GitHub Pages rebuilds automatically a few seconds after the push lands.

## Files

```
/
├── index.html                  single-page showcase
├── style.css                   bespoke rules on top of Tailwind CDN
├── .nojekyll                   disable Jekyll processing
├── README.md                   this file
└── img/
    ├── brand/                  favicon (copied from main once); the hero marchio is inline SVG inside index.html
    └── screenshots/            product screenshots (drop PNGs here)
```

The screenshot filenames are pre-wired in `index.html`. Use the exact names
when adding new images:

| Filename                        | Caption in the landing                                 |
|---------------------------------|--------------------------------------------------------|
| `01-tei-editor.png`             | TEI editor with split view and XPath inspector         |
| `02-ai-panel.png`               | Aracne AI co-editing panel                             |
| `03-public-collection.png`      | Public collection page (reader view)                   |
| `04-corpora-mcp.png`            | Corpora dashboard with MCP token issuance              |
| `05-deposit-tabs.png`           | Deposit tabs for Zenodo, Dataverse and preprint        |
| `06-website-render.png`         | Generated website with custom XSLT theme               |

If a screenshot is missing, the landing falls back gracefully to a parchment
placeholder labelled with the slot name.

## Brand assets

The lockup PNG and the favicon under `img/brand/` are **copies** of the canonical
files maintained on `main` at `frontend/public/aracne-icons/`. If the brand changes
on `main`, re-copy them with:

```bash
git show main:frontend/public/aracne-icons/favicon/favicon.svg \
    > img/brand/favicon.svg
git add img/brand/
git commit -m "site: refresh brand assets from main"
```

## Local preview

```bash
python3 -m http.server 8000
# open http://localhost:8000/
```
