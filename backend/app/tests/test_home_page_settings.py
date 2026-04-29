"""Unit tests for the home-page layout helpers.

Targets the two small pure helpers introduced for the Home page tab:

- ``_home_grid_template`` reads ``theme_config`` keys and returns an
  inline ``grid-template-columns`` string. Defaults match the old
  hard-coded CSS (30/70, 70/30, 20/60/20) so a site without any new
  keys looks identical to the pre-feature rendering.
- ``_overlay_rgba`` converts ``(hex, alpha)`` into a CSS ``rgba(...)``
  string, or an empty string when the overlay should be disabled.
- ``home_body_class`` maps the width setting to the ``<body>`` class
  the index renderer attaches.
"""

from __future__ import annotations

from app.services.websites import (
    _home_grid_template,
    _overlay_rgba,
    home_body_class,
)


# ── _home_grid_template ──────────────────────────────────────────────────────


def test_grid_template_two_default() -> None:
    """New unified ``two`` layout: left-column % default is 30."""
    assert _home_grid_template("two", {}) == "30% 70%"


def test_grid_template_two_reads_overrides() -> None:
    assert _home_grid_template("two", {"home_cols_two_left": "55"}) == "55% 45%"


def test_grid_template_two_left_default() -> None:
    """Legacy ``two_left`` still resolves — old sites keep rendering
    until the Designer re-saves and the frontend normaliser converts
    storage to the new ``two`` shape."""
    assert _home_grid_template("two_left", {}) == "30% 70%"


def test_grid_template_two_right_default() -> None:
    """Legacy ``two_right`` still resolves."""
    assert _home_grid_template("two_right", {}) == "70% 30%"


def test_grid_template_three_default() -> None:
    assert _home_grid_template("three", {}) == "20% 60% 20%"


def test_grid_template_reads_overrides() -> None:
    theme = {"home_cols_two_left": "40", "home_cols_two_right": "65"}
    assert _home_grid_template("two_left", theme) == "40% 60%"
    assert _home_grid_template("two_right", theme) == "65% 35%"


def test_grid_template_clamps_out_of_range() -> None:
    assert _home_grid_template("two_left", {"home_cols_two_left": "200"}) == "95% 5%"
    assert _home_grid_template("two_left", {"home_cols_two_left": "-10"}) == "5% 95%"


def test_grid_template_three_column_sum_is_100() -> None:
    out = _home_grid_template(
        "three",
        {"home_cols_three_left": "25", "home_cols_three_right": "25"},
    )
    assert out == "25% 50% 25%"


def test_grid_template_three_column_over_cap_is_scaled() -> None:
    # 60 + 60 exceeds the 90% cap → both scaled to fit, centre gets 10%.
    out = _home_grid_template(
        "three",
        {"home_cols_three_left": "60", "home_cols_three_right": "60"},
    )
    # 60+60=120, scale = 90/120 = 0.75 → 45 + 45 = 90, centre = 10.
    # Output order is left / centre / right (matches the CSS grid
    # painted left-to-right), not left / right / centre.
    assert out == "45% 10% 45%"


def test_grid_template_single_and_unknown_empty() -> None:
    """No inline style is emitted for single-column or unknown layouts."""
    assert _home_grid_template("single", {}) == ""
    assert _home_grid_template("whatever", {}) == ""


def test_grid_template_non_numeric_falls_back_to_default() -> None:
    assert _home_grid_template(
        "two_left", {"home_cols_two_left": "abc"}
    ) == "30% 70%"


# ── _overlay_rgba ────────────────────────────────────────────────────────────


def test_overlay_six_digit_hex_with_alpha() -> None:
    assert _overlay_rgba("#336699", 0.5) == "rgba(51,102,153,0.50)"


def test_overlay_three_digit_hex_is_expanded() -> None:
    assert _overlay_rgba("#369", 0.25) == "rgba(51,102,153,0.25)"


def test_overlay_without_leading_hash() -> None:
    assert _overlay_rgba("000000", 0.8) == "rgba(0,0,0,0.80)"


def test_overlay_alpha_none_defaults_to_04() -> None:
    assert _overlay_rgba("#000000", None) == "rgba(0,0,0,0.40)"


def test_overlay_alpha_clamped_to_1() -> None:
    assert _overlay_rgba("#000000", 5) == "rgba(0,0,0,1.00)"


def test_overlay_disabled_when_alpha_zero_or_less() -> None:
    assert _overlay_rgba("#000000", 0) == ""
    assert _overlay_rgba("#000000", -0.5) == ""


def test_overlay_invalid_color_returns_empty() -> None:
    assert _overlay_rgba("not-a-hex", 0.5) == ""
    assert _overlay_rgba("", 0.5) == ""


# ── home_body_class ──────────────────────────────────────────────────────────


def test_body_class_standard_is_empty() -> None:
    assert home_body_class({}) == ""
    assert home_body_class({"home_width": "standard"}) == ""
    assert home_body_class(None) == ""


def test_body_class_fullscreen() -> None:
    assert home_body_class({"home_width": "fullscreen"}) == "home-full"


def test_body_class_cover() -> None:
    assert home_body_class({"home_width": "cover"}) == "home-cover"


def test_body_class_unknown_falls_back_to_standard() -> None:
    """An unknown value (e.g. forward-compatible new mode set by a
    future build) just renders as the default bounded layout
    instead of crashing."""
    assert home_body_class({"home_width": "martian"}) == ""
