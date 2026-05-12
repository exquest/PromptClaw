"""Depth-2 senseweave voice report helpers - locked test surface for frac-0030."""
from __future__ import annotations

import dataclasses
import json
import os
import sys
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools"))

from senseweave.synthesis.senseweave_voice import (  # noqa: E402
    ADSR,
    BREATH,
    PAD,
    RHYTHMIC,
    SHIMMER,
    STAB,
    SWELL,
    TIMBRE_MAP,
    ActiveNote,
    SenseweaveVoice,
    VoiceADSRSnapshot,
    VoiceNoteSnapshot,
    VoicePlanReport,
    build_voice_adsr_snapshot,
    build_voice_note_snapshot,
    build_voice_plan_report,
    preset_envelope_band,
    preset_name_for_adsr,
    summarize_active_notes,
    summarize_voice_plan_report,
    voice_amp_band,
    voice_envelope_band,
    voice_polyphony_band,
    voice_register_band,
    voice_synth_for_timbre,
)


def test_voice_helper_bands_map_values_to_named_outputs() -> None:
    assert voice_envelope_band(STAB) == "percussive"
    assert voice_envelope_band(RHYTHMIC) == "percussive"
    assert voice_envelope_band(PAD) == "long_attack"
    assert voice_envelope_band(SWELL) == "long_attack"
    assert voice_envelope_band(BREATH) == "medium_attack"
    assert voice_envelope_band(SHIMMER) == "short_attack"

    assert voice_amp_band(0.0) == "silent"
    assert voice_amp_band(-0.1) == "silent"
    assert voice_amp_band(0.001) == "quiet"
    assert voice_amp_band(0.05) == "quiet"
    assert voice_amp_band(0.0501) == "medium"
    assert voice_amp_band(0.1) == "medium"
    assert voice_amp_band(0.1001) == "loud"

    assert voice_register_band(65.39) == "pedal"
    assert voice_register_band(65.4) == "bass"
    assert voice_register_band(130.79) == "bass"
    assert voice_register_band(130.8) == "middle"
    assert voice_register_band(523.29) == "middle"
    assert voice_register_band(523.3) == "upper"

    assert voice_polyphony_band(0, 8) == "idle"
    assert voice_polyphony_band(-1, 8) == "idle"
    assert voice_polyphony_band(1, 8) == "sparse"
    assert voice_polyphony_band(3, 8) == "sparse"
    assert voice_polyphony_band(4, 8) == "filling"
    assert voice_polyphony_band(7, 8) == "filling"
    assert voice_polyphony_band(8, 8) == "full"
    assert voice_polyphony_band(10, 8) == "full"
    assert voice_polyphony_band(1, 0) == "full"

    assert preset_name_for_adsr(PAD) == "pad"
    assert preset_name_for_adsr(SWELL) == "swell"
    assert preset_name_for_adsr(STAB) == "stab"
    assert preset_name_for_adsr(RHYTHMIC) == "rhythmic"
    assert preset_name_for_adsr(BREATH) == "breath"
    assert preset_name_for_adsr(SHIMMER) == "shimmer"
    assert preset_name_for_adsr(ADSR(0.7, 0.2, 0.5, 1.0)) is None

    assert preset_envelope_band("pad") == "long_attack"
    assert preset_envelope_band("stab") == "percussive"
    assert preset_envelope_band("breath") == "medium_attack"
    assert preset_envelope_band("shimmer") == "short_attack"
    assert preset_envelope_band("nope") == "unknown"

    assert voice_synth_for_timbre("pad") == TIMBRE_MAP["pad"]
    assert voice_synth_for_timbre("warm") == TIMBRE_MAP["warm"]
    assert voice_synth_for_timbre("nope") == TIMBRE_MAP["pad"]


def test_build_voice_adsr_snapshot_summarizes_envelope() -> None:
    snapshot = build_voice_adsr_snapshot(PAD)

    assert isinstance(snapshot, VoiceADSRSnapshot)
    assert dataclasses.is_dataclass(snapshot)
    assert getattr(snapshot, "__dataclass_params__").frozen
    assert snapshot.preset_name == "pad"
    assert snapshot.attack == PAD.attack
    assert snapshot.decay == PAD.decay
    assert snapshot.sustain == PAD.sustain
    assert snapshot.release == PAD.release
    assert snapshot.total_duration == pytest.approx(PAD.attack + PAD.decay)
    assert snapshot.is_percussive is False
    assert snapshot.envelope_band == "long_attack"

    custom = ADSR(0.7, 0.2, 0.5, 1.0)
    custom_snapshot = build_voice_adsr_snapshot(custom)
    assert custom_snapshot.preset_name is None
    assert custom_snapshot.is_percussive is False
    assert custom_snapshot.envelope_band == "short_attack"


def _make_voice_with_notes() -> tuple[SenseweaveVoice, float]:
    voice = SenseweaveVoice(osc=MagicMock(), timbre="stab")
    voice.adsr = STAB
    started_at = 1_000_000.0
    voice._active_notes.append(
        ActiveNote(
            node_id=70001,
            freq=220.0,
            synth=TIMBRE_MAP["stab"],
            adsr=STAB,
            started_at=started_at,
            amp=0.08,
        )
    )
    voice._active_notes.append(
        ActiveNote(
            node_id=70002,
            freq=55.0,
            synth=TIMBRE_MAP["stab"],
            adsr=STAB,
            started_at=started_at,
            amp=0.04,
        )
    )
    return voice, started_at


def test_build_voice_note_snapshot_clamps_elapsed_to_non_negative() -> None:
    note = ActiveNote(
        node_id=70010,
        freq=440.0,
        synth=TIMBRE_MAP["pad"],
        adsr=PAD,
        started_at=1_000_000.0,
        amp=0.06,
    )
    snapshot = build_voice_note_snapshot(note, now=999_999.0)

    assert isinstance(snapshot, VoiceNoteSnapshot)
    assert dataclasses.is_dataclass(snapshot)
    assert getattr(snapshot, "__dataclass_params__").frozen
    assert snapshot.elapsed_seconds == 0.0
    assert snapshot.register_band == "middle"
    assert snapshot.amp_band == "medium"
    assert snapshot.envelope.envelope_band == "long_attack"


def test_build_voice_plan_report_resolves_end_to_end_state() -> None:
    voice, started_at = _make_voice_with_notes()
    report = build_voice_plan_report(voice, now=started_at + 1.5)

    assert isinstance(report, VoicePlanReport)
    assert dataclasses.is_dataclass(report)
    assert getattr(report, "__dataclass_params__").frozen
    assert report.timbre == "stab"
    assert report.synth == TIMBRE_MAP["stab"]
    assert report.preset_name == "stab"
    assert report.envelope.preset_name == "stab"
    assert report.envelope.envelope_band == "percussive"
    assert report.envelope.is_percussive is True
    assert report.max_polyphony == 8
    assert report.active_count == 2
    assert report.polyphony_band == "sparse"
    assert report.is_playing is True
    assert len(report.notes) == 2

    note_a, note_b = report.notes
    assert isinstance(note_a, VoiceNoteSnapshot)
    assert note_a.node_id == 70001
    assert note_a.freq == 220.0
    assert note_a.synth == TIMBRE_MAP["stab"]
    assert note_a.amp == 0.08
    assert note_a.register_band == "middle"
    assert note_a.amp_band == "medium"
    assert note_a.envelope.envelope_band == "percussive"
    assert note_a.elapsed_seconds == pytest.approx(1.5)

    assert note_b.node_id == 70002
    assert note_b.freq == 55.0
    assert note_b.register_band == "pedal"
    assert note_b.amp_band == "quiet"
    assert note_b.elapsed_seconds == pytest.approx(1.5)

    assert report.total_amp == pytest.approx(0.12)
    assert report.mean_amp == pytest.approx(0.06)
    assert report.lowest_frequency_hz == pytest.approx(55.0)
    assert report.highest_frequency_hz == pytest.approx(220.0)
    assert report.register_band_counts == {
        "pedal": 1,
        "bass": 0,
        "middle": 1,
        "upper": 0,
    }
    assert report.amp_band_counts == {
        "silent": 0,
        "quiet": 1,
        "medium": 1,
        "loud": 0,
    }
    assert report.synth_counts == {TIMBRE_MAP["stab"]: 2}


def test_summarize_voice_plan_report_returns_json_safe_summary() -> None:
    voice, started_at = _make_voice_with_notes()
    report = build_voice_plan_report(voice, now=started_at + 1.5)

    summary = summarize_voice_plan_report(report)
    assert summary["timbre"] == "stab"
    assert summary["synth"] == TIMBRE_MAP["stab"]
    assert summary["preset_name"] == "stab"
    assert summary["envelope"]["preset_name"] == "stab"  # type: ignore[index]
    assert summary["envelope"]["envelope_band"] == "percussive"  # type: ignore[index]
    assert summary["envelope"]["is_percussive"] is True  # type: ignore[index]
    assert summary["max_polyphony"] == 8
    assert summary["active_count"] == 2
    assert summary["polyphony_band"] == "sparse"
    assert summary["is_playing"] is True
    assert summary["mean_amp"] == pytest.approx(0.06)
    assert summary["total_amp"] == pytest.approx(0.12)
    assert summary["lowest_frequency_hz"] == pytest.approx(55.0)
    assert summary["highest_frequency_hz"] == pytest.approx(220.0)
    assert summary["register_band_counts"] == {
        "pedal": 1,
        "bass": 0,
        "middle": 1,
        "upper": 0,
    }
    assert summary["amp_band_counts"] == {
        "silent": 0,
        "quiet": 1,
        "medium": 1,
        "loud": 0,
    }
    assert summary["synth_counts"] == {TIMBRE_MAP["stab"]: 2}
    assert isinstance(summary["notes"], list)
    assert summary["notes"][0]["node_id"] == 70001  # type: ignore[index]
    assert summary["notes"][0]["register_band"] == "middle"  # type: ignore[index]
    assert summary["notes"][0]["amp_band"] == "medium"  # type: ignore[index]
    assert summary["notes"][0]["envelope"]["envelope_band"] == "percussive"  # type: ignore[index]
    json.loads(json.dumps(summary))


def test_voice_plan_report_agrees_with_existing_helpers() -> None:
    voice, started_at = _make_voice_with_notes()
    report = build_voice_plan_report(voice, now=started_at + 0.5)

    assert report.synth == voice_synth_for_timbre(voice.timbre)
    assert report.envelope.envelope_band == voice_envelope_band(voice.adsr)
    assert report.preset_name == preset_name_for_adsr(voice.adsr)
    assert report.polyphony_band == voice_polyphony_band(
        voice.active_count, voice.max_polyphony
    )
    assert report.is_playing is voice.is_playing
    for snapshot, live in zip(report.notes, voice._active_notes, strict=True):
        assert snapshot.register_band == voice_register_band(live.freq)
        assert snapshot.amp_band == voice_amp_band(live.amp)
        assert snapshot.synth == live.synth

    aggregate = summarize_active_notes(voice._active_notes)
    assert report.total_amp == pytest.approx(aggregate["total_amp"])
    assert report.mean_amp == pytest.approx(aggregate["mean_amp"])
    assert report.lowest_frequency_hz == pytest.approx(
        aggregate["lowest_frequency_hz"]
    )
    assert report.highest_frequency_hz == pytest.approx(
        aggregate["highest_frequency_hz"]
    )
    assert report.register_band_counts == aggregate["register_band_counts"]
    assert report.amp_band_counts == aggregate["amp_band_counts"]
    assert report.synth_counts == aggregate["synth_counts"]


def test_senseweave_voice_reaches_depth_two() -> None:
    from sdp.fractal import classify_depth

    result = classify_depth(
        "my-claw/tools/senseweave/synthesis/senseweave_voice.py"
    )
    assert result.depth >= 2, result.reason
