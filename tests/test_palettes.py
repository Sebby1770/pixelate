"""Tests for palette registry and lookup."""

import pytest

from pixelate.palettes import PALETTES, get_palette, list_palettes


def test_all_palettes_have_at_least_two_colors():
    for name, palette in PALETTES.items():
        assert len(palette) >= 2, f"{name} has too few colors"


def test_all_palette_colors_are_valid_rgb():
    for name, palette in PALETTES.items():
        for color in palette:
            assert len(color) == 3, f"{name} has malformed color {color}"
            for component in color:
                assert 0 <= component <= 255, f"{name} color {color} out of range"


def test_get_palette_is_case_insensitive():
    assert get_palette("GAMEBOY") == get_palette("gameboy")
    assert get_palette("  Pico8 ") == get_palette("pico8")


def test_get_palette_unknown_raises():
    with pytest.raises(KeyError):
        get_palette("not-a-real-palette")


def test_list_palettes_returns_counts():
    counts = list_palettes()
    assert isinstance(counts, dict)
    assert counts["gameboy"] == 4
    assert counts["pico8"] == 16


def test_gameboy_dmg_is_authentic():
    palette = get_palette("gameboy")
    # The classic DMG palette has the lightest yellow-green
    assert (155, 188, 15) in palette
