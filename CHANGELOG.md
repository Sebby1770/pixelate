# Changelog

All notable changes to this project are documented in this file.

## [3.0.0] — 2026-07-22

### Added

- **Perceptual CIELAB matching** (`--color-space lab`): a vectorized sRGB→CIELAB
  conversion (`pixelate.colorspace`, validated exact against reference colors)
  and a cached nearest-palette LUT (`pixelate.lut`). Matching in LAB tracks how
  the eye reads color instead of raw RGB distance.
- **Five retro effects**: `--posterize`, `--outline` (auto background detection
  + roll-based dilation), `--grid`, `--chromatic` (edge-clamped R/B split), and
  `--color-bleed` (NTSC YIQ chroma bleed). All numpy-vectorized, opt-in kwargs on
  `pixelate_image` / `pixelate_animation`.
- **`pixelate extract` command**: save an extracted palette as `.gpl`/`.hex`
  (new `save_gpl` / `save_hex` writers) plus an optional swatch-sheet PNG.
- **Five new palettes**: Game Gear, Virtual Boy, Amstrad CPC, Teletext, and
  DawnBringer 32.
- Developer tooling: ruff + mypy configuration, both clean; CI now runs the test
  matrix on Python 3.9–3.13 plus a dedicated lint/type job.

### Changed

- Version **3.0.0**.
- Dithering routes palette matching through the new engine; the default RGB
  no-dither path stays exact (byte-identical output). The LUT is used only where
  it wins — LAB error diffusion and large palettes.
- All new features default off, so existing output and the public API are
  unchanged; builds on the 2.1 auto-palette, compare, scale, and report work.

## [2.1.0] — 2026-07-19

### Added

- **Auto palette** — `--palette auto --colors N` extracts an N-color palette from the source image via k-means or median-cut (numpy only, no sklearn).
- **Palette compare collage** — `pixelate compare photo.jpg --palettes gameboy,nes,pico8,c64 -o compare.png` builds a labeled multi-palette grid.
- **Nearest-neighbor scale** — `--scale N` extra integer upscale after pixelate for chunky display pixels (`nearest_scale()` API).
- **Edge-aware pre-pass** — `--edges` sharpen / emboss-lite before quantize to preserve outlines.
- **Color usage report** — `--report` prints a table of how many pixels use each palette color.
- **Invert / contrast** — `--invert` and `--contrast F` pre-quantization helpers.
- **New palettes** — Game Boy Color (`gameboy-color` / `gbc`), VIC-20 (`vic20`), Atari 2600 (`atari2600`), Tokyo Night (`tokyo-night`), Cyberpunk (`cyberpunk`).
- **API** — `extract_palette()`, `compare_palettes()`, `color_usage_report()`, `nearest_scale()` exported from package root.

### Tests

- `test_auto_palette.py`, `test_compare.py`, `test_scale.py`, `test_report.py`.

## [2.0.0] — prior

- Stucki / Burkes / Sierra dithering, custom palette files, animation, batch convert, spritesheets, EGA/MSX/SMS/DB16/vaporwave palettes.
