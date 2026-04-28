"""
Core pixel-art conversion pipeline.

The pipeline:
  1. Load image and convert to RGB.
  2. Downscale to target resolution (this is the "pixelation").
  3. Quantize to a retro palette, optionally with dithering.
  4. Apply optional CRT effects.
  5. Upscale back with nearest-neighbor (so each "pixel" stays crisp).
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Tuple, Union

import numpy as np
from PIL import Image

from pixelate.dithering import get_dither
from pixelate.palettes import get_palette


def _resize_keep_aspect(img: Image.Image, max_dim: int) -> Image.Image:
    """Downscale so the longest side equals `max_dim`, preserving aspect."""
    w, h = img.size
    if max(w, h) <= max_dim:
        return img
    if w >= h:
        new_w = max_dim
        new_h = max(1, round(h * (max_dim / w)))
    else:
        new_h = max_dim
        new_w = max(1, round(w * (max_dim / h)))
    return img.resize((new_w, new_h), Image.LANCZOS)


def _adjust_saturation(img: Image.Image, factor: float) -> Image.Image:
    """Boost or cut saturation. factor=1.0 leaves the image unchanged."""
    if factor == 1.0:
        return img
    from PIL import ImageEnhance
    return ImageEnhance.Color(img).enhance(factor)


def pixelate_image(
    src: Union[str, Path, Image.Image],
    palette: str = "gameboy",
    pixel_size: int = 96,
    dither: str = "floyd",
    upscale: int = 4,
    saturation: float = 1.2,
    crt: bool = False,
    scanlines: bool = False,
) -> Image.Image:
    """
    Convert an image into retro pixel art.

    Parameters
    ----------
    src : path or PIL Image
        Source image.
    palette : str
        Name of the palette (see ``pixelate.palettes.PALETTES``).
    pixel_size : int
        Target resolution of the longest side, in "pixels". Lower = chunkier.
    dither : str
        Dithering algorithm: ``none``, ``floyd``, ``atkinson``, ``bayer``.
    upscale : int
        How many output pixels per logical pixel. ``4`` is a good default.
    saturation : float
        Saturation multiplier applied before quantization.
    crt : bool
        Apply a CRT-style glow + curvature effect after upscaling.
    scanlines : bool
        Overlay horizontal scanlines on the upscaled output.

    Returns
    -------
    PIL.Image
        The pixel-art result, ready to save or display.
    """
    # --- Load -----------------------------------------------------------
    if isinstance(src, (str, Path)):
        img = Image.open(src)
    else:
        img = src
    img = img.convert("RGB")

    # --- Pre-process ----------------------------------------------------
    img = _adjust_saturation(img, saturation)
    img = _resize_keep_aspect(img, pixel_size)

    # --- Quantize -------------------------------------------------------
    palette_arr = np.array(get_palette(palette), dtype=np.float32)
    arr = np.array(img, dtype=np.uint8)
    dither_fn = get_dither(dither)
    quantized = dither_fn(arr.astype(np.float32), palette_arr)

    out = Image.fromarray(quantized.astype(np.uint8), mode="RGB")

    # --- Upscale --------------------------------------------------------
    if upscale > 1:
        new_size = (out.size[0] * upscale, out.size[1] * upscale)
        out = out.resize(new_size, Image.NEAREST)

    # --- Effects --------------------------------------------------------
    if scanlines or crt:
        from pixelate.effects import apply_scanlines, apply_crt
        if scanlines:
            out = apply_scanlines(out)
        if crt:
            out = apply_crt(out)

    return out


def save_image(img: Image.Image, path: Union[str, Path]) -> Path:
    """Save an image, ensuring the parent directory exists."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    img.save(p)
    return p


def get_image_size(src: Union[str, Path]) -> Tuple[int, int]:
    """Return the (width, height) of an image without fully loading it."""
    with Image.open(src) as img:
        return img.size
