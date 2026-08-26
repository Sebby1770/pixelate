"""
Color-space conversion and palette matching.

Default matching for dithering is CIE L*a*b* (CIE76 Euclidean). RGB
Euclidean is available via ``space="rgb"``; perceptual CIEDE2000 via
``space="ciede2000"``.
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

# Inverse of the same matrix (XYZ → linear sRGB)
_XYZ_TO_RGB = np.linalg.inv(_RGB_TO_XYZ)

# CIE L* piecewise threshold (6/29)^3
_LAB_DELTA = 6.0 / 29.0
_LAB_DELTA3 = _LAB_DELTA ** 3
# sRGB electro-optical transfer linear-segment end
_SRGB_LINEAR_CUTOFF = 0.0031308
# CIEDE2000: 25^7 in the G / RC terms
_CIEDE2000_25_7 = 25.0 ** 7


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


def lab_to_srgb(arr: np.ndarray) -> np.ndarray:
    """
    Convert CIE L*a*b* (D65) to sRGB, vectorized inverse of :func:`srgb_to_lab`.

    Parameters
    ----------
    arr :
        ``Nx3`` (or ``...x3``) Lab as float. ``L`` is ``[0, 100]``; ``a`` / ``b``
        are typically ``[-128, 127]``.

    Returns
    -------
    ndarray
        Same leading shape as *arr*, last dim RGB as float64 clipped to
        ``[0, 255]`` (uint8-capable, not cast).
    """
    lab = np.asarray(arr, dtype=np.float64)
    if lab.size == 0:
        return np.zeros(lab.shape, dtype=np.float64)
    if lab.shape[-1] != 3:
        raise ValueError(f"Expected ...x3 Lab array, got shape {lab.shape}")

    orig_shape = lab.shape
    flat = lab.reshape(-1, 3)

    fy = (flat[:, 0] + 16.0) / 116.0
    fx = flat[:, 1] / 500.0 + fy
    fz = fy - flat[:, 2] / 200.0
    f = np.stack([fx, fy, fz], axis=-1)

    t = np.where(
        f > _LAB_DELTA,
        f ** 3,
        (f - 4.0 / 29.0) * (3.0 * _LAB_DELTA * _LAB_DELTA),
    )
    xyz = t * _D65_WHITE
    linear = xyz @ _XYZ_TO_RGB.T

    # IEC 61966-2-1; clip negatives before the power branch
    lin_pos = np.clip(linear, 0.0, None)
    srgb = np.where(
        linear <= _SRGB_LINEAR_CUTOFF,
        12.92 * linear,
        1.055 * np.power(lin_pos, 1.0 / 2.4) - 0.055,
    )
    rgb = np.clip(srgb * 255.0, 0.0, 255.0)
    return rgb.reshape(orig_shape)


def _ciede2000_core(lab1: np.ndarray, lab2: np.ndarray) -> np.ndarray:
    """Pairwise CIEDE2000; *lab1* / *lab2* broadcast, last dim Lab (L, a, b)."""
    L1 = lab1[..., 0]
    a1 = lab1[..., 1]
    b1 = lab1[..., 2]
    L2 = lab2[..., 0]
    a2 = lab2[..., 1]
    b2 = lab2[..., 2]

    C1 = np.sqrt(a1 * a1 + b1 * b1)
    C2 = np.sqrt(a2 * a2 + b2 * b2)
    Cbar = 0.5 * (C1 + C2)
    Cbar7 = Cbar ** 7
    G = 0.5 * (1.0 - np.sqrt(Cbar7 / (Cbar7 + _CIEDE2000_25_7)))

    a1p = (1.0 + G) * a1
    a2p = (1.0 + G) * a2
    C1p = np.sqrt(a1p * a1p + b1 * b1)
    C2p = np.sqrt(a2p * a2p + b2 * b2)
    Cbarp = 0.5 * (C1p + C2p)

    h1p = np.degrees(np.arctan2(b1, a1p)) % 360.0
    h2p = np.degrees(np.arctan2(b2, a2p)) % 360.0
    h1p = np.where(C1p == 0.0, 0.0, h1p)
    h2p = np.where(C2p == 0.0, 0.0, h2p)

    dLp = L2 - L1
    dCp = C2p - C1p

    dhp = h2p - h1p
    dhp = np.where((C1p * C2p) == 0.0, 0.0, dhp)
    dhp = np.where(dhp > 180.0, dhp - 360.0, dhp)
    dhp = np.where(dhp < -180.0, dhp + 360.0, dhp)
    dHp = 2.0 * np.sqrt(np.maximum(C1p * C2p, 0.0)) * np.sin(np.radians(dhp * 0.5))

    Lbar = 0.5 * (L1 + L2)
    hsum = h1p + h2p
    habs = np.abs(h1p - h2p)
    Hbarp = np.where(
        (C1p * C2p) == 0.0,
        hsum,
        np.where(
            habs <= 180.0,
            hsum * 0.5,
            np.where(hsum < 360.0, (hsum + 360.0) * 0.5, (hsum - 360.0) * 0.5),
        ),
    )

    T = (
        1.0
        - 0.17 * np.cos(np.radians(Hbarp - 30.0))
        + 0.24 * np.cos(np.radians(2.0 * Hbarp))
        + 0.32 * np.cos(np.radians(3.0 * Hbarp + 6.0))
        - 0.20 * np.cos(np.radians(4.0 * Hbarp - 63.0))
    )
    dtheta = 30.0 * np.exp(-(((Hbarp - 275.0) / 25.0) ** 2))
    Cbarp7 = Cbarp ** 7
    Rc = 2.0 * np.sqrt(Cbarp7 / (Cbarp7 + _CIEDE2000_25_7))
    Rt = -np.sin(np.radians(2.0 * dtheta)) * Rc

    dL50 = (Lbar - 50.0) ** 2
    Sl = 1.0 + (0.015 * dL50) / np.sqrt(20.0 + dL50)
    Sc = 1.0 + 0.045 * Cbarp
    Sh = 1.0 + 0.015 * Cbarp * T

    t1 = dLp / Sl
    t2 = dCp / Sc
    t3 = dHp / Sh
    dist2 = t1 * t1 + t2 * t2 + t3 * t3 + Rt * t2 * t3
    with np.errstate(invalid="ignore"):
        dist = np.sqrt(np.maximum(dist2, 0.0))
    return np.nan_to_num(dist, nan=0.0, posinf=0.0, neginf=0.0)


def ciede2000(lab1: np.ndarray, lab2: np.ndarray) -> np.ndarray:
    """
    CIEDE2000 colour difference ΔE₀₀ between Lab colors (D65).

    Parameters
    ----------
    lab1, lab2 :
        Lab arrays, last dim ``(L, a, b)``. Accepted layouts:

        * ``(3,)`` vs ``(3,)`` → scalar ``()``
        * ``(N, 3)`` vs ``(P, 3)`` → pairwise ``(N, P)``
        * matching / broadcastable leading dims with last dim 3
          (e.g. ``(N, P, 3)`` vs ``(N, P, 3)``) → those leading dims

    Returns
    -------
    ndarray
        ΔE₀₀ distances as float64.
    """
    a = np.asarray(lab1, dtype=np.float64)
    b = np.asarray(lab2, dtype=np.float64)
    orig_a_ndim = a.ndim
    orig_b_ndim = b.ndim

    if a.size == 0 or b.size == 0:
        if orig_a_ndim <= 1:
            a = a.reshape(1, 3) if a.size else np.zeros((0, 3), dtype=np.float64)
        if orig_b_ndim <= 1:
            b = b.reshape(1, 3) if b.size else np.zeros((0, 3), dtype=np.float64)
        if a.ndim == 2 and a.shape[-1] == 3 and b.ndim == 2 and b.shape[-1] == 3:
            return np.zeros((a.shape[0], b.shape[0]), dtype=np.float64)
        return np.zeros(np.broadcast_shapes(a.shape[:-1], b.shape[:-1]), dtype=np.float64)

    if a.shape[-1] != 3 or b.shape[-1] != 3:
        raise ValueError(
            f"Expected Lab ...x3, got shapes {a.shape} and {b.shape}"
        )

    if a.ndim == 1:
        a = a.reshape(1, 3)
    if b.ndim == 1:
        b = b.reshape(1, 3)

    if a.ndim == 2 and b.ndim == 2:
        dist = _ciede2000_core(a[:, None, :], b[None, :, :])
        if orig_a_ndim == 1 and orig_b_ndim == 1:
            return np.asarray(dist[0, 0], dtype=np.float64)
        return dist

    dist = _ciede2000_core(a, b)
    return dist


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
        ``"rgb"`` Euclidean, ``"lab"`` CIE76 (Euclidean in L*a*b*), or
        ``"ciede2000"`` (Lab then pairwise CIEDE2000).

    Returns
    -------
    ndarray
        Integer indices, shape ``(N,)``.
    """
    key = str(space).lower().strip()
    if key not in ("rgb", "lab", "ciede2000"):
        raise ValueError(
            f"Unknown colorspace '{space}'. Use 'rgb', 'lab', or 'ciede2000'."
        )

    pix = np.asarray(pixels)
    pal = np.asarray(palette)
    if pix.size == 0:
        return np.zeros((0,), dtype=np.intp)
    if pal.ndim != 2 or pal.shape[-1] != 3 or pal.shape[0] == 0:
        raise ValueError(f"Palette must be Px3, got {pal.shape}")

    flat = pix.reshape(-1, 3)
    if key in ("lab", "ciede2000"):
        a = srgb_to_lab(np.clip(flat, 0, 255))
        b = srgb_to_lab(np.clip(pal.reshape(-1, 3), 0, 255))
    else:
        a = flat.astype(np.float64)
        b = pal.reshape(-1, 3).astype(np.float64)

    if key == "ciede2000":
        dist = ciede2000(a, b)
        return np.argmin(dist, axis=1)

    diffs = a[:, None, :] - b[None, :, :]
    dist = np.einsum("ijk,ijk->ij", diffs, diffs)
    return np.argmin(dist, axis=1)
