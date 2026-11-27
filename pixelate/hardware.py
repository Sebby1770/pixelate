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
* **Tile-palette consoles** (Game Boy Color, Mega Drive, SNES) — every 8x8
  tile picks one of a few sub-palettes; the sub-palettes themselves are
  generated per image (tile clustering + Lab k-means) and snapped to the
  console's colour depth (RGB555 / RGB333).
* **Amiga HAM6** — Hold-And-Modify: each pixel either loads one of 16 base
  colours or copies the pixel to its left and changes one RGB channel, so
  up to 4096 colours on screen with the famous horizontal colour fringing.

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
    kind: str = "cells"  # cells | tiled | ham
    bits: int = 8  # colour depth per channel for generated palettes
    sub_palettes: int = 0  # tiled: number of sub-palettes

    @property
    def colors_per_cell(self) -> int:
        return self.per_cell + self.shared

    @property
    def generated(self) -> bool:
        """True when the palette is generated per image (tiled / HAM modes)."""
        return self.kind != "cells"

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
        HardwareMode(
            "gbc", "Game Boy Color", (), (8, 8), 4, kind="tiled", bits=5,
            sub_palettes=8, native=(160, 144),
            notes="8 generated 4-colour sub-palettes (RGB555), one per 8x8 tile",
            aliases=("game-boy-color", "cgb"),
        ),
        HardwareMode(
            "megadrive", "Sega Mega Drive / Genesis", (), (8, 8), 15, shared=1,
            kind="tiled", bits=3, sub_palettes=4, native=(320, 224),
            notes="4 generated 16-colour sub-palettes from 512 colours (RGB333), shared backdrop",
            aliases=("genesis", "md"),
        ),
        HardwareMode(
            "snes", "Super Nintendo", (), (8, 8), 15, shared=1, kind="tiled",
            bits=5, sub_palettes=8, native=(256, 224),
            notes="8 generated 16-colour sub-palettes (RGB555), shared backdrop",
            aliases=("super-famicom", "sfc"),
        ),
        HardwareMode(
            "amiga-ham", "Amiga HAM6", (), (1, 1), 1, kind="ham", bits=4,
            native=(320, 256),
            notes="16 base colours + hold-and-modify one RGB channel (4096 colours)",
            aliases=("ham", "ham6", "amiga"),
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
    # Squared distances (N, px, P) via |a|² - 2ab + |b|² — no (N, px, P, 3) temp.
    cell_sq = np.einsum("npc,npc->np", cells, cells)
    pal_sq = np.einsum("kc,kc->k", pal_m, pal_m)
    dist = cell_sq[:, :, None] - 2.0 * (cells @ pal_m.T) + pal_sq[None, None, :]
    np.maximum(dist, 0.0, out=dist)

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
    palette: Optional[Tuple[RGB, ...]] = None  # generated palettes (tiled / HAM)
    extra: Optional[Dict[str, object]] = None  # mode-specific report fields

    @property
    def colors(self) -> Tuple[RGB, ...]:
        return tuple(self.palette) if self.palette is not None else tuple(self.mode.palette)


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
    metric = _metric_space(space)
    if hw.kind == "ham":
        return _apply_ham(img, hw, key, metric, bayer_size)
    h, w = img.shape[:2]
    cw, ch = hw.cell
    ph = -(-h // ch) * ch
    pw = -(-w // cw) * cw
    padded = np.pad(img, ((0, ph - h), (0, pw - w), (0, 0)), mode="edge")

    generated: Optional[Tuple[RGB, ...]] = None
    if hw.kind == "tiled":
        generated, sets, shared = choose_tile_palettes(padded, hw, space=metric)
        pal = np.asarray(generated, dtype=np.float64)
    else:
        pal = np.asarray(hw.palette, dtype=np.float64)
        sets, shared = choose_cell_colors(padded, hw, space=metric)
    pal_m = _to_metric(pal, metric)
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
    extra: Optional[Dict[str, object]] = None
    if generated is not None:
        groups = {tuple(sorted(set(int(v) for v in row))) for row in sets.reshape(-1, sets.shape[-1])}
        extra = {"sub_palettes": len(groups), "bits": hw.bits}
    return HardwareResult(out, idx.astype(np.int64), sets, shared, hw, generated, extra)


def clash_report(result: HardwareResult) -> Dict[str, object]:
    """Small summary used by the CLI: cells, distinct cell sets, shared colors."""
    sets = result.cell_sets.reshape(-1, result.cell_sets.shape[-1])
    distinct = {tuple(sorted(set(int(v) for v in row))) for row in sets}
    used = sorted({int(v) for v in np.unique(result.indices)})
    report: Dict[str, object] = {
        "mode": result.mode.title,
        "cells": int(sets.shape[0]),
        "distinct_cell_sets": len(distinct),
        "shared": [tuple(result.colors[i]) for i in result.shared],
        "colors_used": len(used),
    }
    report.update(result.extra or {})
    return report


# ---------------------------------------------------------------------------
# Generated palettes: tile-palette consoles and Amiga HAM6
# ---------------------------------------------------------------------------

def snap_to_depth(rgb: np.ndarray, bits: int) -> np.ndarray:
    """Round 0-255 RGB to the nearest colour representable with *bits* per channel."""
    levels = (1 << int(bits)) - 1
    q = np.round(np.clip(np.asarray(rgb, dtype=np.float64), 0, 255) * levels / 255.0)
    return np.round(q * 255.0 / levels)


def _kmeans_rows(features: np.ndarray, k: int, seed: int = 0, iters: int = 15) -> np.ndarray:
    """Deterministic k-means++ labels for a small (N, D) feature matrix."""
    n = features.shape[0]
    k = max(1, min(k, n))
    rng = np.random.default_rng(seed)
    centers = [features[int(rng.integers(0, n))]]
    d2 = ((features - centers[0]) ** 2).sum(axis=1)
    while len(centers) < k:
        total = float(d2.sum())
        pick = int(rng.integers(0, n)) if total <= 0 else int(rng.choice(n, p=d2 / total))
        centers.append(features[pick])
        d2 = np.minimum(d2, ((features - features[pick]) ** 2).sum(axis=1))
    c = np.asarray(centers, dtype=np.float64)
    labels = np.zeros(n, dtype=np.int64)
    for _ in range(iters):
        dist = ((features[:, None, :] - c[None, :, :]) ** 2).sum(axis=2)
        new = dist.argmin(axis=1)
        if np.array_equal(new, labels) and _ > 0:
            break
        labels = new
        for j in range(k):
            if np.any(labels == j):
                c[j] = features[labels == j].mean(axis=0)
    return labels


def _group_palette(pixels: np.ndarray, n: int, bits: int, seed: int = 0) -> List[RGB]:
    from pixelate.core import _kmeans_palette

    if pixels.shape[0] > 6000:
        rng = np.random.default_rng(seed)
        pixels = pixels[rng.choice(pixels.shape[0], 6000, replace=False)]
    uniq = np.unique(snap_to_depth(pixels, bits), axis=0)
    if uniq.shape[0] <= n:
        cols = uniq
    else:
        cols = snap_to_depth(np.asarray(_kmeans_palette(pixels, n, seed=seed), dtype=np.float64), bits)
    out: List[RGB] = []
    for c in cols:
        t = (int(c[0]), int(c[1]), int(c[2]))
        if t not in out:
            out.append(t)
    return out


def choose_tile_palettes(
    image: np.ndarray,
    mode: HardwareMode,
    space: str = "lab",
    rounds: int = 2,
) -> Tuple[Tuple[RGB, ...], np.ndarray, Tuple[int, ...]]:
    """
    Generate a tile-palette console's sub-palettes for *image* (padded to
    whole tiles) and assign one to every tile.

    Tiles are clustered on mean / spread of their Lab colour, each cluster
    gets a Lab k-means palette snapped to the console's colour depth, then
    tiles are re-assigned to whichever sub-palette reproduces them best and
    the palettes are refit (*rounds* times). Returns ``(palette, sets,
    shared)`` where ``sets`` is ``(rows, cols, K)`` indices into ``palette``.
    """
    metric = _metric_space(space)
    cw, ch = mode.cell
    cells_rgb, rows, cols = _cells(np.asarray(image, dtype=np.float64), cw, ch)
    n_tiles = cells_rgb.shape[0]
    lab = srgb_to_lab(np.clip(cells_rgb.reshape(-1, 3), 0, 255)).reshape(cells_rgb.shape)
    features = np.concatenate([lab.mean(axis=1), lab.std(axis=1)], axis=1)
    groups = min(mode.sub_palettes, n_tiles)
    labels = _kmeans_rows(features, groups)

    shared_rgb: List[RGB] = []
    if mode.shared:
        snapped = snap_to_depth(cells_rgb.reshape(-1, 3), mode.bits).astype(np.int64)
        keys = (snapped[:, 0] << 16) | (snapped[:, 1] << 8) | snapped[:, 2]
        vals, counts = np.unique(keys, return_counts=True)
        top = int(vals[int(np.argmax(counts))])
        shared_rgb = [((top >> 16) & 255, (top >> 8) & 255, top & 255)]

    per = mode.per_cell
    pix_m = _to_metric(cells_rgb.reshape(-1, 3), metric).reshape(cells_rgb.shape)
    palettes: List[List[RGB]] = [shared_rgb[:] for _ in range(groups)]
    for r in range(rounds + 1):
        for g in range(groups):
            members = cells_rgb[labels == g]
            if members.shape[0]:
                palettes[g] = shared_rgb + [
                    c for c in _group_palette(members.reshape(-1, 3), per, mode.bits, seed=g)
                    if c not in shared_rgb
                ][:per]
            if not palettes[g]:
                palettes[g] = shared_rgb[:] or [(0, 0, 0)]
        if r == rounds:
            break
        errors = np.empty((n_tiles, groups))
        for g, pal_g in enumerate(palettes):
            pm = _to_metric(np.asarray(pal_g, dtype=np.float64), metric)
            sq = np.einsum("npc,npc->np", pix_m, pix_m)[:, :, None] - 2.0 * (pix_m @ pm.T) + np.einsum("kc,kc->k", pm, pm)
            errors[:, g] = np.maximum(sq, 0).min(axis=2).sum(axis=1)
        labels = errors.argmin(axis=1)

    palette: List[RGB] = []
    index_of: Dict[RGB, int] = {}
    group_idx: List[List[int]] = []
    for pal_g in palettes:
        ids = []
        for c in pal_g:
            if c not in index_of:
                index_of[c] = len(palette)
                palette.append(c)
            ids.append(index_of[c])
        group_idx.append(ids)
    k = mode.colors_per_cell
    sets = np.empty((n_tiles, k), dtype=np.int64)
    for t in range(n_tiles):
        ids = group_idx[int(labels[t])]
        sets[t] = (ids + [ids[-1]] * k)[:k]
    shared = tuple(index_of[c] for c in shared_rgb)
    return tuple(palette), sets.reshape(rows, cols, k), shared


def _apply_ham(img: np.ndarray, hw: HardwareMode, key: str, metric: str, bayer_size: int) -> HardwareResult:
    """
    Amiga HAM6. Base palette: 16 Lab k-means colours snapped to 4 bits per
    channel (index 0, the darkest, is the border colour each line starts
    from). Scanning left to right, every pixel picks the best of: the 16
    base colours, or the previous pixel with R, G or B replaced by any of
    its 16 levels — vectorized across all rows at once. Diffusion dithers
    carry half the error to the right (HAM is inherently left-to-right);
    ordered / pattern dithers offset the target by their threshold map.
    """
    h, w = img.shape[:2]
    bits = hw.bits
    lv = (1 << bits) - 1
    step = 255.0 / lv
    base = _group_palette(img.reshape(-1, 3), 16, bits)
    base.sort(key=lambda c: 0.299 * c[0] + 0.587 * c[1] + 0.114 * c[2])
    base_lv = np.round(np.asarray(base, dtype=np.float64) / step).astype(np.int64)
    nb = base_lv.shape[0]

    side = lv + 1
    grid = np.stack(np.meshgrid(*[np.arange(side)] * 3, indexing="ij"), axis=-1).reshape(-1, 3)
    table = _to_metric(grid * step, metric)  # metric coords for every 12-bit colour

    target = np.clip(img, 0, 255)
    if key == "bayer" or key in ("pattern", "bluenoise", "halftone"):
        m = {"bayer": bayer_matrix(int(bayer_size)), "pattern": bayer_matrix(8),
             "bluenoise": blue_noise(), "halftone": halftone_matrix()}[key]
        target = np.clip(target + (_tile(m, h, w)[..., None] - 0.5) * 32.0, 0, 255)
    diffuse = key in KERNELS or key == "sierra_lite"

    prev = np.repeat(base_lv[:1], h, axis=0)
    out_lv = np.empty((h, w, 3), dtype=np.int64)
    modified = 0
    levels = np.arange(side)
    rows = np.arange(h)
    carry = np.zeros((h, 3))
    for x in range(w):
        t = np.clip(target[:, x] + carry, 0, 255)
        cand = np.empty((h, nb + 3 * side, 3), dtype=np.int64)
        cand[:, :nb] = base_lv[None]
        for c in range(3):
            block = np.repeat(prev[:, None, :], side, axis=1)
            block[:, :, c] = levels[None, :]
            cand[:, nb + c * side: nb + (c + 1) * side] = block
        keys = (cand[..., 0] * side + cand[..., 1]) * side + cand[..., 2]
        tm = _to_metric(t, metric)
        d = ((table[keys] - tm[:, None, :]) ** 2).sum(axis=2)
        pick = d.argmin(axis=1)
        chosen = cand[rows, pick]
        modified += int((pick >= nb).sum())
        out_lv[:, x] = chosen
        prev = chosen
        if diffuse:
            carry = (t - chosen * step) * 0.5

    rgb = np.round(out_lv * step).astype(np.int64)
    flat = rgb.reshape(-1, 3)
    uniq, inverse = np.unique(flat, axis=0, return_inverse=True)
    palette = tuple((int(c[0]), int(c[1]), int(c[2])) for c in uniq)
    idx = inverse.reshape(h, w).astype(np.int64)
    lookup = {c: i for i, c in enumerate(palette)}
    def _rgb(lv_row: np.ndarray) -> RGB:
        r, g, b = (int(v) for v in np.round(lv_row * step))
        return (r, g, b)

    base_ids = np.array([[[lookup.get(_rgb(b), 0) for b in base_lv]]])
    extra: Dict[str, object] = {"base_colors": nb, "modified_pixels": round(100.0 * modified / max(1, h * w), 1)}
    return HardwareResult(rgb.astype(np.uint8), idx, base_ids, (), hw, palette, extra)
