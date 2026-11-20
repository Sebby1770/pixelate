"""Tests for the LUT matcher, fast diffusion engine and pattern dithers."""

import numpy as np
import pytest

from pixelate.colorspace import nearest_palette_indices
from pixelate.dithering import (
    DITHER_ALGORITHMS,
    KERNELS,
    bayer_matrix,
    blue_noise,
    dither_image,
    dither_indices,
    get_dither,
    halftone_matrix,
    pattern_indices,
)
from pixelate.lut import grid_rgb, palette_lut
from pixelate.palettes import get_palette

PICO8 = np.array(get_palette("pico8"), dtype=np.float64)
GRAY = np.array(get_palette("grayscale"), dtype=np.float64)


def _gradient(h=24, w=40):
    x = np.linspace(0, 255, w)
    y = np.linspace(0, 255, h)
    img = np.zeros((h, w, 3))
    img[..., 0] = x[None, :]
    img[..., 1] = y[:, None]
    img[..., 2] = 255 - x[None, :]
    return img


@pytest.mark.parametrize("space", ["rgb", "lab", "ciede2000"])
def test_lut_matches_exact_search_at_cell_centers(space):
    lut = palette_lut(PICO8, space=space, bits=5)
    centers = grid_rgb(5)
    exact = nearest_palette_indices(centers, PICO8, space=space)
    assert np.array_equal(np.frombuffer(lut.table, dtype=np.uint8), exact.astype(np.uint8))


def test_lut_agrees_with_exact_search_almost_everywhere():
    rng = np.random.default_rng(3)
    pixels = rng.integers(0, 256, size=(4000, 3)).astype(np.float64)
    exact = nearest_palette_indices(pixels, PICO8, space="lab")
    approx = palette_lut(PICO8, space="lab").indices(pixels)
    assert (exact == approx).mean() > 0.97


def test_lut_scalar_and_vector_paths_agree_and_clamp():
    lut = palette_lut(PICO8, space="lab")
    for color in [(-40.0, 300.0, 12.5), (0, 0, 0), (255, 255, 255), (128.9, 3.2, 77.7)]:
        assert lut.index(*color) == int(lut.indices(np.array([color]))[0])


def test_lut_is_cached_between_instances():
    a = palette_lut(PICO8, space="rgb")
    b = palette_lut([tuple(c) for c in PICO8], space="rgb")
    assert a.table is b.table


def test_lut_rejects_bad_input():
    with pytest.raises(ValueError):
        palette_lut([], space="lab")
    with pytest.raises(ValueError):
        palette_lut(PICO8, space="hsv")


@pytest.mark.parametrize("name", sorted(KERNELS))
def test_diffusion_output_stays_in_palette(name):
    out = dither_image(_gradient(), PICO8, name)
    colors = {tuple(c) for c in out.reshape(-1, 3)}
    assert colors <= {tuple(int(v) for v in c) for c in PICO8}


def test_diffusion_preserves_mean_tone_on_grayscale():
    img = np.full((40, 40, 3), 100.0)
    out = dither_image(img, GRAY, "floyd").astype(np.float64)
    assert abs(out.mean() - 100.0) < 3.0
    assert len(np.unique(out[..., 0])) >= 2  # really dithered, not flat


def test_serpentine_changes_scan_but_not_palette():
    a = dither_image(_gradient(), PICO8, "floyd", serpentine=True)
    b = dither_image(_gradient(), PICO8, "floyd", serpentine=False)
    assert a.shape == b.shape
    assert not np.array_equal(a, b)


def test_single_pixel_and_single_color_palette():
    one = np.array([[[10.0, 200.0, 30.0]]])
    assert dither_image(one, PICO8, "jjn").shape == (1, 1, 3)
    solo = np.array([[255, 0, 0]], dtype=np.float64)
    for name in ("floyd", "pattern", "bluenoise", "halftone", "bayer", "none"):
        out = dither_image(_gradient(8, 8), solo, name)
        assert (out == np.array([255, 0, 0])).all()


def test_bayer_matrix_is_a_permutation():
    for size in (2, 4, 8, 16):
        m = bayer_matrix(size)
        assert sorted((m * size * size).astype(int).ravel()) == list(range(size * size))
    with pytest.raises(ValueError):
        bayer_matrix(3)


def test_halftone_and_blue_noise_are_permutations():
    h = halftone_matrix()
    assert sorted((h * 64).astype(int).ravel()) == list(range(64))
    bn = blue_noise(16)
    assert sorted((bn * 256).astype(int).ravel()) == list(range(256))
    assert np.array_equal(blue_noise(16), bn)  # deterministic + cached


def test_blue_noise_has_no_low_frequency_clumps():
    bn = blue_noise(32)
    # Each 8x8 block of a good blue-noise mask holds ~half its dots below 0.5.
    blocks = (bn < 0.5).reshape(4, 8, 4, 8).sum(axis=(1, 3))
    assert blocks.min() >= 22 and blocks.max() <= 42


@pytest.mark.parametrize("name", ["pattern", "bluenoise", "halftone"])
def test_pattern_dithers_track_mean_gray(name):
    for level in (40.0, 128.0, 200.0):
        img = np.full((32, 32, 3), level)
        out = dither_image(img, GRAY, name).astype(np.float64)
        assert abs(out.mean() - level) < 12.0
        assert set(np.unique(out)) <= {float(c[0]) for c in GRAY}


def test_pattern_indices_shape_and_range():
    idx = pattern_indices(_gradient(), PICO8, bayer_matrix(8))
    assert idx.shape == (24, 40)
    assert idx.max() < len(PICO8)


def test_dither_indices_matches_dither_image():
    img = _gradient()
    for name in ("floyd", "atkinson", "pattern", "bayer", "none", "sierra_lite"):
        idx = dither_indices(img, PICO8, name)
        assert np.array_equal(PICO8[idx].astype(np.uint8), dither_image(img, PICO8, name))


def test_aliases_resolve():
    assert get_dither("knoll") is DITHER_ALGORITHMS["pattern"]
    assert get_dither("Blue-Noise") is DITHER_ALGORITHMS["bluenoise"]
    assert get_dither("FS") is DITHER_ALGORITHMS["floyd"]
    with pytest.raises(KeyError):
        get_dither("wobble")
