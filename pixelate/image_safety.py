"""Shared image input safety checks."""

from __future__ import annotations

from pathlib import Path
from typing import Union

from PIL import Image


MAX_SOURCE_PIXELS = 50_000_000


class ImageTooLargeError(ValueError):
    """Raised when an input image is too large to process safely."""


def validate_image_size(
    image: Image.Image,
    *,
    max_pixels: int | None = None,
) -> None:
    """Reject empty or overly large images before expensive pixel processing."""
    limit = MAX_SOURCE_PIXELS if max_pixels is None else max_pixels
    width, height = image.size

    if width <= 0 or height <= 0:
        raise ValueError(f"Image dimensions must be positive, got {width}x{height}.")

    pixels = width * height
    if pixels > limit:
        raise ImageTooLargeError(
            f"Refusing to process {width}x{height} image ({pixels:,} pixels). "
            f"The safety limit is {limit:,} pixels."
        )


def load_rgb_image(src: Union[str, Path, Image.Image]) -> Image.Image:
    """Load a path or PIL image as RGB after validating source dimensions."""
    if isinstance(src, (str, Path)):
        try:
            with Image.open(src) as image:
                validate_image_size(image)
                return image.convert("RGB")
        except Image.DecompressionBombError as exc:
            raise ImageTooLargeError(str(exc)) from exc

    validate_image_size(src)
    return src.convert("RGB")
