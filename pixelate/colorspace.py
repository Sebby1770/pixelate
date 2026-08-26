"""
Color-space conversion and palette matching.

Default matching for dithering is CIE L*a*b* (CIE76 Euclidean). RGB
Euclidean is still available via ``space="rgb"``.
"""

from __future__ import annotations

import numpy as np

# sRGB D65 reference white (CIE XYZ, Y=1)
_D65_WHITE = np.array([0.95047, 1.00000, 1.08883], dtype=np.float64)

# Linear sRGB → XYZ (IEC 61966-2-1 / D65)
_RGB_TO_XYZ = np.array(
    [
        [0.4124564, 0.3575761, 0.1804375],
        [0.2126729, 0.7151522, 0.0721750],
        [0.0193339, 0.1191920, 0.9503041],
    ],
    dtype=np.float64,
)

# CIE L* piecewise threshold (6/29)^3
_LAB_DELTA = 6.0 / 29.0
_LAB_DELTA3 = _LAB_DELTA ** 3


def _as_unit_srgb(flat: np.ndarray, dtype_in) -> np.ndarray:
    """Normalize Nx3 RGB to 0–1 sRGB, accepting uint8 or float 0–1 / 0–255."""
    flat = flat.astype(np.float64, copy=False)
    if np.issubdtype(dtype_in, np.integer):
        return np.clip(flat, 0.0, 255.0) / 255.0
    if flat.size and float(np.nanmax(flat)) > 1.0:
        return np.clip(flat, 0.0, 255.0) / 255.0
    return np.clip(flat, 0.0, 1.0)


def srgb_to_lab(arr: np.ndarray) -> np.ndarray:
    """
    Convert sRGB colors to CIE L*a*b* (D65), vectorized.

    Parameters
    ----------
    arr :
        ``Nx3`` (or ``...x3``) uint8 0–255, or float 0–255 / 0–1.

    Returns
    -------
    ndarray
        Same leading shape as *arr*, last dim ``(L, a, b)`` as float64.
        ``L`` is in ``[0, 100]``; ``a`` / ``b`` are typically ``[-128, 127]``.
    """
    rgb = np.asarray(arr)
    if rgb.size == 0:
        return np.zeros(rgb.shape, dtype=np.float64)
    if rgb.shape[-1] != 3:
        raise ValueError(f"Expected ...x3 RGB array, got shape {rgb.shape}")

    orig_shape = rgb.shape
    flat = rgb.reshape(-1, 3)
    srgb = _as_unit_srgb(flat, rgb.dtype)

    # Inverse sRGB transfer (IEC 61966-2-1)
    linear = np.where(
        srgb <= 0.04045,
        srgb / 12.92,
        ((srgb + 0.055) / 1.055) ** 2.4,
    )
    xyz = linear @ _RGB_TO_XYZ.T
    t = xyz / _D65_WHITE

    f = np.where(
        t > _LAB_DELTA3,
        np.cbrt(np.clip(t, 0.0, None)),
        t / (3.0 * _LAB_DELTA * _LAB_DELTA) + 4.0 / 29.0,
    )

    L = 116.0 * f[:, 1] - 16.0
    a = 500.0 * (f[:, 0] - f[:, 1])
    b = 200.0 * (f[:, 1] - f[:, 2])
    lab = np.stack([L, a, b], axis=-1)
    return lab.reshape(orig_shape)


def nearest_palette_indices(
    pixels: np.ndarray,
    palette: np.ndarray,
    space: str = "rgb",
) -> np.ndarray:
    """
    Index of the nearest palette color for each pixel.

    Parameters
    ----------
    pixels :
        ``Nx3`` RGB (uint8 or float).
    palette :
        ``Px3`` RGB (uint8 or float).
    space :
        ``"rgb"`` Euclidean, or ``"lab"`` CIE76 (Euclidean in L*a*b*).

    Returns
    -------
    ndarray
        Integer indices, shape ``(N,)``.
    """
    key = str(space).lower().strip()
    if key not in ("rgb", "lab"):
        raise ValueError(f"Unknown colorspace '{space}'. Use 'rgb' or 'lab'.")

    pix = np.asarray(pixels)
    pal = np.asarray(palette)
    if pix.size == 0:
        return np.zeros((0,), dtype=np.intp)
    if pal.ndim != 2 or pal.shape[-1] != 3 or pal.shape[0] == 0:
        raise ValueError(f"Palette must be Px3, got {pal.shape}")

    flat = pix.reshape(-1, 3)
    if key == "lab":
        a = srgb_to_lab(np.clip(flat, 0, 255))
        b = srgb_to_lab(np.clip(pal.reshape(-1, 3), 0, 255))
    else:
        a = flat.astype(np.float64)
        b = pal.reshape(-1, 3).astype(np.float64)

    diffs = a[:, None, :] - b[None, :, :]
    dist = np.einsum("ijk,ijk->ij", diffs, diffs)
    return np.argmin(dist, axis=1)
