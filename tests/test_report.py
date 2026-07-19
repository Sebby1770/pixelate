"""Tests for color usage report."""

import numpy as np
from PIL import Image

from pixelate.core import color_usage_report, pixelate_image
from pixelate.palettes import get_palette


def _make_test_image(size=(32, 32)):
    arr = np.zeros((size[1], size[0], 3), dtype=np.uint8)
    arr[: size[1] // 2, : size[0] // 2] = (200, 50, 50)
    arr[: size[1] // 2, size[0] // 2 :] = (50, 200, 50)
    arr[size[1] // 2 :, : size[0] // 2] = (50, 50, 200)
    arr[size[1] // 2 :, size[0] // 2 :] = (220, 220, 50)
    return Image.fromarray(arr, mode="RGB")


def test_color_usage_report_solid_image():
    img = Image.new("RGB", (10, 10), (255, 0, 0))
    report = color_usage_report(img)
    assert len(report) == 1
    color, count, pct = report[0]
    assert color == (255, 0, 0)
    assert count == 100
    assert abs(pct - 100.0) < 1e-6


def test_color_usage_report_two_colors():
    arr = np.zeros((4, 4, 3), dtype=np.uint8)
    arr[:2, :] = (0, 0, 0)
    arr[2:, :] = (255, 255, 255)
    img = Image.fromarray(arr, mode="RGB")
    report = color_usage_report(img)
    assert len(report) == 2
    counts = {r[0]: r[1] for r in report}
    assert counts[(0, 0, 0)] == 8
    assert counts[(255, 255, 255)] == 8


def test_color_usage_report_with_palette_filter():
    src = _make_test_image()
    pal = get_palette("cga")
    out = pixelate_image(src, palette="cga", pixel_size=16, upscale=1, dither="none")
    report = color_usage_report(out, palette=pal)
    # One row per palette color
    assert len(report) == len(pal)
    total_pct = sum(r[2] for r in report)
    assert abs(total_pct - 100.0) < 0.1
    # Counts sorted descending
    counts = [r[1] for r in report]
    assert counts == sorted(counts, reverse=True)


def test_color_usage_percentages_sum_to_100_without_filter():
    src = _make_test_image()
    out = pixelate_image(src, palette="gameboy", pixel_size=16, upscale=1, dither="none")
    report = color_usage_report(out)
    assert abs(sum(r[2] for r in report) - 100.0) < 0.1
    assert all(0 <= r[2] <= 100 for r in report)


def test_color_usage_unused_palette_color_zero():
    # Pure white image quantized to gameboy may not use darkest green
    img = Image.new("RGB", (8, 8), (255, 255, 255))
    pal = get_palette("gameboy")
    out = pixelate_image(img, palette="gameboy", pixel_size=8, upscale=1, dither="none")
    report = color_usage_report(out, palette=pal)
    zeros = [r for r in report if r[1] == 0]
    used = [r for r in report if r[1] > 0]
    assert len(used) >= 1
    assert len(zeros) + len(used) == len(pal)
