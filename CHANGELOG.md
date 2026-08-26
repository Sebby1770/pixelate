# Changelog

All notable changes to this project are documented in this file.

## [2.2.0] — 2026-08-26

### Added

- **CIELAB matching** — palette nearest-color uses CIE76 Lab by default (`--colorspace lab|rgb`). `srgb_to_lab()` / `nearest_palette_indices()` / `dither_image()`.
- **Serpentine error diffusion** — even rows L→R, odd rows R→L (`--serpentine` / `--no-serpentine`, default on).
- **Jarvis-Judice-Ninke** — `--dither jjn` (12-element kernel, 48ths).
- **Alpha + EXIF** — `ImageOps.exif_transpose` after open; RGBA sources keep a NEAREST-resized alpha channel; spritesheets preserve alpha if any tile has it.
- **Palette-locked I/O** — JPEG outputs are forced to PNG unless `allow_jpeg=True`. PNG can be written as indexed mode `P` with the exact working palette. GIFs use a shared `P` palette and `disposal=2`.
- **Auto-palette report** — working colors are stashed on `result.info["pixelate_palette"]` so `--report` matches the pipeline (extract after preprocess+resize).
- **Palettes** — Sweetie 16 (`sweetie16`), Endesga 32 (`endesga32`), Macintosh 16-color System (`macintosh`). Duplicate blacks removed from ZX Spectrum and MSX.
- **`pixelate extract`** — extract N colors to a GIMP `.gpl` (optional `.hex`).
- **`pixelate palettes --save-gpl NAME -o file.gpl`** — dump a built-in palette.
- **`save_gpl` / `save_hex`** in `palette_io.py`.
- **Web playground** — static `web/` lab (FileReader, palettes, floyd/atkinson/bayer/jjn/none, CRT/scanlines, PNG download). GitHub Pages workflow publishes it.

### Changed

- Default matching space is Lab (CIE76). RGB Euclidean remains available.
- Batch convert always writes `.png` for stills (never keeps a `.jpg` suffix). Failures raise after the loop so CI notices.
- Sierra docstring now correctly describes Sierra-2 (not Filter Lite).

### Tests

- `test_colorspace.py`, `test_cli.py`, `test_effects.py`, plus extensions for serpentine, JJN, RGBA, indexed PNG, GIF palette lock, unique ZX/MSX, auto-palette info.

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
