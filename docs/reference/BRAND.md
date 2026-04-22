# Brand identity — Aracne icon set

The Aracne identity kit (marchio **Tagweb**, wordmark *Aracne*) lives at
[frontend/public/aracne-icons/](../../frontend/public/aracne-icons/). Every
file in that directory is served statically by Vite at the matching URL
path — e.g. `frontend/public/aracne-icons/favicon/favicon.svg` is reachable
at `/aracne-icons/favicon/favicon.svg` in both dev and prod.

The folder also contains the generation scripts (`generate_icons.py`,
`generate_lockup.py`), the contact-sheet (`preview.html`) and the full
kit README.

---

## Canonical sigla table — lives in the kit

The full **sigla → file path** table is maintained inside the kit itself:

> [frontend/public/aracne-icons/README.md](../../frontend/public/aracne-icons/README.md) —
> § *"Tabella corrispondenze file → sigla"*

That is the single source of truth. When you need the path for a sigla
(e.g. `VT·WHT·512`, `TG·SVG`, `AI·256`, `NM·PCH·1024`), read it from
there — **do not re-maintain the table here**.

Family prefixes, for quick orientation:

| Prefix | Family                                               |
|--------|------------------------------------------------------|
| `FA`   | Favicon (marchio puro, trasparente)                  |
| `AI`   | App icon (marchio on ink background)                 |
| `NM`   | Named lockup (marchio + "ARACNE" tracked — square)   |
| `HZ`   | Horizontal lockup (marchio + "Aracne" side-by-side)  |
| `VT`   | Vertical lockup (marchio stacked + "Aracne")         |
| `TG`   | Tagline lockup (horizontal + "TEI XML encoder")      |

Colour variant goes after the dot (`WHT` on light, `INK` on dark,
`PCH` parchment) then the pixel size (`512`, `1024`, `2048`) or `SVG`
for the vector variant.

---

## Where the app consumes these sigla

The table below is the Aracne2-specific layer: which sigla is wired in
which slot, and which slots are re-brandable. Keep it in sync when the
admin UI or the public face starts using a different asset.

| Area                                    | Sigla in use    | Customisable? |
|-----------------------------------------|-----------------|---------------|
| Browser tab (favicon)                   | `FA·SVG`, `FA·ICO`, `FA·32`, `FA·16`, `AI·256` (apple-touch) | No |
| Admin sidebar — light theme, expanded   | `VT·WHT·512`    | No            |
| Admin sidebar — dark theme, expanded    | `VT·INK·512`    | No            |
| Admin sidebar — collapsed (any theme)   | `FA·SVG`        | No            |
| Public homepage — default               | `VT·WHT·512`    | Yes — Admin can replace via Settings → Homepage |
| Public header (`PublicHeader.vue`)      | whatever the Admin configured (defaults to `VT·WHT·512`) | Yes |

**Rule of thumb**: the admin area is **not re-brandable** — logos there
are hardcoded to the Aracne sigla. The public face (homepage, public
document pages, embed widgets) **is re-brandable** through the
Settings → Homepage form.

---

## Adding a new usage in code

When a Vue component, HTML template, XSLT stylesheet or backend response
needs an Aracne asset, look the path up in the kit README and paste it
verbatim. Do not hard-code variant sizes behind the scenes — always go
through the sigla table so that retiring or renaming a variant is a
single-file change at the kit level.

Example in Vue:

```vue
<img src="/aracne-icons/lockup/aracne-lockup-vertical-512.png" alt="Aracne" />
```

Example in the admin sidebar (already wired in
[AppSidebar.vue](../../frontend/src/components/layout/AppSidebar.vue)):

```ts
const ADMIN_LOGO_LIGHT = "/aracne-icons/lockup/aracne-lockup-vertical-512.png";          // VT·WHT·512
const ADMIN_LOGO_DARK  = "/aracne-icons/lockup/aracne-lockup-vertical-512-inverse.png";  // VT·INK·512
```

The trailing comment with the sigla lets a reader cross-reference the kit
table without loading the image.

---

## Regenerating the kit

The kit is version-controlled source material. PNGs are checked in so
the app can be cloned and run without invoking Python at build time. To
update variants after tweaking colours / geometry:

```bash
cd frontend/public/aracne-icons
python3 generate_icons.py   # favicon + app-icon
python3 generate_lockup.py  # lockup + app-icon-named
```

See the kit README for font requirements (Lora, optionally Fraunces)
and the adaptive-geometry table.
