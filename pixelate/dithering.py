"""
Dithering algorithms.

These take an RGB image (numpy array, float) and a palette (numpy array of
RGB rows) and produce an image where each pixel has been mapped to the
nearest palette color, with quantization error spread to neighboring pixels
to preserve perceived detail.
"""

from __future__ import annotations

import numpy as np


def _nearest_color(pixel: np.ndarray, palette: np.ndarray) -> np.ndarray:
    """Return the palette color closest to `pixel` (Euclidean RGB)."""
    diffs = palette - pixel
    distances = np.einsum("ij,ij->i", diffs, diffs)
    return palette[int(np.argmin(distances))]


def quantize_no_dither(image: np.ndarray, palette: np.ndarray) -> np.ndarray:
    """Map each pixel to the nearest palette color (vectorized, no dithering)."""
    h, w, _ = image.shape
    flat = image.reshape(-1, 3)
    # (N, 1, 3) - (1, P, 3) -> (N, P, 3)
    diffs = flat[:, None, :] - palette[None, :, :]
    dist = np.einsum("ijk,ijk->ij", diffs, diffs)
    idx = np.argmin(dist, axis=1)
    out = palette[idx].reshape(h, w, 3)
    return out


def floyd_steinberg(image: np.ndarray, palette: np.ndarray) -> np.ndarray:
    """
    Floyd-Steinberg error diffusion dithering.

    Diffuses quantization error to neighboring pixels using the classic
    7/16, 3/16, 5/16, 1/16 distribution.
    """
    img = image.astype(np.float32).copy()
    h, w, _ = img.shape

    for y in range(h):
        for x in range(w):
            old = img[y, x].copy()
            new = _nearest_color(old, palette)
            img[y, x] = new
            error = old - new

            if x + 1 < w:
                img[y, x + 1] += error * (7 / 16)
            if y + 1 < h:
                if x > 0:
                    img[y + 1, x - 1] += error * (3 / 16)
                img[y + 1, x] += error * (5 / 16)
                if x + 1 < w:
                    img[y + 1, x + 1] += error * (1 / 16)

    return np.clip(img, 0, 255).astype(np.uint8)


def atkinson(image: np.ndarray, palette: np.ndarray) -> np.ndarray:
    """
    Atkinson dithering — used by the original Apple Macintosh.

    Diffuses 6/8 of the error (lighter than Floyd-Steinberg), which preserves
    contrast and produces a distinctive crisp look.
    """
    img = image.astype(np.float32).copy()
    h, w, _ = img.shape

    offsets = [(0, 1), (0, 2), (1, -1), (1, 0), (1, 1), (2, 0)]

    for y in range(h):
        for x in range(w):
            old = img[y, x].copy()
            new = _nearest_color(old, palette)
            img[y, x] = new
            error = (old - new) / 8.0

            for dy, dx in offsets:
                ny, nx = y + dy, x + dx
                if 0 <= ny < h and 0 <= nx < w:
                    img[ny, nx] += error

    return np.clip(img, 0, 255).astype(np.uint8)


def ordered_bayer(image: np.ndarray, palette: np.ndarray, matrix_size: int = 4) -> np.ndarray:
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
    return quantize_no_dither(img, palette)


DITHER_ALGORITHMS = {
    "none": quantize_no_dither,
    "floyd": floyd_steinberg,
    "atkinson": atkinson,
    "bayer": ordered_bayer,
}


def get_dither(name: str):
    """Return a dithering function by name."""
    key = name.lower().strip()
    if key not in DITHER_ALGORITHMS:
        available = ", ".join(DITHER_ALGORITHMS)
        raise KeyError(f"Unknown dither '{name}'. Available: {available}")
    return DITHER_ALGORITHMS[key]
