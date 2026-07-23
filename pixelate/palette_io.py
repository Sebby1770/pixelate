"""
Load and register custom color palettes from files.

Supported formats:
  - ``.hex`` — one RRGGBB or #RRGGBB color per line
  - ``.gpl`` — GIMP Palette files (``Name:`` header + RGB lines)
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Tuple, Union

from pixelate.palettes import PALETTES, RGB, Palette

PathLike = Union[str, Path]


def _parse_hex_color(token: str) -> RGB:
    """Parse a hex color string like ``FF00AA`` or ``#ff00aa`` into RGB."""
    token = token.strip()
    if token.startswith("#"):
        token = token[1:]
    if len(token) != 6 or not re.fullmatch(r"[0-9A-Fa-f]{6}", token):
        raise ValueError(f"Invalid hex color: {token!r}")
    r = int(token[0:2], 16)
    g = int(token[2:4], 16)
    b = int(token[4:6], 16)
    return (r, g, b)


def load_hex(path: PathLike) -> Palette:
    """
    Load a palette from a ``.hex`` file.

    Each non-empty, non-comment line should be ``RRGGBB`` or ``#RRGGBB``.
    Lines starting with ``;`` or ``//`` are ignored. Bare ``#`` comments
    (``# comment``) are ignored; ``#RRGGBB`` color lines are accepted.
    """
    p = Path(path)
    colors: list[RGB] = []
    for lineno, raw in enumerate(p.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw.strip()
        if not line:
            continue
        if line.startswith(";") or line.startswith("//"):
            continue
        # "# comment" vs "#RRGGBB"
        if line.startswith("#") and not re.fullmatch(r"#[0-9A-Fa-f]{6}", line.split()[0]):
            continue
        token = line.split()[0]
        try:
            colors.append(_parse_hex_color(token))
        except ValueError as exc:
            raise ValueError(f"{p}:{lineno}: {exc}") from exc

    if not colors:
        raise ValueError(f"No colors found in hex palette file: {p}")
    return tuple(colors)


def load_gpl(path: PathLike) -> Tuple[str | None, Palette]:
    """
    Load a GIMP ``.gpl`` palette file.

    Returns ``(name, colors)`` where *name* is the ``Name:`` field if present.
    """
    p = Path(path)
    lines = p.read_text(encoding="utf-8").splitlines()
    if not lines:
        raise ValueError(f"Empty GPL file: {p}")

    name: str | None = None
    colors: list[RGB] = []

    for lineno, raw in enumerate(lines, start=1):
        line = raw.strip()
        if not line:
            continue
        if line.startswith("GIMP Palette"):
            continue
        if line.startswith("Name:"):
            name = line.split(":", 1)[1].strip() or None
            continue
        if line.startswith("Columns:") or line.startswith("#"):
            continue
        # RGB line: R G B [optional name]
        parts = line.split()
        if len(parts) < 3:
            continue
        try:
            r, g, b = int(parts[0]), int(parts[1]), int(parts[2])
        except ValueError:
            continue
        if not all(0 <= c <= 255 for c in (r, g, b)):
            raise ValueError(f"{p}:{lineno}: RGB out of range: {(r, g, b)}")
        colors.append((r, g, b))

    if not colors:
        raise ValueError(f"No colors found in GPL palette file: {p}")
    return name, tuple(colors)


def load_palette_file(path: PathLike) -> Palette:
    """
    Load a palette from ``.hex`` or ``.gpl`` based on file extension.

    Raises ``ValueError`` for unknown extensions or empty palettes.
    """
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(f"Palette file not found: {p}")

    suffix = p.suffix.lower()
    if suffix == ".hex":
        return load_hex(p)
    if suffix == ".gpl":
        _, colors = load_gpl(p)
        return colors
    # Allow extensionless / .txt hex dumps
    if suffix in (".txt", ""):
        return load_hex(p)
    raise ValueError(
        f"Unsupported palette format '{suffix}'. Use .hex or .gpl ({p})"
    )


def register_palette(name: str, colors: Sequence[RGB]) -> Palette:
    """
    Register a custom palette under *name* so it can be used with
    ``get_palette`` / ``--palette``.

    Returns the normalized palette tuple.
    """
    key = name.lower().strip()
    if not key:
        raise ValueError("Palette name must be non-empty")
    if not colors:
        raise ValueError("Palette must contain at least one color")

    normalized: list[RGB] = []
    for c in colors:
        if len(c) != 3:
            raise ValueError(f"Invalid color {c!r}; expected (R, G, B)")
        r, g, b = int(c[0]), int(c[1]), int(c[2])
        if not all(0 <= v <= 255 for v in (r, g, b)):
            raise ValueError(f"Color out of range: {(r, g, b)}")
        normalized.append((r, g, b))

    palette = tuple(normalized)
    PALETTES[key] = palette
    return palette


def register_palette_file(name: str, path: PathLike) -> Palette:
    """Load a palette file and register it under *name*."""
    colors = load_palette_file(path)
    return register_palette(name, colors)


def save_hex(path: PathLike, colors: Sequence[RGB]) -> Path:
    """Write a palette as a ``.hex`` file (one ``RRGGBB`` per line)."""
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    lines = ["{:02X}{:02X}{:02X}".format(*c) for c in colors]
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out


def save_gpl(path: PathLike, colors: Sequence[RGB], name: str = "PIXELATE") -> Path:
    """Write a palette as a GIMP ``.gpl`` file."""
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    lines = ["GIMP Palette", f"Name: {name}", f"Columns: {min(len(colors), 16)}", "#"]
    for r, g, b in colors:
        lines.append(f"{r:3d} {g:3d} {b:3d}\t{r:02X}{g:02X}{b:02X}")
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out


def colors_from_iterable(colors: Iterable[RGB]) -> Palette:
    """Normalize an iterable of RGB triples into a Palette without registering."""
    normalized: list[RGB] = []
    for c in colors:
        if len(c) != 3:
            raise ValueError(f"Invalid color {c!r}; expected (R, G, B)")
        r, g, b = int(c[0]), int(c[1]), int(c[2])
        if not all(0 <= v <= 255 for v in (r, g, b)):
            raise ValueError(f"Color out of range: {(r, g, b)}")
        normalized.append((r, g, b))
    if not normalized:
        raise ValueError("Palette must contain at least one color")
    return tuple(normalized)
