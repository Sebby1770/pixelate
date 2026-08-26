"""Tests for CIELAB conversion and nearest-color matching."""

import numpy as np

from pixelate.colorspace import ciede2000, lab_to_srgb, nearest_palette_indices, srgb_to_lab


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


def test_lab_to_srgb_gray_is_achromatic():
    lab = np.array(
        [[0.0, 0.0, 0.0], [25.0, 0.0, 0.0], [50.0, 0.0, 0.0], [75.0, 0.0, 0.0], [100.0, 0.0, 0.0]],
        dtype=np.float64,
    )
    rgb = lab_to_srgb(lab)
    assert rgb.dtype == np.float64
    assert rgb.min() >= 0.0 and rgb.max() <= 255.0
    # Neutrals stay gray (R=G=B); brightness tracks L
    assert np.max(np.abs(rgb[:, 0] - rgb[:, 1])) < 2.0
    assert np.max(np.abs(rgb[:, 1] - rgb[:, 2])) < 2.0
    assert rgb[0, 0] < rgb[1, 0] < rgb[2, 0] < rgb[3, 0] < rgb[4, 0]
    assert rgb[0, 0] < 2.0
    assert abs(rgb[4, 0] - 255.0) < 2.0


def test_lab_srgb_roundtrip_mid_gray():
    rgb = np.array([[128.0, 128.0, 128.0]], dtype=np.float64)
    back = lab_to_srgb(srgb_to_lab(rgb))
    assert np.max(np.abs(back - rgb)) < 2.0


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
    for space in ("rgb", "lab", "ciede2000"):
        idx = nearest_palette_indices(pixel, palette, space=space)
        assert int(idx[0]) == 1


def test_ciede2000_exported():
    from pixelate import ciede2000 as exported

    assert exported is ciede2000


def test_ciede2000_identical_is_zero():
    lab = np.array([[50.0, 2.5, -1.0]], dtype=np.float64)
    d = ciede2000(lab, lab)
    assert d.shape == (1, 1)
    assert float(d[0, 0]) < 1e-9


def test_ciede2000_sharma_pair():
    """Sharma et al. 2005 dataset, pair 1."""
    lab1 = np.array([50.0000, 2.6772, -79.7751], dtype=np.float64)
    lab2 = np.array([50.0000, 0.0000, -82.7485], dtype=np.float64)
    d = float(ciede2000(lab1, lab2))
    assert abs(d - 2.0425) < 0.02


def test_ciede2000_nx3_vs_px3_shape():
    a = np.array([[50.0, 10.0, 0.0], [40.0, -5.0, 8.0]], dtype=np.float64)
    b = np.array([[50.0, 0.0, 0.0], [60.0, 20.0, -10.0], [30.0, 0.0, 20.0]], dtype=np.float64)
    d = ciede2000(a, b)
    assert d.shape == (2, 3)
    assert np.all(d >= 0.0)


def test_ciede2000_hue_vs_same_euclidean():
    """Same CIE76 ΔE from gray; CIEDE2000 may differ with hue. Optional."""
    gray = np.array([50.0, 0.0, 0.0], dtype=np.float64)
    red = np.array([50.0, 30.0, 0.0], dtype=np.float64)
    yellow = np.array([50.0, 0.0, 30.0], dtype=np.float64)
    d76_r = float(np.linalg.norm(red - gray))
    d76_y = float(np.linalg.norm(yellow - gray))
    assert abs(d76_r - d76_y) < 1e-9
    d00_r = float(ciede2000(gray, red))
    d00_y = float(ciede2000(gray, yellow))
    # Not required to differ; just a finite positive distance.
    assert d00_r > 0.0 and d00_y > 0.0


def test_nearest_ciede2000_index_in_range():
    pixels = np.array([[10, 20, 30], [200, 10, 10], [0, 0, 0]], dtype=np.uint8)
    palette = np.array(
        [[0, 0, 0], [255, 0, 0], [0, 255, 0], [255, 255, 255]],
        dtype=np.uint8,
    )
    idx = nearest_palette_indices(pixels, palette, space="ciede2000")
    assert idx.shape == (3,)
    assert np.all(idx >= 0) and np.all(idx < len(palette))
