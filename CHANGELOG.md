# Changelog

All notable changes to this project are documented in this file.

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
