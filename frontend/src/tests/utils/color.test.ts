import { describe, it, expect } from "vitest";
import { contrastingTextColor } from "@/utils/color";

const LIGHT = "#ffffff";
const DARK = "#111827";

describe("contrastingTextColor", () => {
  it("returns dark text on a white background", () => {
    expect(contrastingTextColor("#ffffff")).toBe(DARK);
  });

  it("returns light text on a black background", () => {
    expect(contrastingTextColor("#000000")).toBe(LIGHT);
  });

  it("returns light text on the default brand blue", () => {
    // #1e40af is Tailwind blue-800 — pure white wins by a wide margin.
    expect(contrastingTextColor("#1e40af")).toBe(LIGHT);
  });

  it("returns dark text on a parchment background", () => {
    // #ece2c8 is the kit's "pergamena" token — clearly on the light side.
    expect(contrastingTextColor("#ece2c8")).toBe(DARK);
  });

  it("returns light text on the kit's inchiostro", () => {
    expect(contrastingTextColor("#131a2a")).toBe(LIGHT);
  });

  it("tolerates hex without leading #", () => {
    expect(contrastingTextColor("1e40af")).toBe(LIGHT);
  });

  it("tolerates uppercase hex", () => {
    expect(contrastingTextColor("#1E40AF")).toBe(LIGHT);
  });

  it("falls back to light text when the input is not a valid hex", () => {
    expect(contrastingTextColor("")).toBe(LIGHT);
    expect(contrastingTextColor(undefined)).toBe(LIGHT);
    expect(contrastingTextColor("red")).toBe(LIGHT);
    expect(contrastingTextColor("#fff")).toBe(LIGHT); // 3-digit shorthand not accepted
    expect(contrastingTextColor("#zzzzzz")).toBe(LIGHT);
  });

  it("flips at the luminance boundary", () => {
    // A medium-light grey — dark text reads better.
    expect(contrastingTextColor("#cccccc")).toBe(DARK);
    // A medium-dark grey — light text reads better.
    expect(contrastingTextColor("#555555")).toBe(LIGHT);
  });
});
