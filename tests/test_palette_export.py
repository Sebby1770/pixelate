"""Tests for palette-file writers and the new built-in palettes."""

from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from pixelate.core import extract_palette, pixelate_image
from pixelate.palette_io import load_palette_file, save_gpl, save_hex
from pixelate.palettes import PALETTES


def _noisy(seed: int = 0, size: int = 48) -> Image.Image:
    rng = np.random.default_rng(seed)
    return Image.fromarray(rng.integers(0, 256, (size, size, 3), dtype=np.uint8), "RGB")


def test_save_and_reload_gpl_roundtrips(tmp_path: Path):
    colors = extract_palette(_noisy(1), n=10)
    path = save_gpl(tmp_path / "p.gpl", colors, name="Test")
    assert path.exists()
    assert load_palette_file(path) == colors


def test_save_and_reload_hex_roundtrips(tmp_path: Path):
    colors = extract_palette(_noisy(2), n=10)
    path = save_hex(tmp_path / "p.hex", colors)
    assert path.exists()
    assert load_palette_file(path) == colors


@pytest.mark.parametrize("name", ["gamegear", "virtualboy", "amstrad", "teletext", "db32"])
def test_new_palettes_registered_and_render(name):
    assert name in PALETTES
    out = pixelate_image(_noisy(3, size=16), palette=name, pixel_size=16, upscale=1, dither="none")
    assert out.size == (16, 16)
