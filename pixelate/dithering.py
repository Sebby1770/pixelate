"""
Dithering algorithms.

These take an RGB image (numpy array, float) and a palette (numpy array of
RGB rows) and produce an image where each pixel has been mapped to a palette
color, with quantization error hidden as diffused noise or a regular pattern.

Nearest-color matching defaults to CIE L*a*b* (CIE76). Pass ``space="rgb"``
for classic Euclidean RGB, or ``space="ciede2000"`` for CIEDE2000.

Three families are available:

* **Error diffusion** (floyd, atkinson, stucki, burkes, sierra, sierra3,
  sierra-lite, jjn) — serpentine by default. Runs on a padded scalar buffer
  with a cached nearest-palette LUT (:mod:`pixelate.lut`), roughly 7–20×
  faster than the old per-pixel numpy search.
* **Ordered threshold** (bayer) — the classic crosshatch.
* **Pattern dithering** (pattern, bluenoise, halftone) — Thomas Knoll's
  candidate-mixing algorithm (as described by Joel Yliluoma). For every
  pixel a mix of palette colors that averages to the source is built and
  one is picked by a threshold map: a Bayer matrix (``pattern``), a
  void-and-cluster blue-noise mask (``bluenoise``) or a clustered-dot
  matrix (``halftone``). Fully vectorized and palette-aware, so it looks
  far better than plain Bayer on small, irregular retro palettes.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Callable, Dict, List, Optional, Tuple

import numpy as np

from pixelate.colorspace import ciede2000, nearest_palette_indices, srgb_to_lab
from pixelate.lut import palette_lut

# (dy, dx, weight) — error distribution kernels
Kernel = List[Tuple[int, int, float]]

KERNELS: Dict[str, Kernel] = {
    "floyd": [(0, 1, 7 / 16), (1, -1, 3 / 16), (1, 0, 5 / 16), (1, 1, 1 / 16)],
    "atkinson": [
        (0, 1, 1 / 8), (0, 2, 1 / 8),
        (1, -1, 1 / 8), (1, 0, 1 / 8), (1, 1, 1 / 8),
        (2, 0, 1 / 8),
    ],
    "stucki": [
        (0, 1, 8 / 42), (0, 2, 4 / 42),
        (1, -2, 2 / 42), (1, -1, 4 / 42), (1, 0, 8 / 42), (1, 1, 4 / 42), (1, 2, 2 / 42),
        (2, -2, 1 / 42), (2, -1, 2 / 42), (2, 0, 4 / 42), (2, 1, 2 / 42), (2, 2, 1 / 42),
    ],
    "burkes": [
        (0, 1, 8 / 32), (0, 2, 4 / 32),
        (1, -2, 2 / 32), (1, -1, 4 / 32), (1, 0, 8 / 32), (1, 1, 4 / 32), (1, 2, 2 / 32),
    ],
    "sierra": [
        (0, 1, 4 / 16), (0, 2, 3 / 16),
        (1, -2, 1 / 16), (1, -1, 2 / 16), (1, 0, 3 / 16), (1, 1, 2 / 16), (1, 2, 1 / 16),
    ],
    "sierra3": [
        (0, 1, 5 / 32), (0, 2, 3 / 32),
        (1, -2, 2 / 32), (1, -1, 4 / 32), (1, 0, 5 / 32), (1, 1, 4 / 32), (1, 2, 2 / 32),
        (2, -1, 2 / 32), (2, 0, 3 / 32), (2, 1, 2 / 32),
    ],
    "sierra-lite": [(0, 1, 2 / 4), (1, -1, 1 / 4), (1, 0, 1 / 4)],
    "jjn": [
        (0, 1, 7 / 48), (0, 2, 5 / 48),
        (1, -2, 3 / 48), (1, -1, 5 / 48), (1, 0, 7 / 48), (1, 1, 5 / 48), (1, 2, 3 / 48),
        (2, -2, 1 / 48), (2, -1, 3 / 48), (2, 0, 5 / 48), (2, 1, 3 / 48), (2, 2, 1 / 48),
    ],
}

_PAD = 2  # every kernel reaches at most 2 px sideways / down


def _palette_lab(palette: np.ndarray) -> np.ndarray:
    return srgb_to_lab(np.clip(np.asarray(palette, dtype=np.float64), 0, 255))


def _check_space(space: str) -> str:
    key = str(space).lower().strip()
    if key not in ("rgb", "lab", "ciede2000"):
        raise ValueError(
            f"Unknown colorspace '{space}'. Use 'rgb', 'lab', or 'ciede2000'."
        )
    return key


def _nearest_color(
    pixel: np.ndarray,
    palette: np.ndarray,
    space: str = "lab",
    palette_lab: Optional[np.ndarray] = None,
) -> np.ndarray:
    """Return the palette color closest to `pixel` (exact; Lab, CIEDE2000, or RGB)."""
    pix = np.clip(np.asarray(pixel, dtype=np.float64).reshape(1, 3), 0, 255)
    key = _check_space(space)
    if key == "rgb":
        diffs = palette.astype(np.float64) - pix.reshape(3)
        return palette[int(np.argmin(np.einsum("ij,ij->i", diffs, diffs)))]
    if palette_lab is None:
        palette_lab = _palette_lab(palette)
    pix_lab = srgb_to_lab(pix)
    if key == "ciede2000":
        return palette[int(np.argmin(ciede2000(pix_lab, palette_lab).reshape(-1)))]
    diffs = palette_lab - pix_lab
    return palette[int(np.argmin(np.einsum("ij,ij->i", diffs, diffs)))]


def quantize_no_dither(
    image: np.ndarray,
    palette: np.ndarray,
    space: str = "lab",
    serpentine: bool = True,  # unused; accepted so dither_image can pass it
) -> np.ndarray:
    """Map each pixel to the nearest palette color (exact, vectorized)."""
    del serpentine
    h, w, _ = image.shape
    flat = np.clip(np.asarray(image).reshape(-1, 3), 0, 255)
    idx = nearest_palette_indices(flat, palette, space=space)
    out = np.asarray(palette)[idx].reshape(h, w, 3)
    return np.clip(out, 0, 255).astype(np.uint8)


# ---------------------------------------------------------------------------
# Error diffusion engine
# ---------------------------------------------------------------------------

def diffuse_indices(
    image: np.ndarray,
    palette: np.ndarray,
    kernel: Kernel,
    serpentine: bool = True,
    space: str = "lab",
) -> np.ndarray:
    """
    Error-diffuse *image* onto *palette* and return palette indices ``(H, W)``.

    The image lives in a flat Python float list padded by two pixels on the
    left, right and bottom, so kernel taps never need bounds checks; error
    that lands in the padding is discarded (same as clipping at the edge).
    Nearest colors come from a cached :class:`pixelate.lut.PaletteLUT`.
    """
    img = np.asarray(image, dtype=np.float64)
    h, w = img.shape[:2]
    pal = np.asarray(palette, dtype=np.float64).reshape(-1, 3)
    lut = palette_lut(pal, space=_check_space(space))
    table = lut.table
    shift = 8 - lut.bits
    bits = lut.bits
    pr = [float(c[0]) for c in pal]
    pg = [float(c[1]) for c in pal]
    pb = [float(c[2]) for c in pal]

    pw = w + 2 * _PAD
    stride = pw * 3
    padded = np.zeros((h + _PAD, pw, 3), dtype=np.float64)
    padded[:h, _PAD:_PAD + w] = img
    buf = padded.ravel().tolist()

    fwd = [(dy * stride + dx * 3, wt) for dy, dx, wt in kernel]
    rev = [(dy * stride - dx * 3, wt) for dy, dx, wt in kernel]
    out = bytearray(h * w)

    for y in range(h):
        reverse = serpentine and (y & 1) == 1
        taps = rev if reverse else fwd
        row = y * stride + _PAD * 3
        xs = range(w - 1, -1, -1) if reverse else range(w)
        orow = y * w
        for x in xs:
            i = row + x * 3
            r = buf[i]
            g = buf[i + 1]
            b = buf[i + 2]
            ri = 0 if r <= 0.0 else 255 if r >= 255.0 else int(r)
            gi = 0 if g <= 0.0 else 255 if g >= 255.0 else int(g)
            bi = 0 if b <= 0.0 else 255 if b >= 255.0 else int(b)
            k = table[((ri >> shift) << (bits + bits)) | ((gi >> shift) << bits) | (bi >> shift)]
            out[orow + x] = k
            er = r - pr[k]
            eg = g - pg[k]
            eb = b - pb[k]
            for off, wt in taps:
                j = i + off
                buf[j] += er * wt
                buf[j + 1] += eg * wt
                buf[j + 2] += eb * wt

    return np.frombuffer(bytes(out), dtype=np.uint8).reshape(h, w)


def _error_diffuse(
    image: np.ndarray,
    palette: np.ndarray,
    kernel: Kernel,
    serpentine: bool = True,
    space: str = "lab",
) -> np.ndarray:
    """Generic error-diffusion dither using an (dy, dx, weight) kernel."""
    pal = np.asarray(palette)
    idx = diffuse_indices(image, pal, kernel, serpentine=serpentine, space=space)
    return np.clip(pal[idx], 0, 255).astype(np.uint8)


def _make_diffuser(name: str, doc: str) -> Callable[..., np.ndarray]:
    kernel = KERNELS[name]

    def fn(
        image: np.ndarray,
        palette: np.ndarray,
        space: str = "lab",
        serpentine: bool = True,
    ) -> np.ndarray:
        return _error_diffuse(image, palette, kernel, serpentine=serpentine, space=space)

    fn.__doc__ = doc
    fn.__name__ = name.replace("-", "_")
    return fn


floyd_steinberg = _make_diffuser(
    "floyd", "Floyd-Steinberg error diffusion (7/16, 3/16, 5/16, 1/16)."
)
atkinson = _make_diffuser(
    "atkinson",
    "Atkinson dithering (original Macintosh): diffuses 6/8 of the error, "
    "keeping contrast crisp.",
)
stucki = _make_diffuser("stucki", "Stucki error diffusion (12 taps, div 42).")
burkes = _make_diffuser("burkes", "Burkes error diffusion (two rows, div 32).")
sierra = _make_diffuser(
    "sierra",
    "Sierra-2 error diffusion (div 16). Not Sierra Lite — see sierra_lite().",
)
sierra3 = _make_diffuser(
    "sierra3", "Sierra-3 error diffusion (div 32; 5,3 / 2,4,5,4,2 / 2,3,2)."
)
sierra_lite = _make_diffuser(
    "sierra-lite", "Sierra Lite / Filter Lite (2/4 right, 1/4 down-left, 1/4 down)."
)
jarvis_judice_ninke = _make_diffuser(
    "jjn", "Jarvis-Judice-Ninke error diffusion (12-element kernel, div 48)."
)
# Short alias used by the CLI / DITHER_ALGORITHMS registry
jjn = jarvis_judice_ninke


# ---------------------------------------------------------------------------
# Threshold maps
# ---------------------------------------------------------------------------

def bayer_matrix(size: int) -> np.ndarray:
    """Normalized Bayer index matrix in ``[0, 1)`` for size 2, 4, 8 or 16."""
    if size not in (2, 4, 8, 16):
        raise ValueError("Bayer matrix size must be 2, 4, 8 or 16")
    m = np.array([[0, 2], [3, 1]], dtype=np.int64)
    while m.shape[0] < size:
        m = np.block([[4 * m, 4 * m + 2], [4 * m + 3, 4 * m + 1]])
    return m.astype(np.float64) / float(size * size)


# Classic 4x4 clustered-dot (spiral) screen — halftone print look.
_CLUSTER_4 = np.array(
    [
        [12, 5, 6, 13],
        [4, 0, 1, 7],
        [11, 3, 2, 8],
        [15, 10, 9, 14],
    ],
    dtype=np.float64,
)


def halftone_matrix() -> np.ndarray:
    """8x8 clustered-dot threshold map in ``[0, 1)`` (two offset 4x4 dots)."""
    a = _CLUSTER_4
    b = 15 - _CLUSTER_4  # complementary dot fills the gaps → 45° screen
    tile = np.block([[a, b], [b, a]])
    order = np.argsort(np.argsort(tile.ravel(), kind="stable"), kind="stable")
    return order.reshape(8, 8).astype(np.float64) / 64.0


@lru_cache(maxsize=4)
def blue_noise(size: int = 64, sigma: float = 1.5, seed: int = 7) -> np.ndarray:
    """
    Void-and-cluster blue-noise threshold map (Ulichney 1993), ``[0, 1)``.

    Deterministic for a given *seed*; computed once and cached (~0.1 s for
    64x64). Energy is a toroidal Gaussian, updated incrementally with rolls.
    """
    n = size * size
    rng = np.random.default_rng(seed)
    yy, xx = np.mgrid[0:size, 0:size]
    dy = np.minimum(yy, size - yy)
    dx = np.minimum(xx, size - xx)
    kernel = np.exp(-(dx * dx + dy * dy) / (2.0 * sigma * sigma))

    def splat(energy: np.ndarray, idx: int, sign: float) -> None:
        y, x = divmod(idx, size)
        energy += sign * np.roll(np.roll(kernel, y, axis=0), x, axis=1)

    ones = n // 10
    pattern = np.zeros(n, dtype=bool)
    pattern[rng.choice(n, size=ones, replace=False)] = True
    energy = np.zeros((size, size))
    for idx in np.flatnonzero(pattern):
        splat(energy, int(idx), 1.0)

    # Phase 0 — relax the initial pattern into an even distribution.
    for _ in range(n):
        flat = energy.ravel()
        cluster = int(np.argmax(np.where(pattern, flat, -np.inf)))
        pattern[cluster] = False
        splat(energy, cluster, -1.0)
        flat = energy.ravel()
        void = int(np.argmin(np.where(pattern, np.inf, flat)))
        if void == cluster:
            pattern[cluster] = True
            splat(energy, cluster, 1.0)
            break
        pattern[void] = True
        splat(energy, void, 1.0)

    rank = np.zeros(n, dtype=np.int64)
    # Phase 1 — rank the initial ones by removing tightest clusters.
    proto = pattern.copy()
    e1 = energy.copy()
    for r in range(ones - 1, -1, -1):
        flat = e1.ravel()
        cluster = int(np.argmax(np.where(proto, flat, -np.inf)))
        proto[cluster] = False
        splat(e1, cluster, -1.0)
        rank[cluster] = r
    # Phase 2/3 — fill the largest voids until the map is full.
    for r in range(ones, n):
        flat = energy.ravel()
        void = int(np.argmin(np.where(pattern, np.inf, flat)))
        pattern[void] = True
        splat(energy, void, 1.0)
        rank[void] = r

    return (rank.reshape(size, size).astype(np.float64)) / float(n)


def _tile(matrix: np.ndarray, h: int, w: int) -> np.ndarray:
    mh, mw = matrix.shape
    return np.tile(matrix, (h // mh + 1, w // mw + 1))[:h, :w]


# ---------------------------------------------------------------------------
# Ordered (Bayer threshold) dithering
# ---------------------------------------------------------------------------

def ordered_bayer(
    image: np.ndarray,
    palette: np.ndarray,
    matrix_size: int = 4,
    space: str = "lab",
    serpentine: bool = True,
) -> np.ndarray:
    """
    Ordered (Bayer) dithering — produces the iconic crosshatched pattern.

    Adds a threshold pattern from a Bayer matrix before quantization, so
    error becomes a regular geometric texture rather than diffused noise.
    """
    del serpentine
    if matrix_size not in (2, 4, 8):
        raise ValueError("matrix_size must be 2, 4, or 8")
    h, w, _ = image.shape
    threshold = _tile(bayer_matrix(matrix_size), h, w)
    # Scale threshold contribution; 32 is a balanced spread for 8-bit RGB
    img = image.astype(np.float32) + (threshold[..., None] - 0.5) * 32.0
    return quantize_no_dither(np.clip(img, 0, 255), palette, space=space)


# ---------------------------------------------------------------------------
# Knoll pattern dithering
# ---------------------------------------------------------------------------

PATTERN_CANDIDATES = 16
PATTERN_ERROR_MULTIPLIER = 0.75


def pattern_indices(
    image: np.ndarray,
    palette: np.ndarray,
    threshold: np.ndarray,
    space: str = "lab",
    candidates: int = PATTERN_CANDIDATES,
    multiplier: float = PATTERN_ERROR_MULTIPLIER,
) -> np.ndarray:
    """
    Thomas Knoll's pattern dither → palette indices ``(H, W)``.

    For each pixel, *candidates* palette picks are accumulated so their mean
    tracks the source color (each pick sees the running error, scaled by
    *multiplier*). Candidates are sorted by luminance and the threshold map
    chooses one. Every step is vectorized over the whole image.
    """
    img = np.clip(np.asarray(image, dtype=np.float64), 0, 255)
    h, w = img.shape[:2]
    pal = np.asarray(palette, dtype=np.float64).reshape(-1, 3)
    if pal.shape[0] == 1:
        return np.zeros((h, w), dtype=np.uint8)
    lut = palette_lut(pal, space=_check_space(space))
    n = max(2, int(candidates))
    picks = np.empty((n, h, w), dtype=np.uint8)
    error = np.zeros_like(img)
    for c in range(n):
        attempt = img + error * multiplier
        idx = lut.indices(attempt)
        picks[c] = idx
        error += img - pal[idx]

    luma = pal @ np.array([0.299, 0.587, 0.114])
    order = np.argsort(luma[picks], axis=0, kind="stable")
    sorted_picks = np.take_along_axis(picks, order, axis=0)
    t = _tile(np.asarray(threshold, dtype=np.float64), h, w)
    which = np.clip((t * n).astype(np.int64), 0, n - 1)
    return np.take_along_axis(sorted_picks, which[None], axis=0)[0]


def _pattern_rgb(image: np.ndarray, palette: np.ndarray, threshold: np.ndarray, space: str) -> np.ndarray:
    pal = np.asarray(palette)
    idx = pattern_indices(image, pal, threshold, space=space)
    return np.clip(pal[idx], 0, 255).astype(np.uint8)


def pattern(
    image: np.ndarray,
    palette: np.ndarray,
    space: str = "lab",
    serpentine: bool = True,
) -> np.ndarray:
    """Knoll pattern dithering over an 8x8 Bayer map — clean, palette-aware ordered dither."""
    del serpentine
    return _pattern_rgb(image, palette, bayer_matrix(8), space)


def bluenoise(
    image: np.ndarray,
    palette: np.ndarray,
    space: str = "lab",
    serpentine: bool = True,
) -> np.ndarray:
    """Knoll pattern dithering over a void-and-cluster blue-noise mask — organic, grain-free."""
    del serpentine
    return _pattern_rgb(image, palette, blue_noise(), space)


def halftone(
    image: np.ndarray,
    palette: np.ndarray,
    space: str = "lab",
    serpentine: bool = True,
) -> np.ndarray:
    """Knoll pattern dithering over a clustered-dot screen — newsprint / comic halftone."""
    del serpentine
    return _pattern_rgb(image, palette, halftone_matrix(), space)


DITHER_ALGORITHMS: dict[str, Callable[..., np.ndarray]] = {
    "none": quantize_no_dither,
    "floyd": floyd_steinberg,
    "atkinson": atkinson,
    "bayer": ordered_bayer,
    "stucki": stucki,
    "burkes": burkes,
    "sierra": sierra,
    "sierra3": sierra3,
    "sierra-lite": sierra_lite,
    "sierra_lite": sierra_lite,
    "jjn": jarvis_judice_ninke,
    "pattern": pattern,
    "bluenoise": bluenoise,
    "halftone": halftone,
}

# Accepted spellings that are not listed as CLI choices.
DITHER_ALIASES = {
    "floyd-steinberg": "floyd",
    "fs": "floyd",
    "knoll": "pattern",
    "blue-noise": "bluenoise",
    "blue_noise": "bluenoise",
    "ordered": "bayer",
}

DITHER_DESCRIPTIONS = {
    "none": "nearest color only",
    "floyd": "Floyd-Steinberg error diffusion",
    "atkinson": "Atkinson (classic Mac), crisp 6/8 diffusion",
    "bayer": "ordered Bayer crosshatch (--bayer-size)",
    "stucki": "Stucki, wide smooth diffusion",
    "burkes": "Burkes, two-row diffusion",
    "sierra": "Sierra-2 diffusion",
    "sierra3": "Sierra-3 diffusion",
    "sierra-lite": "Sierra Lite, fast 3-tap diffusion",
    "jjn": "Jarvis-Judice-Ninke, 12-tap diffusion",
    "pattern": "Knoll pattern dither (Bayer 8x8), palette-aware",
    "bluenoise": "Knoll pattern dither over blue noise, grain-free",
    "halftone": "clustered-dot halftone screen",
}


def _canonical(name: str) -> str:
    key = str(name).lower().strip()
    return DITHER_ALIASES.get(key, key)


def get_dither(name: str) -> Callable[..., np.ndarray]:
    """Return a dithering function by name (aliases accepted)."""
    key = _canonical(name)
    if key not in DITHER_ALGORITHMS:
        available = ", ".join(DITHER_ALGORITHMS)
        raise KeyError(f"Unknown dither '{name}'. Available: {available}")
    return DITHER_ALGORITHMS[key]


def dither_indices(
    image: np.ndarray,
    palette: np.ndarray,
    name: str,
    space: str = "lab",
    serpentine: bool = True,
    bayer_size: int = 4,
) -> np.ndarray:
    """Like :func:`dither_image` but returns palette indices ``(H, W)`` uint8."""
    key = _canonical(name)
    get_dither(key)  # validate
    pal = np.asarray(palette, dtype=np.float64).reshape(-1, 3)
    if key in KERNELS or key == "sierra_lite":
        kernel = KERNELS["sierra-lite" if key == "sierra_lite" else key]
        return diffuse_indices(image, pal, kernel, serpentine=serpentine, space=space)
    if key == "pattern":
        return pattern_indices(image, pal, bayer_matrix(8), space=space)
    if key == "bluenoise":
        return pattern_indices(image, pal, blue_noise(), space=space)
    if key == "halftone":
        return pattern_indices(image, pal, halftone_matrix(), space=space)
    if key == "bayer":
        size = int(bayer_size)
        if size not in (2, 4, 8):
            raise ValueError("bayer_size must be 2, 4, or 8")
        h, w = np.asarray(image).shape[:2]
        t = _tile(bayer_matrix(size), h, w)
        img = np.clip(np.asarray(image, dtype=np.float64) + (t[..., None] - 0.5) * 32.0, 0, 255)
        return nearest_palette_indices(img.reshape(-1, 3), pal, space=space).reshape(h, w).astype(np.uint8)
    h, w = np.asarray(image).shape[:2]
    flat = np.clip(np.asarray(image, dtype=np.float64).reshape(-1, 3), 0, 255)
    return nearest_palette_indices(flat, pal, space=space).reshape(h, w).astype(np.uint8)


def dither_image(
    image: np.ndarray,
    palette: np.ndarray,
    name: str,
    space: str = "lab",
    serpentine: bool = True,
    bayer_size: int = 4,
) -> np.ndarray:
    """
    Apply a named dither with matching space and serpentine scanning.

    All pipeline callers should use this rather than invoking kernel
    functions directly, so Lab matching and serpentine stay consistent.

    *bayer_size* is used only when *name* is ``"bayer"`` (2, 4, or 8).
    """
    fn = get_dither(name)
    key = _canonical(name)
    if key == "bayer":
        size = int(bayer_size)
        if size not in (2, 4, 8):
            raise ValueError("bayer_size must be 2, 4, or 8")
        out = fn(image, palette, matrix_size=size, space=space, serpentine=serpentine)
    else:
        out = fn(image, palette, space=space, serpentine=serpentine)
    return np.clip(out, 0, 255).astype(np.uint8)
