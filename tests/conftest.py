"""Shared fixtures."""

import pytest

from pixelate.palettes import PALETTES
from pixelate.presets import PRESETS


@pytest.fixture(autouse=True)
def _restore_registries():
    """Tests may register palettes / presets; keep the global registries clean."""
    palettes, presets = dict(PALETTES), dict(PRESETS)
    yield
    PALETTES.clear()
    PALETTES.update(palettes)
    PRESETS.clear()
    PRESETS.update(presets)
