"""
Animated GIF / multi-frame WebP support.

Detect multi-frame inputs, pixelate each frame with the same pipeline as
``pixelate_image``, and reassemble an animated GIF preserving approximate
frame durations. Frames are written as mode-P GIFs with a shared palette
from the working colors (Pillow is not allowed to invent extra colors).
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional, Sequence, Tuple, Union

from PIL import Image, ImageOps

from pixelate.core import (
    PALETTE_INFO_KEY,
    collect_working_colors,
    image_has_alpha,
    image_to_indexed,
    pixelate_image,
)
from pixelate.palettes import RGB

PathLike = Union[str, Path]
FrameList = List[Image.Image]
DurationList = List[int]


def is_animated(src: Union[PathLike, Image.Image]) -> bool:
    """Return True if *src* is a multi-frame animated image."""
    if isinstance(src, Image.Image):
        return getattr(src, "is_animated", False) and getattr(src, "n_frames", 1) > 1

    path = Path(src)
    with Image.open(path) as img:
        return bool(getattr(img, "is_animated", False) and getattr(img, "n_frames", 1) > 1)


def _working_frame(frame: Image.Image) -> Image.Image:
    """EXIF-correct a single frame, preserving alpha when present."""
    frame = ImageOps.exif_transpose(frame)
    if image_has_alpha(frame):
        return frame.convert("RGBA").copy()
    return frame.convert("RGB").copy()


def load_frames(src: Union[PathLike, Image.Image]) -> Tuple[FrameList, DurationList]:
    """
    Load all frames and their durations (ms) from an animated image.

    For still images, returns a single frame with duration 100ms.
    Duration defaults to 100ms when not stored in the source.
    Applies EXIF orientation and keeps RGBA when the source has alpha.
    """
    close_after = False
    if isinstance(src, Image.Image):
        img = src
    else:
        img = Image.open(src)
        close_after = True

    frames: FrameList = []
    durations: DurationList = []

    n_frames = getattr(img, "n_frames", 1)
    try:
        for i in range(n_frames):
            img.seek(i)
            frames.append(_working_frame(img))
            duration = img.info.get("duration", 100)
            if duration is None or duration <= 0:
                duration = 100
            durations.append(int(duration))
    finally:
        if close_after:
            img.close()

    return frames, durations


def pixelate_animation(
    src: Union[PathLike, Image.Image],
    *,
    palette: str = "gameboy",
    pixel_size: int = 96,
    dither: str = "floyd",
    upscale: int = 4,
    saturation: float = 1.2,
    crt: bool = False,
    scanlines: bool = False,
    palette_file: Optional[Union[str, Path]] = None,
    output: Optional[PathLike] = None,
    colors: int = 16,
    extract_method: str = "kmeans",
    scale: int = 1,
    edges: bool = False,
    invert: bool = False,
    contrast: float = 1.0,
    colorspace: str = "lab",
    serpentine: bool = True,
    phosphor: bool = False,
    posterize: Optional[int] = None,
    bayer_size: int = 4,
    seed: Optional[int] = None,
    downscale: str = "box",
    distance: Optional[str] = None,
) -> Union[Image.Image, Tuple[FrameList, DurationList]]:
    """
    Pixelate every frame of an animated (or still) image.

    Parameters
    ----------
    src :
        Path or PIL Image (animated GIF/WebP or still).
    palette, pixel_size, dither, upscale, saturation, crt, scanlines, palette_file :
        Forwarded to :func:`pixelate.core.pixelate_image` for each frame.
    colors, extract_method, scale, edges, invert, contrast, colorspace, serpentine,
    phosphor, posterize, bayer_size, seed, downscale, distance :
        Additional pipeline options forwarded per frame.
    output :
        If given, save an animated GIF to this path and return the first
        frame image (for convenience). If ``None``, return
        ``(frames, durations)``.

    Returns
    -------
    PIL.Image or (list[Image], list[int])
        Saved first frame when *output* is set; otherwise pixelated frames
        and per-frame durations in milliseconds.
    """
    source_frames, durations = load_frames(src)

    # For auto palette, extract once from the first frame so colors stay stable
    palette_arg: Union[str, Sequence] = palette
    if (
        palette_file is None
        and isinstance(palette, str)
        and palette.lower().strip() == "auto"
        and source_frames
    ):
        from pixelate.core import extract_palette
        palette_arg = extract_palette(
            source_frames[0], n=colors, method=extract_method, seed=seed
        )

    out_frames: FrameList = []
    for frame in source_frames:
        result = pixelate_image(
            frame,
            palette=palette_arg,
            pixel_size=pixel_size,
            dither=dither,
            upscale=upscale,
            saturation=saturation,
            crt=crt,
            scanlines=scanlines,
            palette_file=palette_file,
            colors=colors,
            extract_method=extract_method,
            scale=scale,
            edges=edges,
            invert=invert,
            contrast=contrast,
            colorspace=colorspace,
            serpentine=serpentine,
            phosphor=phosphor,
            posterize=posterize,
            bayer_size=bayer_size,
            seed=seed,
            downscale=downscale,
            distance=distance,
        )
        out_frames.append(result)

    if output is not None:
        shared = None
        if out_frames:
            shared = out_frames[0].info.get(PALETTE_INFO_KEY)
        save_animation(out_frames, durations, output, palette=shared)
        return out_frames[0]

    return out_frames, durations


def save_animation(
    frames: Sequence[Image.Image],
    durations: Sequence[int],
    path: PathLike,
    *,
    loop: int = 0,
    palette: Optional[Sequence[RGB]] = None,
) -> Path:
    """
    Save frames as an animated GIF.

    Frames are converted to mode ``P`` with a **shared** palette taken from
    the working colors (or *palette* when it covers every pixel). Pillow is
    not asked to invent extra colors. ``disposal=2`` is always set.

    Parameters
    ----------
    frames :
        Pixelated RGB/RGBA frames (must be non-empty).
    durations :
        Per-frame duration in milliseconds. If shorter than *frames*, the
        last duration is reused.
    path :
        Output path (``.gif`` recommended).
    loop :
        Number of loops; ``0`` means infinite.
    palette :
        Optional RGB sequence to use when it contains all working colors.
    """
    if not frames:
        raise ValueError("No frames to save")

    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)

    working = collect_working_colors(frames)
    if palette is not None:
        pal_t = tuple((int(c[0]), int(c[1]), int(c[2])) for c in palette)
        if set(working).issubset(set(pal_t)) and pal_t:
            working = pal_t

    p_frames = [image_to_indexed(f, working) for f in frames]
    durs: list[int] = []
    for i in range(len(p_frames)):
        if i < len(durations):
            durs.append(max(1, int(durations[i])))
        else:
            durs.append(max(1, int(durations[-1]) if durations else 100))

    first, rest = p_frames[0], p_frames[1:]
    save_kwargs = {
        "save_all": True,
        "append_images": list(rest),
        "duration": durs,
        "loop": loop,
        "optimize": False,
        "disposal": 2,
    }
    first.save(p, **save_kwargs)
    return p
