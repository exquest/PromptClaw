"""Tests for tracker instrument patch selection and voice normalization."""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools", "senseweave"))

from senseweave.instrument_patches import (
    INSTRUMENT_PATCHES,
    normalize_patch_voice,
    select_instrument_patch,
)


class TestSelectInstrumentPatch:
    def test_sleep_prefers_house_monastery(self):
        patch = select_instrument_patch(cadence_state="sleep", family_name="nocturne")
        assert patch.name == "house_monastery"

    def test_wake_ramp_prefers_house_chamber(self):
        patch = select_instrument_patch(cadence_state="wake_ramp", family_name="ember")
        assert patch.name == "house_chamber"

    def test_daytime_pulse_prefers_house_procession(self):
        patch = select_instrument_patch(cadence_state="occupied_day", family_name="pulse")
        assert patch.name == "house_procession"

    def test_midday_bloom_prefers_house_garden(self):
        patch = select_instrument_patch(cadence_state="occupied_day", family_name="bloom")
        assert patch.name == "house_garden"

    def test_away_practice_prefers_house_workshop(self):
        patch = select_instrument_patch(cadence_state="away_practice", family_name="forge")
        assert patch.name == "house_workshop"


class TestNormalizePatchVoice:
    def test_house_chamber_softens_inharmonic_and_non_western_voices(self):
        patch = select_instrument_patch(cadence_state="wake_ramp", family_name="ember")

        assert normalize_patch_voice("melody", "bell", patch=patch) == "bowed"
        assert normalize_patch_voice("bass", "tabla_tin", patch=patch) == "pluck"
        assert normalize_patch_voice("color", "metal", patch=patch) == "breath"
        assert normalize_patch_voice("counter", "kotekan", patch=patch) == "bowed"

    def test_house_monastery_pushes_everything_toward_soft_ensemble(self):
        patch = select_instrument_patch(cadence_state="sleep", family_name="nocturne")

        assert normalize_patch_voice("melody", "pluck", patch=patch) == "bowed"
        assert normalize_patch_voice("bass", "kotekan", patch=patch) == "bowed"
        assert normalize_patch_voice("color", "bell", patch=patch) == "breath"
        assert normalize_patch_voice("counter", "metal", patch=patch) == "choir"

    def test_house_workshop_keeps_rhythmic_experiment_but_retires_bell_and_metal(self):
        patch = select_instrument_patch(cadence_state="away_practice", family_name="forge")

        assert normalize_patch_voice("bass", "tabla_tin", patch=patch) == "tabla_tin"
        assert normalize_patch_voice("counter", "metal", patch=patch) == "choir"
        assert normalize_patch_voice("melody", "kotekan", patch=patch) == "kotekan"
        assert normalize_patch_voice("melody", "bell", patch=patch) == "bowed"


class TestInstrumentPatchesEndToEnd:
    def test_end_to_end_patch_runtime_flow(self):
        # 1. Cadence/family selection picks the chamber patch for a daytime
        #    ember scene (no other override fires).
        chamber = select_instrument_patch(
            cadence_state="wake_ramp", family_name="ember"
        )
        assert chamber.name == "house_chamber"
        assert chamber is INSTRUMENT_PATCHES["house_chamber"]

        # 2. Explicit patch_name override wins over cadence/family signals.
        forced_monastery = select_instrument_patch(
            cadence_state="wake_ramp",
            family_name="ember",
            patch_name="house_monastery",
        )
        assert forced_monastery.name == "house_monastery"

        # 3. Per-role normalization through the chamber patch covers each
        #    resolution path: explicit remap, allowed-voice passthrough, and
        #    fallback for an out-of-palette voice.
        normalized = {
            "melody_bell": normalize_patch_voice("melody", "bell", patch=chamber),
            "melody_pluck": normalize_patch_voice("melody", "pluck", patch=chamber),
            "bass_tabla_tin": normalize_patch_voice(
                "bass", "tabla_tin", patch=chamber
            ),
            "color_metal": normalize_patch_voice("color", "metal", patch=chamber),
            "counter_kotekan": normalize_patch_voice(
                "counter", "kotekan", patch=chamber
            ),
            "melody_unknown": normalize_patch_voice(
                "melody", "ocarina", patch=chamber
            ),
        }
        assert normalized == {
            "melody_bell": "bowed",
            "melody_pluck": "pluck",
            "bass_tabla_tin": "pluck",
            "color_metal": "breath",
            "counter_kotekan": "bowed",
            "melody_unknown": "bowed",
        }

        # 4. The resolved palette is JSON-safe so tracker diagnostics can
        #    serialize it without special handling.
        diagnostics = {
            "patch": chamber.name,
            "voices": dict(normalized),
        }
        round_trip = json.loads(json.dumps(diagnostics))
        assert round_trip == diagnostics
