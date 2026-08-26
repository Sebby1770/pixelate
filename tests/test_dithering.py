"""Tests for dithering algorithms."""

import numpy as np
import pytest

from pixelate.dithering import (
    DITHER_ALGORITHMS,
    atkinson,
    burkes,
    dither_image,
    floyd_steinberg,
    get_dither,
    jarvis_judice_ninke,
    ordered_bayer,
    quantize_no_dither,
    sierra,
    stucki,
)


@pytest.fixture
def palette():
    return np.array([[0, 0, 0], [255, 255, 255]], dtype=np.float32)


@pytest.fixture
def gradient():
    # 16x16 horizontal grayscale gradient
    row = np.linspace(0, 255, 16, dtype=np.float32)
    img = np.stack([row, row, row], axis=-1)  # (16, 3)
    return np.tile(img, (16, 1, 1)).astype(np.float32)


def _assert_only_palette(out, palette):
    unique = np.unique(out.reshape(-1, 3), axis=0)
    for color in unique:
        assert any(np.array_equal(color, p) for p in palette.astype(np.uint8))


def test_quantize_no_dither_uses_only_palette_colors(gradient, palette):
    out = quantize_no_dither(gradient, palette)
    _assert_only_palette(out, palette)


def test_floyd_steinberg_uses_only_palette_colors(gradient, palette):
    out = floyd_steinberg(gradient.copy(), palette)
    unique = np.unique(out.reshape(-1, 3), axis=0)
    assert len(unique) <= 2
    _assert_only_palette(out, palette)


def test_atkinson_uses_only_palette_colors(gradient, palette):
    out = atkinson(gradient.copy(), palette)
    unique = np.unique(out.reshape(-1, 3), axis=0)
    assert len(unique) <= 2


def test_ordered_bayer_uses_only_palette_colors(gradient, palette):
    out = ordered_bayer(gradient, palette)
    unique = np.unique(out.reshape(-1, 3), axis=0)
    assert len(unique) <= 2


def test_stucki_uses_only_palette_colors(gradient, palette):
    out = stucki(gradient.copy(), palette)
    unique = np.unique(out.reshape(-1, 3), axis=0)
    assert len(unique) <= 2
    _assert_only_palette(out, palette)


def test_burkes_uses_only_palette_colors(gradient, palette):
    out = burkes(gradient.copy(), palette)
    unique = np.unique(out.reshape(-1, 3), axis=0)
    assert len(unique) <= 2
    _assert_only_palette(out, palette)


def test_sierra_uses_only_palette_colors(gradient, palette):
    out = sierra(gradient.copy(), palette)
    unique = np.unique(out.reshape(-1, 3), axis=0)
    assert len(unique) <= 2
    _assert_only_palette(out, palette)


def test_get_dither_unknown_raises():
    with pytest.raises(KeyError):
        get_dither("turbo-dither")


def test_all_algorithms_registered():
    for name in (
        "none", "floyd", "atkinson", "bayer", "stucki", "burkes", "sierra", "jjn",
    ):
        assert name in DITHER_ALGORITHMS
        assert callable(get_dither(name))


def test_jjn_uses_only_palette_colors(gradient, palette):
    out = jarvis_judice_ninke(gradient.copy(), palette)
    unique = np.unique(out.reshape(-1, 3), axis=0)
    assert len(unique) <= 2
    _assert_only_palette(out, palette)


def test_floyd_serpentine_uses_only_palette_colors(gradient, palette):
    out = floyd_steinberg(gradient.copy(), palette, serpentine=True, space="rgb")
    _assert_only_palette(out, palette)


def test_floyd_serpentine_differs_from_ltr_on_gradient(gradient, palette):
    a = floyd_steinberg(gradient.copy(), palette, serpentine=True, space="rgb")
    b = floyd_steinberg(gradient.copy(), palette, serpentine=False, space="rgb")
    assert a.shape == b.shape
    assert not np.array_equal(a, b)


def test_dither_image_jjn_subset(gradient, palette):
    out = dither_image(gradient.copy(), palette, "jjn", space="lab", serpentine=True)
    _assert_only_palette(out, palette)
    assert out.dtype == np.uint8


@pytest.mark.parametrize("name", ["stucki", "burkes", "sierra"])
def test_new_dithers_via_get_dither(name, gradient, palette):
    fn = get_dither(name)
    out = fn(gradient.copy(), palette)
    assert out.shape == gradient.shape
    assert out.dtype == np.uint8
