/**
 * Colour helpers — WCAG 2.1 relative luminance + text-colour picking.
 *
 * Used by the public header / public views to pick a readable text colour
 * on top of the admin-configured navbar background, without forcing the
 * admin to configure a second colour. A custom CSS override remains the
 * escape hatch if a specific brand wants a tinted text colour.
 */

/** Hex that parses as a valid #RRGGBB colour. Case-insensitive. */
const HEX_RE = /^#?([0-9a-f]{6})$/i;

/** Tailwind `gray-900` — the project's dark text on light surfaces. */
const DARK_TEXT = "#111827";
const LIGHT_TEXT = "#ffffff";

function hexToRgb(hex: string): [number, number, number] | null {
  const m = HEX_RE.exec(hex.trim());
  if (!m) return null;
  const n = parseInt(m[1], 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}

/**
 * WCAG 2.1 relative luminance of an sRGB colour in [0, 1].
 * https://www.w3.org/TR/WCAG21/#dfn-relative-luminance
 */
function relativeLuminance(rgb: [number, number, number]): number {
  const [r, g, b] = rgb.map((v) => {
    const c = v / 255;
    return c <= 0.03928 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4);
  }) as [number, number, number];
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

/** Pre-computed luminance for the two candidate text colours. */
const LUM_LIGHT_TEXT = relativeLuminance(hexToRgb(LIGHT_TEXT)!);
const LUM_DARK_TEXT = relativeLuminance(hexToRgb(DARK_TEXT)!);

/** WCAG contrast ratio in [1, 21]. Higher = more readable. */
function contrastRatio(lumA: number, lumB: number): number {
  const [hi, lo] = lumA > lumB ? [lumA, lumB] : [lumB, lumA];
  return (hi + 0.05) / (lo + 0.05);
}

/**
 * Pick the text colour that best contrasts with *bgHex*, choosing between
 * pure white (``#ffffff``) and the project's dark text (``#111827``).
 *
 * Falls back to white when the input cannot be parsed — matches the
 * previous hard-coded behaviour of the public header.
 */
export function contrastingTextColor(bgHex: string | null | undefined): string {
  if (!bgHex) return LIGHT_TEXT;
  const rgb = hexToRgb(bgHex);
  if (!rgb) return LIGHT_TEXT;
  const bgLum = relativeLuminance(rgb);
  return contrastRatio(bgLum, LUM_LIGHT_TEXT) >= contrastRatio(bgLum, LUM_DARK_TEXT)
    ? LIGHT_TEXT
    : DARK_TEXT;
}
