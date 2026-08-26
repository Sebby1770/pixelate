"""End-to-end tests for the conversion pipeline."""

from pathlib import Path

import numpy as np
from PIL import Image

from pixelate.core import (
    _resize_keep_aspect,
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


def test_box_downscale_32_to_pixel_size_8():
    src = _make_test_image(size=(32, 32))
    out = pixelate_image(
        src, palette="gameboy", pixel_size=8, upscale=1, dither="none", downscale="box"
    )
    assert max(out.size) == 8
    resized = _resize_keep_aspect(src, 8, filter="box")
    assert max(resized.size) == 8


def test_downscale_filters_keep_long_side():
    src = _make_test_image(size=(32, 16))
    for filt in ("box", "lanczos", "nearest"):
        out = pixelate_image(
            src,
            palette="cga",
            pixel_size=8,
            upscale=1,
            dither="none",
            downscale=filt,
        )
        assert max(out.size) == 8


def test_ciede2000_output_subset_of_palette():
    src = _make_test_image()
    pal = set(get_palette("cga"))
    out = pixelate_image(
        src,
        palette="cga",
        pixel_size=16,
        upscale=1,
        dither="none",
        colorspace="ciede2000",
    )
    unique = {tuple(int(x) for x in c) for c in np.array(out).reshape(-1, 3)}
    assert unique.issubset(pal)


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


def test_save_image_jpeg_becomes_png(tmp_path: Path):
    img = _make_test_image((8, 8))
    dest = tmp_path / "out.jpg"
    saved = save_image(img, dest)
    assert saved.suffix == ".png"
    assert saved.is_file()
    assert not dest.exists()


def test_save_image_indexed_png(tmp_path: Path):
    src = _make_test_image()
    out = pixelate_image(src, palette="cga", pixel_size=16, upscale=1, dither="none")
    dest = tmp_path / "indexed.png"
    saved = save_image(out, dest, palette=out.info["pixelate_palette"])
    with Image.open(saved) as im:
        assert im.mode == "P"
        unique = {tuple(c) for c in np.array(im.convert("RGB")).reshape(-1, 3)}
        assert unique.issubset(set(get_palette("cga")))


def test_rgba_keeps_transparent_pixel():
    arr = np.zeros((16, 16, 4), dtype=np.uint8)
    arr[..., :3] = (200, 40, 40)
    arr[..., 3] = 255
    arr[0, 0, 3] = 0
    src = Image.fromarray(arr, mode="RGBA")
    out = pixelate_image(src, palette="cga", pixel_size=16, upscale=1, dither="none")
    assert out.mode == "RGBA"
    assert int(np.array(out)[0, 0, 3]) == 0


def test_auto_palette_stashed_on_info():
    src = _make_test_image()
    out = pixelate_image(
        src, palette="auto", colors=4, pixel_size=16, upscale=1, dither="none"
    )
    assert "pixelate_palette" in out.info
    pal = out.info["pixelate_palette"]
    assert 1 <= len(pal) <= 4
    unique = {tuple(int(x) for x in c) for c in np.array(out.convert("RGB")).reshape(-1, 3)}
    assert unique.issubset({tuple(c) for c in pal})


def test_spritesheet_preserves_alpha():
    opaque = Image.new("RGB", (8, 8), (255, 0, 0))
    trans = Image.new("RGBA", (8, 8), (0, 255, 0, 0))
    sheet = make_spritesheet([opaque, trans], cols=2, padding=0)
    assert sheet.mode == "RGBA"
    arr = np.array(sheet)
    # second tile is fully transparent
    assert int(arr[0, 8, 3]) == 0


def test_pixelate_new_palettes():
    src = _make_test_image()
    for name in ("ega", "msx", "vaporwave", "db16", "sms", "master-system"):
        out = pixelate_image(src, palette=name, pixel_size=16, upscale=1, dither="none")
        assert isinstance(out, Image.Image)


def test_pixelate_new_dithers():
    src = _make_test_image()
    for dither in ("stucki", "burkes", "sierra", "sierra3", "sierra-lite", "jjn"):
        out = pixelate_image(src, palette="cga", pixel_size=16, upscale=1, dither=dither)
        assert isinstance(out, Image.Image)
        unique = {tuple(int(x) for x in c) for c in np.array(out).reshape(-1, 3)}
        assert unique.issubset(set(get_palette("cga")))


def test_posterize_output_subset_of_palette():
    src = _make_test_image()
    pal = set(get_palette("gameboy"))
    out = pixelate_image(
        src, palette="gameboy", posterize=4, pixel_size=32, upscale=1, dither="none"
    )
    unique = {tuple(int(x) for x in c) for c in np.array(out).reshape(-1, 3)}
    assert unique.issubset(pal)


def test_bayer_size_8_subset_of_palette():
    src = _make_test_image()
    pal = set(get_palette("cga"))
    out = pixelate_image(
        src,
        palette="cga",
        dither="bayer",
        bayer_size=8,
        pixel_size=16,
        upscale=1,
    )
    unique = {tuple(int(x) for x in c) for c in np.array(out).reshape(-1, 3)}
    assert unique.issubset(pal)
