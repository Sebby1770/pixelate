"""
Cached nearest-palette lookup tables.

Error diffusion has to pick a palette color for one pixel at a time, which
made the old per-pixel numpy search the slowest part of the pipeline. This
module precomputes, once per ``(palette, space)``, a 3-D table holding the
nearest palette index for every cell of a quantized RGB cube. A lookup then
costs one integer key and one ``bytes`` index — no numpy call per pixel.

The table samples cell centers at ``bits`` per channel (default 6 → 64³ =
262 144 cells, 256 KiB). Decisions can only differ from an exact search for
colors within a couple of RGB units of a Voronoi boundary between two
palette entries, which is invisible after dithering. The exact vectorized
:func:`pixelate.colorspace.nearest_palette_indices` is still used for the
no-dither path, so plain quantization stays byte-identical.

CIEDE2000 tables are exact for palettes up to 32 colors; larger ones use a
CIE76 shortlist (ten nearest Lab colors) re-ranked with CIEDE2000.
"""

from __future__ import annotations

from array import array
from functools import lru_cache
from typing import Sequence, Tuple

import numpy as np

from pixelate.colorspace import ciede2000, srgb_to_lab

SPACES = ("rgb", "lab", "ciede2000")
DEFAULT_BITS = 6
_SHORTLIST = 10
_EXACT_CIEDE = 32
_CHUNK = 1 << 15


def _check_space(space: str) -> str:
    key = str(space).lower().strip()
    if key not in SPACES:
        raise ValueError(
            f"Unknown colorspace '{space}'. Use 'rgb', 'lab', or 'ciede2000'."
        )
    return key


@lru_cache(maxsize=4)
def grid_rgb(bits: int = DEFAULT_BITS) -> np.ndarray:
    """RGB centers of every LUT cell, shape ``(2**(3*bits), 3)`` float64."""
    if not 3 <= bits <= 8:
        raise ValueError("LUT bits must be between 3 and 8")
    step = 256 >> bits
    centers = np.arange(1 << bits, dtype=np.float64) * step + (step - 1) / 2.0
    r, g, b = np.meshgrid(centers, centers, centers, indexing="ij")
    return np.stack([r.ravel(), g.ravel(), b.ravel()], axis=1)


@lru_cache(maxsize=4)
def grid_lab(bits: int = DEFAULT_BITS) -> np.ndarray:
    """CIELAB coordinates of every LUT cell center (palette independent)."""
    return srgb_to_lab(grid_rgb(bits))


@lru_cache(maxsize=2)
def grid_lab_flat(bits: int = DEFAULT_BITS) -> "array[float]":
    """Flat ``array('d')`` of cell Lab triples for fast scalar access."""
    out = array("d")
    out.frombytes(np.ascontiguousarray(grid_lab(bits), dtype=np.float64).tobytes())
    return out


def _nearest_for(points: np.ndarray, pal_points: np.ndarray) -> np.ndarray:
    """Exact Euclidean argmin of each row of *points* against *pal_points*."""
    # |a-b|² = |a|² - 2ab + |b|²; |a|² is constant per row so it can be dropped.
    pal_sq = np.einsum("ij,ij->i", pal_points, pal_points)
    out = np.empty(points.shape[0], dtype=np.uint8)
    for start in range(0, points.shape[0], _CHUNK):
        chunk = points[start:start + _CHUNK]
        score = pal_sq[None, :] - 2.0 * (chunk @ pal_points.T)
        out[start:start + _CHUNK] = np.argmin(score, axis=1)
    return out


def _build(palette: Tuple[Tuple[int, int, int], ...], space: str, bits: int) -> np.ndarray:
    pal = np.asarray(palette, dtype=np.float64)
    if space == "rgb":
        return _nearest_for(grid_rgb(bits), pal)

    pal_lab = srgb_to_lab(pal)
    lab = grid_lab(bits)
    if space == "lab" or pal.shape[0] == 1:
        return _nearest_for(lab, pal_lab)

    # CIEDE2000: exact for small palettes; larger ones use a CIE76 shortlist
    # re-ranked with CIEDE2000 (agrees with the exact search on >99% of cells).
    k = pal.shape[0] if pal.shape[0] <= _EXACT_CIEDE else _SHORTLIST
    pal_sq = np.einsum("ij,ij->i", pal_lab, pal_lab)
    out = np.empty(lab.shape[0], dtype=np.uint8)
    for start in range(0, lab.shape[0], _CHUNK):
        chunk = lab[start:start + _CHUNK]
        score = pal_sq[None, :] - 2.0 * (chunk @ pal_lab.T)
        short = np.argpartition(score, k - 1, axis=1)[:, :k]
        cand = pal_lab[short]  # (n, k, 3)
        d = np.asarray(ciede2000(chunk[:, None, :], cand))  # broadcast → (n, k)
        best = np.argmin(d, axis=1)
        out[start:start + _CHUNK] = short[np.arange(short.shape[0]), best]
    return out


@lru_cache(maxsize=32)
def _cached(palette: Tuple[Tuple[int, int, int], ...], space: str, bits: int) -> bytes:
    return _build(palette, space, bits).tobytes()


class PaletteLUT:
    """Nearest-palette lookup table for one palette in one matching space."""

    __slots__ = ("palette", "space", "bits", "table", "_shift", "_array")

    def __init__(
        self,
        palette: Sequence[Sequence[float]],
        space: str = "lab",
        bits: int = DEFAULT_BITS,
    ) -> None:
        pal = tuple(
            (int(round(float(c[0]))), int(round(float(c[1]))), int(round(float(c[2]))))
            for c in palette
        )
        if not pal:
            raise ValueError("Palette must contain at least one color")
        if len(pal) > 256:
            raise ValueError("LUT palettes are limited to 256 colors")
        self.palette = pal
        self.space = _check_space(space)
        self.bits = int(bits)
        self.table: bytes = _cached(pal, self.space, self.bits)
        self._shift = 8 - self.bits
        self._array = np.frombuffer(self.table, dtype=np.uint8)

    def key(self, r: float, g: float, b: float) -> int:
        """Table key for an (unclamped, float) RGB value."""
        s, bits = self._shift, self.bits
        ri = 0 if r <= 0 else 255 if r >= 255 else int(r)
        gi = 0 if g <= 0 else 255 if g >= 255 else int(g)
        bi = 0 if b <= 0 else 255 if b >= 255 else int(b)
        return ((ri >> s) << (2 * bits)) | ((gi >> s) << bits) | (bi >> s)

    def index(self, r: float, g: float, b: float) -> int:
        """Nearest palette index for a single color."""
        return self.table[self.key(r, g, b)]

    def indices(self, pixels: np.ndarray) -> np.ndarray:
        """Vectorized lookup for an ``(..., 3)`` array; returns ``(...)`` uint8."""
        arr = np.clip(np.asarray(pixels, dtype=np.float64), 0, 255).astype(np.int64)
        s, bits = self._shift, self.bits
        keys = ((arr[..., 0] >> s) << (2 * bits)) | ((arr[..., 1] >> s) << bits) | (arr[..., 2] >> s)
        return self._array[keys]


def palette_lut(
    palette: Sequence[Sequence[float]],
    space: str = "lab",
    bits: int = DEFAULT_BITS,
) -> PaletteLUT:
    """Return a (cached) :class:`PaletteLUT` for *palette* in *space*."""
    return PaletteLUT(palette, space=space, bits=bits)


def clear_cache() -> None:
    """Drop every cached table (mainly for tests and benchmarks)."""
    _cached.cache_clear()
