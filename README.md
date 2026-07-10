# PIXELATE

```
██████╗ ██╗██╗  ██╗███████╗██╗      █████╗ ████████╗███████╗
██╔══██╗██║╚██╗██╔╝██╔════╝██║     ██╔══██╗╚══██╔══╝██╔════╝
██████╔╝██║ ╚███╔╝ █████╗  ██║     ███████║   ██║   █████╗
██╔═══╝ ██║ ██╔██╗ ██╔══╝  ██║     ██╔══██║   ██║   ██╔══╝
██║     ██║██╔╝ ██╗███████╗███████╗██║  ██║   ██║   ███████╗
╚═╝     ╚═╝╚═╝  ╚═╝╚══════╝╚══════╝╚═╝  ╚═╝   ╚═╝   ╚══════╝
        retro pixel art from any image  ·  v2.0.0
```

[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![CI](https://github.com/Sebby1770/pixelate/actions/workflows/ci.yml/badge.svg)](https://github.com/Sebby1770/pixelate/actions/workflows/ci.yml)
[![Built with Pillow](https://img.shields.io/badge/built%20with-Pillow-8A2BE2.svg)](https://python-pillow.org/)

> Turn any image (or animated GIF) into authentic retro pixel art using classic gaming palettes, seven dithering algorithms, CRT glow + scanlines, batch conversion, and spritesheet export. Or print it as ANSI art straight to your terminal.

---

## Gallery

| Source | Game Boy | PICO-8 (Bayer) | C64 + CRT |
|:---:|:---:|:---:|:---:|
| ![source](assets/source.png) | ![gameboy](assets/example_gameboy.png) | ![pico8](assets/example_pico8.png) | ![c64](assets/example_c64_crt.png) |
| original | `--palette gameboy` | `--palette pico8 --dither bayer` | `--palette c64 --crt --scanlines` |

---

## Why?

Modern image filters smooth everything out. PIXELATE goes the other way — it crushes color depth down to the exact palettes used by the consoles and home computers of the 80s and 90s, dithers cleverly to preserve detail, and gives you a finished pixel-art image that looks like it shipped on a cartridge.

## Features (v2.0)

- **18+ retro palettes** — Game Boy DMG/Pocket, NES, C64, ZX Spectrum, CGA, PICO-8, Apple II, EGA, MSX, Sega Master System, DawnBringer 16, vaporwave, sunset, mono phosphor, grayscale.
- **7 dithering algorithms** — Floyd-Steinberg, Atkinson, Ordered Bayer, Stucki, Burkes, Sierra (two-row), and flat quantization.
- **Custom palette files** — load GIMP `.gpl` or `.hex` palettes via `--palette-file` or the Python API.
- **Animated GIF / WebP** — multi-frame inputs are auto-detected; frame durations are preserved.
- **Batch convert** — process whole directories with a rich progress bar.
- **Spritesheet export** — tile converted images into a grid.
- **CRT effects** — soft bloom + corner vignette + horizontal scanlines.
- **ASCII / ANSI mode** — render any image as colored terminal art.
- **Beautifully retro CLI** — green-on-black banner, palette previews, swatches, progress bars.
- **Clean Python API** — backward-compatible `pixelate_image()` with optional new kwargs.

## Install

```bash
git clone https://github.com/Sebby1770/pixelate.git
cd pixelate
pip install -e .
```

Dev / tests:

```bash
pip install -e ".[dev]"
pytest
```

Or just install the dependencies and run as a module:

```bash
pip install -r requirements.txt
python -m pixelate --help
```

## Usage

### Convert an image

```bash
pixelate convert photo.jpg --palette gameboy --pixel-size 96 --dither floyd
```

Crank up the retro:

```bash
pixelate convert photo.jpg \
  --palette nes \
  --pixel-size 128 \
  --dither stucki \
  --upscale 4 \
  --crt --scanlines \
  -o photo_retro.png
```

### Custom palette file

```bash
pixelate convert photo.jpg --palette-file my_colors.gpl -o custom.png
pixelate convert photo.jpg --palette-file neon.hex --dither burkes
```

`.hex` files are one `RRGGBB` or `#RRGGBB` color per line. `.gpl` is the GIMP palette format.

Preview / session-register a file:

```bash
pixelate palettes --load my_colors.gpl
pixelate palettes --load my_colors.gpl --register-as neon
```

### Animated GIF

Animated GIF/WebP inputs are detected automatically. Output defaults to `.gif` and keeps approximate frame durations:

```bash
pixelate convert walk_cycle.gif --palette pico8 --pixel-size 64 -o walk_pixel.gif
```

### Batch convert

```bash
pixelate batch ./photos -o ./pixelated --palette vaporwave --dither sierra
pixelate batch ./sprites -o ./out --recursive --palette db16
```

### Spritesheet

Convert and tile images (files and/or a directory) into one sheet:

```bash
pixelate sheet ./frames --cols 8 -o sheet.png --palette gameboy
pixelate sheet a.png b.png c.png --cols 3 --no-convert -o stitch.png
```

### Render to ASCII

```bash
pixelate ascii photo.jpg --width 120 --ramp blocks
pixelate ascii photo.jpg --no-color -o art.txt
```

### Browse palettes

```bash
pixelate palettes          # list all built-in palettes
pixelate preview pico8     # print a color swatch
pixelate preview ega
pixelate preview vaporwave
```

## CLI reference

```
pixelate convert IMAGE [OPTIONS]
  -p, --palette         built-in palette name
      --palette-file    .hex or .gpl path (overrides --palette)
  -s, --pixel-size      Resolution of longest side (8–1024)
  -d, --dither          none | floyd | atkinson | bayer |
                        stucki | burkes | sierra
  -u, --upscale         1–16 (output pixels per logical pixel)
      --saturation      0.0–3.0 (pre-quantize boost)
      --crt             Apply CRT bloom + vignette
      --scanlines       Overlay horizontal scanlines
  -o, --output          Output path (default: <name>_pixel.png/.gif)

pixelate batch INPUT_DIR -o OUTPUT_DIR [same convert options]
  -r, --recursive       Scan subdirectories

pixelate sheet PATH [PATH...] [OPTIONS]
  --cols N              Grid columns (default 4)
  --padding N           Gap between tiles
  --convert/--no-convert  Pixelate first (default: convert)
  -o, --output          Output spritesheet path
  [same palette/dither/etc options as convert]

pixelate ascii IMAGE [OPTIONS]
  -w, --width           Output width in characters
  -r, --ramp            dense | blocks | classic | binary | <custom>
      --color           24-bit ANSI color (default on)
      --invert          Invert ramp (light terminals)
  -o, --output          Save to .txt

pixelate palettes [--load FILE] [--register-as NAME]
pixelate preview PALETTE
```

### Built-in palettes

| Name | Colors | Notes |
|------|--------|--------|
| `gameboy` | 4 | Original DMG green-yellow |
| `gameboy-pocket` | 4 | Pocket / Light |
| `nes` | 16 | NES subset |
| `c64` | 16 | Commodore 64 |
| `zx` | 16 | ZX Spectrum |
| `cga` | 4 | CGA Mode 4 high intensity |
| `pico8` | 16 | PICO-8 |
| `apple2` | 16 | Apple II low-res |
| `ega` | 16 | IBM EGA |
| `msx` | 16 | MSX Screen 2 |
| `sms` / `master-system` | 16 | Sega Master System |
| `db16` | 16 | DawnBringer 16 |
| `vaporwave` | 12 | Aesthetic neon |
| `sunset` | 8 | Modern gradient |
| `mono-green` / `mono-amber` | 5 | Phosphor CRTs |
| `grayscale` | 9 | Neutral steps |

## Python API

```python
from pixelate import pixelate_image, pixelate_animation, register_palette, load_palette_file

img = pixelate_image(
    "photo.jpg",
    palette="pico8",
    pixel_size=128,
    dither="stucki",
    upscale=4,
    crt=True,
    scanlines=True,
)
img.save("output.png")

# Custom palette file
img = pixelate_image("photo.jpg", palette_file="my.gpl", dither="burkes")

# Or register for reuse
register_palette("neon", load_palette_file("neon.hex"))
img = pixelate_image("photo.jpg", palette="neon")

# Animation
from pixelate import pixelate_animation
pixelate_animation("walk.gif", palette="gameboy", output="walk_pixel.gif")
```

```python
from pixelate.ascii_art import image_to_ascii

print(image_to_ascii("photo.jpg", width=80, ramp="blocks", color=True))
```

```python
from pixelate.core import make_spritesheet, collect_images, pixelate_image
from PIL import Image

paths = collect_images(["./sprites"])
tiles = [pixelate_image(p, palette="db16", pixel_size=32, upscale=2) for p in paths]
sheet = make_spritesheet(tiles, cols=8)
sheet.save("sheet.png")
```

## How it works

1. **Resize** — the source image is downsampled with Lanczos to a low resolution (you control this — `pixel_size`). This is the actual "pixelation."
2. **Quantize** — every pixel is matched against the chosen palette using Euclidean distance in RGB.
3. **Dither** — quantization error is either spread to neighboring pixels (Floyd-Steinberg, Atkinson, Stucki, Burkes, Sierra) or hidden in a deterministic pattern (Bayer).
4. **Upscale** — the small image is enlarged with nearest-neighbor so the pixels stay crisp and chunky.
5. **Effects (optional)** — scanlines and a CRT-style bloom-plus-vignette pass.
6. **Animation** — multi-frame sources run the pipeline per frame, then reassemble with original durations.

## Tests & CI

```bash
pip install -e ".[dev]"
pytest
```

GitHub Actions runs pytest on Python 3.10, 3.11, and 3.12 (see `.github/workflows/ci.yml`).

## Project layout

```
pixelate/
├── pixelate/
│   ├── __init__.py
│   ├── __main__.py
│   ├── cli.py          # Click CLI (convert, batch, sheet, ascii, palettes)
│   ├── core.py         # Conversion pipeline, spritesheet helpers
│   ├── animation.py    # Multi-frame GIF/WebP
│   ├── palette_io.py   # .hex / .gpl loaders + register_palette
│   ├── palettes.py     # Built-in retro palettes
│   ├── dithering.py    # FS, Atkinson, Bayer, Stucki, Burkes, Sierra
│   ├── effects.py      # CRT, scanlines, vignette
│   ├── ascii_art.py    # ASCII / ANSI rendering
│   └── ui.py           # Rich-styled banner + tables
├── tests/
├── .github/workflows/ci.yml
├── pyproject.toml
├── requirements.txt
├── LICENSE
└── README.md
```

## Roadmap

- [x] Animated GIF input/output
- [x] Custom palette files (.gpl / .hex)
- [x] Sprite sheet export
- [x] More dithering kernels (Stucki, Burkes, Sierra)
- [x] Batch convert
- [x] More built-in palettes (EGA, MSX, SMS, DB16, vaporwave)
- [ ] Web playground
- [ ] Optional LAB / perceptual color distance
- [ ] Palette extraction from source images

## License

MIT — see [LICENSE](LICENSE).

## Author

Made by [Seb (Sebby1770)](https://github.com/Sebby1770).
