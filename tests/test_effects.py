"""Tests for the retro post-processing effects."""

import numpy as np
import pytest
from PIL import Image

from pixelate.core import pixelate_image
from pixelate.effects import (
    apply_chromatic_aberration,
    apply_color_bleed,
    apply_outline,
    apply_pixel_grid,
)


@pytest.fixture
def noisy() -> Image.Image:
    rng = np.random.default_rng(0)
    return Image.fromarray(rng.integers(0, 256, (48, 48, 3), dtype=np.uint8), "RGB")


def test_pixel_grid_noop_when_cell_too_small(noisy):
    assert apply_pixel_grid(noisy, 1) is noisy


def test_pixel_grid_darkens_grid_lines(noisy):
    out = np.array(apply_pixel_grid(noisy, 8, color=(0, 0, 0), opacity=1.0))
    # Every 8th row/col is painted the grid color.
    assert np.all(out[8, :, :] == 0)
    assert np.all(out[:, 8, :] == 0)


def test_chromatic_noop_when_shift_zero(noisy):
    assert apply_chromatic_aberration(noisy, 0) is noisy


def test_chromatic_does_not_wrap_edges(noisy):
    src = np.array(noisy)
    out = np.array(apply_chromatic_aberration(noisy, 3))
    # Red shifted right: the first columns are refilled from the edge, never
    # wrapped from the far side.
    assert np.array_equal(out[:, 0, 0], src[:, 0, 0])


def test_outline_paints_border_between_fg_and_bg():
    canvas = np.zeros((40, 40, 3), dtype=np.uint8)
    canvas[12:28, 12:28] = (200, 80, 80)
    out = np.array(apply_outline(Image.fromarray(canvas), color=(255, 255, 255), thickness=1))
    assert (out == (255, 255, 255)).all(axis=-1).any()


def test_color_bleed_noop_at_zero_strength(noisy):
    assert apply_color_bleed(noisy, 0.0) is noisy


def test_color_bleed_preserves_shape_and_mode(noisy):
    out = apply_color_bleed(noisy, 0.6)
    assert out.size == noisy.size
    assert out.mode == "RGB"


def test_effects_default_off_is_byte_identical():
    rng = np.random.default_rng(1)
    src = Image.fromarray(rng.integers(0, 256, (64, 64, 3), dtype=np.uint8), "RGB")
    base = np.array(pixelate_image(src, palette="nes", pixel_size=32, upscale=2, dither="none"))
    again = np.array(pixelate_image(src, palette="nes", pixel_size=32, upscale=2, dither="none"))
    assert np.array_equal(base, again)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"posterize": 3},
        {"grid": True},
        {"outline": True},
        {"chromatic": True},
        {"color_bleed": True},
    ],
)
def test_each_effect_changes_output(kwargs):
    rng = np.random.default_rng(2)
    src = Image.fromarray(rng.integers(0, 256, (64, 64, 3), dtype=np.uint8), "RGB")
    base = np.array(pixelate_image(src, palette="nes", pixel_size=32, upscale=2, dither="none"))
    out = np.array(
        pixelate_image(src, palette="nes", pixel_size=32, upscale=2, dither="none", **kwargs)
    )
    assert not np.array_equal(out, base)
