"""Attribute-clash rules for every hardware mode."""

import numpy as np
import pytest

from pixelate.hardware import (
    HARDWARE_MODES,
    apply_hardware,
    choose_cell_colors,
    clash_report,
    get_hardware_mode,
    snap_to_depth,
)


def _scene(h=40, w=56, seed=0):
    rng = np.random.default_rng(seed)
    x = np.linspace(0, 255, w)
    y = np.linspace(0, 255, h)
    img = np.zeros((h, w, 3))
    img[..., 0] = x[None, :]
    img[..., 1] = y[:, None]
    img[..., 2] = 255 - x[None, :] * 0.5
    img += rng.normal(0, 18, img.shape)
    return np.clip(img, 0, 255)


def _cells(idx, cw, ch):
    h, w = idx.shape
    for y in range(0, h, ch):
        for x in range(0, w, cw):
            yield set(np.unique(idx[y:y + ch, x:x + cw]).tolist())


@pytest.mark.parametrize("name", list(HARDWARE_MODES))
@pytest.mark.parametrize("dither", ["none", "floyd", "pattern", "bayer"])
def test_cells_respect_color_budget(name, dither):
    mode = get_hardware_mode(name)
    res = apply_hardware(_scene(), mode, dither=dither)
    assert res.image.shape == (40, 56, 3)
    pal = {tuple(c) for c in res.colors}
    assert {tuple(c) for c in res.image.reshape(-1, 3)} <= pal
    for cell in _cells(res.indices, *mode.cell):
        assert len(cell) <= mode.colors_per_cell


@pytest.mark.parametrize("dither", ["none", "floyd", "bluenoise"])
def test_zx_ink_and_paper_share_a_bright_bank(dither):
    mode = get_hardware_mode("zx")
    res = apply_hardware(_scene(seed=3), mode, dither=dither)
    for cell in _cells(res.indices, 8, 8):
        banks = {("bright" if i >= 8 else "normal") for i in cell if mode.palette[i] != (0, 0, 0)}
        assert len(banks) <= 1


def test_c64_multicolor_background_is_in_every_cell_set():
    mode = get_hardware_mode("c64-multi")
    res = apply_hardware(_scene(), mode, dither="floyd")
    assert len(res.shared) == 1
    bg = res.shared[0]
    assert all(bg in row for row in res.cell_sets.reshape(-1, res.cell_sets.shape[-1]).tolist())


def test_nes_uses_at_most_four_sub_palettes_sharing_one_background():
    mode = get_hardware_mode("nes")
    res = apply_hardware(_scene(64, 64, seed=5), mode, dither="none")
    sets = res.cell_sets.reshape(-1, res.cell_sets.shape[-1])
    bg = res.shared[0]
    assert all(row[0] == bg for row in sets.tolist())
    subs = {tuple(sorted(set(row[1:]))) for row in sets.tolist()}
    assert len(subs) <= 4


def test_msx_uses_8x1_cells():
    res = apply_hardware(_scene(), "msx", dither="pattern")
    for cell in _cells(res.indices, 8, 1):
        assert len(cell) <= 2


def test_odd_sizes_and_solid_colors():
    solid = np.full((13, 21, 3), (250.0, 10.0, 10.0))
    res = apply_hardware(solid, "zx")
    assert res.image.shape == (13, 21, 3)
    assert {tuple(c) for c in res.image.reshape(-1, 3)} == {(255, 0, 0)}


def test_choose_cell_colors_shapes():
    mode = get_hardware_mode("c64")
    sets, shared = choose_cell_colors(_scene(16, 24), mode)
    assert sets.shape == (2, 3, 2)
    assert shared == ()


def test_aliases_and_errors():
    assert get_hardware_mode("Spectrum").name == "zx"
    assert get_hardware_mode("c64_multicolor").name == "c64-multi"
    assert get_hardware_mode("famicom").name == "nes"
    assert get_hardware_mode("amiga").name == "amiga-ham"
    with pytest.raises(KeyError):
        get_hardware_mode("atari-st")
    with pytest.raises(KeyError):
        apply_hardware(_scene(), "zx", dither="wobble")


def test_clash_report_keys():
    report = clash_report(apply_hardware(_scene(), "c64-multi"))
    assert set(report) == {"mode", "cells", "distinct_cell_sets", "shared", "colors_used"}
    assert report["cells"] == 5 * 14  # 40/8 rows x 56/4 cols
    assert len(report["shared"]) == 1


def test_rgb_metric_also_respects_rules():
    res = apply_hardware(_scene(), "zx", dither="floyd", space="rgb")
    for cell in _cells(res.indices, 8, 8):
        assert len(cell) <= 2


# ----------------------------------------------------- generated-palette modes
@pytest.mark.parametrize("name", ["gbc", "megadrive", "snes"])
@pytest.mark.parametrize("dither", ["none", "floyd", "pattern"])
def test_tile_palette_modes(name, dither):
    mode = get_hardware_mode(name)
    res = apply_hardware(_scene(48, 64, seed=2), mode, dither=dither)
    for c in res.colors:  # every colour is representable at the console's depth
        assert tuple(snap_to_depth(np.array(c, dtype=float), mode.bits).astype(int)) == tuple(c)
    sets = res.cell_sets.reshape(-1, res.cell_sets.shape[-1])
    assert len({tuple(sorted(set(r))) for r in sets.tolist()}) <= mode.sub_palettes
    for cell in _cells(res.indices, 8, 8):
        assert len(cell) <= mode.colors_per_cell
    if mode.shared:
        assert all(res.shared[0] in r for r in sets.tolist())
    assert clash_report(res)["sub_palettes"] <= mode.sub_palettes


@pytest.mark.parametrize("dither", ["none", "floyd", "bayer"])
def test_amiga_ham_hold_and_modify_rule(dither):
    res = apply_hardware(_scene(24, 40, seed=4), "ham6", dither=dither)
    img = res.image.astype(int)
    assert all(v % 17 == 0 for v in img.reshape(-1))  # 4 bits per channel
    base = {tuple(c) for c in (np.array(res.colors)[res.cell_sets.reshape(-1)]).tolist()}
    assert len(base) <= 16
    for y in range(img.shape[0]):
        for x in range(1, img.shape[1]):
            cur, prev = tuple(img[y, x]), img[y, x - 1]
            assert cur in base or int((img[y, x] != prev).sum()) <= 1
    report = clash_report(res)
    assert 0 <= report["modified_pixels"] <= 100 and report["base_colors"] <= 16
