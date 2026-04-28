"""
Retro post-processing effects: scanlines, CRT glow.
"""

from __future__ import annotations

import numpy as np
from PIL import Image, ImageDraw, ImageFilter


def apply_scanlines(img: Image.Image, intensity: float = 0.35, gap: int = 2) -> Image.Image:
    """
    Overlay horizontal dark lines that mimic CRT scan lines.

    Parameters
    ----------
    intensity : float
        How dark the scanlines are (0.0 = none, 1.0 = black).
    gap : int
        Pixels between scanlines.
    """
    arr = np.array(img).astype(np.float32)
    h = arr.shape[0]
    mask = np.ones(h, dtype=np.float32)
    mask[::gap] = 1.0 - intensity
    arr = arr * mask[:, None, None]
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))


def apply_crt(img: Image.Image, glow: float = 0.5, vignette: float = 0.4) -> Image.Image:
    """
    Approximate a CRT screen with a soft glow and corner vignette.

    The image is blended with a blurred copy of itself (bloom) and then
    darkened toward the corners (vignette).
    """
    base = img.convert("RGB")
    blurred = base.filter(ImageFilter.GaussianBlur(radius=3))

    # Blend bloom
    arr_base = np.array(base, dtype=np.float32)
    arr_blur = np.array(blurred, dtype=np.float32)
    bloom = np.clip(arr_base + glow * (arr_blur - arr_base) * 0.6, 0, 255)

    # Vignette
    h, w, _ = bloom.shape
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    cy, cx = (h - 1) / 2.0, (w - 1) / 2.0
    dist = np.sqrt(((xx - cx) / cx) ** 2 + ((yy - cy) / cy) ** 2)
    falloff = np.clip(1.0 - vignette * dist, 0, 1)
    bloom = bloom * falloff[..., None]

    return Image.fromarray(np.clip(bloom, 0, 255).astype(np.uint8))
