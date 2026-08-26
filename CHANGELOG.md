# Changelog

All notable changes to this project are documented in this file.

## [2.4.0] — 2026-08-26

### Added

- **Lab k-means** — auto-palette k-means++ clusters in CIE L*a*b* (same space as matching), then converts centers back with `lab_to_srgb()`.
- **`lab_to_srgb()`** — vectorized inverse of `srgb_to_lab` (D65, same matrices); RGB clipped to 0–255 floats.
- **`--seed INT`** — RNG seed for auto-palette k-means (default 0). `extract_palette(..., seed=)` / `pixelate_image(..., seed=)`.
- **Batch `--jobs N`** — `ThreadPoolExecutor` when N>1 (default 1 stays sequential, no executor). Failures still raise after the run.
- **Web lab** — phosphor checkbox (RGB column stripes on the output canvas) and posterize slider (0=off, 2–8 bit-crush before dither). Version tag 2.4.0.

### Tests

- `lab_to_srgb` gray / mid-gray round-trip, `extract_palette` same-seed identity, seed 0 vs 1, CLI `--seed 1` with `--palette auto`, batch `--jobs 2`.

## [2.3.0] — 2026-08-26

### Added

- **k-means++** — auto-palette k-means uses k-means++ initialization (seed 0) instead of random unique picks.
- **Phosphor mask** — `--phosphor` / `apply_phosphor()` RGB column stripes (after CRT, before scanlines).
- **Bayer matrix size** — `--bayer-size 2|4|8` (default 4), threaded through `dither_image` (ignored unless dither is Bayer).
- **Posterize pre-pass** — `--posterize N` (2–16 levels per channel) before palette quantization.
- **Web lab** — drag-and-drop onto the page, serpentine checkbox (default on), palette compare split view.

### Changed

- CRT bloom runs **before** scanlines so scanlines stay sharp (phosphor sits between them).
- `apply_crt` is glow + vignette only (no curvature).

### Tests

- CRT-then-scanlines vs scanlines-then-CRT, phosphor size/variation, k-means++ determinism, posterize ⊆ palette, CLI `--phosphor` / `--posterize 4`, Bayer size 8 ⊆ palette.

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
