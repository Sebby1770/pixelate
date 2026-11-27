"""PIXELATE — retro pixel art converter."""

__version__ = "3.0.0"
__author__ = "Seb"

from pixelate.animation import is_animated, pixelate_animation
from pixelate.colorspace import ciede2000, lab_to_srgb, nearest_palette_indices, srgb_to_lab
from pixelate.core import (
    color_usage_report,
    compare_palettes,
    extract_palette,
    nearest_scale,
    pixelate_image,
    resolve_palette,
    save_image,
)
from pixelate.dithering import DITHER_ALGORITHMS, dither_image, dither_indices
from pixelate.effects import (
    apply_chromatic_aberration,
    apply_color_bleed,
    apply_curvature,
    apply_grid,
    apply_outline,
    apply_phosphor,
    cleanup_orphans,
)
from pixelate.export import export_indexed, swatch_sheet, to_c_header, to_json, to_svg
from pixelate.hardware import HARDWARE_MODES, apply_hardware, get_hardware_mode
from pixelate.lut import palette_lut
from pixelate.palette_io import load_palette_file, register_palette, save_gpl, save_hex
from pixelate.palettes import PALETTES, get_palette
from pixelate.presets import PRESETS, get_preset, load_presets_file, register_preset
from pixelate.upscale import upscale_image

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
    "lab_to_srgb",
    "ciede2000",
    "nearest_palette_indices",
    "dither_image",
    "dither_indices",
    "DITHER_ALGORITHMS",
    "palette_lut",
    "apply_phosphor",
    "apply_grid",
    "apply_outline",
    "apply_chromatic_aberration",
    "apply_color_bleed",
    "apply_curvature",
    "cleanup_orphans",
    "apply_hardware",
    "get_hardware_mode",
    "HARDWARE_MODES",
    "PRESETS",
    "get_preset",
    "register_preset",
    "load_presets_file",
    "upscale_image",
    "to_svg",
    "to_json",
    "to_c_header",
    "export_indexed",
    "swatch_sheet",
    "save_gpl",
    "save_hex",
    "PALETTES",
    "get_palette",
    "load_palette_file",
    "register_palette",
    "__version__",
]
