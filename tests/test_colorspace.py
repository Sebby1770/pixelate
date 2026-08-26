"""Tests for CIELAB conversion and nearest-color matching."""

import numpy as np

from pixelate.colorspace import nearest_palette_indices, srgb_to_lab


def test_srgb_to_lab_gray_is_achromatic():
    gray = np.array(
        [[0, 0, 0], [64, 64, 64], [128, 128, 128], [255, 255, 255]],
        dtype=np.uint8,
    )
    lab = srgb_to_lab(gray)
    # L increases with brightness; a/b stay near 0 for neutrals
    assert lab[0, 0] < 1.0
    assert abs(lab[3, 0] - 100.0) < 1.5
    assert lab[0, 0] < lab[1, 0] < lab[2, 0] < lab[3, 0]
    assert np.max(np.abs(lab[:, 1:])) < 1.5


def test_srgb_to_lab_float_0_255_matches_uint8():
    rgb = np.array([[12, 80, 200]], dtype=np.uint8)
    a = srgb_to_lab(rgb)
    b = srgb_to_lab(rgb.astype(np.float64))
    assert np.allclose(a, b, atol=1e-6)


def test_srgb_to_lab_accepts_unit_float():
    white = srgb_to_lab(np.array([[1.0, 1.0, 1.0]], dtype=np.float64))
    assert abs(white[0, 0] - 100.0) < 1.5


def test_nearest_lab_can_differ_from_rgb_on_reddish_pixel():
    """Green-heavy palette: RGB Euclidean vs CIE76 can pick different entries."""
    pixel = np.array([[207, 3, 43]], dtype=np.uint8)
    palette = np.array(
        [
            [96, 162, 47],
            [41, 220, 33],
            [32, 113, 22],
            [90, 161, 56],
            [37, 102, 66],
            [7, 200, 94],
            [168, 190, 11],
            [75, 220, 93],
        ],
        dtype=np.uint8,
    )
    rgb_idx = int(nearest_palette_indices(pixel, palette, space="rgb")[0])
    lab_idx = int(nearest_palette_indices(pixel, palette, space="lab")[0])
    assert rgb_idx != lab_idx


def test_nearest_exact_match():
    pixel = np.array([[10, 20, 30]], dtype=np.uint8)
    palette = np.array([[0, 0, 0], [10, 20, 30], [255, 255, 255]], dtype=np.uint8)
    for space in ("rgb", "lab"):
        idx = nearest_palette_indices(pixel, palette, space=space)
        assert int(idx[0]) == 1
