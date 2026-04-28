"""PIXELATE — retro pixel art converter."""

__version__ = "1.0.0"
__author__ = "Seb"

from pixelate.core import pixelate_image
from pixelate.palettes import PALETTES, get_palette

__all__ = ["pixelate_image", "PALETTES", "get_palette", "__version__"]
