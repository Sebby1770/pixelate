"""
Animated GIF / multi-frame WebP support.

Detect multi-frame inputs, pixelate each frame with the same pipeline as
``pixelate_image``, and reassemble an animated GIF preserving approximate
frame durations.
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional, Sequence, Tuple, Union

from PIL import Image

from pixelate.core import pixelate_image

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


def load_frames(src: Union[PathLike, Image.Image]) -> Tuple[FrameList, DurationList]:
    """
    Load all frames and their durations (ms) from an animated image.

    For still images, returns a single frame with duration 100ms.
    Duration defaults to 100ms when not stored in the source.
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
            frame = img.convert("RGB").copy()
            frames.append(frame)
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
    color_space: str = "rgb",
    posterize: Optional[int] = None,
    grid: bool = False,
    outline: bool = False,
    chromatic: bool = False,
    color_bleed: bool = False,
) -> Union[Image.Image, Tuple[FrameList, DurationList]]:
    """
    Pixelate every frame of an animated (or still) image.

    Parameters
    ----------
    src :
        Path or PIL Image (animated GIF/WebP or still).
    palette, pixel_size, dither, upscale, saturation, crt, scanlines, palette_file :
        Forwarded to :func:`pixelate.core.pixelate_image` for each frame.
    colors, extract_method, scale, edges, invert, contrast :
        Additional v2.1 pipeline options forwarded per frame.
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
            source_frames[0], n=colors, method=extract_method
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
            color_space=color_space,
            posterize=posterize,
            grid=grid,
            outline=outline,
            chromatic=chromatic,
            color_bleed=color_bleed,
        )
        out_frames.append(result.convert("RGB"))

    if output is not None:
        save_animation(out_frames, durations, output)
        return out_frames[0]

    return out_frames, durations


def save_animation(
    frames: Sequence[Image.Image],
    durations: Sequence[int],
    path: PathLike,
    *,
    loop: int = 0,
) -> Path:
    """
    Save frames as an animated GIF.

    Parameters
    ----------
    frames :
        Pixelated RGB frames (must be non-empty).
    durations :
        Per-frame duration in milliseconds. If shorter than *frames*, the
        last duration is reused.
    path :
        Output path (``.gif`` recommended).
    loop :
        Number of loops; ``0`` means infinite.
    """
    if not frames:
        raise ValueError("No frames to save")

    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)

    rgb_frames = [f.convert("RGB") for f in frames]
    durs: list[int] = []
    for i in range(len(rgb_frames)):
        if i < len(durations):
            durs.append(max(1, int(durations[i])))
        else:
            durs.append(max(1, int(durations[-1]) if durations else 100))

    first, rest = rgb_frames[0], rgb_frames[1:]
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
