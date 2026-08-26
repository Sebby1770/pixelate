"""CLI tests via click.testing.CliRunner."""

from pathlib import Path

from click.testing import CliRunner
from PIL import Image

from pixelate.cli import cli


def _write_rgb(path: Path, size=(24, 24), color=(180, 40, 40)) -> Path:
    Image.new("RGB", size, color).save(path)
    return path


def test_convert_writes_png(tmp_path: Path):
    src = _write_rgb(tmp_path / "photo.png")
    dest = tmp_path / "out.png"
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "convert",
            str(src),
            "-o", str(dest),
            "--pixel-size", "16",
            "--upscale", "1",
            "--dither", "none",
        ],
    )
    assert result.exit_code == 0, result.output
    assert dest.is_file()
    with Image.open(dest) as im:
        assert im.format == "PNG"


def test_convert_jpeg_output_forced_png(tmp_path: Path):
    src = _write_rgb(tmp_path / "photo.png")
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "convert",
            str(src),
            "-o", str(tmp_path / "out.jpg"),
            "--pixel-size", "16",
            "--upscale", "1",
            "--dither", "none",
        ],
    )
    assert result.exit_code == 0, result.output
    assert (tmp_path / "out.png").is_file()
    assert not (tmp_path / "out.jpg").exists()


def test_batch_jpg_input_writes_png_dest(tmp_path: Path):
    inp = tmp_path / "in"
    out = tmp_path / "out"
    inp.mkdir()
    Image.new("RGB", (20, 20), (10, 20, 30)).save(inp / "shot.jpg", quality=90)
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "batch",
            str(inp),
            "-o", str(out),
            "--pixel-size", "16",
            "--upscale", "1",
            "--dither", "none",
        ],
    )
    assert result.exit_code == 0, result.output
    pngs = list(out.glob("*.png"))
    assert pngs, list(out.iterdir())
    assert list(out.glob("*.jpg")) == []


def test_extract_writes_gpl(tmp_path: Path):
    src = _write_rgb(tmp_path / "src.png", color=(12, 34, 56))
    dest = tmp_path / "pal.gpl"
    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["extract", str(src), "-o", str(dest), "--colors", "4"],
    )
    assert result.exit_code == 0, result.output
    text = dest.read_text(encoding="utf-8")
    assert "GIMP Palette" in text
    assert "12" in text or " 12 " in text


def test_unknown_palette_errors(tmp_path: Path):
    src = _write_rgb(tmp_path / "src.png")
    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["convert", str(src), "--palette", "not-a-real-palette"],
    )
    assert result.exit_code != 0
    assert "Unknown palette" in (result.output + (result.exception and str(result.exception) or ""))


def test_convert_phosphor_and_posterize(tmp_path: Path):
    src = _write_rgb(tmp_path / "photo.png")
    dest = tmp_path / "out.png"
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "convert",
            str(src),
            "-o", str(dest),
            "--pixel-size", "16",
            "--upscale", "1",
            "--dither", "none",
            "--phosphor",
            "--posterize", "4",
        ],
    )
    assert result.exit_code == 0, result.output
    assert dest.is_file()
    with Image.open(dest) as im:
        assert im.size[0] > 0 and im.size[1] > 0


def test_palettes_save_gpl(tmp_path: Path):
    dest = tmp_path / "gb.gpl"
    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["palettes", "--save-gpl", "gameboy", "-o", str(dest)],
    )
    assert result.exit_code == 0, result.output
    assert dest.is_file()
    assert "GIMP Palette" in dest.read_text(encoding="utf-8")
