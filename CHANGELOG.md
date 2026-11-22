# Changelog

All notable changes to this project are documented in this file.

## [3.0.0] — 2026-11-22

### Added

- **Hardware modes** (`pixelate/hardware.py`, `--hardware`) — attribute-clash emulation for ZX Spectrum (ink + paper per 8×8 cell from one BRIGHT bank), C64 hires (2 of 16 per 8×8), C64 multicolor (double-wide pixels, shared background + 3 per 4×8 cell), MSX / TMS9918 (2 colors per 8×1) and NES (universal background + four 3-color sub-palettes on 16×16 areas, chosen by a facility-location search). Every legal combination is scored per cell in Lab/RGB, then any dither runs inside each cell's colors. Defaults to the machine's native resolution. `clash_report()` summary on `result.info["pixelate_hardware"]`; `pixelate hardware` lists the rules; `compare --palettes hw:zx,hw:nes,...`.
- **Pattern dithering** — `pattern` (Thomas Knoll's candidate mixing over Bayer 8×8), `bluenoise` (deterministic void-and-cluster mask) and `halftone` (clustered-dot screen). Fully vectorized. Aliases `knoll`, `blue-noise`, `fs`, `ordered` in the API. `dither_indices()` returns palette indices.
- **Presets** (`pixelate/presets.py`, `--preset`, `--presets-file`, `pixelate presets`) — 12 built-in looks; JSON user presets; typed CLI flags / non-default API arguments always win.
- **Exports** (`pixelate/export.py`) — `-o art.svg` (run-merged rects grouped by color, `crispEdges`, transparency), `.json` (`pixelate-indexed` v1), `.h` / `.c` (palette + index arrays), `pixelate swatches` palette sheets. Results carry the logical index map on `result.info["pixelate_indices"]`.
- **Effects** — `--outline` / `--outline-color` (palette-locked, alpha-aware), `--grid`, `--chromatic`, `--color-bleed` (NTSC YIQ), `--curvature` (barrel CRT), `--cleanup` (orphan pixels). Outline, grid, chromatic and bleed were first written for the unmerged 3.0 branch (PR #3) and are folded in here.
- **Upscalers** (`pixelate/upscale.py`, `--upscaler`) — Scale2x / Scale3x / Scale4x (EPX); never introduce new colors.
- **Palettes** — Game Gear, Virtual Boy, Amstrad CPC, Teletext, DB32, CGA palette 0, 1-bit, SLSO8, 2-bit Demichrome, Kirokaze GB, Ice Cream GB, Hollow, AYY4 (+ aliases). 38 unique palettes.
- **Commands** — `pixelate hardware`, `presets`, `dithers`, `swatches`.
- **PIXELATE Studio** — the web lab rebuilt around a worker-hosted port of the Python engine (see `web/`).
- **Tooling** — `tools/build_web_data.py` generates `web/data.json` / `web/data.js` from the package; ruff + mypy configs; CI matrix 3.9–3.14, lint job, web job (fresh data + `node --test`).

### Changed

- **Error diffusion is 30–80× faster** — `pixelate/lut.py` caches a 64³ nearest-palette table per (palette, space); diffusion runs on a padded scalar buffer. Floyd–Steinberg 512 px 3.9 s → 0.12 s; CIEDE2000 256 px 3.1 s → 33 ms. Outputs can differ from 2.5 on pixels within ~2 RGB units of a palette boundary; `--dither none` is still exact.
- The pipeline quantizes to an index map first, so cleanup, outline and exports stay palette-locked.
- `pixelate_animation()` forwards every `pixelate_image()` option and resolves presets once for all frames.
- PIL resampling constants use `Image.Resampling.*`.

## [2.5.0] — 2026-08-26

### Added

- **Box downscale** — `_resize_keep_aspect(..., filter="box")` uses Pillow `Image.BOX` (area average). CLI `--downscale box|lanczos|nearest` (default **box**). Threaded through convert / animation / batch / sheet. Web lab downscale select (box averages source blocks; lanczos = smoothing on; nearest = smoothing off).
- **CIEDE2000** — `ciede2000(lab1, lab2)` vectorized over Nx3 vs Px3 (or pairwise NxP). `nearest_palette_indices(..., space="ciede2000")`. `--distance ciede2000` (alias `--colorspace`). Default matching stays **lab** (CIE76).
- **Sierra-3 / Sierra Lite** — `--dither sierra3` (5/32, 3/32; 2,4,5,4,2 /32; 2,3,2 /32) and `--dither sierra-lite` (alias `sierra_lite`). Existing `sierra` remains Sierra-2.
- **Seeded subsample** — `_unique_sample_pixels(..., seed=42)`; `extract_palette(..., seed=)` and CLI `--seed` now seed both the pixel subsample RNG and k-means.
- **Process-pool batch** — `--jobs N` (N>1) uses `ProcessPoolExecutor` via module-level `pixelate.cli._batch_convert_one`; falls back to `ThreadPoolExecutor` on spawn failure. `jobs=1` stays in-process.
- **Web 2.5.0** — downscale select, sierra3 / sierra-lite.

### Tests

- Box downscale 32×32 → pixel_size 8 (long side 8), sierra3 / sierra-lite ⊆ palette, CIEDE2000 nearest index in range, seed 1 vs 2 on a gradient, CLI `--downscale nearest --distance ciede2000 --dither none`.

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
