"""
Core pixel-art conversion pipeline.

The pipeline:
  1. Load image and convert to RGB.
  2. Optional invert / contrast / edge pre-pass.
  3. Downscale to target resolution (this is the "pixelation").
  4. Quantize to a retro (or auto-extracted) palette, optionally with dithering.
  5. Upscale with nearest-neighbor (so each "pixel" stays crisp).
  6. Optional CRT effects and extra display scale.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple, Union

import numpy as np
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageOps

from pixelate.dithering import get_dither
from pixelate.palettes import RGB, Palette, get_palette

PathLike = Union[str, Path]
ColorUsage = Tuple[RGB, int, float]  # color, pixel count, percentage


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
    return ImageEnhance.Color(img).enhance(factor)


def _adjust_contrast(img: Image.Image, factor: float) -> Image.Image:
    """Adjust contrast. factor=1.0 leaves the image unchanged."""
    if factor == 1.0:
        return img
    return ImageEnhance.Contrast(img).enhance(factor)


def _apply_edges(img: Image.Image) -> Image.Image:
    """
    Edge-aware pre-pass: mild unsharp + emboss-lite blend to preserve outlines
    before quantization.
    """
    sharpened = img.filter(ImageFilter.UnsharpMask(radius=1.5, percent=140, threshold=2))
    # Emboss-lite: blend original with a light EDGE_ENHANCE pass
    edged = sharpened.filter(ImageFilter.EDGE_ENHANCE_MORE)
    return Image.blend(sharpened, edged, alpha=0.35)


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

    Note: ``"auto"`` is not resolved here — use :func:`extract_palette` first.
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

    key = str(palette).lower().strip()
    if key == "auto":
        raise ValueError(
            "Palette 'auto' requires extract_palette() — pass colors via "
            "pixelate_image(..., palette='auto', colors=N) or an RGB sequence."
        )

    return get_palette(str(palette))


# ---------------------------------------------------------------------------
# Palette extraction (k-means / median-cut) — numpy only, no sklearn
# ---------------------------------------------------------------------------

def _unique_sample_pixels(arr: np.ndarray, max_samples: int = 10000) -> np.ndarray:
    """Flatten HxWx3 image and optionally subsample for clustering speed."""
    flat = arr.reshape(-1, 3).astype(np.float64)
    n = flat.shape[0]
    if n <= max_samples:
        return flat
    rng = np.random.default_rng(42)
    idx = rng.choice(n, size=max_samples, replace=False)
    return flat[idx]


def _kmeans_palette(pixels: np.ndarray, n: int, max_iter: int = 20) -> Palette:
    """Simple k-means clustering in RGB space (numpy only)."""
    if pixels.shape[0] == 0:
        raise ValueError("No pixels to cluster")
    n = max(1, min(n, pixels.shape[0]))

    # Init: pick n distinct-ish seeds by spread sampling
    rng = np.random.default_rng(0)
    if pixels.shape[0] >= n:
        seeds_idx = rng.choice(pixels.shape[0], size=n, replace=False)
        centers = pixels[seeds_idx].copy()
    else:
        centers = pixels.copy()

    for _ in range(max_iter):
        # Assign
        diffs = pixels[:, None, :] - centers[None, :, :]  # (N, K, 3)
        dist = np.einsum("ijk,ijk->ij", diffs, diffs)
        labels = np.argmin(dist, axis=1)

        new_centers = centers.copy()
        for k in range(centers.shape[0]):
            mask = labels == k
            if np.any(mask):
                new_centers[k] = pixels[mask].mean(axis=0)
            else:
                # Re-seed empty cluster
                new_centers[k] = pixels[rng.integers(0, pixels.shape[0])]

        if np.allclose(new_centers, centers, atol=0.5):
            centers = new_centers
            break
        centers = new_centers

    # Sort by luminance for stable ordering
    centers = np.clip(np.round(centers), 0, 255).astype(np.int32)
    order = np.argsort(0.299 * centers[:, 0] + 0.587 * centers[:, 1] + 0.114 * centers[:, 2])
    centers = centers[order]

    # Deduplicate exact matches
    seen = set()
    colors: List[RGB] = []
    for c in centers:
        t = (int(c[0]), int(c[1]), int(c[2]))
        if t not in seen:
            seen.add(t)
            colors.append(t)
    return tuple(colors)  # type: ignore[return-value]


def _median_cut_palette(pixels: np.ndarray, n: int) -> Palette:
    """Median-cut style quantization (bucket splits by largest channel range)."""
    if pixels.shape[0] == 0:
        raise ValueError("No pixels to quantize")
    n = max(1, min(n, pixels.shape[0]))

    buckets: List[np.ndarray] = [pixels.astype(np.float64)]

    while len(buckets) < n:
        # Split the bucket with the largest channel range
        best_i = 0
        best_range = -1.0
        best_ch = 0
        for i, b in enumerate(buckets):
            if b.shape[0] < 2:
                continue
            ranges = b.max(axis=0) - b.min(axis=0)
            ch = int(np.argmax(ranges))
            r = float(ranges[ch])
            if r > best_range:
                best_range = r
                best_i = i
                best_ch = ch

        if best_range <= 0:
            break

        bucket = buckets.pop(best_i)
        order = np.argsort(bucket[:, best_ch])
        bucket = bucket[order]
        mid = bucket.shape[0] // 2
        buckets.append(bucket[:mid])
        buckets.append(bucket[mid:])

    colors: List[RGB] = []
    seen = set()
    for b in buckets:
        mean = np.clip(np.round(b.mean(axis=0)), 0, 255).astype(int)
        t = (int(mean[0]), int(mean[1]), int(mean[2]))
        if t not in seen:
            seen.add(t)
            colors.append(t)

    colors.sort(key=lambda c: 0.299 * c[0] + 0.587 * c[1] + 0.114 * c[2])
    return tuple(colors)  # type: ignore[return-value]


def extract_palette(
    img: Union[str, Path, Image.Image],
    n: int = 16,
    method: str = "kmeans",
    max_samples: int = 10000,
) -> Palette:
    """
    Extract an N-color palette from an image (auto palette).

    Parameters
    ----------
    img :
        Path or PIL Image.
    n :
        Target number of colors (clamped to unique sample size).
    method :
        ``"kmeans"`` (default) or ``"median-cut"`` / ``"mediancut"``.
    max_samples :
        Subsample large images for speed.

    Returns
    -------
    Palette
        Tuple of ``(R, G, B)`` colors sorted by luminance.
    """
    if n < 1:
        raise ValueError("n must be >= 1")

    if isinstance(img, (str, Path)):
        pil = Image.open(img).convert("RGB")
    else:
        pil = img.convert("RGB")

    # Downsample huge images first for speed / stability
    if max(pil.size) > 256:
        pil = _resize_keep_aspect(pil, 256)

    arr = np.array(pil, dtype=np.uint8)
    pixels = _unique_sample_pixels(arr, max_samples=max_samples)

    # Collapse near-duplicates before clustering when few unique colors
    # (use full unique if small)
    unique = np.unique(arr.reshape(-1, 3), axis=0).astype(np.float64)
    if unique.shape[0] <= n:
        colors = [
            (int(c[0]), int(c[1]), int(c[2]))
            for c in sorted(
                unique,
                key=lambda c: 0.299 * c[0] + 0.587 * c[1] + 0.114 * c[2],
            )
        ]
        return tuple(colors)  # type: ignore[return-value]

    key = method.lower().strip().replace("_", "-")
    if key in ("kmeans", "k-means"):
        return _kmeans_palette(pixels, n)
    if key in ("median-cut", "mediancut", "median"):
        return _median_cut_palette(pixels, n)
    raise ValueError(f"Unknown extract method '{method}'. Use 'kmeans' or 'median-cut'.")


def color_usage_report(
    img: Union[str, Path, Image.Image],
    palette: Optional[Sequence[RGB]] = None,
) -> List[ColorUsage]:
    """
    Count how many pixels use each color in *img*.

    If *palette* is given, report usage only for those colors (others ignored
    or zero). Otherwise report every unique color present.

    Returns
    -------
    list of (color, count, percentage)
        Sorted by count descending.
    """
    if isinstance(img, (str, Path)):
        pil = Image.open(img).convert("RGB")
    else:
        pil = img.convert("RGB")

    arr = np.array(pil, dtype=np.uint8)
    flat = arr.reshape(-1, 3)
    total = flat.shape[0]
    if total == 0:
        return []

    # Pack RGB into uint32 for fast counting
    packed = (
        flat[:, 0].astype(np.uint32) << 16
        | flat[:, 1].astype(np.uint32) << 8
        | flat[:, 2].astype(np.uint32)
    )
    unique, counts = np.unique(packed, return_counts=True)
    usage_map: Dict[RGB, int] = {}
    for u, c in zip(unique, counts):
        r = int((u >> 16) & 0xFF)
        g = int((u >> 8) & 0xFF)
        b = int(u & 0xFF)
        usage_map[(r, g, b)] = int(c)

    if palette is not None:
        report: List[ColorUsage] = []
        for col in palette:
            rgb = (int(col[0]), int(col[1]), int(col[2]))
            count = usage_map.get(rgb, 0)
            pct = 100.0 * count / total
            report.append((rgb, count, pct))
        report.sort(key=lambda x: (-x[1], x[0]))
        return report

    report = [
        (color, count, 100.0 * count / total)
        for color, count in usage_map.items()
    ]
    report.sort(key=lambda x: (-x[1], x[0]))
    return report


def nearest_scale(img: Image.Image, factor: int) -> Image.Image:
    """Upscale *img* by integer *factor* using nearest-neighbor (chunky pixels)."""
    if factor < 1:
        raise ValueError("scale factor must be >= 1")
    if factor == 1:
        return img
    w, h = img.size
    return img.resize((w * factor, h * factor), Image.NEAREST)


def compare_palettes(
    src: Union[str, Path, Image.Image],
    palettes: Sequence[Union[str, Sequence[RGB]]],
    *,
    pixel_size: int = 64,
    dither: str = "floyd",
    upscale: int = 2,
    saturation: float = 1.2,
    cols: Optional[int] = None,
    label: bool = True,
    padding: int = 8,
    bg: RGB = (20, 20, 24),
    **kwargs,
) -> Image.Image:
    """
    Convert *src* with each palette and tile results into a labeled collage.

    Parameters
    ----------
    src :
        Source image path or PIL Image.
    palettes :
        Sequence of palette names or RGB sequences.
    pixel_size, dither, upscale, saturation :
        Forwarded to :func:`pixelate_image`.
    cols :
        Grid columns (default: auto, min(len, 4)).
    label :
        Burn palette name captions under each tile.
    padding :
        Gap between tiles in pixels.
    bg :
        Background fill color.
    **kwargs :
        Extra kwargs forwarded to :func:`pixelate_image`.

    Returns
    -------
    PIL.Image
        Collage grid of conversions.
    """
    if not palettes:
        raise ValueError("palettes list is empty")

    names: List[str] = []
    tiles: List[Image.Image] = []
    for p in palettes:
        if isinstance(p, str):
            names.append(p)
            tile = pixelate_image(
                src,
                palette=p,
                pixel_size=pixel_size,
                dither=dither,
                upscale=upscale,
                saturation=saturation,
                **kwargs,
            )
        else:
            names.append(f"{len(p)}col")
            tile = pixelate_image(
                src,
                palette=p,
                pixel_size=pixel_size,
                dither=dither,
                upscale=upscale,
                saturation=saturation,
                **kwargs,
            )
        tiles.append(tile.convert("RGB"))

    n = len(tiles)
    if cols is None:
        cols = min(n, 4)
    cols = max(1, cols)
    rows = (n + cols - 1) // cols

    tile_w = max(t.size[0] for t in tiles)
    tile_h = max(t.size[1] for t in tiles)
    label_h = 18 if label else 0
    cell_w = tile_w
    cell_h = tile_h + label_h

    sheet_w = cols * cell_w + max(0, cols - 1) * padding + padding * 2
    sheet_h = rows * cell_h + max(0, rows - 1) * padding + padding * 2
    sheet = Image.new("RGB", (sheet_w, sheet_h), bg)
    draw = ImageDraw.Draw(sheet)

    try:
        font = ImageFont.load_default()
    except Exception:  # pragma: no cover
        font = None

    for i, (tile, name) in enumerate(zip(tiles, names)):
        row, col = divmod(i, cols)
        x = padding + col * (cell_w + padding)
        y = padding + row * (cell_h + padding)
        ox = x + (tile_w - tile.size[0]) // 2
        oy = y + (tile_h - tile.size[1]) // 2
        sheet.paste(tile, (ox, oy))
        if label:
            text = name[:24]
            ty = y + tile_h + 2
            # Simple shadow for readability
            if font is not None:
                draw.text((x + 1, ty + 1), text, fill=(0, 0, 0), font=font)
                draw.text((x, ty), text, fill=(220, 220, 220), font=font)
            else:
                draw.text((x, ty), text, fill=(220, 220, 220))

    return sheet


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
    *,
    colors: int = 16,
    extract_method: str = "kmeans",
    scale: int = 1,
    edges: bool = False,
    invert: bool = False,
    contrast: float = 1.0,
) -> Image.Image:
    """
    Convert an image into retro pixel art.

    Parameters
    ----------
    src : path or PIL Image
        Source image.
    palette : str | path | sequence of RGB
        Name of a built-in palette, ``"auto"`` to extract from the image,
        path to a ``.hex``/``.gpl`` file, or an explicit sequence of
        ``(R, G, B)`` triples. See ``pixelate.palettes.PALETTES``.
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
    colors : int
        When *palette* is ``"auto"``, number of colors to extract.
    extract_method : str
        Auto-palette method: ``"kmeans"`` or ``"median-cut"``.
    scale : int
        Extra integer nearest-neighbor upscale applied after the main
        pipeline (default 1 = none). Use for chunky display pixels.
    edges : bool
        Apply an edge-aware sharpen/emboss-lite pre-pass before quantize.
    invert : bool
        Invert colors before palette quantization.
    contrast : float
        Contrast multiplier (1.0 = unchanged).

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
    if invert:
        img = ImageOps.invert(img)
    img = _adjust_contrast(img, contrast)
    img = _adjust_saturation(img, saturation)
    if edges:
        img = _apply_edges(img)
    img = _resize_keep_aspect(img, pixel_size)

    # --- Palette --------------------------------------------------------
    if palette_file is not None:
        palette_colors = resolve_palette(palette, palette_file=palette_file)
    elif isinstance(palette, str) and palette.lower().strip() == "auto":
        palette_colors = extract_palette(img, n=colors, method=extract_method)
    else:
        palette_colors = resolve_palette(palette, palette_file=None)

    # --- Quantize -------------------------------------------------------
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

    # --- Extra display scale (chunky nearest-neighbor) ------------------
    if scale > 1:
        out = nearest_scale(out, scale)

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
