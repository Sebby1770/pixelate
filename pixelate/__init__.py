"""PIXELATE — retro pixel art converter."""

__version__ = "2.0.0"
__author__ = "Seb"

from pixelate.core import pixelate_image, resolve_palette
from pixelate.palettes import PALETTES, get_palette
from pixelate.palette_io import load_palette_file, register_palette
from pixelate.animation import is_animated, pixelate_animation

__all__ = [
    "pixelate_image",
    "pixelate_animation",
    "is_animated",
    "resolve_palette",
    "PALETTES",
    "get_palette",
    "load_palette_file",
    "register_palette",
    "__version__",
]
