"""
Dithering algorithms.

These take an RGB image (numpy array, float) and a palette (numpy array of
RGB rows) and produce an image where each pixel has been mapped to the
nearest palette color, with quantization error spread to neighboring pixels
to preserve perceived detail.

Nearest-color matching defaults to CIE L*a*b* (CIE76). Pass ``space="rgb"``
for classic Euclidean RGB, or ``space="ciede2000"`` for CIEDE2000. Error-diffusion
kernels default to serpentine scanning (even rows L→R, odd rows R→L with the
kernel's dx mirrored).
"""

from __future__ import annotations

from typing import Callable, List, Optional, Tuple

import numpy as np

from pixelate.colorspace import ciede2000, nearest_palette_indices, srgb_to_lab

# (dy, dx, weight) — error distribution kernels
Kernel = List[Tuple[int, int, float]]


def _palette_lab(palette: np.ndarray) -> np.ndarray:
    return srgb_to_lab(np.clip(np.asarray(palette, dtype=np.float64), 0, 255))


def _nearest_color(
    pixel: np.ndarray,
    palette: np.ndarray,
    space: str = "lab",
    palette_lab: Optional[np.ndarray] = None,
) -> np.ndarray:
    """Return the palette color closest to `pixel` (Lab CIE76, CIEDE2000, or RGB)."""
    pix = np.clip(np.asarray(pixel, dtype=np.float64).reshape(1, 3), 0, 255)
    key = str(space).lower().strip()
    if key == "rgb":
        diffs = palette.astype(np.float64) - pix.reshape(3)
        distances = np.einsum("ij,ij->i", diffs, diffs)
        return palette[int(np.argmin(distances))]
    if key not in ("lab", "ciede2000"):
        raise ValueError(
            f"Unknown colorspace '{space}'. Use 'rgb', 'lab', or 'ciede2000'."
        )
    if palette_lab is None:
        palette_lab = _palette_lab(palette)
    pix_lab = srgb_to_lab(pix)
    if key == "ciede2000":
        distances = ciede2000(pix_lab, palette_lab).reshape(-1)
        return palette[int(np.argmin(distances))]
    diffs = palette_lab - pix_lab
    distances = np.einsum("ij,ij->i", diffs, diffs)
    return palette[int(np.argmin(distances))]


def quantize_no_dither(
    image: np.ndarray,
    palette: np.ndarray,
    space: str = "lab",
    serpentine: bool = True,  # unused; accepted so dither_image can pass it
) -> np.ndarray:
    """Map each pixel to the nearest palette color (vectorized, no dithering)."""
    del serpentine
    h, w, _ = image.shape
    flat = np.clip(np.asarray(image).reshape(-1, 3), 0, 255)
    idx = nearest_palette_indices(flat, palette, space=space)
    out = np.asarray(palette)[idx].reshape(h, w, 3)
    return np.clip(out, 0, 255).astype(np.uint8)


def _error_diffuse(
    image: np.ndarray,
    palette: np.ndarray,
    kernel: Kernel,
    serpentine: bool = True,
    space: str = "lab",
) -> np.ndarray:
    """Generic error-diffusion dither using an (dy, dx, weight) kernel."""
    img = image.astype(np.float32).copy()
    h, w, _ = img.shape
    pal = np.asarray(palette, dtype=np.float32)
    pal_lab = (
        _palette_lab(pal)
        if str(space).lower().strip() in ("lab", "ciede2000")
        else None
    )

    for y in range(h):
        reverse = bool(serpentine) and (y % 2 == 1)
        xs = range(w - 1, -1, -1) if reverse else range(w)
        for x in xs:
            old = img[y, x].copy()
            new = _nearest_color(old, pal, space=space, palette_lab=pal_lab)
            img[y, x] = new
            error = old - new

            for dy, dx, weight in kernel:
                if reverse:
                    dx = -dx
                ny, nx = y + dy, x + dx
                if 0 <= ny < h and 0 <= nx < w:
                    img[ny, nx] += error * weight

    return np.clip(img, 0, 255).astype(np.uint8)


def floyd_steinberg(
    image: np.ndarray,
    palette: np.ndarray,
    space: str = "lab",
    serpentine: bool = True,
) -> np.ndarray:
    """
    Floyd-Steinberg error diffusion dithering.

    Diffuses quantization error to neighboring pixels using the classic
    7/16, 3/16, 5/16, 1/16 distribution. Serpentine scanning is on by default.
    """
    kernel: Kernel = [
        (0, 1, 7 / 16),
        (1, -1, 3 / 16),
        (1, 0, 5 / 16),
        (1, 1, 1 / 16),
    ]
    return _error_diffuse(image, palette, kernel, serpentine=serpentine, space=space)


def atkinson(
    image: np.ndarray,
    palette: np.ndarray,
    space: str = "lab",
    serpentine: bool = True,
) -> np.ndarray:
    """
    Atkinson dithering — used by the original Apple Macintosh.

    Diffuses 6/8 of the error (lighter than Floyd-Steinberg), which preserves
    contrast and produces a distinctive crisp look.
    """
    img = image.astype(np.float32).copy()
    h, w, _ = img.shape
    pal = np.asarray(palette, dtype=np.float32)
    pal_lab = (
        _palette_lab(pal)
        if str(space).lower().strip() in ("lab", "ciede2000")
        else None
    )
    offsets = [(0, 1), (0, 2), (1, -1), (1, 0), (1, 1), (2, 0)]

    for y in range(h):
        reverse = bool(serpentine) and (y % 2 == 1)
        xs = range(w - 1, -1, -1) if reverse else range(w)
        for x in xs:
            old = img[y, x].copy()
            new = _nearest_color(old, pal, space=space, palette_lab=pal_lab)
            img[y, x] = new
            error = (old - new) / 8.0

            for dy, dx in offsets:
                if reverse:
                    dx = -dx
                ny, nx = y + dy, x + dx
                if 0 <= ny < h and 0 <= nx < w:
                    img[ny, nx] += error

    return np.clip(img, 0, 255).astype(np.uint8)


def stucki(
    image: np.ndarray,
    palette: np.ndarray,
    space: str = "lab",
    serpentine: bool = True,
) -> np.ndarray:
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
    return _error_diffuse(image, palette, kernel, serpentine=serpentine, space=space)


def burkes(
    image: np.ndarray,
    palette: np.ndarray,
    space: str = "lab",
    serpentine: bool = True,
) -> np.ndarray:
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
    return _error_diffuse(image, palette, kernel, serpentine=serpentine, space=space)


def sierra(
    image: np.ndarray,
    palette: np.ndarray,
    space: str = "lab",
    serpentine: bool = True,
) -> np.ndarray:
    """
    Sierra-2 (two-row) error diffusion.

    Classic Sierra-2 kernel (div 16). This is not Sierra Filter Lite
    (Sierra-2-4A), which uses a 3-element 1/2 + 1/4 + 1/4 kernel.
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
    return _error_diffuse(image, palette, kernel, serpentine=serpentine, space=space)


def sierra3(
    image: np.ndarray,
    palette: np.ndarray,
    space: str = "lab",
    serpentine: bool = True,
) -> np.ndarray:
    """
    Sierra-3 (three-row) error diffusion.

    Classic Sierra kernel (div 32): 5, 3 on the current row; 2, 4, 5, 4, 2
    on the next; 2, 3, 2 on the row after.
    """
    kernel: Kernel = [
        (0, 1, 5 / 32),
        (0, 2, 3 / 32),
        (1, -2, 2 / 32),
        (1, -1, 4 / 32),
        (1, 0, 5 / 32),
        (1, 1, 4 / 32),
        (1, 2, 2 / 32),
        (2, -1, 2 / 32),
        (2, 0, 3 / 32),
        (2, 1, 2 / 32),
    ]
    return _error_diffuse(image, palette, kernel, serpentine=serpentine, space=space)


def sierra_lite(
    image: np.ndarray,
    palette: np.ndarray,
    space: str = "lab",
    serpentine: bool = True,
) -> np.ndarray:
    """
    Sierra Filter Lite (Sierra-2-4A) error diffusion.

    Three-element kernel (div 4): ``(0, 1, 2/4)``, ``(1, -1, 1/4)``,
    ``(1, 0, 1/4)``.
    """
    kernel: Kernel = [
        (0, 1, 2 / 4),
        (1, -1, 1 / 4),
        (1, 0, 1 / 4),
    ]
    return _error_diffuse(image, palette, kernel, serpentine=serpentine, space=space)


def jarvis_judice_ninke(
    image: np.ndarray,
    palette: np.ndarray,
    space: str = "lab",
    serpentine: bool = True,
) -> np.ndarray:
    """
    Jarvis-Judice-Ninke error diffusion (12-element kernel, div 48).

    Wider than Floyd-Steinberg; smoother gradients, more of a "classic
    print dither" look.
    """
    kernel: Kernel = [
        (0, 1, 7 / 48),
        (0, 2, 5 / 48),
        (1, -2, 3 / 48),
        (1, -1, 5 / 48),
        (1, 0, 7 / 48),
        (1, 1, 5 / 48),
        (1, 2, 3 / 48),
        (2, -2, 1 / 48),
        (2, -1, 3 / 48),
        (2, 0, 5 / 48),
        (2, 1, 3 / 48),
        (2, 2, 1 / 48),
    ]
    return _error_diffuse(image, palette, kernel, serpentine=serpentine, space=space)


# Short alias used by the CLI / DITHER_ALGORITHMS registry
jjn = jarvis_judice_ninke


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
    if matrix_size == 2:
        bayer = np.array([[0, 2], [3, 1]]) / 4.0
    elif matrix_size == 4:
        bayer = np.array([
            [0, 8, 2, 10],
            [12, 4, 14, 6],
            [3, 11, 1, 9],
            [15, 7, 13, 5],
        ]) / 16.0
    elif matrix_size == 8:
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
    else:
        raise ValueError("matrix_size must be 2, 4, or 8")

    h, w, _ = image.shape
    bh, bw = bayer.shape
    threshold = np.tile(bayer, (h // bh + 1, w // bw + 1))[:h, :w]
    # Scale threshold contribution; 32 is a balanced spread for 8-bit RGB
    img = image.astype(np.float32) + (threshold[..., None] - 0.5) * 32.0
    img = np.clip(img, 0, 255)
    return quantize_no_dither(img, palette, space=space)


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
}


def get_dither(name: str) -> Callable[..., np.ndarray]:
    """Return a dithering function by name."""
    key = name.lower().strip()
    if key not in DITHER_ALGORITHMS:
        available = ", ".join(DITHER_ALGORITHMS)
        raise KeyError(f"Unknown dither '{name}'. Available: {available}")
    return DITHER_ALGORITHMS[key]


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
    key = name.lower().strip()
    if key == "bayer":
        size = int(bayer_size)
        if size not in (2, 4, 8):
            raise ValueError("bayer_size must be 2, 4, or 8")
        out = fn(
            image, palette, matrix_size=size, space=space, serpentine=serpentine
        )
    else:
        out = fn(image, palette, space=space, serpentine=serpentine)
    return np.clip(out, 0, 255).astype(np.uint8)
