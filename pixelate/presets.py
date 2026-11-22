"""
Named recipes — one flag for a whole look.

A preset is a bundle of :func:`pixelate.core.pixelate_image` keyword
arguments. Anything you pass explicitly wins over the preset (on the CLI,
any flag you type; in Python, any argument that differs from its default).
User presets can be loaded from a JSON file of ``{name: {kwarg: value}}``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Mapping, Union


@dataclass(frozen=True)
class Preset:
    name: str
    description: str
    options: Mapping[str, Any]


def _p(name: str, description: str, **options: Any) -> Preset:
    return Preset(name, description, options)


PRESETS: Dict[str, Preset] = {
    p.name: p
    for p in (
        _p("gameboy-camera", "Game Boy Camera: 4 greens, ordered dither, punchy contrast",
           palette="gameboy", pixel_size=128, dither="bayer", bayer_size=4,
           contrast=1.35, saturation=1.0, upscale=4),
        _p("zx-loading-screen", "ZX Spectrum loading screen with real attribute clash",
           hardware="zx", pixel_size=256, dither="pattern", saturation=1.4, upscale=3),
        _p("c64-demo", "C64 multicolor: wide pixels, shared background, Bayer texture",
           hardware="c64-multi", pixel_size=320, dither="bayer", bayer_size=4,
           saturation=1.3, upscale=3, color_bleed=0.4),
        _p("nes-cart", "NES background: four sub-palettes on 16x16 attribute areas",
           hardware="nes", pixel_size=256, dither="none", saturation=1.3, upscale=3),
        _p("msx-title", "MSX title card: two colors per 8x1 line",
           hardware="msx", pixel_size=256, dither="pattern", upscale=3),
        _p("pico8-postcard", "PICO-8 at 128px with blue-noise dithering",
           palette="pico8", pixel_size=128, dither="bluenoise", saturation=1.25, upscale=4),
        _p("mac-classic", "1-bit Macintosh: black, white and Atkinson dithering",
           palette="1bit", pixel_size=256, dither="atkinson", contrast=1.2, saturation=0.0, upscale=2),
        _p("newsprint", "Halftone print: clustered dots in grayscale",
           palette="grayscale", pixel_size=200, dither="halftone", saturation=0.0, upscale=3),
        _p("vaporwave-vhs", "Neon VHS tape: chroma bleed, RGB split, scanlines",
           palette="vaporwave", pixel_size=160, dither="bluenoise", upscale=4,
           crt=True, scanlines=True, chromatic=2, color_bleed=0.6),
        _p("arcade-crt", "Arcade cabinet: curved glass, bloom, phosphor mask",
           palette="sms", pixel_size=160, dither="floyd", upscale=4,
           crt=True, phosphor=True, scanlines=True, curvature=0.06),
        _p("sprite", "Game sprite: auto 16 colors, clean pixels, outline, smooth scale",
           palette="auto", colors=16, pixel_size=64, dither="none", cleanup=1,
           outline=1, upscale=6, upscaler="scale3x"),
        _p("virtual-boy", "Virtual Boy: red-on-black pattern dither with scanlines",
           palette="virtualboy", pixel_size=192, dither="pattern", saturation=0.0,
           contrast=1.2, upscale=3, scanlines=True),
    )
}


def get_preset(name: str) -> Preset:
    key = str(name).lower().strip().replace("_", "-")
    if key not in PRESETS:
        raise KeyError(f"Unknown preset '{name}'. Available: {', '.join(PRESETS)}")
    return PRESETS[key]


def register_preset(name: str, description: str = "", **options: Any) -> Preset:
    """Add (or replace) a preset at runtime."""
    preset = Preset(str(name).lower().strip(), description or "user preset", dict(options))
    PRESETS[preset.name] = preset
    return preset


def load_presets_file(path: Union[str, Path]) -> Dict[str, Preset]:
    """Register every preset in a JSON file ``{name: {"description": ..., kwarg: value}}``."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Preset file must be a JSON object of {name: {options}}")
    loaded: Dict[str, Preset] = {}
    for name, opts in data.items():
        if not isinstance(opts, dict):
            raise ValueError(f"Preset '{name}' must map to an object of options")
        opts = dict(opts)
        desc = str(opts.pop("description", ""))
        loaded[name] = register_preset(name, desc, **opts)
    return loaded


def merge_preset(name: str, given: Mapping[str, Any], defaults: Mapping[str, Any]) -> Dict[str, Any]:
    """
    Overlay preset *name* onto *given* kwargs: a preset value is used only
    where *given* still holds the parameter's default.
    """
    preset = get_preset(name)
    merged = dict(given)
    for key, value in preset.options.items():
        if key not in defaults:
            raise KeyError(f"Preset '{preset.name}' sets unknown option '{key}'")
        if merged.get(key, defaults[key]) == defaults[key]:
            merged[key] = value
    return merged
