"""PIXELATE — retro pixel art converter."""

__version__ = "3.0.0"
__author__ = "Seb"

from pixelate.animation import is_animated, pixelate_animation
from pixelate.core import (
    color_usage_report,
    compare_palettes,
    extract_palette,
    nearest_scale,
    pixelate_image,
    resolve_palette,
)
from pixelate.palette_io import load_palette_file, register_palette
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
    "PALETTES",
    "get_palette",
    "load_palette_file",
    "register_palette",
    "__version__",
]
