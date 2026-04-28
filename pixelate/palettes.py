"""
Classic retro color palettes.

Each palette is a tuple of (R, G, B) tuples representing the canonical
colors for that hardware/era. These are used to quantize images down
to authentic-looking retro output.
"""

from __future__ import annotations

from typing import Dict, Tuple

RGB = Tuple[int, int, int]
Palette = Tuple[RGB, ...]


# ---- Classic console palettes ---------------------------------------------

GAMEBOY_DMG: Palette = (
    (15, 56, 15),     # darkest green
    (48, 98, 48),     # dark green
    (139, 172, 15),   # light green
    (155, 188, 15),   # lightest green
)

GAMEBOY_POCKET: Palette = (
    (8, 24, 32),
    (52, 104, 86),
    (136, 192, 112),
    (224, 248, 208),
)

# Nintendo Entertainment System (subset of common 54-color palette)
NES: Palette = (
    (0, 0, 0),         (124, 124, 124),  (188, 188, 188),  (252, 252, 252),
    (124, 0, 0),       (228, 0, 88),     (248, 56, 0),     (252, 160, 68),
    (172, 124, 0),     (0, 88, 0),       (0, 168, 0),      (88, 248, 152),
    (0, 64, 88),       (0, 120, 248),    (104, 136, 252),  (216, 168, 248),
)

# Commodore 64 (16 colors)
C64: Palette = (
    (0, 0, 0),         (255, 255, 255),  (136, 0, 0),      (170, 255, 238),
    (204, 68, 204),    (0, 204, 85),     (0, 0, 170),      (238, 238, 119),
    (221, 136, 85),    (102, 68, 0),     (255, 119, 119),  (51, 51, 51),
    (119, 119, 119),   (170, 255, 102),  (0, 136, 255),    (187, 187, 187),
)

# ZX Spectrum (15 unique colors — black is shared)
ZX_SPECTRUM: Palette = (
    (0, 0, 0),         (0, 0, 215),      (215, 0, 0),      (215, 0, 215),
    (0, 215, 0),       (0, 215, 215),    (215, 215, 0),    (215, 215, 215),
    (0, 0, 0),         (0, 0, 255),      (255, 0, 0),      (255, 0, 255),
    (0, 255, 0),       (0, 255, 255),    (255, 255, 0),    (255, 255, 255),
)

# CGA Mode 4 Palette 1 (high intensity)
CGA: Palette = (
    (0, 0, 0),
    (85, 255, 255),
    (255, 85, 255),
    (255, 255, 255),
)

# PICO-8 fantasy console (16 colors)
PICO8: Palette = (
    (0, 0, 0),         (29, 43, 83),     (126, 37, 83),    (0, 135, 81),
    (171, 82, 54),     (95, 87, 79),     (194, 195, 199),  (255, 241, 232),
    (255, 0, 77),      (255, 163, 0),    (255, 236, 39),   (0, 228, 54),
    (41, 173, 255),    (131, 118, 156),  (255, 119, 168),  (255, 204, 170),
)

# Apple II low-res
APPLE2: Palette = (
    (0, 0, 0),         (157, 9, 102),    (42, 42, 229),    (199, 52, 255),
    (0, 116, 51),      (123, 123, 123),  (36, 156, 255),   (170, 170, 255),
    (84, 71, 0),       (231, 117, 0),    (170, 170, 170),  (255, 161, 207),
    (15, 186, 0),      (210, 211, 25),   (66, 233, 167),   (255, 255, 255),
)

# A modern, hand-picked sunset palette
SUNSET: Palette = (
    (28, 16, 51),      (66, 30, 86),     (122, 41, 105),   (181, 67, 99),
    (224, 116, 84),    (244, 168, 96),   (251, 215, 134),  (255, 247, 208),
)

# Monochrome variants
MONO_GREEN: Palette = tuple((0, v, 0) for v in (8, 64, 128, 200, 255))  # type: ignore
MONO_AMBER: Palette = tuple((v, int(v * 0.6), 0) for v in (8, 64, 128, 200, 255))  # type: ignore
GRAYSCALE: Palette = tuple((v, v, v) for v in (0, 32, 64, 96, 128, 160, 192, 224, 255))  # type: ignore


# ---- Registry --------------------------------------------------------------

PALETTES: Dict[str, Palette] = {
    "gameboy": GAMEBOY_DMG,
    "gameboy-pocket": GAMEBOY_POCKET,
    "nes": NES,
    "c64": C64,
    "zx": ZX_SPECTRUM,
    "cga": CGA,
    "pico8": PICO8,
    "apple2": APPLE2,
    "sunset": SUNSET,
    "mono-green": MONO_GREEN,
    "mono-amber": MONO_AMBER,
    "grayscale": GRAYSCALE,
}


def get_palette(name: str) -> Palette:
    """Return a palette by name (case-insensitive). Raises KeyError if unknown."""
    key = name.lower().strip()
    if key not in PALETTES:
        available = ", ".join(sorted(PALETTES))
        raise KeyError(f"Unknown palette '{name}'. Available: {available}")
    return PALETTES[key]


def list_palettes() -> Dict[str, int]:
    """Return {name: color_count} for all registered palettes."""
    return {name: len(p) for name, p in PALETTES.items()}
