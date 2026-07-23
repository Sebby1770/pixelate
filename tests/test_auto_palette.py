"""Tests for auto palette extraction and --palette auto pipeline."""

from pathlib import Path

import numpy as np
from PIL import Image

from pixelate.core import extract_palette, pixelate_image
from pixelate.palettes import get_palette

ASSETS = Path(__file__).resolve().parent.parent / "assets"
SOURCE = ASSETS / "source.png"


def _make_test_image(size=(64, 64)):
    arr = np.zeros((size[1], size[0], 3), dtype=np.uint8)
    arr[: size[1] // 2, : size[0] // 2] = (200, 50, 50)
    arr[: size[1] // 2, size[0] // 2 :] = (50, 200, 50)
    arr[size[1] // 2 :, : size[0] // 2] = (50, 50, 200)
    arr[size[1] // 2 :, size[0] // 2 :] = (220, 220, 50)
    return Image.fromarray(arr, mode="RGB")


def test_extract_palette_kmeans_count():
    src = _make_test_image()
    pal = extract_palette(src, n=4, method="kmeans")
    assert 2 <= len(pal) <= 4
    for c in pal:
        assert len(c) == 3
        assert all(0 <= v <= 255 for v in c)


def test_extract_palette_median_cut_count():
    src = _make_test_image()
    pal = extract_palette(src, n=4, method="median-cut")
    assert 2 <= len(pal) <= 4


def test_extract_palette_from_few_unique():
    img = Image.new("RGB", (16, 16), (10, 20, 30))
    pal = extract_palette(img, n=8, method="kmeans")
    assert len(pal) == 1
    assert pal[0] == (10, 20, 30)


def test_pixelate_auto_palette():
    src = _make_test_image()
    out = pixelate_image(
        src,
        palette="auto",
        colors=4,
        pixel_size=32,
        upscale=1,
        dither="none",
    )
    assert isinstance(out, Image.Image)
    arr = np.array(out)
    unique = {tuple(c) for c in arr.reshape(-1, 3)}
    assert len(unique) <= 4


def test_pixelate_auto_median_cut():
    src = _make_test_image()
    out = pixelate_image(
        src,
        palette="auto",
        colors=3,
        extract_method="median-cut",
        pixel_size=24,
        upscale=1,
        dither="none",
    )
    unique = {tuple(c) for c in np.array(out).reshape(-1, 3)}
    assert len(unique) <= 3


def test_extract_palette_from_asset_if_present():
    if not SOURCE.is_file():
        return
    pal = extract_palette(SOURCE, n=8, method="kmeans")
    assert 2 <= len(pal) <= 8


def test_auto_still_uses_only_extracted_colors():
    src = _make_test_image()
    pal = extract_palette(src, n=4, method="kmeans")
    out = pixelate_image(src, palette=pal, pixel_size=32, upscale=1, dither="none")
    unique = {tuple(c) for c in np.array(out).reshape(-1, 3)}
    assert unique.issubset(set(pal))


def test_builtin_palette_still_works():
    src = _make_test_image()
    out = pixelate_image(src, palette="gameboy", pixel_size=16, upscale=1, dither="none")
    unique = {tuple(c) for c in np.array(out).reshape(-1, 3)}
    assert unique.issubset(set(get_palette("gameboy")))
