"""
Retro post-processing effects: scanlines, CRT glow, pixel grid, sprite
outline, chromatic aberration, and NTSC-style color bleed.
"""

from __future__ import annotations

from typing import Tuple

import numpy as np
from PIL import Image, ImageFilter

RGB = Tuple[int, int, int]


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
    darkened toward the corners (vignette).
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


def apply_pixel_grid(
    img: Image.Image,
    cell: int,
    color: RGB = (0, 0, 0),
    opacity: float = 0.6,
) -> Image.Image:
    """
    Blend a 1px grid line every ``cell`` pixels on both axes.

    Emphasizes the pixel structure like a sprite-editor grid. Returns the
    image unchanged when ``cell < 2`` (nothing to draw).
    """
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
    h, w, _ = arr.shape
    border = np.concatenate(
        [arr[0, :, :], arr[-1, :, :], arr[:, 0, :], arr[:, -1, :]], axis=0
    )
    colors, counts = np.unique(border.reshape(-1, 3), axis=0, return_counts=True)
    bg = colors[int(np.argmax(counts))]
    return np.all(arr == bg, axis=-1)


def apply_outline(
    img: Image.Image,
    color: RGB = (16, 16, 16),
    thickness: int = 1,
) -> Image.Image:
    """
    Draw a solid outline around the foreground sprite.

    The background is inferred from the dominant border color; foreground is
    everything else. The foreground mask is dilated by ``thickness`` (numpy
    roll-based, no scipy) and outline pixels are painted where the dilation
    spills onto background.
    """
    if thickness < 1:
        return img
    arr = np.array(img.convert("RGB"), dtype=np.uint8)
    background = _background_mask(arr)
    foreground = ~background

    dilated = foreground.copy()
    for _ in range(thickness):
        shifted = dilated.copy()
        shifted[1:, :] |= dilated[:-1, :]
        shifted[:-1, :] |= dilated[1:, :]
        shifted[:, 1:] |= dilated[:, :-1]
        shifted[:, :-1] |= dilated[:, 1:]
        dilated = shifted

    outline = dilated & background
    out = arr.copy()
    out[outline] = np.array(color, dtype=np.uint8)
    return Image.fromarray(out)


def apply_chromatic_aberration(img: Image.Image, shift: int) -> Image.Image:
    """
    Split the red and blue channels horizontally for a VHS/CRT fringe.

    Red is shifted ``+shift`` px and blue ``-shift`` px; columns rolled in at
    the edges are refilled with the edge value so no wrap-around shows.
    """
    if shift < 1:
        return img
    arr = np.array(img.convert("RGB"), dtype=np.uint8)

    def _shift_channel(channel: np.ndarray, amount: int) -> np.ndarray:
        rolled = np.roll(channel, amount, axis=1)
        if amount > 0:
            rolled[:, :amount] = channel[:, :1]
        elif amount < 0:
            rolled[:, amount:] = channel[:, -1:]
        return rolled

    out = arr.copy()
    out[:, :, 0] = _shift_channel(arr[:, :, 0], shift)
    out[:, :, 2] = _shift_channel(arr[:, :, 2], -shift)
    return Image.fromarray(out)


# sRGB <-> YIQ (NTSC) transforms.
_RGB_TO_YIQ = np.array(
    [
        [0.299, 0.587, 0.114],
        [0.596, -0.274, -0.322],
        [0.211, -0.523, 0.312],
    ],
    dtype=np.float32,
)
_YIQ_TO_RGB = np.linalg.inv(_RGB_TO_YIQ).astype(np.float32)


def _box_blur_h(channel: np.ndarray, width: int) -> np.ndarray:
    """Horizontal sliding-mean blur via cumulative sums."""
    if width < 2:
        return channel
    pad = width // 2
    padded = np.pad(channel, ((0, 0), (pad + 1, pad)), mode="edge")
    cumsum = np.cumsum(padded, axis=1)
    window = cumsum[:, width:] - cumsum[:, :-width]
    return (window / width)[:, : channel.shape[1]]


def apply_color_bleed(img: Image.Image, strength: float = 0.6, width: int = 3) -> Image.Image:
    """
    NTSC-style horizontal chroma bleed.

    Converts to YIQ, horizontally box-blurs only the I/Q chroma channels
    (luma stays sharp), then blends the bleed back in by ``strength``.
    """
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
