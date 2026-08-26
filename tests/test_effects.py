"""Tests for scanlines, CRT, and phosphor post-effects."""

import numpy as np
from PIL import Image

from pixelate.effects import apply_crt, apply_phosphor, apply_scanlines


def test_scanlines_darken_scanline_rows():
    img = Image.new("RGB", (8, 8), (200, 200, 200))
    out = apply_scanlines(img, intensity=0.35, gap=2)
    arr = np.array(out)
    base = np.array(img)
    # gap=2 darkens rows 0, 2, 4, ...
    assert arr[0, 0, 0] < base[0, 0, 0]
    assert arr[2, 3, 1] < base[2, 3, 1]
    # odd rows unchanged
    assert int(arr[1, 0, 0]) == int(base[1, 0, 0])
    assert out.size == img.size


def test_crt_size_unchanged():
    img = Image.new("RGB", (32, 24), (100, 80, 60))
    out = apply_crt(img)
    assert out.size == img.size
    assert isinstance(out, Image.Image)


def test_crt_then_scanlines_keeps_dark_rows_darker():
    """Scanline rows stay darker when bloom runs first (not after)."""
    img = Image.new("RGB", (32, 32), (200, 200, 200))
    crt_then_scan = apply_scanlines(apply_crt(img), intensity=0.35, gap=2)
    scan_then_crt = apply_crt(apply_scanlines(img, intensity=0.35, gap=2))
    a = np.array(crt_then_scan, dtype=np.float32)
    b = np.array(scan_then_crt, dtype=np.float32)
    # gap=2 darkens rows 0, 2, 4, ...
    assert float(a[0].mean()) < float(b[0].mean())
    assert float(a[2].mean()) < float(b[2].mean())


def test_apply_phosphor_keeps_size_and_varies_pixels():
    img = Image.new("RGB", (9, 6), (200, 180, 160))
    out = apply_phosphor(img, strength=0.35)
    assert out.size == img.size
    arr = np.array(out)
    assert not np.all(arr == arr[0, 0])
    # RGB column stripes: neighbouring columns differ
    assert not np.array_equal(arr[:, 0], arr[:, 1])
