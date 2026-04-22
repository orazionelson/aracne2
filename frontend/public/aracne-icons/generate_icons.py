"""
Aracne icon set generator.
Genera favicon (trasparente) + app icon (fondo inchiostro) alle
dimensioni 16, 32, 48, 64, 128, 256, 512, più favicon.ico multi-res.

Strategia di rendering:
  — disegna su canvas N× la dimensione target (supersampling)
  — Pillow ImageDraw per cerchi + linee + giunzioni arrotondate a mano
  — downscale LANCZOS per antialiasing
  — geometria adattata alla dimensione (tratti più grossi alle taglie piccole,
    cerchio esterno rimosso sotto i 48 px perché si perde)
"""

import math
import os
from pathlib import Path
from PIL import Image, ImageDraw

# ─── Palette ──────────────────────────────────────────────────
INK          = (19, 26, 42, 255)    # #131A2A
PARCHMENT    = (236, 226, 200, 255) # #ECE2C8
RUBRIC       = (166, 38, 57, 255)   # #A62639
RUBRIC_LIGHT = (212, 74, 92, 255)   # #D44A5C

# ─── Geometria del marchio (SVG units, viewBox -100..100) ─────
# Chevron base: polyline da (76,-17.55) a (16,0) a (76,17.55)
DEFAULT_CHEVRON = ((76.0, -17.55), (16.0, 0.0), (76.0, 17.55))

def rotate(x, y, angle_deg):
    a = math.radians(angle_deg)
    c, s = math.cos(a), math.sin(a)
    return (x * c - y * s, x * s + y * c)

def draw_aracne(
    size,
    *,
    stroke_color,
    body_color,
    bg_color=None,
    include_outer_circle=True,
    stroke_width_svg=2.4,
    outer_circle_width_svg=1.3,
    outer_circle_radius_svg=92,
    body_radius_svg=6,
    chevron_points=DEFAULT_CHEVRON,
    supersample=4,
):
    """Disegna il marchio Aracne. Ritorna PIL.Image RGBA alla `size` finale."""
    W = size * supersample
    center = W / 2
    scale = W / 200.0  # SVG units (-100..+100, total 200) → W pixels

    def to_px(sx, sy):
        return (center + sx * scale, center + sy * scale)

    bg = bg_color if bg_color is not None else (0, 0, 0, 0)
    img = Image.new("RGBA", (W, W), bg)
    draw = ImageDraw.Draw(img)

    # ── Cerchio esterno ────────────────────────────────────
    if include_outer_circle:
        r = outer_circle_radius_svg * scale
        w = max(1, round(outer_circle_width_svg * scale))
        draw.ellipse(
            [center - r, center - r, center + r, center + r],
            outline=stroke_color, fill=None, width=w
        )

    # ── Otto chevron ───────────────────────────────────────
    sw = stroke_width_svg * scale
    sw_i = max(1, round(sw))
    a_pt, b_pt, c_pt = chevron_points
    rr = sw / 2.0   # raggio dei cerchietti di raccordo

    for angle in (0, 45, 90, 135, 180, 225, 270, 315):
        a = rotate(*a_pt, angle)
        b = rotate(*b_pt, angle)
        c = rotate(*c_pt, angle)
        ax, ay = to_px(*a)
        bx, by = to_px(*b)
        cx, cy = to_px(*c)

        # Due segmenti A-B e B-C
        draw.line([(ax, ay), (bx, by)], fill=stroke_color, width=sw_i)
        draw.line([(bx, by), (cx, cy)], fill=stroke_color, width=sw_i)

        # Cerchi di raccordo sui tre vertici per arrotondare end/join
        for px, py in ((ax, ay), (bx, by), (cx, cy)):
            draw.ellipse(
                [px - rr, py - rr, px + rr, py + rr],
                fill=stroke_color
            )

    # ── Corpo centrale (rubrica) ───────────────────────────
    br = body_radius_svg * scale
    draw.ellipse(
        [center - br, center - br, center + br, center + br],
        fill=body_color
    )

    # ── Downsample ─────────────────────────────────────────
    return img.resize((size, size), Image.LANCZOS)


def geometry_for(size):
    """Adatta la geometria alla dimensione di output.

    Grandi (≥96 px): geometria canonica, tratto fine, cerchio esterno presente.
    Medie (48–95 px): tratto più grosso, cerchio ancora visibile.
    Piccole (<48 px): niente cerchio esterno (si perde), tratto molto grosso,
                      chevron più larghi, corpo più grande.
    """
    if size >= 96:
        return dict(
            stroke_width_svg=2.4,
            outer_circle_width_svg=1.3,
            body_radius_svg=6,
            include_outer_circle=True,
        )
    elif size >= 48:
        return dict(
            stroke_width_svg=3.6,
            outer_circle_width_svg=1.9,
            body_radius_svg=8,
            include_outer_circle=True,
        )
    else:
        # Ultra-minimal: niente cerchio esterno, chevron spessi e larghi
        return dict(
            stroke_width_svg=10,
            outer_circle_width_svg=0,
            body_radius_svg=16,
            include_outer_circle=False,
            chevron_points=((72.0, -24.0), (20.0, 0.0), (72.0, 24.0)),
        )


# ─── Generazione dei file ─────────────────────────────────────
SIZES = [16, 32, 48, 64, 128, 256, 512]
out_base = Path("/mnt/user-data/outputs/aracne-icons")
(out_base / "favicon").mkdir(parents=True, exist_ok=True)
(out_base / "app-icon").mkdir(parents=True, exist_ok=True)

print("Generating icons…")
for size in SIZES:
    params = geometry_for(size)

    # FAVICON — fondo trasparente, inchiostro + rubrica
    fav = draw_aracne(
        size,
        stroke_color=INK,
        body_color=RUBRIC,
        bg_color=None,
        **params,
    )
    fav.save(out_base / "favicon" / f"aracne-favicon-{size}.png", optimize=True)

    # APP ICON — fondo inchiostro pieno, pergamena + rubrica chiara
    app = draw_aracne(
        size,
        stroke_color=PARCHMENT,
        body_color=RUBRIC_LIGHT,
        bg_color=INK,
        **params,
    )
    app.convert("RGB").save(out_base / "app-icon" / f"aracne-appicon-{size}.png", optimize=True)

    print(f"  ✓ {size:4d} px")

# ─── favicon.ico multi-risoluzione (16/32/48) ─────────────────
print("Building favicon.ico (multi-res 16/32/48)…")
ico_16 = Image.open(out_base / "favicon" / "aracne-favicon-16.png").convert("RGBA")
ico_32 = Image.open(out_base / "favicon" / "aracne-favicon-32.png").convert("RGBA")
ico_48 = Image.open(out_base / "favicon" / "aracne-favicon-48.png").convert("RGBA")
ico_16.save(
    out_base / "favicon" / "favicon.ico",
    format="ICO",
    append_images=[ico_32, ico_48],
)
print("  ✓ favicon.ico")

# ─── favicon.svg (vettoriale per browser moderni) ─────────────
print("Writing favicon.svg…")
favicon_svg = """<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" viewBox="-100 -100 200 200">
  <defs>
    <g id="leg">
      <polyline points="76,-17.55 16,0 76,17.55" fill="none"
                stroke="#131A2A" stroke-width="2.4"
                stroke-linecap="round" stroke-linejoin="round"/>
    </g>
  </defs>
  <circle cx="0" cy="0" r="92" fill="none" stroke="#131A2A" stroke-width="1.3"/>
  <use href="#leg" transform="rotate(0)"/>
  <use href="#leg" transform="rotate(45)"/>
  <use href="#leg" transform="rotate(90)"/>
  <use href="#leg" transform="rotate(135)"/>
  <use href="#leg" transform="rotate(180)"/>
  <use href="#leg" transform="rotate(225)"/>
  <use href="#leg" transform="rotate(270)"/>
  <use href="#leg" transform="rotate(315)"/>
  <circle cx="0" cy="0" r="6" fill="#A62639"/>
</svg>
"""
(out_base / "favicon" / "favicon.svg").write_text(favicon_svg)
print("  ✓ favicon.svg")

print("\nDone. Output:", out_base)
