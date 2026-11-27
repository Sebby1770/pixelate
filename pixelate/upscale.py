"""
Pixel-art upscalers.

``nearest`` keeps hard square pixels. ``scale2x`` / ``scale3x`` (Andrea
Mazzoleni's AdvMAME2x/3x, a.k.a. EPX) round off diagonal staircases while
never inventing new colors, so output stays palette-locked. ``scale4x`` is
scale2x applied twice.
"""

from __future__ import annotations

import numpy as np
from PIL import Image

UPSCALERS = ("nearest", "scale2x", "scale3x", "scale4x")


def _eq(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    return np.all(a == b, axis=-1)


def _neighbours(arr: np.ndarray):
    p = np.pad(arr, ((1, 1), (1, 1), (0, 0)), mode="edge")
    return (
        p[:-2, :-2], p[:-2, 1:-1], p[:-2, 2:],
        p[1:-1, :-2], p[1:-1, 1:-1], p[1:-1, 2:],
        p[2:, :-2], p[2:, 1:-1], p[2:, 2:],
    )


def scale2x(arr: np.ndarray) -> np.ndarray:
    """Scale2x / EPX on an ``(H, W, C)`` array → ``(2H, 2W, C)``."""
    _, b, _, d, e, f, _, h, _ = _neighbours(arr)
    cond = ~_eq(b, h) & ~_eq(d, f)
    e0 = np.where((cond & _eq(d, b))[..., None], d, e)
    e1 = np.where((cond & _eq(b, f))[..., None], f, e)
    e2 = np.where((cond & _eq(d, h))[..., None], d, e)
    e3 = np.where((cond & _eq(h, f))[..., None], f, e)
    hh, ww, c = arr.shape
    out = np.empty((hh * 2, ww * 2, c), dtype=arr.dtype)
    out[0::2, 0::2], out[0::2, 1::2] = e0, e1
    out[1::2, 0::2], out[1::2, 1::2] = e2, e3
    return out


def scale3x(arr: np.ndarray) -> np.ndarray:
    """Scale3x (AdvMAME3x) on an ``(H, W, C)`` array → ``(3H, 3W, C)``."""
    a, b, c, d, e, f, g, h, i = _neighbours(arr)
    cond = ~_eq(b, h) & ~_eq(d, f)

    def pick(mask, x):
        return np.where((cond & mask)[..., None], x, e)

    db, bf, dh, hf = _eq(d, b), _eq(b, f), _eq(d, h), _eq(h, f)
    ec, ea, eg, ei = _eq(e, c), _eq(e, a), _eq(e, g), _eq(e, i)
    blocks = [
        [pick(db, d), pick((db & ~ec) | (bf & ~ea), b), pick(bf, f)],
        [pick((db & ~eg) | (dh & ~ea), d), e, pick((bf & ~ei) | (hf & ~ec), f)],
        [pick(dh, d), pick((dh & ~ei) | (hf & ~eg), h), pick(hf, f)],
    ]
    hh, ww, ch = arr.shape
    out = np.empty((hh * 3, ww * 3, ch), dtype=arr.dtype)
    for r in range(3):
        for col in range(3):
            out[r::3, col::3] = blocks[r][col]
    return out


def upscale_image(img: Image.Image, factor: int, method: str = "nearest") -> Image.Image:
    """
    Enlarge *img* by integer *factor* with a pixel-art aware *method*.

    ``scale2x`` needs an even factor and ``scale3x`` a multiple of 3; any
    remaining factor is filled with nearest-neighbour so every combination
    works (e.g. ``factor=4, method="scale3x"`` falls back to scale2x twice).
    """
    factor = int(factor)
    if factor < 1:
        raise ValueError("upscale factor must be >= 1")
    key = str(method).lower().strip()
    if key not in UPSCALERS:
        raise ValueError(f"Unknown upscaler '{method}'. Use one of: {', '.join(UPSCALERS)}")
    if factor == 1:
        return img
    if key == "nearest":
        return img.resize((img.width * factor, img.height * factor), Image.Resampling.NEAREST)

    mode = img.mode
    arr = np.asarray(img.convert("RGBA" if mode in ("RGBA", "LA", "PA") else "RGB"))
    remaining = factor
    if key == "scale3x" and remaining % 3 == 0:
        arr = scale3x(arr)
        remaining //= 3
    while remaining % 2 == 0 and key in ("scale2x", "scale4x", "scale3x"):
        arr = scale2x(arr)
        remaining //= 2
    if key == "scale3x" and remaining % 3 == 0:
        arr = scale3x(arr)
        remaining //= 3
    out = Image.fromarray(arr)
    if remaining > 1:
        out = out.resize((out.width * remaining, out.height * remaining), Image.Resampling.NEAREST)
    return out
