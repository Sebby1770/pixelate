"""End-to-end tests for the conversion pipeline."""

from pathlib import Path

import numpy as np
from PIL import Image

from pixelate.core import (
    collect_images,
    make_spritesheet,
    pixelate_image,
    resolve_palette,
    save_image,
)
from pixelate.palettes import get_palette


def _make_test_image(size=(64, 64)):
    arr = np.zeros((size[1], size[0], 3), dtype=np.uint8)
    # Simple 4-quadrant test image
    arr[: size[1] // 2, : size[0] // 2] = (200, 50, 50)
    arr[: size[1] // 2, size[0] // 2:] = (50, 200, 50)
    arr[size[1] // 2:, : size[0] // 2] = (50, 50, 200)
    arr[size[1] // 2:, size[0] // 2:] = (220, 220, 50)
    return Image.fromarray(arr, mode="RGB")


def test_pixelate_image_returns_image():
    src = _make_test_image()
    out = pixelate_image(src, palette="gameboy", pixel_size=32, upscale=2, dither="none")
    assert isinstance(out, Image.Image)


def test_pixelate_image_uses_only_palette_colors():
    src = _make_test_image()
    out = pixelate_image(src, palette="gameboy", pixel_size=32, upscale=1, dither="none")
    arr = np.array(out)
    palette = {tuple(c) for c in get_palette("gameboy")}
    unique = {tuple(c) for c in arr.reshape(-1, 3)}
    assert unique.issubset(palette)


def test_pixelate_image_respects_pixel_size():
    src = _make_test_image(size=(128, 64))
    out = pixelate_image(src, palette="gameboy", pixel_size=32, upscale=1, dither="none")
    # Longest side downscaled to 32 before upscale=1
    assert max(out.size) == 32


def test_pixelate_image_upscale_multiplies_size():
    src = _make_test_image(size=(64, 64))
    out = pixelate_image(src, palette="gameboy", pixel_size=32, upscale=4, dither="none")
    assert out.size == (32 * 4, 32 * 4)


def test_pixelate_image_palette_file(tmp_path: Path):
    hex_path = tmp_path / "tiny.hex"
    hex_path.write_text("000000\nFFFFFF\nFF0000\n", encoding="utf-8")
    src = _make_test_image()
    out = pixelate_image(
        src,
        palette="gameboy",  # overridden by palette_file
        palette_file=hex_path,
        pixel_size=16,
        upscale=1,
        dither="none",
    )
    arr = np.array(out)
    unique = {tuple(c) for c in arr.reshape(-1, 3)}
    assert unique.issubset({(0, 0, 0), (255, 255, 255), (255, 0, 0)})


def test_pixelate_image_palette_sequence():
    src = _make_test_image()
    custom = ((0, 0, 0), (255, 255, 0), (0, 255, 255))
    out = pixelate_image(src, palette=custom, pixel_size=16, upscale=1, dither="none")
    unique = {tuple(c) for c in np.array(out).reshape(-1, 3)}
    assert unique.issubset(set(custom))


def test_resolve_palette_name():
    assert resolve_palette("pico8") == get_palette("pico8")


def test_resolve_palette_file(tmp_path: Path):
    p = tmp_path / "p.hex"
    p.write_text("112233\n445566\n", encoding="utf-8")
    assert resolve_palette(p) == ((0x11, 0x22, 0x33), (0x44, 0x55, 0x66))


def test_collect_images(tmp_path: Path):
    (tmp_path / "a.png").write_bytes(b"")
    # write real minimal png via PIL
    Image.new("RGB", (4, 4), (1, 2, 3)).save(tmp_path / "a.png")
    Image.new("RGB", (4, 4), (1, 2, 3)).save(tmp_path / "b.jpg")
    (tmp_path / "notes.txt").write_text("nope", encoding="utf-8")
    found = collect_images([tmp_path])
    names = {f.name for f in found}
    assert "a.png" in names
    assert "b.jpg" in names
    assert "notes.txt" not in names


def test_make_spritesheet():
    imgs = [
        Image.new("RGB", (10, 10), (255, 0, 0)),
        Image.new("RGB", (10, 10), (0, 255, 0)),
        Image.new("RGB", (10, 10), (0, 0, 255)),
    ]
    sheet = make_spritesheet(imgs, cols=2, padding=0)
    # 2 cols → 2 rows (3 tiles), tile 10x10
    assert sheet.size == (20, 20)


def test_make_spritesheet_padding():
    imgs = [Image.new("RGB", (8, 8), (1, 1, 1)) for _ in range(4)]
    sheet = make_spritesheet(imgs, cols=2, padding=2)
    # 2*8 + 1*2 = 18
    assert sheet.size == (18, 18)


def test_save_image(tmp_path: Path):
    img = _make_test_image((8, 8))
    dest = tmp_path / "nested" / "out.png"
    saved = save_image(img, dest)
    assert saved.is_file()


def test_pixelate_new_palettes():
    src = _make_test_image()
    for name in ("ega", "msx", "vaporwave", "db16", "sms", "master-system"):
        out = pixelate_image(src, palette=name, pixel_size=16, upscale=1, dither="none")
        assert isinstance(out, Image.Image)


def test_pixelate_new_dithers():
    src = _make_test_image()
    for dither in ("stucki", "burkes", "sierra"):
        out = pixelate_image(src, palette="cga", pixel_size=16, upscale=1, dither=dither)
        assert isinstance(out, Image.Image)
