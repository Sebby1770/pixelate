"""Tests for scanlines and CRT post-effects."""

import numpy as np
from PIL import Image

from pixelate.effects import apply_crt, apply_scanlines


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
