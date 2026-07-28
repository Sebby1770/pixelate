"""Tests for animated GIF / multi-frame support."""

from pathlib import Path

import numpy as np
from PIL import Image

from pixelate.animation import (
    is_animated,
    load_frames,
    pixelate_animation,
    save_animation,
)


def _make_still(size=(32, 32)) -> Image.Image:
    arr = np.zeros((size[1], size[0], 3), dtype=np.uint8)
    arr[:, :] = (180, 40, 40)
    return Image.fromarray(arr, mode="RGB")


def _make_animated_gif(path: Path, n_frames: int = 3, duration: int = 80) -> Path:
    frames = []
    for i in range(n_frames):
        arr = np.zeros((24, 24, 3), dtype=np.uint8)
        # Shift a bright block so frames differ
        arr[:, i * 4 : i * 4 + 8] = (50 + i * 40, 100, 200 - i * 30)
        frames.append(Image.fromarray(arr, mode="RGB"))
    frames[0].save(
        path,
        save_all=True,
        append_images=frames[1:],
        duration=duration,
        loop=0,
    )
    return path


def test_is_animated_false_for_still():
    img = _make_still()
    assert is_animated(img) is False


def test_is_animated_true_for_gif(tmp_path: Path):
    gif = _make_animated_gif(tmp_path / "anim.gif")
    assert is_animated(gif) is True


def test_load_frames_preserves_count_and_duration(tmp_path: Path):
    gif = _make_animated_gif(tmp_path / "anim.gif", n_frames=4, duration=50)
    frames, durations = load_frames(gif)
    assert len(frames) == 4
    assert len(durations) == 4
    assert all(d == 50 for d in durations)
    assert all(isinstance(f, Image.Image) for f in frames)


def test_load_frames_still_returns_one():
    frames, durations = load_frames(_make_still())
    assert len(frames) == 1
    assert len(durations) == 1


def test_pixelate_animation_returns_frames(tmp_path: Path):
    gif = _make_animated_gif(tmp_path / "anim.gif", n_frames=3)
    result = pixelate_animation(
        gif,
        palette="gameboy",
        pixel_size=16,
        upscale=2,
        dither="none",
    )
    assert isinstance(result, tuple)
    frames, durations = result
    assert len(frames) == 3
    assert len(durations) == 3
    assert all(f.mode == "RGB" for f in frames)


def test_pixelate_animation_saves_gif(tmp_path: Path):
    gif = _make_animated_gif(tmp_path / "anim.gif", n_frames=3, duration=60)
    out = tmp_path / "out.gif"
    first = pixelate_animation(
        gif,
        palette="pico8",
        pixel_size=16,
        upscale=2,
        dither="floyd",
        output=out,
    )
    assert out.is_file()
    assert isinstance(first, Image.Image)
    assert is_animated(out) is True
    with Image.open(out) as saved:
        assert saved.n_frames == 3


def test_save_animation_roundtrip(tmp_path: Path):
    a = _make_still((16, 16))
    b_arr = np.zeros((16, 16, 3), dtype=np.uint8)
    b_arr[:, :] = (40, 180, 40)
    b = Image.fromarray(b_arr, mode="RGB")
    frames = [a, b]
    durations = [100, 200]
    out = tmp_path / "sheet.gif"
    save_animation(frames, durations, out)
    loaded, durs = load_frames(out)
    assert len(loaded) == 2
    assert durs[0] == 100
    assert durs[1] == 200


def test_auto_palette_is_extracted_once_for_all_frames(tmp_path: Path):
    """
    An auto palette must be derived once and reused, not re-extracted per
    frame — otherwise the palette drifts and the animation visibly flickers.
    """
    gif = _make_animated_gif(tmp_path / "in.gif", n_frames=3)
    frames, _ = pixelate_animation(
        gif,
        palette="auto",
        colors=6,
        pixel_size=16,
        upscale=1,
        dither="none",
    )
    assert len(frames) == 3
    used = set()
    for frame in frames:
        used |= set(map(tuple, np.array(frame).reshape(-1, 3)))
    # Every frame draws from the same <= 6 color palette.
    assert len(used) <= 6


def test_new_conversion_kwargs_reach_every_frame(tmp_path: Path):
    """color_space and the effect flags must be forwarded per frame."""
    gif = _make_animated_gif(tmp_path / "in.gif", n_frames=2)
    base, _ = pixelate_animation(
        gif, palette="nes", pixel_size=16, upscale=2, dither="none"
    )
    for kwargs in (
        {"color_space": "lab"},
        {"posterize": 2},
        {"outline": True},
        {"grid": True},
        {"chromatic": True},
        {"color_bleed": True},
    ):
        out, _ = pixelate_animation(
            gif, palette="nes", pixel_size=16, upscale=2, dither="none", **kwargs
        )
        assert len(out) == len(base)
        changed = any(
            not np.array_equal(np.array(a), np.array(b)) for a, b in zip(base, out)
        )
        assert changed, f"{kwargs} had no effect on any frame"
