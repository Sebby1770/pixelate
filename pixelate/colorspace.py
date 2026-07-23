"""
Color space conversions.

Everything here is vectorized numpy — no per-pixel Python loops. The only
conversion currently needed is sRGB -> CIELAB, which gives a perceptually
uniform space where Euclidean distance is a much better match for "these
two colors look alike" than raw RGB distance.
"""

from __future__ import annotations

import numpy as np

# sRGB (D65) -> XYZ, the standard linear transform (IEC 61966-2-1).
_SRGB_TO_XYZ = np.array(
    [
        [0.4124564, 0.3575761, 0.1804375],
        [0.2126729, 0.7151522, 0.0721750],
        [0.0193339, 0.1191920, 0.9503041],
    ],
    dtype=np.float32,
)

# D65 reference white, normalized so Yn == 1.0.
_D65_WHITE = np.array([0.95047, 1.00000, 1.08883], dtype=np.float32)

# CIELAB f() knee: delta = 6/29.
_DELTA = 6.0 / 29.0
_DELTA_CUBED = _DELTA ** 3
_DELTA_SLOPE = 1.0 / (3.0 * _DELTA * _DELTA)
_DELTA_OFFSET = 4.0 / 29.0

COLOR_SPACES = ("rgb", "lab")


def _srgb_to_linear(arr: np.ndarray) -> np.ndarray:
    """Undo the sRGB transfer function. Input/output are 0-1 floats."""
    return np.where(
        arr <= 0.04045,
        arr / 12.92,
        np.power((arr + 0.055) / 1.055, 2.4),
    ).astype(np.float32)


def srgb_to_lab(arr: np.ndarray) -> np.ndarray:
    """
    Convert sRGB values to CIELAB.

    Parameters
    ----------
    arr : np.ndarray
        Array of shape ``(..., 3)`` holding R, G, B in the 0-255 range
        (floats are fine; values are clipped into range).

    Returns
    -------
    np.ndarray
        Float32 array of the same shape holding ``(L*, a*, b*)``. ``L*``
        runs 0-100; ``a*``/``b*`` are roughly -128..127.
    """
    values = np.asarray(arr, dtype=np.float32)
    if values.shape[-1] != 3:
        raise ValueError(f"Expected trailing axis of size 3, got {values.shape}")

    shape = values.shape
    flat = np.clip(values.reshape(-1, 3), 0.0, 255.0) / np.float32(255.0)

    linear = _srgb_to_linear(flat)
    xyz = linear @ _SRGB_TO_XYZ.T
    xyz /= _D65_WHITE

    f = np.where(
        xyz > _DELTA_CUBED,
        np.cbrt(xyz),
        xyz * _DELTA_SLOPE + _DELTA_OFFSET,
    ).astype(np.float32)

    fx, fy, fz = f[:, 0], f[:, 1], f[:, 2]
    lab = np.empty_like(f)
    lab[:, 0] = 116.0 * fy - 16.0
    lab[:, 1] = 500.0 * (fx - fy)
    lab[:, 2] = 200.0 * (fy - fz)

    return lab.reshape(shape)


def convert_for_matching(arr: np.ndarray, color_space: str = "rgb") -> np.ndarray:
    """
    Prepare colors for nearest-neighbor matching in *color_space*.

    ``rgb`` returns a float32 view of the input; ``lab`` converts via
    :func:`srgb_to_lab`. Unknown spaces raise ``ValueError``.
    """
    key = color_space.lower().strip()
    if key == "rgb":
        return np.asarray(arr, dtype=np.float32)
    if key == "lab":
        return srgb_to_lab(arr)
    available = ", ".join(COLOR_SPACES)
    raise ValueError(f"Unknown color space '{color_space}'. Available: {available}")
