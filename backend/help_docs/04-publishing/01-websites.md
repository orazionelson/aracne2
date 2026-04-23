# Websites — publishing to the web

A **website** is a public-facing presentation of a collection: a cover
page, a browsable document list, each individual document rendered via
XSLT, a bibliography page, optional indices, and free-form pages that
the Designer can add.

A collection can have more than one website (e.g. a scholarly long-form
presentation and a simpler public one). Each has its own URL slug under
`/sites/<slug>/`.

## What a website includes

- **Home page** — cover page with title, description, and optional
  multi-column layout.
- **Browse** — the document list, paginated.
- **Search** — full-text search across the collection's documents.
- **Bibliography** — the public `CollectionBibliography` version
  rendered as a readable page.
- **Indices** — browsable indices of named entities or custom tags.
- **Free pages** — Markdown or WYSIWYG pages added by the Designer
  (e.g. "About this edition", "Credits").

## Rendering modes

| Mode | Description |
|------|-------------|
| Static | Full build generates HTML on disk and serves it via a fast static file handler. |
| Dynamic | No files on disk — every request renders the page live from eXist-db + XSLT. |
| Hybrid | Static cover / browse / bibliography + dynamic documents and search. Best for collections that change frequently. |

A Designer can switch modes at any time from the website's settings.
Switching to Static requires clicking **Build** once — subsequent
changes show up only after another build.

## XSLT stylesheets — making documents look good

The XSLT stylesheet controls how TEI XML is turned into HTML. Each
website can use:

- The built-in default stylesheet (generic TEI rendering).
- A custom inline XSLT written in the Designer's editor.
- An external XSLT fetched from a URL at build time.
- A stylesheet from the platform's XSLT catalogue (reusable library).

## Indices

From the website settings, add one or more indices — each bound to a
TEI element or attribute (for example `<persName>` or
`<rs type="work">`). Click **Rebuild** to refresh the index data from
eXist-db.

## Building and downloading the site

For Static and Hybrid modes, click **Build** to produce the files on
disk. Large collections may take several minutes — the build runs in
the background and the website page shows progress.

Once built, the **Download** button produces a ZIP archive of the
entire built site, ready to upload to any static hosting provider if
you want to mirror the site elsewhere.

## Custom homepage CSS

Designers can upload a custom CSS file to override the default styles
on the public homepage and (optionally) the other public views. See
the technical reference in `docs/reference/PUBLIC_PAGES.md` for the
list of semantic CSS classes you can target.

## Discoverability

Aracne2 generates `robots.txt` and `sitemap.xml` automatically. Every
public website is listed in the platform-wide sitemap index, and each
website has its own per-site sitemap covering every visible page.
Designers do not need to manage these files manually.
