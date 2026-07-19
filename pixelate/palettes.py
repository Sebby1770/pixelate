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

# IBM Enhanced Graphics Adapter (16 colors)
EGA: Palette = (
    (0, 0, 0),         (0, 0, 170),      (0, 170, 0),      (0, 170, 170),
    (170, 0, 0),       (170, 0, 170),    (170, 85, 0),     (170, 170, 170),
    (85, 85, 85),      (85, 85, 255),    (85, 255, 85),    (85, 255, 255),
    (255, 85, 85),     (255, 85, 255),   (255, 255, 85),   (255, 255, 255),
)

# MSX Screen 2 common 16-color palette
MSX: Palette = (
    (0, 0, 0),         (0, 0, 0),        (62, 184, 73),    (116, 208, 125),
    (89, 85, 224),     (128, 118, 241),  (185, 94, 81),     (101, 219, 239),
    (219, 101, 89),    (255, 137, 125),  (204, 195, 94),    (222, 208, 135),
    (58, 162, 65),     (183, 102, 181),  (204, 204, 204),  (255, 255, 255),
)

# Sega Master System / Mark III (common 16-color subset of 64-color palette)
SMS: Palette = (
    (0, 0, 0),         (85, 85, 85),     (170, 170, 170),  (255, 255, 255),
    (85, 0, 0),        (170, 0, 0),      (255, 85, 85),    (255, 170, 170),
    (0, 85, 0),        (0, 170, 0),      (85, 255, 85),    (170, 255, 170),
    (0, 0, 85),        (0, 0, 170),      (85, 85, 255),    (170, 170, 255),
)

# DawnBringer 16 — widely used pixel-art palette by DawnBringer
DB16: Palette = (
    (20, 12, 28),      (68, 36, 52),     (48, 52, 109),    (78, 74, 78),
    (133, 76, 48),     (52, 101, 36),    (208, 70, 72),    (117, 113, 97),
    (89, 125, 206),    (210, 125, 44),   (133, 149, 161),  (109, 170, 44),
    (210, 170, 153),   (109, 194, 202),  (218, 212, 94),   (222, 238, 214),
)

# Aesthetic vaporwave palette
VAPORWAVE: Palette = (
    (15, 12, 33),      (45, 24, 72),     (90, 40, 120),    (255, 113, 206),
    (1, 205, 254),     (5, 255, 161),    (185, 103, 255),  (255, 251, 150),
    (255, 110, 199),   (148, 198, 255),  (36, 23, 52),     (255, 255, 255),
)

# Game Boy Color — key 32-color subset (BGP / hardware sample)
GAMEBOY_COLOR: Palette = (
    (0, 0, 0),         (8, 24, 16),      (48, 104, 80),    (136, 192, 112),
    (224, 248, 208),   (255, 255, 255),  (255, 0, 0),      (255, 128, 0),
    (255, 255, 0),     (0, 255, 0),      (0, 255, 255),    (0, 0, 255),
    (128, 0, 255),     (255, 0, 255),    (255, 128, 192),  (192, 128, 64),
    (128, 64, 0),      (64, 32, 0),      (32, 16, 0),      (0, 64, 128),
    (0, 128, 192),     (64, 192, 255),   (128, 255, 255),  (255, 192, 128),
    (255, 64, 64),     (192, 0, 64),     (64, 0, 128),     (0, 128, 64),
    (128, 192, 0),     (255, 255, 128),  (192, 192, 192),  (96, 96, 96),
)

# Commodore VIC-20 (16 colors)
VIC20: Palette = (
    (0, 0, 0),         (255, 255, 255),  (103, 55, 43),    (112, 164, 178),
    (111, 61, 134),    (88, 141, 67),    (53, 40, 121),    (184, 199, 111),
    (111, 79, 37),     (67, 57, 0),      (154, 103, 89),   (68, 68, 68),
    (108, 108, 108),   (154, 210, 132),  (108, 94, 181),   (149, 149, 149),
)

# Atari 2600 — representative subset of the TIA palette
ATARI2600: Palette = (
    (0, 0, 0),         (64, 64, 64),     (108, 108, 108),  (144, 144, 144),
    (176, 176, 176),   (192, 192, 192),  (216, 216, 216),  (255, 255, 255),
    (72, 0, 0),        (168, 24, 0),     (228, 80, 16),    (248, 144, 56),
    (0, 48, 0),        (0, 112, 0),      (48, 176, 48),    (112, 216, 112),
    (0, 0, 72),        (0, 40, 136),     (32, 96, 192),    (80, 160, 240),
    (72, 0, 72),       (144, 24, 136),   (200, 72, 192),   (240, 136, 240),
    (72, 40, 0),       (144, 88, 0),     (200, 144, 24),   (240, 200, 80),
    (0, 48, 48),       (0, 112, 112),    (40, 176, 176),   (96, 216, 216),
)

# Tokyo Night inspired dark theme
TOKYO_NIGHT: Palette = (
    (26, 27, 38),      (36, 40, 59),     (41, 46, 66),     (56, 62, 90),
    (122, 162, 247),   (125, 207, 255),  (158, 206, 106),  (187, 154, 247),
    (247, 118, 142),   (255, 158, 100),  (224, 175, 104),  (115, 218, 202),
    (192, 202, 245),   (169, 177, 214),  (65, 72, 104),    (15, 15, 25),
)

# Cyberpunk neon night palette
CYBERPUNK: Palette = (
    (10, 5, 20),       (25, 10, 40),     (255, 0, 110),    (0, 245, 212),
    (5, 217, 232),     (255, 214, 10),   (157, 0, 255),    (255, 94, 0),
    (0, 255, 135),     (255, 255, 255),  (80, 80, 100),    (180, 180, 200),
    (255, 65, 180),    (40, 200, 255),   (120, 20, 80),    (30, 30, 50),
)

# ---- Registry --------------------------------------------------------------

PALETTES: Dict[str, Palette] = {
    "gameboy": GAMEBOY_DMG,
    "gameboy-pocket": GAMEBOY_POCKET,
    "gameboy-color": GAMEBOY_COLOR,
    "gbc": GAMEBOY_COLOR,  # alias
    "nes": NES,
    "c64": C64,
    "vic20": VIC20,
    "vic-20": VIC20,  # alias
    "atari2600": ATARI2600,
    "atari-2600": ATARI2600,  # alias
    "zx": ZX_SPECTRUM,
    "cga": CGA,
    "pico8": PICO8,
    "apple2": APPLE2,
    "sunset": SUNSET,
    "mono-green": MONO_GREEN,
    "mono-amber": MONO_AMBER,
    "grayscale": GRAYSCALE,
    "ega": EGA,
    "msx": MSX,
    "sms": SMS,
    "master-system": SMS,  # alias
    "db16": DB16,
    "vaporwave": VAPORWAVE,
    "tokyo-night": TOKYO_NIGHT,
    "tokyo": TOKYO_NIGHT,  # alias
    "cyberpunk": CYBERPUNK,
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
