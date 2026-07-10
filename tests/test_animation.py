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
