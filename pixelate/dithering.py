"""
Dithering algorithms.

These take an RGB image (numpy array, float) and a palette (numpy array of
RGB rows) and produce an image where each pixel has been mapped to the
nearest palette color, with quantization error spread to neighboring pixels
to preserve perceived detail.
"""

from __future__ import annotations

from typing import Callable, List, Tuple

import numpy as np

from pixelate.colorspace import convert_for_matching
from pixelate.lut import PaletteMatcher

# (dy, dx, weight) — error distribution kernels
Kernel = List[Tuple[int, int, float]]


def _loop_matcher(palette: np.ndarray, color_space: str) -> PaletteMatcher | None:
    """
    Matcher for the per-pixel error-diffusion loops, or ``None`` for a direct
    RGB scan.

    In ``lab`` space the LUT is the right tool — it turns each pixel's match
    into an O(1) index and avoids an sRGB→CIELAB conversion per pixel (≈4×
    faster than converting on the fly). In ``rgb`` space, for the small
    palettes retro art uses, a direct Euclidean scan of a handful of colors
    beats the LUT's indexing overhead, so we skip it.
    """
    if color_space.lower().strip() == "rgb":
        return None
    return PaletteMatcher(np.asarray(palette, dtype=np.float32), color_space)


def _nearest_color(
    pixel: np.ndarray,
    palette: np.ndarray,
    matcher: PaletteMatcher | None = None,
) -> np.ndarray:
    """
    Return the palette color closest to ``pixel``.

    With a ``matcher`` the lookup is an O(1) LUT index in its color space;
    without one it falls back to a direct Euclidean-RGB scan (kept so the
    helper stays usable on its own).
    """
    if matcher is not None:
        return matcher.nearest(pixel)
    diffs = palette - pixel
    distances = np.einsum("ij,ij->i", diffs, diffs)
    return palette[int(np.argmin(distances))]


def quantize_no_dither(
    image: np.ndarray,
    palette: np.ndarray,
    color_space: str = "rgb",
) -> np.ndarray:
    """
    Map each pixel to the nearest palette color (vectorized, no dithering).

    ``color_space`` selects the matching metric: ``rgb`` for Euclidean RGB or
    ``lab`` for perceptual CIELAB. Matching is exact (not LUT-binned): the
    whole image and palette are compared in one vectorized ``argmin``, which
    is already fast for the small palettes retro art uses.
    """
    h, w, _ = image.shape
    palette = np.asarray(palette, dtype=np.float32)
    flat = np.asarray(image, dtype=np.float32).reshape(-1, 3)

    query = convert_for_matching(flat, color_space)
    ref = convert_for_matching(palette, color_space)
    # (N, 1, C) - (1, P, C) -> nearest reference index per pixel.
    diffs = query[:, None, :] - ref[None, :, :]
    idx = np.argmin(np.einsum("ijk,ijk->ij", diffs, diffs), axis=1)
    return palette[idx].reshape(h, w, 3)


def _error_diffuse(
    image: np.ndarray,
    palette: np.ndarray,
    kernel: Kernel,
    color_space: str = "rgb",
) -> np.ndarray:
    """Generic error-diffusion dither using an (dy, dx, weight) kernel."""
    img = image.astype(np.float32).copy()
    h, w, _ = img.shape
    matcher = _loop_matcher(palette, color_space)

    for y in range(h):
        for x in range(w):
            old = img[y, x].copy()
            new = _nearest_color(old, palette, matcher)
            img[y, x] = new
            error = old - new

            for dy, dx, weight in kernel:
                ny, nx = y + dy, x + dx
                if 0 <= ny < h and 0 <= nx < w:
                    img[ny, nx] += error * weight

    return np.clip(img, 0, 255).astype(np.uint8)


def floyd_steinberg(image: np.ndarray, palette: np.ndarray, color_space: str = "rgb") -> np.ndarray:
    """
    Floyd-Steinberg error diffusion dithering.

    Diffuses quantization error to neighboring pixels using the classic
    7/16, 3/16, 5/16, 1/16 distribution.
    """
    kernel: Kernel = [
        (0, 1, 7 / 16),
        (1, -1, 3 / 16),
        (1, 0, 5 / 16),
        (1, 1, 1 / 16),
    ]
    return _error_diffuse(image, palette, kernel, color_space)


def atkinson(image: np.ndarray, palette: np.ndarray, color_space: str = "rgb") -> np.ndarray:
    """
    Atkinson dithering — used by the original Apple Macintosh.

    Diffuses 6/8 of the error (lighter than Floyd-Steinberg), which preserves
    contrast and produces a distinctive crisp look.
    """
    img = image.astype(np.float32).copy()
    h, w, _ = img.shape
    matcher = _loop_matcher(palette, color_space)

    offsets = [(0, 1), (0, 2), (1, -1), (1, 0), (1, 1), (2, 0)]

    for y in range(h):
        for x in range(w):
            old = img[y, x].copy()
            new = _nearest_color(old, palette, matcher)
            img[y, x] = new
            error = (old - new) / 8.0

            for dy, dx in offsets:
                ny, nx = y + dy, x + dx
                if 0 <= ny < h and 0 <= nx < w:
                    img[ny, nx] += error

    return np.clip(img, 0, 255).astype(np.uint8)


def stucki(image: np.ndarray, palette: np.ndarray, color_space: str = "rgb") -> np.ndarray:
    """
    Stucki error diffusion dithering.

    A wider kernel than Floyd-Steinberg (div 42) that produces smoother
    gradients with less directional artifacts.
    """
    kernel: Kernel = [
        (0, 1, 8 / 42),
        (0, 2, 4 / 42),
        (1, -2, 2 / 42),
        (1, -1, 4 / 42),
        (1, 0, 8 / 42),
        (1, 1, 4 / 42),
        (1, 2, 2 / 42),
        (2, -2, 1 / 42),
        (2, -1, 2 / 42),
        (2, 0, 4 / 42),
        (2, 1, 2 / 42),
        (2, 2, 1 / 42),
    ]
    return _error_diffuse(image, palette, kernel, color_space)


def burkes(image: np.ndarray, palette: np.ndarray, color_space: str = "rgb") -> np.ndarray:
    """
    Burkes error diffusion dithering.

    A simplified Stucki-style kernel (div 32) — only two rows, good balance
    of quality and speed.
    """
    kernel: Kernel = [
        (0, 1, 8 / 32),
        (0, 2, 4 / 32),
        (1, -2, 2 / 32),
        (1, -1, 4 / 32),
        (1, 0, 8 / 32),
        (1, 1, 4 / 32),
        (1, 2, 2 / 32),
    ]
    return _error_diffuse(image, palette, kernel, color_space)


def sierra(image: np.ndarray, palette: np.ndarray, color_space: str = "rgb") -> np.ndarray:
    """
    Sierra two-row (Sierra-2-4A / Filter Lite variant) error diffusion.

    Diffuses error with a compact two-row kernel (div 16). Faster than full
    Sierra-3 and Stucki while retaining good gradient quality.
    """
    kernel: Kernel = [
        (0, 1, 4 / 16),
        (0, 2, 3 / 16),
        (1, -2, 1 / 16),
        (1, -1, 2 / 16),
        (1, 0, 3 / 16),
        (1, 1, 2 / 16),
        (1, 2, 1 / 16),
    ]
    return _error_diffuse(image, palette, kernel, color_space)


def ordered_bayer(
    image: np.ndarray,
    palette: np.ndarray,
    matrix_size: int = 4,
    color_space: str = "rgb",
) -> np.ndarray:
    """
    Ordered (Bayer) dithering — produces the iconic crosshatched pattern.

    Adds a threshold pattern from a Bayer matrix before quantization, so
    error becomes a regular geometric texture rather than diffused noise.
    """
    if matrix_size == 2:
        bayer = np.array([[0, 2], [3, 1]]) / 4.0
    elif matrix_size == 4:
        bayer = np.array([
            [0, 8, 2, 10],
            [12, 4, 14, 6],
            [3, 11, 1, 9],
            [15, 7, 13, 5],
        ]) / 16.0
    else:
        bayer = np.array([
            [0, 32, 8, 40, 2, 34, 10, 42],
            [48, 16, 56, 24, 50, 18, 58, 26],
            [12, 44, 4, 36, 14, 46, 6, 38],
            [60, 28, 52, 20, 62, 30, 54, 22],
            [3, 35, 11, 43, 1, 33, 9, 41],
            [51, 19, 59, 27, 49, 17, 57, 25],
            [15, 47, 7, 39, 13, 45, 5, 37],
            [63, 31, 55, 23, 61, 29, 53, 21],
        ]) / 64.0

    h, w, _ = image.shape
    bh, bw = bayer.shape
    threshold = np.tile(bayer, (h // bh + 1, w // bw + 1))[:h, :w]
    # Scale threshold contribution; 32 is a balanced spread for 8-bit RGB
    img = image.astype(np.float32) + (threshold[..., None] - 0.5) * 32.0
    img = np.clip(img, 0, 255)
    return quantize_no_dither(img, palette, color_space)


DITHER_ALGORITHMS: dict[str, Callable[..., np.ndarray]] = {
    "none": quantize_no_dither,
    "floyd": floyd_steinberg,
    "atkinson": atkinson,
    "bayer": ordered_bayer,
    "stucki": stucki,
    "burkes": burkes,
    "sierra": sierra,
}


def get_dither(name: str) -> Callable[..., np.ndarray]:
    """Return a dithering function by name."""
    key = name.lower().strip()
    if key not in DITHER_ALGORITHMS:
        available = ", ".join(DITHER_ALGORITHMS)
        raise KeyError(f"Unknown dither '{name}'. Available: {available}")
    return DITHER_ALGORITHMS[key]
