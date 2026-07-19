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


def test_new_palettes_present():
    for name in ("ega", "msx", "vaporwave", "db16", "sms", "master-system"):
        assert name in PALETTES


def test_v21_palettes_present():
    for name in (
        "gameboy-color",
        "gbc",
        "vic20",
        "vic-20",
        "atari2600",
        "atari-2600",
        "tokyo-night",
        "tokyo",
        "cyberpunk",
    ):
        assert name in PALETTES


def test_ega_has_16_colors():
    assert len(get_palette("ega")) == 16


def test_db16_has_16_colors():
    assert len(get_palette("db16")) == 16


def test_sms_alias_matches_master_system():
    assert get_palette("sms") == get_palette("master-system")


def test_vaporwave_has_colors():
    assert len(get_palette("vaporwave")) >= 8


def test_gbc_alias_matches_gameboy_color():
    assert get_palette("gbc") == get_palette("gameboy-color")
    assert len(get_palette("gameboy-color")) == 32


def test_vic20_has_16_colors():
    assert len(get_palette("vic20")) == 16
    assert get_palette("vic20") == get_palette("vic-20")


def test_atari2600_has_colors():
    assert len(get_palette("atari2600")) >= 16
    assert get_palette("atari2600") == get_palette("atari-2600")


def test_tokyo_night_and_cyberpunk():
    assert len(get_palette("tokyo-night")) == 16
    assert get_palette("tokyo") == get_palette("tokyo-night")
    assert len(get_palette("cyberpunk")) == 16
