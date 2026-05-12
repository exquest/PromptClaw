"""Tests for EMSD sound palette studies."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools", "senseweave"))

from senseweave.sound_palette_lab import VOICE_STUDIES, catalog_by_method, study_for_patch


def test_palette_catalog_spans_multiple_synthesis_methods() -> None:
    methods = catalog_by_method()

    assert len(VOICE_STUDIES) >= 10
    assert {"subtractive", "additive", "fm", "wavetable", "granular"} <= set(methods)


def test_patch_study_uses_house_patch_identity() -> None:
    study = study_for_patch(patch_name="house_workshop", cadence_state="away_practice", family_name="forge")

    assert study.patch_name == "house_workshop"
    assert "FM" in study.study_focus or "articulation" in study.study_focus
    assert study.primary_voices
