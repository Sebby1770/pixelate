"""End-to-end tests for the conversion pipeline."""

import numpy as np
from PIL import Image

from pixelate.core import pixelate_image
from pixelate.palettes import get_palette


def _make_test_image(size=(64, 64)):
    arr = np.zeros((size[1], size[0], 3), dtype=np.uint8)
    # Simple 4-quadrant test image
    arr[: size[1] // 2, : size[0] // 2] = (200, 50, 50)
    arr[: size[1] // 2, size[0] // 2:] = (50, 200, 50)
    arr[size[1] // 2:, : size[0] // 2] = (50, 50, 200)
    arr[size[1] // 2:, size[0] // 2:] = (220, 220, 50)
    return Image.fromarray(arr, mode="RGB")


def test_pixelate_image_returns_image():
    src = _make_test_image()
    out = pixelate_image(src, palette="gameboy", pixel_size=32, upscale=2, dither="none")
    assert isinstance(out, Image.Image)


def test_pixelate_image_uses_only_palette_colors():
    src = _make_test_image()
    out = pixelate_image(src, palette="gameboy", pixel_size=32, upscale=1, dither="none")
    arr = np.array(out)
    palette = {tuple(c) for c in get_palette("gameboy")}
    unique = {tuple(c) for c in arr.reshape(-1, 3)}
    assert unique.issubset(palette)


def test_pixelate_image_respects_pixel_size():
    src = _make_test_image(size=(128, 64))
    out = pixelate_image(src, palette="gameboy", pixel_size=32, upscale=1, dither="none")
    # Longest side downscaled to 32 before upscale=1
    assert max(out.size) == 32


def test_pixelate_image_upscale_multiplies_size():
    src = _make_test_image(size=(64, 64))
    out = pixelate_image(src, palette="gameboy", pixel_size=32, upscale=4, dither="none")
    assert out.size == (32 * 4, 32 * 4)
