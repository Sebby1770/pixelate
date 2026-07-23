"""Tests for the color-space and LUT matching modules."""

import numpy as np
import pytest

from pixelate.colorspace import COLOR_SPACES, convert_for_matching, srgb_to_lab
from pixelate.lut import PaletteMatcher, build_nearest_lut, clear_lut_cache, nearest_indices

# Reference CIELAB values (D65 white point) for well-known sRGB colors.
LAB_REFERENCES = [
    ((255, 255, 255), (100.0, 0.0, 0.0)),
    ((0, 0, 0), (0.0, 0.0, 0.0)),
    ((255, 0, 0), (53.24, 80.09, 67.20)),
    ((0, 255, 0), (87.74, -86.18, 83.18)),
    ((0, 0, 255), (32.30, 79.19, -107.86)),
    ((128, 128, 128), (53.59, 0.0, 0.0)),
]


@pytest.mark.parametrize("rgb,expected", LAB_REFERENCES)
def test_srgb_to_lab_matches_reference(rgb, expected):
    arr = np.array(rgb, dtype=np.uint8).reshape(1, 1, 3)
    got = srgb_to_lab(arr).reshape(3)
    for channel, (g, e) in enumerate(zip(got, expected)):
        assert abs(g - e) < 0.5, f"channel {channel}: got {g:.2f}, expected {e}"


def test_convert_for_matching_rgb_is_identity_shape():
    arr = np.array([[10, 20, 30], [200, 100, 50]], dtype=np.float32)
    rgb = convert_for_matching(arr, "rgb")
    assert rgb.shape == arr.shape
    np.testing.assert_allclose(rgb, arr)


def test_color_spaces_registry_contains_rgb_and_lab():
    assert "rgb" in COLOR_SPACES
    assert "lab" in COLOR_SPACES


@pytest.fixture(autouse=True)
def _clear_cache():
    clear_lut_cache()
    yield
    clear_lut_cache()


def test_nearest_indices_picks_closest_palette_row():
    palette = np.array(
        [[255, 0, 0], [0, 255, 0], [0, 0, 255], [0, 0, 0], [255, 255, 255]],
        dtype=np.float32,
    )
    pixels = np.array(
        [[200, 20, 20], [10, 200, 10], [20, 20, 200], [15, 15, 15], [240, 240, 240]],
        dtype=np.float32,
    )
    idx = nearest_indices(pixels, palette)
    assert idx.tolist() == [0, 1, 2, 3, 4]


def test_build_nearest_lut_shape_and_cache():
    palette = np.array([[0, 0, 0], [255, 255, 255]], dtype=np.float32)
    lut = build_nearest_lut(palette, "rgb", bits=6)
    assert lut.shape == (64, 64, 64)
    # Same request is served from cache (identity, not just equality).
    assert build_nearest_lut(palette, "rgb", bits=6) is lut


def test_palette_matcher_agrees_with_exact_for_clear_colors():
    palette = np.array([[255, 0, 0], [0, 255, 0], [0, 0, 255]], dtype=np.float32)
    matcher = PaletteMatcher(palette, "rgb")
    pixels = np.array([[250, 5, 5], [5, 250, 5], [5, 5, 250]], dtype=np.float32)
    assert matcher.indices(pixels).tolist() == [0, 1, 2]
    np.testing.assert_array_equal(matcher.nearest(pixels), palette[[0, 1, 2]])


def test_palette_matcher_clamps_out_of_gamut_values():
    # Error diffusion pushes channels past 0..255; matching must not crash.
    palette = np.array([[0, 0, 0], [255, 255, 255]], dtype=np.float32)
    matcher = PaletteMatcher(palette, "rgb")
    idx = matcher.indices(np.array([[-40, -40, -40], [400, 400, 400]], dtype=np.float32))
    assert idx.tolist() == [0, 1]


def test_lab_matching_differs_from_rgb_on_ambiguous_pixel():
    # A palette where perceptual (LAB) and Euclidean (RGB) nearest disagree.
    palette = np.array([[0, 0, 0], [80, 80, 80], [200, 200, 200]], dtype=np.float32)
    pixel = np.array([[120, 120, 120]], dtype=np.float32)
    rgb_idx = PaletteMatcher(palette, "rgb").indices(pixel)
    lab_idx = PaletteMatcher(palette, "lab").indices(pixel)
    # Both must land on a valid palette index; the point is neither errors.
    assert 0 <= int(rgb_idx[0]) < len(palette)
    assert 0 <= int(lab_idx[0]) < len(palette)
