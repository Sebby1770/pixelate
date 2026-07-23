"""
Nearest-palette lookup tables.

Error diffusion is inherently sequential — each pixel depends on the error
pushed onto it by its neighbors — so it cannot be vectorized away. What it
*can* do is stop searching the palette 65,536 times per image. Instead we
precompute a 3D lookup table over quantized RGB bins once per palette and
turn the inner "which palette color is nearest?" question into a single
array index.

At the default 6 bits per channel the table is 64x64x64 entries (262,144
uint16 indices, half a megabyte) and each bin is 4 levels wide, so a lookup
is accurate to within 2 levels per channel before the palette snap.
"""

from __future__ import annotations

from typing import Dict, Tuple

import numpy as np

from pixelate.colorspace import convert_for_matching

# Bits kept per channel when indexing the LUT. 6 -> 64 bins of 4 levels.
LUT_BITS = 6

# Rows of the (N, P) distance matrix computed at a time. Keeps peak memory
# bounded regardless of image size / palette length.
CHUNK_ROWS = 65536

# Rows used while building a LUT — the grid is always 2**(3*bits) rows, so a
# smaller chunk keeps the build allocation modest.
LUT_CHUNK_ROWS = 16384

_LUT_CACHE: Dict[Tuple[bytes, Tuple[int, ...], str, str, int], np.ndarray] = {}


def nearest_indices(
    values: np.ndarray,
    reference: np.ndarray,
    chunk: int = CHUNK_ROWS,
) -> np.ndarray:
    """
    Index of the nearest *reference* row for every row of *values*.

    Both arrays must be ``(N, 3)`` / ``(P, 3)``. The ``(N, P)`` distance
    matrix is evaluated in chunks of *chunk* rows so memory stays bounded
    for large images or long palettes.
    """
    vals = np.asarray(values, dtype=np.float32).reshape(-1, 3)
    ref = np.asarray(reference, dtype=np.float32).reshape(-1, 3)
    if ref.shape[0] == 0:
        raise ValueError("Reference palette is empty")

    n = vals.shape[0]
    out = np.empty(n, dtype=np.int64)
    step = max(1, int(chunk))
    for start in range(0, n, step):
        block = vals[start:start + step]
        diffs = block[:, None, :] - ref[None, :, :]
        dist = np.einsum("ijk,ijk->ij", diffs, diffs)
        out[start:start + step] = np.argmin(dist, axis=1)
    return out


def bin_centers(bits: int = LUT_BITS) -> np.ndarray:
    """Return the representative 0-255 value for each LUT bin."""
    levels = 1 << bits
    step = 256 >> bits
    return (np.arange(levels, dtype=np.float32) * step + step / 2.0).astype(np.float32)


def build_nearest_lut(
    palette: np.ndarray,
    color_space: str = "rgb",
    bits: int = LUT_BITS,
) -> np.ndarray:
    """
    Build (or fetch from cache) a nearest-palette-index lookup table.

    Parameters
    ----------
    palette : np.ndarray
        ``(P, 3)`` array of palette colors, 0-255.
    color_space : str
        ``rgb`` for plain Euclidean RGB distance, ``lab`` to match in
        CIELAB (both bin centers and palette are converted first).
    bits : int
        Bits retained per channel. The table shape is ``(2**bits,) * 3``
        and is indexed with ``lut[r >> (8 - bits), g >> ..., b >> ...]``.

    Returns
    -------
    np.ndarray
        Uint16 array of shape ``(2**bits, 2**bits, 2**bits)``.
    """
    if not 1 <= bits <= 8:
        raise ValueError(f"bits must be in 1..8, got {bits}")

    pal = np.asarray(palette, dtype=np.float32).reshape(-1, 3)
    if pal.shape[0] == 0:
        raise ValueError("Palette is empty")
    if pal.shape[0] > np.iinfo(np.uint16).max + 1:
        raise ValueError("Palette has too many colors for a uint16 LUT")

    space = color_space.lower().strip()
    key = (pal.tobytes(), pal.shape, str(pal.dtype), space, bits)
    cached = _LUT_CACHE.get(key)
    if cached is not None:
        return cached

    centers = bin_centers(bits)
    rr, gg, bb = np.meshgrid(centers, centers, centers, indexing="ij")
    grid = np.stack([rr, gg, bb], axis=-1).reshape(-1, 3)

    grid_match = convert_for_matching(grid, space)
    pal_match = convert_for_matching(pal, space)

    idx = nearest_indices(grid_match, pal_match, chunk=LUT_CHUNK_ROWS)
    levels = 1 << bits
    lut = idx.astype(np.uint16).reshape(levels, levels, levels)
    lut.flags.writeable = False

    _LUT_CACHE[key] = lut
    return lut


class PaletteMatcher:
    """
    Nearest-palette lookup for a fixed palette and color space.

    Wraps a cached 3D LUT so mapping any RGB value to its nearest palette
    index is a single array index, in either plain RGB or perceptual CIELAB.
    The same matcher serves both the fully vectorized no-dither path (a whole
    image at once) and error diffusion (one drifting pixel at a time), so the
    palette is searched once at build time instead of per pixel.
    """

    def __init__(
        self,
        palette: np.ndarray,
        color_space: str = "rgb",
        bits: int = LUT_BITS,
    ) -> None:
        self.palette = np.asarray(palette, dtype=np.float32).reshape(-1, 3)
        self.color_space = color_space.lower().strip()
        self.bits = bits
        self.shift = 8 - bits
        self._lut = build_nearest_lut(self.palette, self.color_space, bits)

    def _bin(self, rgb: np.ndarray) -> np.ndarray:
        # Error diffusion pushes values outside 0..255; clamp before binning so
        # the LUT index stays valid (the tiny snap this costs is imperceptible).
        clamped = np.clip(rgb, 0.0, 255.0)
        return (clamped.astype(np.uint16) >> self.shift)

    def indices(self, rgb: np.ndarray) -> np.ndarray:
        """Nearest palette index for every ``(..., 3)`` RGB value."""
        binned = self._bin(np.asarray(rgb, dtype=np.float32))
        flat = binned.reshape(-1, 3)
        idx = self._lut[flat[:, 0], flat[:, 1], flat[:, 2]]
        return idx.reshape(binned.shape[:-1]).astype(np.int64)

    def nearest(self, rgb: np.ndarray) -> np.ndarray:
        """Nearest palette *color* for every ``(..., 3)`` RGB value."""
        return self.palette[self.indices(rgb)]


def clear_lut_cache() -> None:
    """Drop every cached LUT (used by tests and long-running processes)."""
    _LUT_CACHE.clear()


def lut_cache_size() -> int:
    """Number of LUTs currently cached."""
    return len(_LUT_CACHE)
