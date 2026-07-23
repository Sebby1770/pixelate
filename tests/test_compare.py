"""Tests for multi-palette compare collage."""

from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from pixelate.core import compare_palettes, save_image

ASSETS = Path(__file__).resolve().parent.parent / "assets"
SOURCE = ASSETS / "source.png"


def _make_test_image(size=(48, 48)):
    arr = np.zeros((size[1], size[0], 3), dtype=np.uint8)
    arr[: size[1] // 2, : size[0] // 2] = (200, 50, 50)
    arr[: size[1] // 2, size[0] // 2 :] = (50, 200, 50)
    arr[size[1] // 2 :, : size[0] // 2] = (50, 50, 200)
    arr[size[1] // 2 :, size[0] // 2 :] = (220, 220, 50)
    return Image.fromarray(arr, mode="RGB")


def test_compare_palettes_returns_image():
    src = _make_test_image()
    collage = compare_palettes(
        src,
        ["gameboy", "nes", "c64"],
        pixel_size=24,
        upscale=1,
        dither="none",
    )
    assert isinstance(collage, Image.Image)
    # Should be larger than a single tile
    assert collage.size[0] > 24
    assert collage.size[1] > 24


def test_compare_palettes_four_default_style():
    src = _make_test_image()
    collage = compare_palettes(
        src,
        ["gameboy", "nes", "pico8", "c64"],
        pixel_size=20,
        upscale=2,
        dither="none",
        cols=2,
    )
    assert collage.size[0] > 0 and collage.size[1] > 0


def test_compare_palettes_no_label():
    src = _make_test_image()
    with_label = compare_palettes(
        src, ["gameboy", "cga"], pixel_size=16, upscale=1, label=True, dither="none"
    )
    no_label = compare_palettes(
        src, ["gameboy", "cga"], pixel_size=16, upscale=1, label=False, dither="none"
    )
    # With labels the canvas is taller (or equal if padding dominates)
    assert with_label.size[1] >= no_label.size[1]


def test_compare_palettes_empty_raises():
    src = _make_test_image()
    with pytest.raises(ValueError):
        compare_palettes(src, [])


def test_compare_saves(tmp_path: Path):
    src = _make_test_image()
    collage = compare_palettes(
        src, ["gameboy", "pico8"], pixel_size=16, upscale=1, dither="none"
    )
    dest = tmp_path / "compare.png"
    save_image(collage, dest)
    assert dest.is_file()
    loaded = Image.open(dest)
    assert loaded.size == collage.size


def test_compare_with_asset_if_present():
    if not SOURCE.is_file():
        return
    collage = compare_palettes(
        SOURCE,
        ["gameboy", "nes"],
        pixel_size=32,
        upscale=1,
        dither="none",
    )
    assert isinstance(collage, Image.Image)
