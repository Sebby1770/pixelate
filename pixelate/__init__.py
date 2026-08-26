"""PIXELATE — retro pixel art converter."""

__version__ = "2.3.0"
__author__ = "Seb"

from pixelate.animation import is_animated, pixelate_animation
from pixelate.colorspace import nearest_palette_indices, srgb_to_lab
from pixelate.core import (
    color_usage_report,
    compare_palettes,
    extract_palette,
    nearest_scale,
    pixelate_image,
    resolve_palette,
    save_image,
)
from pixelate.dithering import dither_image
from pixelate.effects import apply_phosphor
from pixelate.palette_io import load_palette_file, register_palette, save_gpl, save_hex
from pixelate.palettes import PALETTES, get_palette

__all__ = [
    "pixelate_image",
    "pixelate_animation",
    "is_animated",
    "resolve_palette",
    "extract_palette",
    "compare_palettes",
    "color_usage_report",
    "nearest_scale",
    "save_image",
    "srgb_to_lab",
    "nearest_palette_indices",
    "dither_image",
    "apply_phosphor",
    "save_gpl",
    "save_hex",
    "PALETTES",
    "get_palette",
    "load_palette_file",
    "register_palette",
    "__version__",
]
