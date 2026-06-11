"""Tests for image input safety checks."""

import pytest
from PIL import Image

from pixelate.ascii_art import image_to_ascii
from pixelate.core import pixelate_image
from pixelate.image_safety import ImageTooLargeError, validate_image_size


def test_validate_image_size_rejects_too_many_pixels():
    image = Image.new("RGB", (4, 4))

    with pytest.raises(ImageTooLargeError):
        validate_image_size(image, max_pixels=15)


def test_pixelate_image_rejects_large_sources(monkeypatch):
    monkeypatch.setattr("pixelate.image_safety.MAX_SOURCE_PIXELS", 15)
    image = Image.new("RGB", (4, 4))

    with pytest.raises(ImageTooLargeError):
        pixelate_image(image, dither="none")


def test_ascii_rejects_empty_custom_ramp():
    image = Image.new("RGB", (2, 2))

    with pytest.raises(ValueError, match="ramp"):
        image_to_ascii(image, ramp="")


def test_pixelate_image_rejects_invalid_api_sizes():
    image = Image.new("RGB", (2, 2))

    with pytest.raises(ValueError, match="pixel_size"):
        pixelate_image(image, pixel_size=0)
