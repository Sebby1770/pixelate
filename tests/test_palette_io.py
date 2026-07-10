"""Tests for custom palette file loading and registration."""

from pathlib import Path

import pytest

from pixelate.palette_io import (
    load_gpl,
    load_hex,
    load_palette_file,
    register_palette,
    register_palette_file,
)
from pixelate.palettes import PALETTES, get_palette


@pytest.fixture
def hex_file(tmp_path: Path) -> Path:
    p = tmp_path / "custom.hex"
    p.write_text(
        "# comment line\n"
        "FF0000\n"
        "#00FF00\n"
        "0000FF\n"
        "; ignored\n"
        "// also ignored\n",
        encoding="utf-8",
    )
    return p


@pytest.fixture
def gpl_file(tmp_path: Path) -> Path:
    p = tmp_path / "custom.gpl"
    p.write_text(
        "GIMP Palette\n"
        "Name: Test Retro\n"
        "Columns: 4\n"
        "#\n"
        "  0   0   0 Black\n"
        "255   0   0 Red\n"
        "  0 255   0 Green\n"
        "  0   0 255 Blue\n",
        encoding="utf-8",
    )
    return p


def test_load_hex(hex_file: Path):
    colors = load_hex(hex_file)
    assert colors == ((255, 0, 0), (0, 255, 0), (0, 0, 255))


def test_load_gpl(gpl_file: Path):
    name, colors = load_gpl(gpl_file)
    assert name == "Test Retro"
    assert colors == ((0, 0, 0), (255, 0, 0), (0, 255, 0), (0, 0, 255))


def test_load_palette_file_hex(hex_file: Path):
    assert load_palette_file(hex_file) == ((255, 0, 0), (0, 255, 0), (0, 0, 255))


def test_load_palette_file_gpl(gpl_file: Path):
    colors = load_palette_file(gpl_file)
    assert len(colors) == 4
    assert colors[0] == (0, 0, 0)


def test_load_palette_file_missing(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        load_palette_file(tmp_path / "nope.hex")


def test_load_palette_file_empty_hex(tmp_path: Path):
    p = tmp_path / "empty.hex"
    p.write_text("# only comments\n", encoding="utf-8")
    with pytest.raises(ValueError, match="No colors"):
        load_hex(p)


def test_register_palette():
    name = "_test_register_unique_xyz"
    try:
        register_palette(name, [(10, 20, 30), (40, 50, 60)])
        assert get_palette(name) == ((10, 20, 30), (40, 50, 60))
    finally:
        PALETTES.pop(name, None)


def test_register_palette_file(hex_file: Path):
    name = "_test_file_palette_xyz"
    try:
        register_palette_file(name, hex_file)
        assert len(get_palette(name)) == 3
    finally:
        PALETTES.pop(name, None)


def test_register_palette_empty_raises():
    with pytest.raises(ValueError):
        register_palette("bad", [])


def test_unsupported_extension(tmp_path: Path):
    p = tmp_path / "palette.json"
    p.write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="Unsupported"):
        load_palette_file(p)
