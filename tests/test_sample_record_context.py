"""Default-value and serialization round-trip tests for SampleRecord context fields."""
from __future__ import annotations

import dataclasses
import json
import os
import sys
import wave
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools", "senseweave"))

from senseweave.sample_library import SampleLibrary, SampleRecord


CONTEXT_FIELDS = ("character_tags", "arc_context", "pitch", "duration")


def test_sample_record_declares_context_fields() -> None:
    field_names = {f.name for f in dataclasses.fields(SampleRecord)}
    for name in CONTEXT_FIELDS:
        assert name in field_names, f"missing context field: {name}"


def test_arc_context_defaults_to_empty_string() -> None:
    record = SampleRecord(character_tags=frozenset())
    assert record.arc_context == ""


def test_pitch_defaults_to_none() -> None:
    record = SampleRecord(character_tags=frozenset())
    assert record.pitch is None


def test_duration_defaults_to_zero() -> None:
    record = SampleRecord(character_tags=frozenset())
    assert record.duration == 0.0
    assert isinstance(record.duration, float)


def test_arc_context_accepts_dict() -> None:
    ctx = {"phase": "Emergence", "intensity": 0.5}
    record = SampleRecord(character_tags=frozenset(), arc_context=ctx)
    assert record.arc_context == ctx


def test_arc_context_accepts_string() -> None:
    record = SampleRecord(character_tags=frozenset(), arc_context="Convergence")
    assert record.arc_context == "Convergence"


def test_pitch_accepts_float() -> None:
    record = SampleRecord(character_tags=frozenset(), pitch=440.0)
    assert record.pitch == 440.0


def test_serialization_round_trip_with_string_arc_context() -> None:
    original = SampleRecord(
        character_tags=frozenset({"warm", "harmonic"}),
        sample_id="s-1",
        path=Path("/data/samples/s-1.wav"),
        source="library",
        pitch_hz=220.0,
        arc_phase="Emergence",
        mood=0.4,
        captured_at=datetime(2026, 4, 25, 18, 39, 59, tzinfo=timezone.utc),
        arc_context="Emergence",
        pitch=220.0,
        duration=2.5,
    )
    payload = {f.name: getattr(original, f.name) for f in dataclasses.fields(original)}
    restored = SampleRecord(**payload)
    assert restored == original
    assert restored.arc_context == "Emergence"
    assert restored.pitch == 220.0
    assert restored.duration == 2.5


def test_serialization_round_trip_with_dict_arc_context() -> None:
    original = SampleRecord(
        character_tags=frozenset({"voice"}),
        sample_id="s-2",
        path=Path("/data/samples/s-2.wav"),
        source="self",
        arc_context={"phase": "Convergence", "intensity": 0.75, "notes": "duet"},
        pitch=329.63,
        duration=4.0,
    )
    payload = {f.name: getattr(original, f.name) for f in dataclasses.fields(original)}
    restored = SampleRecord(**payload)
    assert restored == original
    assert restored.arc_context == {"phase": "Convergence", "intensity": 0.75, "notes": "duet"}
    assert restored.pitch == 329.63
    assert restored.duration == 4.0


def test_context_fields_preserved_through_dataclasses_replace() -> None:
    base = SampleRecord(
        character_tags=frozenset({"pulse"}),
        arc_context="Emergence",
        pitch=110.0,
        duration=1.0,
    )
    updated = dataclasses.replace(base, duration=2.0)
    assert updated.character_tags == frozenset({"pulse"})
    assert updated.arc_context == "Emergence"
    assert updated.pitch == 110.0
    assert updated.duration == 2.0


def _write_pcm_wav(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    samples = (0, 12_000, -12_000, 6_000, -6_000, 0)
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


class SampleRecordContextEndToEndTests:
    """End-to-end coverage for sample-record context fields."""

    __test__ = True

    def test_context_fields_persist_filter_and_round_trip_json_diagnostic(
        self, tmp_path: Path
    ) -> None:
        audio_path = _write_pcm_wav(tmp_path / "samples" / "self" / "ctx.wav")
        captured_at = datetime(2026, 5, 3, 14, 30, tzinfo=timezone.utc)
        arc_context = {
            "phase": "Convergence",
            "intensity": 0.65,
            "notes": "duet",
        }
        original = SampleRecord(
            character_tags=frozenset({"warm", "harmonic"}),
            sample_id="sample-context-001",
            path=audio_path,
            source="self",
            pitch_hz=329.63,
            arc_phase="Convergence",
            mood=0.42,
            captured_at=captured_at,
            arc_context=arc_context,
            pitch=329.63,
            duration=2.75,
        )

        payload = original.to_dict()
        assert payload["character_tags"] == ["harmonic", "warm"]
        assert payload["arc_context"] == arc_context
        assert payload["pitch"] == 329.63
        assert payload["duration"] == 2.75

        restored = SampleRecord.from_dict(json.loads(json.dumps(payload)))
        assert restored == original

        with SampleLibrary(tmp_path / "library") as library:
            sample_id = library.add(restored)
            found = library.find(
                source="self",
                character_any=["harmonic"],
                mood_range=(0.4, 0.5),
                limit=1,
            )

        assert sample_id == "sample-context-001"
        assert len(found) == 1
        stored = found[0]
        assert stored.sample_id == original.sample_id
        assert stored.path == audio_path
        assert stored.source == "self"
        assert stored.character_tags == frozenset({"warm", "harmonic"})
        assert stored.arc_context == arc_context
        assert stored.pitch == 329.63
        assert stored.duration == 2.75

        diagnostic = {
            "sample_id": stored.sample_id,
            "path": str(stored.path),
            "source": stored.source,
            "tags": sorted(stored.character_tags),
            "context": {
                "arc_context": stored.arc_context,
                "pitch": stored.pitch,
                "duration": stored.duration,
            },
        }
        round_tripped = json.loads(json.dumps(diagnostic, sort_keys=True))

        assert round_tripped == diagnostic
        assert round_tripped["context"]["arc_context"]["phase"] == "Convergence"
        assert round_tripped["context"]["pitch"] > 0.0
        assert round_tripped["context"]["duration"] > 0.0
