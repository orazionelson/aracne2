# Aracne — Identity set

Marchio **Tagweb** (Concept II) derivato dallo studio di marchio.
Otto chevron radiali — *angle brackets* XML / zampe di ragno — convergenti verso una radice rossa centrale.

---

## Struttura dell'archivio

```
aracne-icons/
├─ README.md
├─ preview.html                          ← contact sheet favicon/app-icon
│
├─ favicon/                              ← marchio puro, trasparente
│  ├─ favicon.svg                        ← vettoriale per browser moderni
│  ├─ favicon.ico                        ← multi-res 16/32/48, legacy
│  ├─ aracne-favicon-{16,32,48,64,128,256,512}.png
│
├─ app-icon/                             ← marchio su fondo inchiostro
│  └─ aracne-appicon-{16,32,48,64,128,256,512}.png
│
├─ lockup/                               ← marchio + wordmark "Aracne"
│  ├─ aracne-lockup-horizontal.svg       ← orizzontale, testo vivo
│  ├─ aracne-lockup-horizontal-{512,1024,2048}.png
│  ├─ aracne-lockup-horizontal-{512,1024,2048}-inverse.png  ← su fondo inchiostro
│  ├─ aracne-lockup-vertical.svg
│  ├─ aracne-lockup-vertical-{512,1024,2048}.png
│  ├─ aracne-lockup-tagline.svg          ← orizzontale + "TEI XML encoder"
│  └─ aracne-lockup-tagline-{1024,2048}.png
│
└─ app-icon-named/                       ← marchio + "ARACNE" tracked, su inchiostro
   └─ aracne-named-{256,512,1024}.png
```

---

## Mapping d'uso consigliato

| Contesto                               | File consigliato                                        |
|----------------------------------------|---------------------------------------------------------|
| Tab browser (moderni)                  | `favicon/favicon.svg`                                   |
| Tab browser (legacy)                   | `favicon/favicon.ico`                                   |
| Apple touch-icon                       | `app-icon/aracne-appicon-256.png`                       |
| Android / Play Store                   | `app-icon-named/aracne-named-1024.png`                  |
| Desktop shortcut (macOS/Windows)       | `app-icon/aracne-appicon-512.png`                       |
| Header sito / README GitHub            | `lockup/aracne-lockup-horizontal-1024.png`              |
| Header sito su sfondo scuro            | `lockup/aracne-lockup-horizontal-1024-inverse.png`      |
| Splash screen / about page             | `lockup/aracne-lockup-vertical-1024.png`                |
| Hero con tagline (landing page)        | `lockup/aracne-lockup-tagline-2048.png`                 |

---

## HTML snippet — favicon

```html
<link rel="icon" type="image/svg+xml" href="/favicon.svg">
<link rel="icon" type="image/png" sizes="32x32" href="/aracne-favicon-32.png">
<link rel="icon" type="image/png" sizes="16x16" href="/aracne-favicon-16.png">
<link rel="apple-touch-icon" sizes="256x256" href="/aracne-appicon-256.png">
<link rel="shortcut icon" href="/favicon.ico">
```

---

## Tipografia del wordmark

**Font: Lora** (SIL OFL — Google Fonts, variabile, disponibile localmente)
Peso: 500 (Medium). L'istanza Italic è usata per la sola *a* centrale: `Ar`*`a`*`cne`.

Questo micro-dettaglio — la 'a' italica in contrasto con le lettere upright — richiama
la distinzione tra testo-fonte e apparato critico nella tradizione filologica.

**Fraunces** era il font target della presentazione iniziale (stessa famiglia Google Fonts,
opsz variabile, contrasto più alto). Non installato localmente: i file SVG lo referenziano
via `@import` CDN — aprire in browser con Internet per vedere la versione definitiva.

Per rigenarare i PNG in Fraunces:
1. Scaricare `Fraunces[opsz,wght].ttf` e `Fraunces-Italic[opsz,wght].ttf`
2. Aggiornare `LORA_REG` / `LORA_ITA` in `generate_lockup.py`
3. `python3 generate_lockup.py`

---

## Colori

| Token       | Hex       | Uso                                         |
|-------------|-----------|---------------------------------------------|
| Inchiostro  | `#131A2A` | Tratti marchio, testo wordmark, fondo scuro |
| Pergamena   | `#ECE2C8` | Marchio su scuro, sfondo chiaro             |
| Rubrica     | `#A62639` | Corpo centrale su fondo chiaro              |
| Rubrica+    | `#D44A5C` | Corpo centrale su fondo scuro               |

---

## Geometria adattiva (marchio puro)

| Dimensione output | Cerchio esterno | Tratto | Corpo  |
|-------------------|-----------------|--------|--------|
| ≥ 96 px           | sì (1.3 pt)     | 2.4 pt | r = 6u |
| 48–95 px          | sì (1.9 pt)     | 3.6 pt | r = 8u |
| < 48 px           | rimosso         | 10 pt  | r = 16u|

A 16 px il marchio si riduce a un asterisco a otto punte con centro rosso — limite fisico accettato.
`favicon.svg` è il riferimento canonico per contesti web moderni.

---

## Rigenera i file

```bash
python3 generate_icons.py   # favicon + app-icon
python3 generate_lockup.py  # lockup + app-icon-named
```
