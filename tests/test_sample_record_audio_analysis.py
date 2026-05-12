"""Audio analysis field tests for SampleRecord (rms, peak, transient_density)."""
from __future__ import annotations

import dataclasses
import json
import os
import sys
import wave
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools", "senseweave"))

from senseweave.sample_library import SampleLibrary, SampleRecord


AUDIO_ANALYSIS_FIELDS = ("rms", "peak", "transient_density")


def test_sample_record_declares_audio_analysis_fields() -> None:
    field_names = {f.name for f in dataclasses.fields(SampleRecord)}
    for name in AUDIO_ANALYSIS_FIELDS:
        assert name in field_names, f"missing audio analysis field: {name}"


def test_audio_analysis_fields_default_to_zero() -> None:
    record = SampleRecord(character_tags=frozenset())
    assert record.rms == 0.0
    assert record.peak == 0.0
    assert record.transient_density == 0.0


def test_audio_analysis_fields_are_float_type() -> None:
    record = SampleRecord(character_tags=frozenset())
    assert isinstance(record.rms, float)
    assert isinstance(record.peak, float)
    assert isinstance(record.transient_density, float)


def test_audio_analysis_fields_accept_typical_values() -> None:
    record = SampleRecord(
        character_tags=frozenset(),
        rms=0.3,
        peak=0.8,
        transient_density=4.2,
    )
    assert record.rms == 0.3
    assert record.peak == 0.8
    assert record.transient_density == 4.2


def test_peak_equal_to_rms_is_allowed() -> None:
    record = SampleRecord(character_tags=frozenset(), rms=0.5, peak=0.5)
    assert record.peak == record.rms == 0.5


def test_zero_boundary_values_allowed() -> None:
    record = SampleRecord(
        character_tags=frozenset(),
        rms=0.0,
        peak=0.0,
        transient_density=0.0,
    )
    assert record.rms == 0.0
    assert record.peak == 0.0
    assert record.transient_density == 0.0


def test_negative_rms_rejected() -> None:
    with pytest.raises(ValueError, match="rms must be non-negative"):
        SampleRecord(character_tags=frozenset(), rms=-0.001, peak=0.5)


def test_negative_peak_rejected() -> None:
    with pytest.raises(ValueError, match="peak must be non-negative"):
        SampleRecord(character_tags=frozenset(), rms=0.0, peak=-0.001)


def test_negative_transient_density_rejected() -> None:
    with pytest.raises(ValueError, match="transient_density must be non-negative"):
        SampleRecord(character_tags=frozenset(), transient_density=-0.001)


def test_peak_below_rms_rejected() -> None:
    with pytest.raises(ValueError, match=r"peak .* must be >= rms"):
        SampleRecord(character_tags=frozenset(), rms=0.6, peak=0.5)


def test_peak_just_below_rms_rejected_at_boundary() -> None:
    with pytest.raises(ValueError, match=r"peak .* must be >= rms"):
        SampleRecord(character_tags=frozenset(), rms=0.5, peak=0.4999999)


def test_peak_just_above_rms_allowed_at_boundary() -> None:
    record = SampleRecord(character_tags=frozenset(), rms=0.5, peak=0.5000001)
    assert record.peak > record.rms


def test_audio_analysis_fields_round_trip() -> None:
    original = SampleRecord(
        character_tags=frozenset({"warm"}),
        rms=0.25,
        peak=0.9,
        transient_density=12.5,
    )
    payload = {f.name: getattr(original, f.name) for f in dataclasses.fields(original)}
    restored = SampleRecord(**payload)
    assert restored == original
    assert restored.rms == 0.25
    assert restored.peak == 0.9
    assert restored.transient_density == 12.5


def _write_pcm_wav(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    samples = (0, 16_384, -16_384, 8_192, -8_192, 0)
    frames = b"".join(
        sample.to_bytes(2, byteorder="little", signed=True)
        for sample in samples
    )
    with wave.open(str(path), "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(48_000)
        wav_file.writeframes(frames)
    return path


class SampleRecordAudioAnalysisEndToEndTests:
    """End-to-end coverage for sample-record audio metrics."""

    __test__ = True

    def test_audio_metrics_persist_filter_and_round_trip_json_diagnostic(
        self, tmp_path: Path
    ) -> None:
        audio_path = _write_pcm_wav(tmp_path / "samples" / "self" / "tap.wav")
        captured_at = datetime(2026, 5, 3, 12, 0, tzinfo=timezone.utc)
        original = SampleRecord(
            character_tags=frozenset({"warm", "transient"}),
            sample_id="sample-analysis-001",
            path=audio_path,
            source="self",
            pitch_hz=220.0,
            arc_phase="Emergence",
            mood=0.55,
            captured_at=captured_at,
            duration=1.25,
            rms=0.31,
            peak=0.76,
            transient_density=9.0,
            extras={"analysis": "manual-e2e"},
        )

        payload = original.to_dict()
        assert payload["duration"] == 1.25
        assert payload["rms"] == 0.31
        assert payload["peak"] == 0.76
        assert payload["transient_density"] == 9.0

        restored = SampleRecord.from_dict(json.loads(json.dumps(payload)))
        assert restored == original

        with SampleLibrary(tmp_path / "library") as library:
            sample_id = library.add(restored)
            found = library.find(
                source="self",
                character_any=["transient"],
                mood_range=(0.5, 0.6),
                limit=1,
            )

        assert sample_id == "sample-analysis-001"
        assert len(found) == 1
        stored = found[0]
        assert stored.sample_id == original.sample_id
        assert stored.path == audio_path
        assert stored.source == "self"
        assert stored.character_tags == frozenset({"warm", "transient"})
        assert stored.duration == 1.25
        assert stored.rms == 0.31
        assert stored.peak == 0.76
        assert stored.transient_density == 9.0

        diagnostic = {
            "sample_id": stored.sample_id,
            "path": str(stored.path),
            "source": stored.source,
            "tags": sorted(stored.character_tags),
            "metrics": {
                "duration": stored.duration,
                "rms": stored.rms,
                "peak": stored.peak,
                "transient_density": stored.transient_density,
            },
        }
        round_tripped = json.loads(json.dumps(diagnostic, sort_keys=True))

        assert round_tripped == diagnostic
        assert round_tripped["metrics"]["peak"] >= round_tripped["metrics"]["rms"]
        assert round_tripped["metrics"]["transient_density"] > 0.0
