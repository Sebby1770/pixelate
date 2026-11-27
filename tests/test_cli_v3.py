"""CLI coverage for the 3.0 options and commands."""

import json

import numpy as np
from click.testing import CliRunner
from PIL import Image

from pixelate.cli import cli
from pixelate.hardware import get_hardware_mode


def _src(tmp_path, size=(48, 32)):
    w, h = size
    arr = np.zeros((h, w, 3), dtype=np.uint8)
    arr[..., 0] = np.linspace(0, 255, w, dtype=np.uint8)[None, :]
    arr[..., 1] = np.linspace(0, 255, h, dtype=np.uint8)[:, None]
    arr[..., 2] = 120
    path = tmp_path / "src.png"
    Image.fromarray(arr).save(path)
    return path


def _run(*args):
    result = CliRunner().invoke(cli, [str(a) for a in args], catch_exceptions=False)
    return result


def test_hardware_flag_uses_machine_palette_and_native_size(tmp_path):
    src = _src(tmp_path, (400, 300))  # larger than native: downscale only shrinks
    out = tmp_path / "zx.png"
    r = _run("convert", src, "--hardware", "zx", "--upscale", "1", "-o", out)
    assert r.exit_code == 0, r.output
    assert "Clash:" in r.output and "hw:zx" in r.output
    img = Image.open(out).convert("RGB")
    assert max(img.size) == get_hardware_mode("zx").pixel_size
    zx = {tuple(c) for c in get_hardware_mode("zx").palette}
    assert {tuple(c) for c in np.asarray(img).reshape(-1, 3)} <= zx


def test_hardware_alias_and_explicit_pixel_size(tmp_path):
    src = _src(tmp_path, (400, 300))
    out = tmp_path / "s.png"
    r = _run("convert", src, "--hardware", "spectrum", "--pixel-size", "64", "--upscale", "1", "-o", out)
    assert r.exit_code == 0, r.output
    assert max(Image.open(out).size) == 64


def test_preset_applies_and_typed_flags_win(tmp_path):
    src = _src(tmp_path)
    out = tmp_path / "p.png"
    r = _run("convert", src, "--preset", "pico8-postcard", "--pixel-size", "32", "--upscale", "1", "-o", out)
    assert r.exit_code == 0, r.output
    assert "Preset:" in r.output and "pico8-postcard" in r.output
    assert max(Image.open(out).size) == 32  # typed flag beat the preset's 128


def test_preset_sets_studio_options(tmp_path):
    src = _src(tmp_path)
    r = _run("convert", src, "--preset", "c64-demo", "--pixel-size", "64", "-o", tmp_path / "c.png")
    assert r.exit_code == 0, r.output
    assert "hardware=c64-multi" in r.output and "color-bleed=0.4" in r.output


def test_unknown_preset_errors(tmp_path):
    r = CliRunner().invoke(cli, ["convert", str(_src(tmp_path)), "--preset", "nope"])
    assert r.exit_code != 0
    assert "Unknown preset" in r.output


def test_presets_file(tmp_path):
    presets = tmp_path / "mine.json"
    presets.write_text(json.dumps({"tiny-gb": {"description": "tiny", "palette": "gameboy", "pixel_size": 16}}))
    out = tmp_path / "t.png"
    r = _run("convert", _src(tmp_path), "--presets-file", presets, "--preset", "tiny-gb", "--upscale", "1", "-o", out)
    assert r.exit_code == 0, r.output
    assert max(Image.open(out).size) == 16


def test_outline_color_upscaler_and_effects(tmp_path):
    out = tmp_path / "o.png"
    r = _run(
        "convert", _src(tmp_path), "--palette", "pico8", "--pixel-size", "24",
        "--outline", "1", "--outline-color", "#f0f", "--upscaler", "scale2x", "--upscale", "2",
        "--grid", "--chromatic", "1", "--color-bleed", "0.3", "--curvature", "0.05", "--cleanup", "1",
        "-o", out,
    )
    assert r.exit_code == 0, r.output
    assert "upscaler=scale2x" in r.output and "outline=1" in r.output
    assert Image.open(out).size[0] == 48


def test_bad_outline_color(tmp_path):
    r = CliRunner().invoke(cli, ["convert", str(_src(tmp_path)), "--outline", "1", "--outline-color", "nothex"])
    assert r.exit_code != 0
    assert "#RRGGBB" in r.output


def test_svg_json_header_outputs(tmp_path):
    src = _src(tmp_path)
    for ext in ("svg", "json", "h"):
        out = tmp_path / f"art.{ext}"
        r = _run("convert", src, "--palette", "gameboy", "--pixel-size", "16", "-o", out)
        assert r.exit_code == 0, r.output
        text = out.read_text()
        assert {"svg": "<svg", "json": '"pixelate-indexed"', "h": "art_pixels"}[ext] in text
    doc = json.loads((tmp_path / "art.json").read_text())
    assert max(doc["width"], doc["height"]) == 16


def test_new_dithers_on_cli(tmp_path):
    src = _src(tmp_path)
    for name in ("pattern", "bluenoise", "halftone", "knoll"):
        r = CliRunner().invoke(cli, ["convert", str(src), "--dither", name, "--pixel-size", "16", "-o", str(tmp_path / f"{name}.png")])
        if name == "knoll":  # alias is accepted by the API, not listed as a CLI choice
            assert r.exit_code != 0
        else:
            assert r.exit_code == 0, r.output


def test_listing_commands():
    for cmd, needle in (("hardware", "ZX Spectrum"), ("presets", "zx-loading-screen"), ("dithers", "bluenoise")):
        r = _run(cmd)
        assert r.exit_code == 0
        assert needle in r.output


def test_swatches_command(tmp_path):
    for name in ("pico8", "hw:c64"):
        out = tmp_path / f"{name.replace(':', '-')}.png"
        r = _run("swatches", name, "-o", out, "--cols", "4")
        assert r.exit_code == 0, r.output
        assert Image.open(out).size[0] > 0
    r = CliRunner().invoke(cli, ["swatches", "hw:amiga"])
    assert r.exit_code != 0


def test_compare_hardware_modes(tmp_path):
    out = tmp_path / "cmp.png"
    r = _run("compare", _src(tmp_path), "--palettes", "hw:zx,hw:nes,gameboy", "--pixel-size", "32", "-o", out)
    assert r.exit_code == 0, r.output
    bad = CliRunner().invoke(cli, ["compare", str(_src(tmp_path)), "--palettes", "hw:atari-st"])
    assert bad.exit_code != 0


def test_batch_with_preset_and_jobs(tmp_path):
    indir = tmp_path / "in"
    indir.mkdir()
    for i in range(3):
        Image.new("RGB", (20, 12), (i * 80, 40, 200 - i * 60)).save(indir / f"{i}.png")
    outdir = tmp_path / "out"
    r = _run("batch", indir, "-o", outdir, "--preset", "nes-cart", "--pixel-size", "32", "--jobs", "2")
    assert r.exit_code == 0, r.output
    assert len(list(outdir.glob("*.png"))) == 3


def test_animation_with_hardware(tmp_path):
    frames = [Image.new("RGB", (24, 16), (c, 255 - c, 90)) for c in (0, 128, 255)]
    gif = tmp_path / "anim.gif"
    frames[0].save(gif, save_all=True, append_images=frames[1:], duration=80, loop=0)
    out = tmp_path / "anim_out.gif"
    r = _run("convert", gif, "--hardware", "c64", "--pixel-size", "16", "--outline", "1", "-o", out)
    assert r.exit_code == 0, r.output
    assert Image.open(out).n_frames == 3
