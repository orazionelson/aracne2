# Brand identity — Aracne icon set

The Aracne identity kit (marchio **Tagweb**, wordmark *Aracne*) lives at
[frontend/public/aracne-icons/](../../frontend/public/aracne-icons/). Every
file in that directory is served statically by Vite at the matching URL
path — e.g. the file `frontend/public/aracne-icons/favicon/favicon.svg`
is reachable at `/aracne-icons/favicon/favicon.svg` in both dev and prod.

The folder also contains the generation scripts (`generate_icons.py`,
`generate_lockup.py`), the contact-sheet (`preview.html`) and the full
design README — these are tracked in git but harmless in the production
build. See [frontend/public/aracne-icons/README.md](../../frontend/public/aracne-icons/README.md)
for the full kit catalogue, geometry and colour tokens.

---

## Sigla reference — use this table when Aracne assets are needed

Each sigla maps to the largest commonly-useful size. Most assets also
ship in 16 / 32 / 48 / 64 / 128 / 256 / 512 / 1024 / 2048 PNG variants
where applicable; pick the smallest that renders crisp at the target size
to keep the bundle light.

### Marchio only (no wordmark)

| Sigla      | Path                                               | Use                                |
|------------|----------------------------------------------------|------------------------------------|
| `FV·SVG`   | `/aracne-icons/favicon/favicon.svg`                | Browser tab (modern), any background |
| `FV·ICO`   | `/aracne-icons/favicon/favicon.ico`                | Legacy browser tab                 |
| `FV·512`   | `/aracne-icons/favicon/aracne-favicon-512.png`     | Favicon raster, transparent bg     |
| `AI·512`   | `/aracne-icons/app-icon/aracne-appicon-512.png`    | App icon — marchio on ink square   |

### Named lockup — marchio + wordmark *ARACNE* (square format)

| Sigla       | Path                                                               | Use                                       |
|-------------|--------------------------------------------------------------------|-------------------------------------------|
| `NM·WHT`    | `/aracne-icons/app-icon-named/aracne-named-white-512.png`          | Admin sidebar (light theme); public home default |
| `NM·INK`    | `/aracne-icons/app-icon-named/aracne-named-512.png`                | Admin sidebar (dark theme)                |
| `NM·PAR`    | `/aracne-icons/app-icon-named/aracne-named-parchment-512.png`      | Parchment variant (special contexts)      |

### Horizontal lockup — marchio + wordmark side-by-side

| Sigla       | Path                                                                | Use                              |
|-------------|---------------------------------------------------------------------|----------------------------------|
| `LH·SVG`    | `/aracne-icons/lockup/aracne-lockup-horizontal.svg`                 | Vector; best for headers         |
| `LH·1024`   | `/aracne-icons/lockup/aracne-lockup-horizontal-1024.png`            | Header on light background       |
| `LH·1024·I` | `/aracne-icons/lockup/aracne-lockup-horizontal-1024-inverse.png`    | Header on dark background        |

### Vertical lockup — stacked marchio + wordmark

| Sigla       | Path                                                          | Use                            |
|-------------|---------------------------------------------------------------|--------------------------------|
| `LV·SVG`    | `/aracne-icons/lockup/aracne-lockup-vertical.svg`             | Splash screens, about pages    |
| `LV·1024`   | `/aracne-icons/lockup/aracne-lockup-vertical-1024.png`        | Splash screens, raster         |

### Tagline lockup — horizontal lockup + "TEI XML encoder"

| Sigla       | Path                                                                  | Use                                   |
|-------------|-----------------------------------------------------------------------|---------------------------------------|
| `LT·SVG`    | `/aracne-icons/lockup/aracne-lockup-tagline.svg`                      | Landing-page hero                     |
| `LT·2048`   | `/aracne-icons/lockup/aracne-lockup-tagline-2048.png`                 | Landing-page hero raster              |

---

## How the app consumes the set today

| Area                                  | Sigla(s) in use     | Customisable? |
|---------------------------------------|---------------------|---------------|
| Browser tab                           | `FV·SVG`, `FV·ICO`  | No            |
| Admin sidebar — light theme, expanded | `NM·WHT`            | No            |
| Admin sidebar — dark theme, expanded  | `NM·INK`            | No            |
| Admin sidebar — collapsed (any theme) | `FV·SVG`            | No            |
| Public homepage — default             | `NM·WHT`            | Yes — Admin can replace via Settings → Homepage |
| Public header (`PublicHeader.vue`)    | whatever the Admin configured (defaults to `NM·WHT`) | Yes |

**Rule of thumb**: the admin area is not re-brandable. The public face
(homepage, public document pages, embed widgets) is re-brandable through
the Settings → Homepage form.

---

## Adding a new usage in code

When a Vue component, Jinja-style template or XSLT stylesheet needs an
Aracne asset, reference the sigla from the tables above (or ask the
operator which sigla to use) and paste the matching path verbatim. Do
not hard-code variant sizes elsewhere — always go through the tables so
that retiring or renaming a variant is a single-file change here.

Example in Vue:

```vue
<img src="/aracne-icons/app-icon-named/aracne-named-white-512.png" alt="Aracne" />
```

Example in the admin sidebar (already wired in
[AppSidebar.vue](../../frontend/src/components/layout/AppSidebar.vue)):

```ts
const ADMIN_LOGO_LIGHT = "/aracne-icons/app-icon-named/aracne-named-white-256.png";
const ADMIN_LOGO_DARK  = "/aracne-icons/app-icon-named/aracne-named-256.png";
```

---

## Regenerating the kit

The kit is version-controlled source material. PNGs are checked in so
the app can be cloned and run without running Python at build time. To
update variants after tweaking colours / geometry:

```bash
cd frontend/public/aracne-icons
python3 generate_icons.py   # favicon + app-icon
python3 generate_lockup.py  # lockup + app-icon-named
```

See `frontend/public/aracne-icons/README.md` for font requirements
(Lora, optionally Fraunces) and the adaptive-geometry table.
