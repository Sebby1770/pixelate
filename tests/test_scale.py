"""Tests for nearest-neighbor --scale and edge/invert/contrast flags."""

import numpy as np
from PIL import Image

from pixelate.core import nearest_scale, pixelate_image


def _make_test_image(size=(64, 64)):
    arr = np.zeros((size[1], size[0], 3), dtype=np.uint8)
    arr[: size[1] // 2, : size[0] // 2] = (200, 50, 50)
    arr[: size[1] // 2, size[0] // 2 :] = (50, 200, 50)
    arr[size[1] // 2 :, : size[0] // 2] = (50, 50, 200)
    arr[size[1] // 2 :, size[0] // 2 :] = (220, 220, 50)
    return Image.fromarray(arr, mode="RGB")


def test_nearest_scale_multiplies_size():
    img = Image.new("RGB", (10, 8), (1, 2, 3))
    out = nearest_scale(img, 4)
    assert out.size == (40, 32)


def test_nearest_scale_one_is_noop_size():
    img = Image.new("RGB", (10, 8), (1, 2, 3))
    out = nearest_scale(img, 1)
    assert out.size == (10, 8)


def test_nearest_scale_invalid():
    img = Image.new("RGB", (4, 4), (0, 0, 0))
    try:
        nearest_scale(img, 0)
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_pixelate_scale_extra():
    src = _make_test_image()
    base = pixelate_image(
        src, palette="gameboy", pixel_size=16, upscale=1, scale=1, dither="none"
    )
    scaled = pixelate_image(
        src, palette="gameboy", pixel_size=16, upscale=1, scale=4, dither="none"
    )
    assert scaled.size == (base.size[0] * 4, base.size[1] * 4)


def test_pixelate_scale_preserves_palette_blockiness():
    """Nearest scale should keep hard edges (no intermediate colors)."""
    src = _make_test_image()
    out = pixelate_image(
        src, palette="cga", pixel_size=16, upscale=1, scale=3, dither="none"
    )
    arr = np.array(out)
    # Every 3x3 block of the scaled image should be uniform if source was solid
    # At minimum, unique colors must still be subset of CGA
    from pixelate.palettes import get_palette

    unique = {tuple(c) for c in arr.reshape(-1, 3)}
    assert unique.issubset(set(get_palette("cga")))


def test_edges_flag_runs():
    src = _make_test_image()
    out = pixelate_image(
        src, palette="nes", pixel_size=24, upscale=1, edges=True, dither="none"
    )
    assert isinstance(out, Image.Image)


def test_invert_flag_changes_output():
    src = _make_test_image()
    normal = pixelate_image(
        src, palette="grayscale", pixel_size=16, upscale=1, invert=False, dither="none"
    )
    inverted = pixelate_image(
        src, palette="grayscale", pixel_size=16, upscale=1, invert=True, dither="none"
    )
    # Not guaranteed different for all palettes, but for 4-quadrant color image
    # invert + grayscale should differ
    assert not np.array_equal(np.array(normal), np.array(inverted))


def test_contrast_flag_runs():
    src = _make_test_image()
    out = pixelate_image(
        src, palette="pico8", pixel_size=16, upscale=1, contrast=1.8, dither="none"
    )
    assert isinstance(out, Image.Image)


def test_combined_v21_flags():
    src = _make_test_image()
    out = pixelate_image(
        src,
        palette="cyberpunk",
        pixel_size=20,
        upscale=2,
        scale=2,
        edges=True,
        invert=False,
        contrast=1.2,
        dither="bayer",
    )
    assert out.size[0] > 0
    # upscale 2 * scale 2 on ~20px → ~80
    assert max(out.size) == 20 * 2 * 2
