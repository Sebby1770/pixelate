"""
ASCII / ANSI art renderer.

Converts an image to a text grid where each character represents the
brightness of a downscaled pixel. Optional ANSI 24-bit color support
preserves the source colors so the output looks great in any modern
terminal.
"""

from __future__ import annotations

from pathlib import Path
from typing import Union

import numpy as np
from PIL import Image

from pixelate.image_safety import load_rgb_image

# Ramps go dark -> light. Pick the one that suits your terminal background.
RAMPS = {
    "dense": "@%#*+=-:. ",
    "blocks": "█▓▒░ ",
    "classic": "$@B%8&WM#*oahkbdpqwmZO0QLCJUYXzcvunxrjft/\\|()1{}[]?-_+~<>i!lI;:,\"^`'. ",
    "binary": "#.",
}


def image_to_ascii(
    src: Union[str, Path, Image.Image],
    width: int = 100,
    ramp: str = "dense",
    color: bool = False,
    invert: bool = False,
) -> str:
    """
    Convert an image to an ASCII art string.

    Parameters
    ----------
    width : int
        Character width of the output. Height is computed to preserve aspect
        ratio (terminal cells are ~2x taller than wide, so we compensate).
    ramp : str
        Name of a built-in ramp (``dense``, ``blocks``, ``classic``, ``binary``)
        or a custom string of characters from dark to light.
    color : bool
        If True, wrap each char in an ANSI 24-bit color escape using the
        corresponding source pixel's color.
    invert : bool
        Reverse the ramp (useful for light terminal backgrounds).
    """
    if width < 1:
        raise ValueError("ASCII width must be at least 1.")

    chars = RAMPS.get(ramp, ramp)
    if not chars:
        raise ValueError("ASCII ramp must contain at least one character.")

    img = load_rgb_image(src)

    # Compensate for terminal cell aspect (chars are ~2:1 tall:wide)
    w_orig, h_orig = img.size
    new_h = max(1, int(width * h_orig / w_orig * 0.5))
    img = img.resize((width, new_h), Image.LANCZOS)

    arr = np.array(img)
    gray = (0.299 * arr[..., 0] + 0.587 * arr[..., 1] + 0.114 * arr[..., 2])

    if invert:
        chars = chars[::-1]

    n = len(chars) - 1
    indices = (gray / 255.0 * n).astype(int)

    lines = []
    for y in range(arr.shape[0]):
        row_chars = []
        for x in range(arr.shape[1]):
            ch = chars[indices[y, x]]
            if color:
                r, g, b = arr[y, x]
                row_chars.append(f"\x1b[38;2;{r};{g};{b}m{ch}")
            else:
                row_chars.append(ch)
        if color:
            row_chars.append("\x1b[0m")
        lines.append("".join(row_chars))

    return "\n".join(lines)


def save_ascii(text: str, path: Union[str, Path]) -> Path:
    """Save ASCII art to a text file."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    # Strip ANSI codes when saving to a plain .txt
    if str(p).endswith(".txt"):
        import re
        text = re.sub(r"\x1b\[[0-9;]*m", "", text)
    p.write_text(text, encoding="utf-8")
    return p
