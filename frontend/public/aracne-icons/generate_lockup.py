"""
Aracne — lockup & named app icon generator.

Produce:
  lockup/
    aracne-lockup-horizontal.svg        (testo vivo + @font-face Google Fonts)
    aracne-lockup-horizontal-{512,1024,2048}.png
    aracne-lockup-vertical.svg
    aracne-lockup-vertical-{512,1024,2048}.png
    aracne-lockup-tagline.svg           (orizzontale + "TEI XML encoder")
    aracne-lockup-tagline-{1024,2048}.png
  app-icon-named/
    aracne-named-{256,512,1024}.png     (marchio + "ARACNE" su fondo inchiostro)

Font del wordmark: Lora (SIL OFL), variable serif — disponibile localmente in
/usr/share/fonts/truetype/google-fonts/. La 'a' centrale è in corsivo come
micro-dettaglio distintivo (eredità della presentazione iniziale su "Ar*a*cne").
"""

import math
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

# ═══ Palette ══════════════════════════════════════════════════
INK          = (19, 26, 42, 255)
PARCHMENT    = (236, 226, 200, 255)
RUBRIC       = (166, 38, 57, 255)
RUBRIC_LIGHT = (212, 74, 92, 255)

INK_HEX       = "#131A2A"
PARCHMENT_HEX = "#ECE2C8"
RUBRIC_HEX    = "#A62639"

# ═══ Font paths ═══════════════════════════════════════════════
LORA_REG = "/usr/share/fonts/truetype/google-fonts/Lora-Variable.ttf"
LORA_ITA = "/usr/share/fonts/truetype/google-fonts/Lora-Italic-Variable.ttf"

def load_lora(path, size, weight=500):
    f = ImageFont.truetype(path, size)
    try:
        f.set_variation_by_axes([weight])
    except Exception:
        pass
    return f

# ═══ Marchio drawing (geometrica pura, riuso dall'iteration precedente) ═══
DEFAULT_CHEVRON = ((76.0, -17.55), (16.0, 0.0), (76.0, 17.55))

def rotate(x, y, angle_deg):
    a = math.radians(angle_deg)
    c, s = math.cos(a), math.sin(a)
    return (x * c - y * s, x * s + y * c)

def draw_mark_on(draw, center_x, center_y, diameter_px,
                 stroke_color, body_color,
                 stroke_width_svg=2.4, outer_circle_width_svg=1.3,
                 outer_circle_radius_svg=92, body_radius_svg=6,
                 chevron=DEFAULT_CHEVRON,
                 include_outer_circle=True):
    """Disegna il marchio Aracne direttamente sul Draw passato, a diametro target."""
    scale = diameter_px / 200.0  # SVG units (±100) → pixels
    def to_px(sx, sy):
        return (center_x + sx * scale, center_y + sy * scale)

    if include_outer_circle:
        r = outer_circle_radius_svg * scale
        w = max(1, round(outer_circle_width_svg * scale))
        draw.ellipse(
            [center_x - r, center_y - r, center_x + r, center_y + r],
            outline=stroke_color, fill=None, width=w
        )

    sw = stroke_width_svg * scale
    sw_i = max(1, round(sw))
    rr = sw / 2.0
    for angle in (0, 45, 90, 135, 180, 225, 270, 315):
        a = rotate(*chevron[0], angle)
        b = rotate(*chevron[1], angle)
        c = rotate(*chevron[2], angle)
        ax, ay = to_px(*a); bx, by = to_px(*b); cx, cy = to_px(*c)
        draw.line([(ax, ay), (bx, by)], fill=stroke_color, width=sw_i)
        draw.line([(bx, by), (cx, cy)], fill=stroke_color, width=sw_i)
        for px, py in ((ax, ay), (bx, by), (cx, cy)):
            draw.ellipse([px - rr, py - rr, px + rr, py + rr], fill=stroke_color)

    br = body_radius_svg * scale
    draw.ellipse(
        [center_x - br, center_y - br, center_x + br, center_y + br],
        fill=body_color
    )


# ═══ Mixed text rendering (Ar + a-italic + cne) ═══════════════
def draw_wordmark_aracne(draw, x_start, baseline_y, cap_height_px, fill, weight=500):
    """Disegna 'Aracne' con 'a' centrale in corsivo. Ritorna la larghezza totale."""
    # size tale che cap_height in pixels = cap_height_px
    # cap_ratio di Lora = 73/100 = 0.73
    size = round(cap_height_px / 0.73)
    f_reg = load_lora(LORA_REG, size, weight)
    f_ita = load_lora(LORA_ITA, size, weight)
    segments = [("Ar", f_reg), ("a", f_ita), ("cne", f_reg)]
    x = x_start
    for text, fnt in segments:
        draw.text((x, baseline_y), text, font=fnt, fill=fill, anchor="ls")
        x += fnt.getlength(text)
    return x - x_start


def measure_wordmark_width(cap_height_px, weight=500):
    size = round(cap_height_px / 0.73)
    f_reg = load_lora(LORA_REG, size, weight)
    f_ita = load_lora(LORA_ITA, size, weight)
    return (f_reg.getlength("Ar") + f_ita.getlength("a") + f_reg.getlength("cne"))


def draw_tracked_caps(draw, text, cap_height_px, x_start, baseline_y, fill,
                       tracking_em=0.22, weight=500):
    """Disegna maiuscoletto tracked. Ritorna larghezza totale."""
    size = round(cap_height_px / 0.73)
    f = load_lora(LORA_REG, size, weight)
    tracking_px = tracking_em * size
    x = x_start
    last_ch_advance = 0
    for i, ch in enumerate(text):
        draw.text((x, baseline_y), ch, font=f, fill=fill, anchor="ls")
        last_ch_advance = f.getlength(ch)
        x += last_ch_advance + (tracking_px if i < len(text) - 1 else 0)
    return x - x_start


def measure_tracked_caps(text, cap_height_px, tracking_em=0.22, weight=500):
    size = round(cap_height_px / 0.73)
    f = load_lora(LORA_REG, size, weight)
    tracking_px = tracking_em * size
    w = sum(f.getlength(ch) for ch in text)
    w += tracking_px * (len(text) - 1)
    return w


# ═══ Lockup compositions ══════════════════════════════════════
def lockup_horizontal(output_w, ss=3, tagline=None,
                      stroke_color=INK, body_color=RUBRIC, bg=None,
                      text_color=INK, tagline_color=None):
    """
    Render lockup orizzontale: marchio + "Aracne" (+ eventuale tagline sotto).
    output_w: larghezza finale in px.
    ss: supersample factor per l'antialiasing del marchio.
    """
    # --- Definizione proporzioni in unità di lavoro (uguali a pixel finali) ---
    # Impostiamo l'altezza canonica del lockup a 1 unità, tutto in rapporti.
    # Dopo calibro all'output_w target.
    mark_d_u = 1.0                              # diametro marchio = 1 unità
    cap_h_u = 0.58                              # cap height wordmark
    spacing_u = 0.30                            # gap marchio→testo
    # Misuro la larghezza del wordmark in unità di lavoro
    # Renderizzando a una dim. pilota e scalando
    pilot_cap = 100
    wordmark_w_pilot = measure_wordmark_width(pilot_cap)
    wordmark_u = wordmark_w_pilot * (cap_h_u / pilot_cap)

    content_w_u = mark_d_u + spacing_u + wordmark_u
    # padding laterale/verticale (aria)
    pad_h_u = 0.12
    pad_v_u = 0.14
    canvas_w_u = content_w_u + 2 * pad_h_u
    canvas_h_u = mark_d_u + 2 * pad_v_u

    if tagline:
        tagline_cap_u = 0.085                  # piccola, allineata sotto "Aracne"
        tagline_tracking = 0.32
        tagline_pilot = measure_tracked_caps(tagline, 100, tagline_tracking)
        tagline_w_u = tagline_pilot * (tagline_cap_u / 100)
        tagline_gap_u = 0.08                    # gap verticale wordmark→tagline
        canvas_h_u = mark_d_u + 2 * pad_v_u + tagline_gap_u + tagline_cap_u

    # --- scaling a pixel finali ---
    ratio = canvas_h_u / canvas_w_u
    W = output_w
    H = round(W * ratio)
    u = W / canvas_w_u  # unit → px

    # supersampling
    Ws, Hs = W * ss, H * ss
    us = u * ss

    bg_color = bg if bg else (0, 0, 0, 0)
    img = Image.new("RGBA", (Ws, Hs), bg_color)
    draw = ImageDraw.Draw(img)

    # --- marchio ---
    mark_cx = (pad_h_u + mark_d_u / 2) * us
    mark_cy = canvas_h_u / 2 * us if not tagline else (pad_v_u + mark_d_u / 2) * us
    mark_d_px = mark_d_u * us
    draw_mark_on(
        draw, mark_cx, mark_cy, mark_d_px,
        stroke_color=stroke_color, body_color=body_color,
    )

    # --- wordmark ---
    text_x = (pad_h_u + mark_d_u + spacing_u) * us
    cap_h_px = cap_h_u * us
    # baseline allineata all'asse ottico del marchio
    baseline_y = mark_cy + cap_h_px / 2
    draw_wordmark_aracne(draw, text_x, baseline_y, cap_h_px, fill=text_color)

    # --- tagline opzionale ---
    if tagline:
        t_cap_h_px = tagline_cap_u * us
        t_color = tagline_color if tagline_color else text_color
        t_gap_px = tagline_gap_u * us
        t_baseline = baseline_y + t_gap_px + t_cap_h_px
        # tagline allineata all'x del wordmark
        draw_tracked_caps(
            draw, tagline, t_cap_h_px, text_x, t_baseline,
            fill=t_color, tracking_em=0.32
        )

    return img.resize((W, H), Image.LANCZOS)


def lockup_vertical(output_w, ss=3,
                    stroke_color=INK, body_color=RUBRIC, bg=None,
                    text_color=INK):
    """Lockup verticale: marchio in alto, 'Aracne' sotto centrato.
    Il marchio è in outline (peso ottico leggero), il wordmark Lora in pieno
    (peso ottico pesante). Compenso con cap-height piccolo (0.18 × diametro)."""
    mark_d_u = 1.0
    cap_h_u = 0.18
    spacing_vert_u = 0.16
    pilot_cap = 100
    wordmark_w_pilot = measure_wordmark_width(pilot_cap)
    wordmark_u = wordmark_w_pilot * (cap_h_u / pilot_cap)

    # canvas: si adatta al più largo tra marchio e testo
    content_w_u = max(mark_d_u, wordmark_u)
    pad_h_u = 0.14
    pad_v_u = 0.14
    canvas_w_u = content_w_u + 2 * pad_h_u
    canvas_h_u = mark_d_u + spacing_vert_u + cap_h_u + 2 * pad_v_u

    ratio = canvas_h_u / canvas_w_u
    W = output_w
    H = round(W * ratio)
    u = W / canvas_w_u
    Ws, Hs = W * ss, H * ss
    us = u * ss

    bg_color = bg if bg else (0, 0, 0, 0)
    img = Image.new("RGBA", (Ws, Hs), bg_color)
    draw = ImageDraw.Draw(img)

    # marchio centrato orizzontalmente
    mark_cx = (canvas_w_u / 2) * us
    mark_cy = (pad_v_u + mark_d_u / 2) * us
    mark_d_px = mark_d_u * us
    draw_mark_on(draw, mark_cx, mark_cy, mark_d_px,
                 stroke_color=stroke_color, body_color=body_color)

    # wordmark centrato orizzontalmente sotto
    cap_h_px = cap_h_u * us
    text_baseline = mark_cy + (mark_d_u / 2 + spacing_vert_u) * us + cap_h_px
    wordmark_w_px = wordmark_u * us
    text_x = (canvas_w_u / 2) * us - wordmark_w_px / 2
    draw_wordmark_aracne(draw, text_x, text_baseline, cap_h_px, fill=text_color)

    return img.resize((W, H), Image.LANCZOS)


def app_icon_named(size, ss=2):
    """App icon quadrato: marchio grande + 'ARACNE' tracked sotto, fondo inchiostro."""
    # Proporzioni in unità di lavoro (canvas = 1.0 × 1.0)
    mark_d_u = 0.58           # marchio grande ma non a bordo
    cap_h_u = 0.082           # maiuscoletto tracked
    tracking = 0.32

    # misura larghezza del testo "ARACNE" tracked
    pilot = measure_tracked_caps("ARACNE", 100, tracking)
    text_w_u = pilot * (cap_h_u / 100)

    # layout verticale: top_pad + mark + gap + cap + bottom_pad = 1.0
    # top_pad ≈ bottom_pad per simmetria ottica
    top_pad_u = 0.13
    gap_u = 0.08

    Ws = size * ss
    img = Image.new("RGBA", (Ws, Ws), INK)
    draw = ImageDraw.Draw(img)

    u = Ws  # canvas = 1 unit = Ws pixels

    mark_cx = 0.5 * u
    mark_cy = (top_pad_u + mark_d_u / 2) * u
    mark_d_px = mark_d_u * u
    draw_mark_on(
        draw, mark_cx, mark_cy, mark_d_px,
        stroke_color=PARCHMENT, body_color=RUBRIC_LIGHT,
    )

    cap_h_px = cap_h_u * u
    text_baseline = (top_pad_u + mark_d_u + gap_u) * u + cap_h_px
    text_w_px = text_w_u * u
    text_x = 0.5 * u - text_w_px / 2
    draw_tracked_caps(
        draw, "ARACNE", cap_h_px, text_x, text_baseline,
        fill=PARCHMENT, tracking_em=tracking
    )

    return img.resize((size, size), Image.LANCZOS).convert("RGB")


# ═══ SVG generators ═══════════════════════════════════════════
SVG_FONT_STYLE = """    <style>
      @import url('https://fonts.googleapis.com/css2?family=Lora:ital,wght@0,500;1,500&display=swap');
      .wm { font-family: 'Lora', 'Iowan Old Style', Georgia, serif;
            font-weight: 500; fill: __TEXT__; }
      .wm-i { font-style: italic; }
      .tag { font-family: 'JetBrains Mono', 'SF Mono', monospace;
             font-size: 14px; letter-spacing: 0.32em;
             text-transform: uppercase; fill: __TAG__; }
    </style>"""


def svg_mark_group(cx, cy, diameter, stroke=INK_HEX, body=RUBRIC_HEX, body_hex=None):
    """Ritorna un gruppo SVG del marchio alla posizione/diametro indicati."""
    scale = diameter / 200.0
    body_color = body_hex if body_hex else body
    uses = "\n        ".join(
        f'<use href="#aracne-leg" transform="rotate({a})"/>'
        for a in (0, 45, 90, 135, 180, 225, 270, 315)
    )
    return f"""  <g transform="translate({cx}, {cy}) scale({scale})">
      <circle cx="0" cy="0" r="92" fill="none" stroke="{stroke}" stroke-width="1.3"/>
      <g stroke="{stroke}" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" fill="none">
        {uses}
      </g>
      <circle cx="0" cy="0" r="6" fill="{body_color}"/>
    </g>"""


def svg_defs():
    return """  <defs>
    <g id="aracne-leg">
      <polyline points="76,-17.55 16,0 76,17.55"/>
    </g>
  </defs>"""


def make_svg_horizontal(tagline=None, out_path=None):
    """Genera SVG lockup orizzontale."""
    # unità SVG = scala comoda: canvas height = 200
    mark_d = 200
    cap_h = 116
    spacing = 60
    pad_h = 24
    pad_v = 28

    # misura wordmark (allineata al PNG renderer)
    wm_w = measure_wordmark_width(cap_h)
    content_w = mark_d + spacing + wm_w
    H = mark_d + 2 * pad_v
    W = content_w + 2 * pad_h

    mark_cx = pad_h + mark_d / 2
    mark_cy = H / 2
    text_x = pad_h + mark_d + spacing
    baseline_y = mark_cy + cap_h / 2

    # se c'è tagline, estendiamo il canvas
    tag_gap = 16
    tag_cap = 17
    if tagline:
        H = pad_v + mark_d + tag_gap + tag_cap + pad_v
        mark_cy = pad_v + mark_d / 2
        baseline_y = mark_cy + cap_h / 2
        tag_baseline = baseline_y + tag_gap + tag_cap

    style = SVG_FONT_STYLE.replace("__TEXT__", INK_HEX).replace("__TAG__", INK_HEX)
    mark_svg = svg_mark_group(mark_cx, mark_cy, mark_d)
    defs = svg_defs()

    font_size = round(cap_h / 0.73)

    tagline_el = ""
    if tagline:
        tagline_el = (
            f'<text x="{text_x}" y="{tag_baseline}" class="tag">{tagline}</text>'
        )

    svg = f"""<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W:.1f} {H:.1f}" width="{W:.0f}" height="{H:.0f}">
{style}
{defs}
{mark_svg}
  <text x="{text_x:.1f}" y="{baseline_y:.1f}" class="wm"
        font-size="{font_size}" letter-spacing="-0.005em">Ar<tspan class="wm-i">a</tspan>cne</text>
  {tagline_el}
</svg>
"""
    if out_path:
        Path(out_path).write_text(svg)
    return svg


def make_svg_vertical(out_path=None):
    mark_d = 240           # marchio dominante
    cap_h = 43             # cap-height ≈ 0.18 del marchio
    gap_v = 38
    pad_h = 40
    pad_v = 36
    wm_w = measure_wordmark_width(cap_h)
    content_w = max(mark_d, wm_w)
    W = content_w + 2 * pad_h
    H = pad_v + mark_d + gap_v + cap_h + pad_v

    mark_cx = W / 2
    mark_cy = pad_v + mark_d / 2
    baseline_y = pad_v + mark_d + gap_v + cap_h
    text_x = mark_cx - wm_w / 2

    style = SVG_FONT_STYLE.replace("__TEXT__", INK_HEX).replace("__TAG__", INK_HEX)
    mark_svg = svg_mark_group(mark_cx, mark_cy, mark_d)
    defs = svg_defs()
    font_size = round(cap_h / 0.73)

    svg = f"""<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W:.1f} {H:.1f}" width="{W:.0f}" height="{H:.0f}">
{style}
{defs}
{mark_svg}
  <text x="{text_x:.1f}" y="{baseline_y:.1f}" class="wm"
        font-size="{font_size}" letter-spacing="-0.005em">Ar<tspan class="wm-i">a</tspan>cne</text>
</svg>
"""
    if out_path:
        Path(out_path).write_text(svg)
    return svg


# ═══ Main ═════════════════════════════════════════════════════
if __name__ == "__main__":
    out = Path("/mnt/user-data/outputs/aracne-icons")
    (out / "lockup").mkdir(parents=True, exist_ok=True)
    (out / "app-icon-named").mkdir(parents=True, exist_ok=True)

    # --- PNG horizontal ---
    print("Generating horizontal lockups…")
    for w in [512, 1024, 2048]:
        img = lockup_horizontal(w)
        img.save(out / "lockup" / f"aracne-lockup-horizontal-{w}.png", optimize=True)
        print(f"  ✓ horizontal {w}")
        # Versione inversa (pergamena su ink) per usi su scuro
        img_inv = lockup_horizontal(
            w, stroke_color=PARCHMENT, body_color=RUBRIC_LIGHT,
            bg=INK, text_color=PARCHMENT,
        )
        img_inv.convert("RGB").save(
            out / "lockup" / f"aracne-lockup-horizontal-{w}-inverse.png", optimize=True
        )
        print(f"  ✓ horizontal {w} inverse")

    # --- PNG vertical ---
    print("Generating vertical lockups…")
    for w in [512, 1024, 2048]:
        img = lockup_vertical(w)
        img.save(out / "lockup" / f"aracne-lockup-vertical-{w}.png", optimize=True)
        print(f"  ✓ vertical {w}")

    # --- PNG with tagline ---
    print("Generating tagline lockups…")
    for w in [1024, 2048]:
        img = lockup_horizontal(w, tagline="TEI XML encoder")
        img.save(out / "lockup" / f"aracne-lockup-tagline-{w}.png", optimize=True)
        print(f"  ✓ tagline {w}")

    # --- PNG named app icons ---
    print("Generating named app icons…")
    for s in [256, 512, 1024]:
        img = app_icon_named(s)
        img.save(out / "app-icon-named" / f"aracne-named-{s}.png", optimize=True)
        print(f"  ✓ app-icon-named {s}")

    # --- SVG lockup (vivi, testo editabile) ---
    print("Writing SVG lockups…")
    make_svg_horizontal(out_path=out / "lockup" / "aracne-lockup-horizontal.svg")
    make_svg_horizontal(
        tagline="TEI XML encoder",
        out_path=out / "lockup" / "aracne-lockup-tagline.svg",
    )
    make_svg_vertical(out_path=out / "lockup" / "aracne-lockup-vertical.svg")
    print("  ✓ 3 SVG files")

    print("\nDone.")
