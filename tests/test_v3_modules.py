"""3.0 pipeline options, exports, presets, upscalers, effects, palettes, web data."""

import importlib.util
import json
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from pixelate import pixelate_image
from pixelate.core import HARDWARE_INFO_KEY, INDICES_INFO_KEY, PALETTE_INFO_KEY, save_image
from pixelate.effects import (
    _dilate,
    apply_chromatic_aberration,
    apply_color_bleed,
    apply_curvature,
    apply_grid,
    apply_outline,
    cleanup_orphans,
)
from pixelate.export import export_indexed, swatch_sheet, to_c_header, to_json, to_svg
from pixelate.hardware import HARDWARE_MODES
from pixelate.palettes import PALETTES
from pixelate.presets import (
    PRESETS,
    get_preset,
    load_presets_file,
    merge_preset,
    register_preset,
)
from pixelate.upscale import scale2x, scale3x, upscale_image

ROOT = Path(__file__).resolve().parents[1]


def _photo(w=60, h=40):
    x = np.linspace(0, 255, w)
    y = np.linspace(0, 255, h)
    arr = np.zeros((h, w, 3), dtype=np.uint8)
    arr[..., 0] = x[None, :].astype(np.uint8)
    arr[..., 1] = y[:, None].astype(np.uint8)
    arr[..., 2] = 128
    return Image.fromarray(arr)


def _sprite(size=16, rgba=False):
    arr = np.zeros((size, size, 4 if rgba else 3), dtype=np.uint8)
    arr[...] = (255, 255, 255, 0)[: arr.shape[2]] if rgba else (255, 255, 255)
    arr[5:11, 5:11, :3] = (255, 0, 77)
    if rgba:
        arr[5:11, 5:11, 3] = 255
    return Image.fromarray(arr, "RGBA" if rgba else "RGB")


# --------------------------------------------------------------- pipeline
def test_hardware_overrides_palette_and_reports():
    img = pixelate_image(_photo(), hardware="zx", pixel_size=48, upscale=1, palette="gameboy")
    pal = img.info[PALETTE_INFO_KEY]
    assert len(pal) == 16
    assert img.info[HARDWARE_INFO_KEY]["mode"] == "ZX Spectrum"


def test_c64_multicolor_pixels_come_in_pairs():
    img = pixelate_image(_photo(64, 40), hardware="c64-multi", pixel_size=64, upscale=1, dither="floyd")
    idx = img.info[INDICES_INFO_KEY]
    assert idx.shape[1] % 2 == 0
    assert np.array_equal(idx[:, 0::2], idx[:, 1::2])


def test_indices_reproduce_the_image():
    img = pixelate_image(_photo(), palette="pico8", pixel_size=30, upscale=1, dither="pattern")
    idx, pal = img.info[INDICES_INFO_KEY], np.array(img.info[PALETTE_INFO_KEY])
    assert idx.shape == (img.size[1], img.size[0])
    assert np.array_equal(pal[idx].astype(np.uint8), np.asarray(img))


@pytest.mark.parametrize("method,factor", [("scale2x", 2), ("scale3x", 3), ("scale4x", 4), ("scale3x", 6)])
def test_upscaler_in_pipeline_stays_palette_locked(method, factor):
    img = pixelate_image(_photo(), palette="pico8", pixel_size=20, upscale=factor, upscaler=method)
    pal = {tuple(c) for c in img.info[PALETTE_INFO_KEY]}
    assert {tuple(c) for c in np.asarray(img).reshape(-1, 3)} <= pal
    assert img.size == (20 * factor, round(40 * 20 / 60) * factor)


def test_outline_default_ink_is_darkest_palette_color():
    img = pixelate_image(_sprite(), palette="pico8", pixel_size=16, upscale=1, dither="none", outline=1)
    arr = np.asarray(img)
    assert tuple(arr[4, 7]) == (0, 0, 0)  # just above the sprite
    assert tuple(arr[0, 0]) != (0, 0, 0)  # background untouched


def test_outline_custom_color_extends_palette_and_alpha_is_used():
    img = pixelate_image(_sprite(rgba=True), palette="pico8", pixel_size=16, upscale=1,
                         dither="none", outline=1, outline_color=(1, 2, 3))
    assert (1, 2, 3) in img.info[PALETTE_INFO_KEY]
    assert img.mode == "RGBA"
    assert tuple(np.asarray(img.convert("RGB"))[4, 7]) == (1, 2, 3)


def test_cleanup_removes_isolated_pixel():
    arr = np.full((9, 9, 3), 255, dtype=np.uint8)
    arr[4, 4] = (0, 0, 0)
    img = pixelate_image(Image.fromarray(arr), palette="1bit", pixel_size=9, upscale=1, dither="none", cleanup=1)
    assert (np.asarray(img) == 255).all()


@pytest.mark.parametrize("kw", [dict(grid=True), dict(chromatic=2), dict(color_bleed=0.8), dict(curvature=0.1)])
def test_effects_change_pixels_but_not_size(kw):
    base = pixelate_image(_photo(), palette="pico8", pixel_size=20, upscale=4)
    out = pixelate_image(_photo(), palette="pico8", pixel_size=20, upscale=4, **kw)
    assert out.size == base.size
    assert not np.array_equal(np.asarray(out), np.asarray(base))


def test_preset_applies_and_explicit_args_win():
    a = pixelate_image(_photo(200, 120), preset="pico8-postcard", upscale=1)
    assert max(a.size) == 128
    assert len(a.info[PALETTE_INFO_KEY]) == 16
    b = pixelate_image(_photo(200, 120), preset="pico8-postcard", pixel_size=40, upscale=1)
    assert max(b.size) == 40
    with pytest.raises(KeyError):
        pixelate_image(_photo(), preset="nope")


def test_hardware_defaults_to_native_resolution():
    img = pixelate_image(_photo(400, 300), hardware="nes", upscale=1)
    assert max(img.size) == 256


# ----------------------------------------------------------------- export
def _runs(idx):
    return sum(1 + int(np.count_nonzero(row[1:] != row[:-1])) for row in idx)


def test_svg_is_valid_and_merges_runs():
    idx = np.array([[0, 0, 1, 1, 1], [2, 2, 2, 2, 2], [0, 1, 0, 1, 0]])
    pal = [(0, 0, 0), (255, 0, 0), (0, 0, 255)]
    svg = to_svg(idx, pal, pixel=4)
    root = ET.fromstring(svg)
    rects = root.findall(".//{http://www.w3.org/2000/svg}rect")
    assert len(rects) == _runs(idx)
    assert root.get("shape-rendering") == "crispEdges"
    assert root.get("width") == "20"
    mask = np.zeros_like(idx, dtype=bool)
    mask[1] = True
    assert len(ET.fromstring(to_svg(idx, pal, transparent=mask)).findall(".//{http://www.w3.org/2000/svg}rect")) == _runs(idx) - 1


def test_json_round_trip_and_c_header():
    idx = np.array([[0, 1], [1, 0]])
    pal = [(0, 0, 0), (255, 255, 255)]
    doc = json.loads(to_json(idx, pal))
    assert doc["format"] == "pixelate-indexed" and doc["pixels"] == [[0, 1], [1, 0]]
    assert doc["palette"] == ["#000000", "#ffffff"]
    header = to_c_header(idx, pal, name="8-bit hero")
    assert "_8_bit_hero_pixels[4]" in header
    assert "#ifndef _8_BIT_HERO_H" in header
    assert "{255, 255, 255}," in header


def test_export_dispatch_and_errors(tmp_path):
    idx = np.zeros((2, 3), dtype=int)
    for ext in ("svg", "json", "h", "c"):
        assert export_indexed(idx, [(1, 2, 3)], tmp_path / f"a.{ext}").exists()
    with pytest.raises(ValueError):
        export_indexed(idx, [(1, 2, 3)], tmp_path / "a.bmp")


def test_save_image_exports_and_strips_private_info(tmp_path):
    img = pixelate_image(_photo(), palette="gameboy", pixel_size=12, upscale=2)
    for ext in ("svg", "json", "h"):
        assert save_image(img, tmp_path / f"art.{ext}").stat().st_size > 0
    doc = json.loads((tmp_path / "art.json").read_text())
    assert (doc["width"], doc["height"]) == (12, 8)
    png = save_image(img, tmp_path / "art.png", palette=img.info[PALETTE_INFO_KEY])
    assert Image.open(png).mode == "P"
    assert INDICES_INFO_KEY in img.info and PALETTE_INFO_KEY in img.info  # restored
    plain = Image.new("RGB", (3, 2), (9, 9, 9))
    assert json.loads(save_image(plain, tmp_path / "plain.json").read_text())["palette"] == ["#090909"]


def test_swatch_sheet():
    sheet = swatch_sheet([(255, 0, 0), (0, 255, 0), (0, 0, 255)], cols=2, swatch=10, label=False)
    assert sheet.size == (8 + 2 * 18, 8 + 2 * 18)
    assert sheet.getpixel((8, 8)) == (255, 0, 0)
    with pytest.raises(ValueError):
        swatch_sheet([])


# ---------------------------------------------------------------- presets
@pytest.mark.parametrize("name", list(PRESETS))
def test_every_preset_renders(name):
    img = pixelate_image(_photo(48, 32), preset=name, pixel_size=24)
    assert img.size[0] > 0


def test_merge_register_and_load(tmp_path):
    defaults = {"palette": "gameboy", "pixel_size": 96, "dither": "floyd"}
    register_preset("tiny", "t", palette="pico8", pixel_size=16)
    merged = merge_preset("tiny", {"palette": "gameboy", "pixel_size": 40, "dither": "floyd"}, defaults)
    assert merged == {"palette": "pico8", "pixel_size": 40, "dither": "floyd"}
    with pytest.raises(KeyError):
        merge_preset("tiny", {}, {"palette": "gameboy"})  # preset sets unknown pixel_size
    good = tmp_path / "p.json"
    good.write_text(json.dumps({"neon": {"description": "glow", "palette": "cyberpunk"}}))
    assert load_presets_file(good)["neon"].description == "glow"
    assert get_preset("NEON").options == {"palette": "cyberpunk"}
    bad = tmp_path / "bad.json"
    bad.write_text("[1, 2]")
    with pytest.raises(ValueError):
        load_presets_file(bad)
    bad.write_text(json.dumps({"x": 3}))
    with pytest.raises(ValueError):
        load_presets_file(bad)


# --------------------------------------------------------------- upscale
def test_scale2x_and_scale3x_never_invent_colors():
    rng = np.random.default_rng(1)
    pal = np.array([[0, 0, 0], [255, 0, 0], [0, 255, 0], [10, 20, 30]], dtype=np.uint8)
    arr = pal[rng.integers(0, 4, size=(9, 7))]
    for fn, f in ((scale2x, 2), (scale3x, 3)):
        out = fn(arr)
        assert out.shape == (9 * f, 7 * f, 3)
        assert {tuple(c) for c in out.reshape(-1, 3)} <= {tuple(c) for c in pal}


def test_scale2x_solid_and_checkerboard_unchanged():
    solid = np.full((3, 3, 3), 7, dtype=np.uint8)
    assert (scale2x(solid) == 7).all()
    checker = np.indices((4, 4)).sum(axis=0) % 2 * 255
    checker = np.repeat(checker[..., None], 3, axis=2).astype(np.uint8)
    # Interior pixels have equal up/down neighbours, so EPX leaves them alone
    # (edge pixels see clamped neighbours and may round off, as in AdvMAME).
    expected = np.repeat(np.repeat(checker, 2, 0), 2, 1)
    assert np.array_equal(scale2x(checker)[2:6, 2:6], expected[2:6, 2:6])


def test_upscale_image_sizes_alpha_and_errors():
    img = Image.new("RGBA", (5, 4), (10, 20, 30, 128))
    for method in ("nearest", "scale2x", "scale3x", "scale4x"):
        for f in (2, 3, 4, 6, 8):
            out = upscale_image(img, f, method)
            assert out.size == (5 * f, 4 * f) and out.mode == "RGBA"
    assert upscale_image(img, 1, "scale2x") is img
    with pytest.raises(ValueError):
        upscale_image(img, 0)
    with pytest.raises(ValueError):
        upscale_image(img, 2, "hq2x")


# ---------------------------------------------------------------- effects
def test_effect_functions():
    img = Image.new("RGB", (20, 10), (200, 100, 50))
    grid = np.asarray(apply_grid(img, 5))
    assert tuple(grid[5, 1]) != (200, 100, 50) and tuple(grid[1, 1]) == (200, 100, 50)
    assert apply_grid(img, 1) is img
    edge = np.zeros((4, 6, 3), dtype=np.uint8)
    edge[:, 0] = 255
    shifted = np.asarray(apply_chromatic_aberration(Image.fromarray(edge), 2))
    assert shifted[0, 1, 0] == 255 and shifted[0, -1, 2] == 0  # clamped, no wrap
    bled = np.asarray(apply_color_bleed(img, 0.7)).astype(float)
    assert abs(bled.mean() - np.asarray(img).astype(float).mean()) < 6
    curved = apply_curvature(Image.new("RGB", (40, 30), (255, 255, 255)), 0.2)
    assert curved.size == (40, 30) and curved.getpixel((0, 0)) == (0, 0, 0)
    assert apply_curvature(img, 0) is img


def test_outline_cleanup_and_dilate():
    sprite = _sprite()
    out = np.asarray(apply_outline(sprite, color=(9, 9, 9)))
    assert tuple(out[4, 7]) == (9, 9, 9) and tuple(out[0, 0]) == (255, 255, 255)
    alpha_out = np.asarray(apply_outline(_sprite(rgba=True).convert("RGB"), alpha=_sprite(rgba=True).getchannel("A")))
    assert tuple(alpha_out[4, 7]) == (16, 16, 16)
    labels = np.ones((5, 5), dtype=int)
    labels[1, 1] = labels[3, 3] = 2
    assert (cleanup_orphans(labels, passes=2) == 1).all()
    mask = np.zeros((5, 5), dtype=bool)
    mask[2, 2] = True
    assert _dilate(mask, 1).sum() == 5 and _dilate(mask, 1, diagonal=True).sum() == 9


# --------------------------------------------------------------- palettes
@pytest.mark.parametrize("name,size", [
    ("gamegear", 16), ("virtualboy", 4), ("amstrad", 16), ("teletext", 8), ("db32", 32),
    ("cga0", 4), ("1bit", 2), ("slso8", 8), ("demichrome", 4), ("kirokaze", 4),
    ("ice-cream-gb", 4), ("hollow", 4), ("ayy4", 4),
])
def test_new_palettes(name, size):
    assert len(PALETTES[name]) == size


def test_palette_aliases_and_validity():
    assert PALETTES["game-gear"] is PALETTES["gamegear"]
    assert PALETTES["cpc"] is PALETTES["amstrad"]
    assert PALETTES["virtual-boy"] is PALETTES["virtualboy"]
    for name, colors in PALETTES.items():
        assert all(len(c) == 3 and all(0 <= v <= 255 for v in c) for c in colors), name
        assert len(set(colors)) == len(colors), f"{name} has duplicate colors"


# --------------------------------------------------------------- web data
def test_generated_web_data_is_fresh():
    spec = importlib.util.spec_from_file_location("build_web_data", ROOT / "tools" / "build_web_data.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert json.loads((ROOT / "web" / "data.json").read_text()) == json.loads(mod.render()), \
        "web/data.json is stale — run python tools/build_web_data.py"
    assert (ROOT / "web" / "data.js").read_text() == mod.render_js(), \
        "web/data.js is stale — run python tools/build_web_data.py"
    data = json.loads(mod.render())
    assert set(data["hardware"]) == set(HARDWARE_MODES)
    assert set(data["presets"]) == set(PRESETS)
    covered = set(data["palettes"]) | set(data["paletteAliases"])
    assert covered == set(PALETTES)
