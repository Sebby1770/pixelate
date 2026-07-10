"""
Core pixel-art conversion pipeline.

The pipeline:
  1. Load image and convert to RGB.
  2. Downscale to target resolution (this is the "pixelation").
  3. Quantize to a retro palette, optionally with dithering.
  4. Apply optional CRT effects.
  5. Upscale back with nearest-neighbor (so each "pixel" stays crisp).
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Sequence, Tuple, Union

import numpy as np
from PIL import Image

from pixelate.dithering import get_dither
from pixelate.palettes import RGB, Palette, get_palette

PathLike = Union[str, Path]


def _resize_keep_aspect(img: Image.Image, max_dim: int) -> Image.Image:
    """Downscale so the longest side equals `max_dim`, preserving aspect."""
    w, h = img.size
    if max(w, h) <= max_dim:
        return img
    if w >= h:
        new_w = max_dim
        new_h = max(1, round(h * (max_dim / w)))
    else:
        new_h = max_dim
        new_w = max(1, round(w * (max_dim / h)))
    return img.resize((new_w, new_h), Image.LANCZOS)


def _adjust_saturation(img: Image.Image, factor: float) -> Image.Image:
    """Boost or cut saturation. factor=1.0 leaves the image unchanged."""
    if factor == 1.0:
        return img
    from PIL import ImageEnhance
    return ImageEnhance.Color(img).enhance(factor)


def resolve_palette(
    palette: Union[str, Path, Sequence[RGB]] = "gameboy",
    palette_file: Optional[PathLike] = None,
) -> Palette:
    """
    Resolve a palette from a built-in name, file path, or RGB sequence.

    Precedence:
      1. *palette_file* if provided
      2. *palette* as an RGB sequence
      3. *palette* as an existing ``.hex`` / ``.gpl`` path
      4. *palette* as a built-in / registered name
    """
    if palette_file is not None:
        from pixelate.palette_io import load_palette_file
        return load_palette_file(palette_file)

    if not isinstance(palette, (str, Path)):
        # Sequence of RGB triples
        colors = tuple((int(c[0]), int(c[1]), int(c[2])) for c in palette)
        if not colors:
            raise ValueError("Palette sequence is empty")
        return colors  # type: ignore[return-value]

    path = Path(palette)
    if path.is_file() and path.suffix.lower() in (".hex", ".gpl", ".txt"):
        from pixelate.palette_io import load_palette_file
        return load_palette_file(path)

    return get_palette(str(palette))


def pixelate_image(
    src: Union[str, Path, Image.Image],
    palette: Union[str, Path, Sequence[RGB]] = "gameboy",
    pixel_size: int = 96,
    dither: str = "floyd",
    upscale: int = 4,
    saturation: float = 1.2,
    crt: bool = False,
    scanlines: bool = False,
    palette_file: Optional[PathLike] = None,
) -> Image.Image:
    """
    Convert an image into retro pixel art.

    Parameters
    ----------
    src : path or PIL Image
        Source image.
    palette : str | path | sequence of RGB
        Name of a built-in palette, path to a ``.hex``/``.gpl`` file, or an
        explicit sequence of ``(R, G, B)`` triples. See
        ``pixelate.palettes.PALETTES``.
    pixel_size : int
        Target resolution of the longest side, in "pixels". Lower = chunkier.
    dither : str
        Dithering algorithm: ``none``, ``floyd``, ``atkinson``, ``bayer``,
        ``stucki``, ``burkes``, ``sierra``.
    upscale : int
        How many output pixels per logical pixel. ``4`` is a good default.
    saturation : float
        Saturation multiplier applied before quantization.
    crt : bool
        Apply a CRT-style glow + curvature effect after upscaling.
    scanlines : bool
        Overlay horizontal scanlines on the upscaled output.
    palette_file : path, optional
        Load palette colors from a ``.hex`` or ``.gpl`` file (overrides
        *palette* name when set).

    Returns
    -------
    PIL.Image
        The pixel-art result, ready to save or display.
    """
    # --- Load -----------------------------------------------------------
    if isinstance(src, (str, Path)):
        img = Image.open(src)
    else:
        img = src
    img = img.convert("RGB")

    # --- Pre-process ----------------------------------------------------
    img = _adjust_saturation(img, saturation)
    img = _resize_keep_aspect(img, pixel_size)

    # --- Quantize -------------------------------------------------------
    palette_colors = resolve_palette(palette, palette_file=palette_file)
    palette_arr = np.array(palette_colors, dtype=np.float32)
    arr = np.array(img, dtype=np.uint8)
    dither_fn = get_dither(dither)
    quantized = dither_fn(arr.astype(np.float32), palette_arr)

    out = Image.fromarray(quantized.astype(np.uint8), mode="RGB")

    # --- Upscale --------------------------------------------------------
    if upscale > 1:
        new_size = (out.size[0] * upscale, out.size[1] * upscale)
        out = out.resize(new_size, Image.NEAREST)

    # --- Effects --------------------------------------------------------
    if scanlines or crt:
        from pixelate.effects import apply_scanlines, apply_crt
        if scanlines:
            out = apply_scanlines(out)
        if crt:
            out = apply_crt(out)

    return out


def save_image(img: Image.Image, path: Union[str, Path]) -> Path:
    """Save an image, ensuring the parent directory exists."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    img.save(p)
    return p


def get_image_size(src: Union[str, Path]) -> Tuple[int, int]:
    """Return the (width, height) of an image without fully loading it."""
    with Image.open(src) as img:
        return img.size


# Common image extensions for batch / sheet discovery
IMAGE_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".tif", ".tiff",
}


def collect_images(paths: Sequence[PathLike], recursive: bool = False) -> list[Path]:
    """
    Expand paths and directories into a sorted list of image files.

    Directories are scanned for common image extensions.
    """
    found: list[Path] = []
    for raw in paths:
        p = Path(raw)
        if p.is_dir():
            pattern_iter = p.rglob("*") if recursive else p.glob("*")
            for child in pattern_iter:
                if child.is_file() and child.suffix.lower() in IMAGE_EXTENSIONS:
                    found.append(child)
        elif p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS:
            found.append(p)
        elif p.is_file():
            # Allow explicit files even with unusual extensions
            found.append(p)
    return sorted(set(found), key=lambda x: str(x).lower())


def make_spritesheet(
    images: Sequence[Image.Image],
    cols: int = 4,
    padding: int = 0,
    bg: RGB = (0, 0, 0),
) -> Image.Image:
    """
    Tile images into a single spritesheet grid.

    All tiles are padded to the maximum width/height among inputs so the
    grid stays aligned. Empty cells (if any) are filled with *bg*.
    """
    if not images:
        raise ValueError("No images to arrange into a spritesheet")
    if cols < 1:
        raise ValueError("cols must be >= 1")

    rgb_images = [im.convert("RGB") for im in images]
    tile_w = max(im.size[0] for im in rgb_images)
    tile_h = max(im.size[1] for im in rgb_images)
    n = len(rgb_images)
    rows = (n + cols - 1) // cols

    sheet_w = cols * tile_w + max(0, cols - 1) * padding
    sheet_h = rows * tile_h + max(0, rows - 1) * padding
    sheet = Image.new("RGB", (sheet_w, sheet_h), bg)

    for i, im in enumerate(rgb_images):
        row, col = divmod(i, cols)
        x = col * (tile_w + padding)
        y = row * (tile_h + padding)
        # Center smaller images in the tile cell
        ox = x + (tile_w - im.size[0]) // 2
        oy = y + (tile_h - im.size[1]) // 2
        sheet.paste(im, (ox, oy))

    return sheet
