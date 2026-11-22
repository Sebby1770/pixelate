"""
Hardware modes — authentic attribute-clash emulation.

Real 8-bit machines could not put any palette color on any pixel. Video
memory stored a small set of colors per *attribute cell*, and every pixel
in that cell had to use one of them:

* **ZX Spectrum** — 8x8 cells, ink + paper, both from the same BRIGHT bank.
* **C64 hires** — 8x8 cells, any two of the 16 colors.
* **C64 multicolor** — double-wide pixels, 4x8 cells: one global background
  color plus three per cell.
* **MSX / TMS9918 Graphics II** — two colors per 8x1 line segment.
* **NES** — 16x16 attribute areas, each choosing one of four 3-color
  sub-palettes that share one universal background color.

:func:`apply_hardware` searches, per cell, for the color set that best fits
the source (exhaustively over every legal combination, in CIELAB or RGB),
optionally picks the shared colors / sub-palettes globally, and then
dithers each pixel *within its cell's colors* — so error diffusion and
pattern dithers still work, but the infamous color clash shows exactly
where the hardware would have forced it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from itertools import combinations
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

from pixelate.colorspace import srgb_to_lab
from pixelate.dithering import (
    KERNELS,
    _canonical,
    _tile,
    bayer_matrix,
    blue_noise,
    get_dither,
    halftone_matrix,
)
from pixelate.lut import DEFAULT_BITS, grid_lab_flat
from pixelate.palettes import C64, MSX, NES, RGB

ZX_NORMAL: Tuple[RGB, ...] = (
    (0, 0, 0), (0, 0, 215), (215, 0, 0), (215, 0, 215),
    (0, 215, 0), (0, 215, 215), (215, 215, 0), (215, 215, 215),
)
ZX_BRIGHT: Tuple[RGB, ...] = (
    (0, 0, 0), (0, 0, 255), (255, 0, 0), (255, 0, 255),
    (0, 255, 0), (0, 255, 255), (255, 255, 0), (255, 255, 255),
)


@dataclass(frozen=True)
class HardwareMode:
    """Description of one machine's color-attribute rules."""

    name: str
    title: str
    palette: Tuple[RGB, ...]
    cell: Tuple[int, int]  # (width, height) in logical pixels
    per_cell: int  # colors chosen per cell (excluding shared ones)
    shared: int = 0  # globally shared colors (background), 0 or 1
    max_sets: Optional[int] = None  # distinct per-cell sets allowed (NES: 4)
    groups: Tuple[Tuple[int, ...], ...] = ()  # legal color banks (ZX bright)
    pixel_width: int = 1  # horizontal pixel aspect (C64 multicolor = 2)
    native: Tuple[int, int] = (256, 192)
    notes: str = ""
    aliases: Tuple[str, ...] = field(default=())

    @property
    def colors_per_cell(self) -> int:
        return self.per_cell + self.shared

    @property
    def pixel_size(self) -> int:
        """Long side of the native display, in display pixels."""
        return max(self.native)


HARDWARE_MODES: Dict[str, HardwareMode] = {
    m.name: m
    for m in (
        HardwareMode(
            "zx", "ZX Spectrum", ZX_NORMAL + ZX_BRIGHT, (8, 8), 2,
            groups=(tuple(range(8)), tuple(range(8, 16))),
            native=(256, 192),
            notes="ink + paper per 8x8 cell, both from the same BRIGHT bank",
            aliases=("spectrum", "zx-spectrum"),
        ),
        HardwareMode(
            "c64", "Commodore 64 hires", tuple(C64), (8, 8), 2,
            native=(320, 200),
            notes="any 2 of 16 colors per 8x8 cell",
            aliases=("c64-hires",),
        ),
        HardwareMode(
            "c64-multi", "Commodore 64 multicolor", tuple(C64), (4, 8), 3,
            shared=1, pixel_width=2, native=(320, 200),
            notes="double-wide pixels; shared background + 3 colors per 4x8 cell",
            aliases=("c64-multicolor", "c64mc"),
        ),
        HardwareMode(
            "msx", "MSX / TMS9918 Graphics II", tuple(MSX), (8, 1), 2,
            native=(256, 192),
            notes="2 colors per 8x1 line segment",
            aliases=("tms9918",),
        ),
        HardwareMode(
            "nes", "NES background", tuple(NES), (16, 16), 3,
            shared=1, max_sets=4, native=(256, 240),
            notes="universal background + one of four 3-color sub-palettes per 16x16 area",
            aliases=("famicom",),
        ),
    )
}

_ALIASES = {alias: m.name for m in HARDWARE_MODES.values() for alias in m.aliases}


def get_hardware_mode(name: str) -> HardwareMode:
    """Look up a hardware mode by name or alias (case-insensitive)."""
    key = str(name).lower().strip().replace("_", "-")
    key = _ALIASES.get(key, key)
    if key not in HARDWARE_MODES:
        raise KeyError(
            f"Unknown hardware mode '{name}'. Available: {', '.join(HARDWARE_MODES)}"
        )
    return HARDWARE_MODES[key]


def list_hardware_modes() -> List[HardwareMode]:
    return list(HARDWARE_MODES.values())


# ---------------------------------------------------------------------------
# Cell color selection
# ---------------------------------------------------------------------------

def _metric_space(space: str) -> str:
    return "rgb" if str(space).lower().strip() == "rgb" else "lab"


def _to_metric(rgb: np.ndarray, space: str) -> np.ndarray:
    if space == "rgb":
        return np.asarray(rgb, dtype=np.float64)
    return srgb_to_lab(np.clip(np.asarray(rgb, dtype=np.float64), 0, 255))


def _cells(arr: np.ndarray, cw: int, ch: int) -> Tuple[np.ndarray, int, int]:
    """Reshape padded ``(H, W, C)`` into ``(N, cw*ch, C)`` cells."""
    h, w, c = arr.shape
    rows, cols = h // ch, w // cw
    cells = arr.reshape(rows, ch, cols, cw, c).transpose(0, 2, 1, 3, 4)
    return cells.reshape(rows * cols, ch * cw, c), rows, cols


def _combos(mode: HardwareMode, exclude: Sequence[int] = ()) -> List[Tuple[int, ...]]:
    banks = mode.groups or (tuple(range(len(mode.palette))),)
    seen = set()
    out: List[Tuple[int, ...]] = []
    for bank in banks:
        pool = [i for i in bank if i not in exclude]
        k = min(mode.per_cell, len(pool))
        for combo in combinations(pool, k):
            key = tuple(sorted({tuple(mode.palette[i]) for i in combo}))
            if key in seen:  # e.g. ZX black exists in both banks
                continue
            seen.add(key)
            out.append(combo)
    return out


def _combo_errors(dist: np.ndarray, combos: List[Tuple[int, ...]], base: Optional[np.ndarray]) -> np.ndarray:
    """``E[n, c]`` = summed distance of cell *n* using combo *c* (+ base)."""
    n = dist.shape[0]
    errors = np.empty((n, len(combos)), dtype=np.float64)
    for j, combo in enumerate(combos):
        best = dist[:, :, combo[0]] if base is None else np.minimum(base, dist[:, :, combo[0]])
        for idx in combo[1:]:
            best = np.minimum(best, dist[:, :, idx])
        errors[:, j] = best.sum(axis=1)
    return errors


def _facility_location(errors: np.ndarray, m: int) -> List[int]:
    """Choose *m* columns minimizing ``sum_n min_chosen errors[n]`` (greedy + swaps)."""
    m = min(m, errors.shape[1])
    chosen: List[int] = []
    current = np.full(errors.shape[0], np.inf)
    for _ in range(m):
        totals = np.minimum(current[:, None], errors).sum(axis=0)
        totals[chosen] = np.inf
        pick = int(np.argmin(totals))
        chosen.append(pick)
        current = np.minimum(current, errors[:, pick])
    improved = True
    while improved:
        improved = False
        best_total = errors[:, chosen].min(axis=1).sum()
        for slot in range(len(chosen)):
            others = [c for i, c in enumerate(chosen) if i != slot]
            rest = errors[:, others].min(axis=1) if others else np.full(errors.shape[0], np.inf)
            totals = np.minimum(rest[:, None], errors).sum(axis=0)
            cand = int(np.argmin(totals))
            if totals[cand] < best_total - 1e-9 and cand not in chosen:
                chosen[slot] = cand
                best_total = totals[cand]
                improved = True
    return chosen


def choose_cell_colors(
    image: np.ndarray,
    mode: HardwareMode,
    space: str = "lab",
) -> Tuple[np.ndarray, Tuple[int, ...]]:
    """
    Pick legal colors for every attribute cell.

    *image* must already be padded to whole cells. Returns ``(sets, shared)``
    where ``sets`` is ``(rows, cols, K)`` palette indices allowed in each
    cell (shared colors included) and ``shared`` the global color indices.
    """
    metric = _metric_space(space)
    pal = np.asarray(mode.palette, dtype=np.float64)
    pal_m = _to_metric(pal, metric)
    pix_m = _to_metric(image.reshape(-1, 3), metric).reshape(image.shape)
    cw, ch = mode.cell
    cells, rows, cols = _cells(pix_m, cw, ch)
    diff = cells[:, :, None, :] - pal_m[None, None, :, :]
    dist = np.einsum("npkc,npkc->npk", diff, diff)  # (N, px, P)

    bg_candidates: List[Optional[int]] = [None]
    if mode.shared:
        usage = np.bincount(dist.argmin(axis=2).ravel(), minlength=len(pal))
        order = np.argsort(-usage)
        bg_candidates = [int(i) for i in order[: min(len(pal), 6 if mode.max_sets else len(pal))]]

    best: Optional[Tuple[float, Optional[int], List[Tuple[int, ...]], np.ndarray]] = None
    for bg in bg_candidates:
        combos = _combos(mode, exclude=() if bg is None else (bg,))
        base = None if bg is None else dist[:, :, bg]
        errors = _combo_errors(dist, combos, base)
        if mode.max_sets:
            chosen = _facility_location(errors, mode.max_sets)
            pick_local = errors[:, chosen].argmin(axis=1)
            assign = np.asarray(chosen)[pick_local]
        else:
            assign = errors.argmin(axis=1)
        total = float(errors[np.arange(errors.shape[0]), assign].sum())
        if best is None or total < best[0]:
            best = (total, bg, combos, assign)

    assert best is not None
    _, bg, combos, assign = best
    shared: Tuple[int, ...] = () if bg is None else (int(bg),)
    k = mode.colors_per_cell
    sets = np.empty((rows * cols, k), dtype=np.int64)
    for n, c in enumerate(assign):
        combo = list(shared) + list(combos[int(c)])
        while len(combo) < k:  # tiny palettes / degenerate banks
            combo.append(combo[-1])
        sets[n] = combo
    return sets.reshape(rows, cols, k), shared


# ---------------------------------------------------------------------------
# Restricted dithering
# ---------------------------------------------------------------------------

def _expand_sets(sets: np.ndarray, cw: int, ch: int) -> np.ndarray:
    return np.repeat(np.repeat(sets, ch, axis=0), cw, axis=1)


def _restricted_nearest(img: np.ndarray, pix_sets: np.ndarray, pal_m: np.ndarray, metric: str) -> np.ndarray:
    pix = _to_metric(np.clip(img, 0, 255).reshape(-1, 3), metric).reshape(img.shape)
    cand = pal_m[pix_sets]  # (H, W, K, 3)
    d = ((pix[:, :, None, :] - cand) ** 2).sum(axis=-1)
    pick = d.argmin(axis=2)
    return np.take_along_axis(pix_sets, pick[..., None], axis=2)[..., 0]


def _restricted_pattern(img: np.ndarray, pix_sets: np.ndarray, pal: np.ndarray, pal_m: np.ndarray,
                        metric: str, threshold: np.ndarray, n: int = 16, mult: float = 0.75) -> np.ndarray:
    h, w = img.shape[:2]
    src = np.clip(img, 0, 255)
    picks = np.empty((n, h, w), dtype=np.int64)
    error = np.zeros_like(src)
    for c in range(n):
        idx = _restricted_nearest(src + error * mult, pix_sets, pal_m, metric)
        picks[c] = idx
        error += src - pal[idx]
    luma = pal @ np.array([0.299, 0.587, 0.114])
    order = np.argsort(luma[picks], axis=0, kind="stable")
    sorted_picks = np.take_along_axis(picks, order, axis=0)
    which = np.clip((_tile(threshold, h, w) * n).astype(np.int64), 0, n - 1)
    return np.take_along_axis(sorted_picks, which[None], axis=0)[0]


def _restricted_diffuse(img: np.ndarray, pix_sets: np.ndarray, pal: np.ndarray, pal_m: np.ndarray,
                        metric: str, kernel, serpentine: bool) -> np.ndarray:
    h, w = img.shape[:2]
    pad = 2
    pw = w + 2 * pad
    stride = pw * 3
    padded = np.zeros((h + pad, pw, 3), dtype=np.float64)
    padded[:h, pad:pad + w] = img
    buf = padded.ravel().tolist()
    sets = pix_sets.reshape(h * w, -1).tolist()
    pm = [tuple(float(v) for v in row) for row in pal_m]
    pr = [float(c[0]) for c in pal]
    pg = [float(c[1]) for c in pal]
    pb = [float(c[2]) for c in pal]
    lab_grid = grid_lab_flat(DEFAULT_BITS)
    shift = 8 - DEFAULT_BITS
    bits = DEFAULT_BITS
    use_lab = metric == "lab"
    fwd = [(dy * stride + dx * 3, wt) for dy, dx, wt in kernel]
    rev = [(dy * stride - dx * 3, wt) for dy, dx, wt in kernel]
    out = [0] * (h * w)
    for y in range(h):
        reverse = serpentine and (y & 1) == 1
        taps = rev if reverse else fwd
        row = y * stride + pad * 3
        xs = range(w - 1, -1, -1) if reverse else range(w)
        for x in xs:
            i = row + x * 3
            r, g, b = buf[i], buf[i + 1], buf[i + 2]
            if use_lab:
                ri = 0 if r <= 0.0 else 255 if r >= 255.0 else int(r)
                gi = 0 if g <= 0.0 else 255 if g >= 255.0 else int(g)
                bi = 0 if b <= 0.0 else 255 if b >= 255.0 else int(b)
                j3 = (((ri >> shift) << (bits + bits)) | ((gi >> shift) << bits) | (bi >> shift)) * 3
                p0, p1, p2 = lab_grid[j3], lab_grid[j3 + 1], lab_grid[j3 + 2]
            else:
                p0, p1, p2 = r, g, b
            best = -1
            best_d = 1e300
            for k in sets[y * w + x]:
                q = pm[k]
                d = (p0 - q[0]) ** 2 + (p1 - q[1]) ** 2 + (p2 - q[2]) ** 2
                if d < best_d:
                    best_d = d
                    best = k
            out[y * w + x] = best
            er, eg, eb = r - pr[best], g - pg[best], b - pb[best]
            for off, wt in taps:
                j = i + off
                buf[j] += er * wt
                buf[j + 1] += eg * wt
                buf[j + 2] += eb * wt
    return np.asarray(out, dtype=np.int64).reshape(h, w)


@dataclass
class HardwareResult:
    """Output of :func:`apply_hardware`."""

    image: np.ndarray  # (H, W, 3) uint8, cropped to the input size
    indices: np.ndarray  # (H, W) palette indices
    cell_sets: np.ndarray  # (rows, cols, K) palette indices per cell
    shared: Tuple[int, ...]
    mode: HardwareMode


def apply_hardware(
    image: np.ndarray,
    mode: HardwareMode | str,
    dither: str = "none",
    space: str = "lab",
    serpentine: bool = True,
    bayer_size: int = 4,
) -> HardwareResult:
    """
    Quantize *image* (``(H, W, 3)`` RGB, logical pixels) under *mode*'s
    attribute rules. For modes with ``pixel_width > 1`` pass the image at
    its narrow (logical) resolution — :func:`pixelate.core.pixelate_image`
    does this automatically.
    """
    hw = get_hardware_mode(mode) if isinstance(mode, str) else mode
    key = _canonical(dither)
    get_dither(key)  # validate name
    img = np.asarray(image, dtype=np.float64)
    h, w = img.shape[:2]
    cw, ch = hw.cell
    ph = -(-h // ch) * ch
    pw = -(-w // cw) * cw
    padded = np.pad(img, ((0, ph - h), (0, pw - w), (0, 0)), mode="edge")

    metric = _metric_space(space)
    pal = np.asarray(hw.palette, dtype=np.float64)
    pal_m = _to_metric(pal, metric)
    sets, shared = choose_cell_colors(padded, hw, space=metric)
    pix_sets = _expand_sets(sets, cw, ch)

    if key in KERNELS or key == "sierra_lite":
        kernel = KERNELS["sierra-lite" if key == "sierra_lite" else key]
        idx = _restricted_diffuse(padded, pix_sets, pal, pal_m, metric, kernel, serpentine)
    elif key in ("pattern", "bluenoise", "halftone"):
        threshold = {"pattern": bayer_matrix(8), "bluenoise": blue_noise(), "halftone": halftone_matrix()}[key]
        idx = _restricted_pattern(padded, pix_sets, pal, pal_m, metric, threshold)
    elif key == "bayer":
        t = _tile(bayer_matrix(int(bayer_size)), ph, pw)
        idx = _restricted_nearest(padded + (t[..., None] - 0.5) * 32.0, pix_sets, pal_m, metric)
    else:
        idx = _restricted_nearest(padded, pix_sets, pal_m, metric)

    idx = idx[:h, :w]
    out = np.clip(pal[idx], 0, 255).astype(np.uint8)
    return HardwareResult(out, idx.astype(np.int64), sets, shared, hw)


def clash_report(result: HardwareResult) -> Dict[str, object]:
    """Small summary used by the CLI: cells, distinct cell sets, shared colors."""
    sets = result.cell_sets.reshape(-1, result.cell_sets.shape[-1])
    distinct = {tuple(sorted(set(int(v) for v in row))) for row in sets}
    used = sorted({int(v) for v in np.unique(result.indices)})
    return {
        "mode": result.mode.title,
        "cells": int(sets.shape[0]),
        "distinct_cell_sets": len(distinct),
        "shared": [tuple(result.mode.palette[i]) for i in result.shared],
        "colors_used": len(used),
    }
