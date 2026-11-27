"""
Retro post-processing effects: CRT bloom, phosphor mask, scanlines, barrel
curvature, chromatic aberration, NTSC color bleed, sprite outline, pixel grid,
and orphan-pixel cleanup.
"""

from __future__ import annotations

import numpy as np
from PIL import Image, ImageFilter


def apply_scanlines(img: Image.Image, intensity: float = 0.35, gap: int = 2) -> Image.Image:
    """
    Overlay horizontal dark lines that mimic CRT scan lines.

    Parameters
    ----------
    intensity : float
        How dark the scanlines are (0.0 = none, 1.0 = black).
    gap : int
        Pixels between scanlines.
    """
    arr = np.array(img).astype(np.float32)
    h = arr.shape[0]
    mask = np.ones(h, dtype=np.float32)
    mask[::gap] = 1.0 - intensity
    arr = arr * mask[:, None, None]
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))


def apply_crt(img: Image.Image, glow: float = 0.5, vignette: float = 0.4) -> Image.Image:
    """
    Approximate a CRT screen with a soft glow and corner vignette.

    The image is blended with a blurred copy of itself (bloom) and then
    darkened toward the corners (vignette). There is no geometric
    curvature or barrel distortion — glow + vignette only.
    """
    base = img.convert("RGB")
    blurred = base.filter(ImageFilter.GaussianBlur(radius=3))

    # Blend bloom
    arr_base = np.array(base, dtype=np.float32)
    arr_blur = np.array(blurred, dtype=np.float32)
    bloom = np.clip(arr_base + glow * (arr_blur - arr_base) * 0.6, 0, 255)

    # Vignette
    h, w, _ = bloom.shape
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    cy, cx = (h - 1) / 2.0, (w - 1) / 2.0
    dist = np.sqrt(((xx - cx) / cx) ** 2 + ((yy - cy) / cy) ** 2)
    falloff = np.clip(1.0 - vignette * dist, 0, 1)
    bloom = bloom * falloff[..., None]

    return Image.fromarray(np.clip(bloom, 0, 255).astype(np.uint8))


def apply_phosphor(img: Image.Image, strength: float = 0.35) -> Image.Image:
    """
    RGB aperture-grille phosphor mask: repeating R, G, B column stripes.

    Columns ``x % 3 == 0/1/2`` keep the R/G/B channel and scale the other
    two by ``1 - strength``. Output size is unchanged.
    """
    strength = min(1.0, max(0.0, float(strength)))
    fade = 1.0 - strength
    base = img.convert("RGB")
    arr = np.array(base, dtype=np.float32)
    w = arr.shape[1]
    xs = np.arange(w) % 3
    r_mul = np.where(xs == 0, 1.0, fade).astype(np.float32)
    g_mul = np.where(xs == 1, 1.0, fade).astype(np.float32)
    b_mul = np.where(xs == 2, 1.0, fade).astype(np.float32)
    arr[:, :, 0] *= r_mul
    arr[:, :, 1] *= g_mul
    arr[:, :, 2] *= b_mul
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))


# ---------------------------------------------------------------------------
# 3.0 effects (outline / grid / chromatic / bleed ported from the 3.0 branch;
# curvature + cleanup are new)
# ---------------------------------------------------------------------------

RGBTuple = tuple


def apply_grid(
    img: Image.Image,
    cell: int,
    color: RGBTuple = (0, 0, 0),
    opacity: float = 0.35,
) -> Image.Image:
    """Overlay a sprite-editor grid every *cell* output pixels (no-op if < 2)."""
    if cell < 2:
        return img
    arr = np.array(img.convert("RGB"), dtype=np.float32)
    h, w, _ = arr.shape
    line = np.array(color, dtype=np.float32)
    opacity = float(np.clip(opacity, 0.0, 1.0))
    rows = np.arange(1, h)
    cols = np.arange(1, w)
    row_lines = rows[rows % cell == 0]
    col_lines = cols[cols % cell == 0]
    arr[row_lines, :, :] = arr[row_lines, :, :] * (1 - opacity) + line * opacity
    arr[:, col_lines, :] = arr[:, col_lines, :] * (1 - opacity) + line * opacity
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))


def _background_mask(arr: np.ndarray) -> np.ndarray:
    """Boolean mask of pixels equal to the dominant border color."""
    border = np.concatenate([arr[0], arr[-1], arr[:, 0], arr[:, -1]], axis=0)
    colors, counts = np.unique(border.reshape(-1, 3), axis=0, return_counts=True)
    bg = colors[int(np.argmax(counts))]
    return np.all(arr == bg, axis=-1)


def _dilate(mask: np.ndarray, steps: int, diagonal: bool = False) -> np.ndarray:
    out = mask.copy()
    for _ in range(steps):
        grown = out.copy()
        grown[1:, :] |= out[:-1, :]
        grown[:-1, :] |= out[1:, :]
        grown[:, 1:] |= out[:, :-1]
        grown[:, :-1] |= out[:, 1:]
        if diagonal:
            grown[1:, 1:] |= out[:-1, :-1]
            grown[1:, :-1] |= out[:-1, 1:]
            grown[:-1, 1:] |= out[1:, :-1]
            grown[:-1, :-1] |= out[1:, 1:]
        out = grown
    return out


def apply_outline(
    img: Image.Image,
    color: RGBTuple = (16, 16, 16),
    thickness: int = 1,
    alpha: Image.Image | None = None,
) -> Image.Image:
    """
    Draw a solid outline around the foreground sprite.

    Foreground is the opaque area of *alpha* when given, otherwise
    everything that differs from the dominant border color. The mask is
    dilated by *thickness* and outline pixels land where it spills onto
    background.
    """
    if thickness < 1:
        return img
    arr = np.array(img.convert("RGB"), dtype=np.uint8)
    if alpha is not None:
        foreground = np.asarray(alpha.resize(img.size, Image.Resampling.NEAREST)) > 127
    else:
        foreground = ~_background_mask(arr)
    outline = _dilate(foreground, thickness) & ~foreground
    out = arr.copy()
    out[outline] = np.array(color, dtype=np.uint8)
    return Image.fromarray(out)


def apply_chromatic_aberration(img: Image.Image, shift: int) -> Image.Image:
    """Split red (+shift) and blue (-shift) horizontally, edge-clamped (no wrap)."""
    if shift < 1:
        return img
    arr = np.array(img.convert("RGB"), dtype=np.uint8)

    def _shift(channel: np.ndarray, amount: int) -> np.ndarray:
        rolled = np.roll(channel, amount, axis=1)
        if amount > 0:
            rolled[:, :amount] = channel[:, :1]
        elif amount < 0:
            rolled[:, amount:] = channel[:, -1:]
        return rolled

    out = arr.copy()
    out[:, :, 0] = _shift(arr[:, :, 0], shift)
    out[:, :, 2] = _shift(arr[:, :, 2], -shift)
    return Image.fromarray(out)


_RGB_TO_YIQ = np.array(
    [[0.299, 0.587, 0.114], [0.596, -0.274, -0.322], [0.211, -0.523, 0.312]],
    dtype=np.float32,
)
_YIQ_TO_RGB = np.linalg.inv(_RGB_TO_YIQ).astype(np.float32)


def _box_blur_h(channel: np.ndarray, width: int) -> np.ndarray:
    if width < 2:
        return channel
    pad = width // 2
    padded = np.pad(channel, ((0, 0), (pad + 1, pad)), mode="edge")
    cumsum = np.cumsum(padded, axis=1)
    window = cumsum[:, width:] - cumsum[:, :-width]
    return (window / width)[:, : channel.shape[1]]


def apply_color_bleed(img: Image.Image, strength: float = 0.6, width: int = 3) -> Image.Image:
    """NTSC chroma bleed: blur only the YIQ I/Q channels horizontally."""
    strength = float(np.clip(strength, 0.0, 1.0))
    if strength <= 0.0:
        return img
    arr = np.array(img.convert("RGB"), dtype=np.float32) / 255.0
    yiq = arr @ _RGB_TO_YIQ.T
    bled = yiq.copy()
    for c in (1, 2):
        blurred = _box_blur_h(yiq[:, :, c], max(3, width))
        bled[:, :, c] = yiq[:, :, c] * (1 - strength) + blurred * strength
    rgb = bled @ _YIQ_TO_RGB.T
    return Image.fromarray(np.clip(rgb * 255.0, 0, 255).astype(np.uint8))


def apply_curvature(img: Image.Image, amount: float = 0.08, border: RGBTuple = (0, 0, 0)) -> Image.Image:
    """
    Barrel-distort the frame like a curved CRT tube (inverse mapping,
    nearest sampling so pixels stay crisp). Corners fall off to *border*.
    """
    amount = float(amount)
    if amount <= 0:
        return img
    has_alpha = img.mode == "RGBA"
    arr = np.array(img.convert("RGBA" if has_alpha else "RGB"))
    h, w = arr.shape[:2]
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float64)
    nx = (xx + 0.5) / w * 2 - 1
    ny = (yy + 0.5) / h * 2 - 1
    r2 = nx * nx + ny * ny
    factor = 1 + amount * r2
    sx = ((nx * factor + 1) / 2 * w - 0.5).round().astype(np.int64)
    sy = ((ny * factor + 1) / 2 * h - 0.5).round().astype(np.int64)
    inside = (sx >= 0) & (sx < w) & (sy >= 0) & (sy < h)
    out = np.empty_like(arr)
    out[...] = np.array(tuple(border) + ((255,) if has_alpha else ()), dtype=arr.dtype)[: arr.shape[2]]
    out[inside] = arr[sy[inside], sx[inside]]
    return Image.fromarray(out)


def cleanup_orphans(indices: np.ndarray, passes: int = 1) -> np.ndarray:
    """
    Remove isolated "orphan" pixels from an index map (logical resolution).

    A pixel whose four neighbours all share one value that differs from it
    is replaced by that value — the stray specks pixel artists clean up by
    hand. Works on palette indices or any integer label map.
    """
    out = np.asarray(indices).copy()
    for _ in range(max(0, int(passes))):
        p = np.pad(out, 1, mode="edge")
        up, down = p[:-2, 1:-1], p[2:, 1:-1]
        left, right = p[1:-1, :-2], p[1:-1, 2:]
        same = (up == down) & (up == left) & (up == right) & (up != out)
        if not same.any():
            break
        out = np.where(same, up, out)
    return out
