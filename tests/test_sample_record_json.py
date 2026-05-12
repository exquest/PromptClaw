"""JSON serialization helper tests for SampleRecord (to_dict / from_dict)."""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools", "senseweave"))

from senseweave.sample_library import SampleRecord


def _full_record() -> SampleRecord:
    return SampleRecord(
        character_tags=frozenset({"warm", "harmonic"}),
        sample_id="s-json-1",
        path=Path("/data/samples/s-json-1.wav"),
        source="library",
        pitch_hz=220.0,
        arc_phase="Emergence",
        mood=0.4,
        captured_at=datetime(2026, 4, 25, 18, 39, 59, tzinfo=timezone.utc),
        arc_context={"phase": "Emergence", "intensity": 0.5},
        pitch=220.0,
        duration=2.5,
        rms=0.3,
        peak=0.85,
        transient_density=4.0,
    )


def test_to_dict_returns_json_compatible_payload() -> None:
    record = _full_record()
    payload = record.to_dict()
    # Must be JSON-serializable end-to-end.
    encoded = json.dumps(payload)
    assert isinstance(encoded, str)
    decoded = json.loads(encoded)
    assert decoded == payload


def test_to_dict_serializes_path_as_string() -> None:
    record = _full_record()
    payload = record.to_dict()
    assert payload["path"] == "/data/samples/s-json-1.wav"
    assert isinstance(payload["path"], str)


def test_to_dict_serializes_datetime_as_isoformat() -> None:
    record = _full_record()
    payload = record.to_dict()
    assert payload["captured_at"] == "2026-04-25T18:39:59+00:00"
    assert isinstance(payload["captured_at"], str)


def test_to_dict_serializes_character_tags_as_sorted_list() -> None:
    record = _full_record()
    payload = record.to_dict()
    assert payload["character_tags"] == ["harmonic", "warm"]


def test_to_dict_handles_none_path_and_captured_at() -> None:
    record = SampleRecord(character_tags=frozenset({"pulse"}))
    payload = record.to_dict()
    assert payload["path"] is None
    assert payload["captured_at"] is None


def test_round_trip_preserves_equality() -> None:
    original = _full_record()
    restored = SampleRecord.from_dict(original.to_dict())
    assert restored == original


def test_round_trip_through_json_string() -> None:
    original = _full_record()
    restored = SampleRecord.from_dict(json.loads(json.dumps(original.to_dict())))
    assert restored == original
    assert isinstance(restored.path, Path)
    assert isinstance(restored.captured_at, datetime)
    assert restored.captured_at.tzinfo is not None
    assert restored.character_tags == frozenset({"warm", "harmonic"})


def test_from_dict_coerces_path_string_to_path() -> None:
    payload = _full_record().to_dict()
    restored = SampleRecord.from_dict(payload)
    assert isinstance(restored.path, Path)
    assert restored.path == Path("/data/samples/s-json-1.wav")


def test_from_dict_coerces_isoformat_to_datetime() -> None:
    payload = _full_record().to_dict()
    restored = SampleRecord.from_dict(payload)
    assert isinstance(restored.captured_at, datetime)
    assert restored.captured_at == datetime(
        2026, 4, 25, 18, 39, 59, tzinfo=timezone.utc
    )


def test_from_dict_accepts_list_of_character_tags() -> None:
    payload = _full_record().to_dict()
    assert isinstance(payload["character_tags"], list)
    restored = SampleRecord.from_dict(payload)
    assert isinstance(restored.character_tags, frozenset)
    assert restored.character_tags == frozenset({"warm", "harmonic"})


def test_round_trip_with_string_arc_context() -> None:
    original = SampleRecord(
        character_tags=frozenset({"voice"}),
        sample_id="s-json-2",
        path=Path("/data/samples/s-json-2.wav"),
        source="self",
        arc_context="Convergence",
        pitch=329.63,
        duration=4.0,
    )
    restored = SampleRecord.from_dict(json.loads(json.dumps(original.to_dict())))
    assert restored == original
    assert restored.arc_context == "Convergence"


def test_round_trip_with_minimal_record() -> None:
    original = SampleRecord(character_tags=frozenset())
    restored = SampleRecord.from_dict(json.loads(json.dumps(original.to_dict())))
    assert restored == original
    assert restored.path is None
    assert restored.captured_at is None
    assert restored.character_tags == frozenset()


def test_round_trip_preserves_audio_analysis_fields() -> None:
    original = _full_record()
    restored = SampleRecord.from_dict(json.loads(json.dumps(original.to_dict())))
    assert restored.rms == 0.3
    assert restored.peak == 0.85
    assert restored.transient_density == 4.0


def test_from_dict_rejects_invalid_tags_via_post_init() -> None:
    payload = _full_record().to_dict()
    payload["character_tags"] = ["warm", "not-a-real-tag"]
    import pytest

    with pytest.raises(ValueError, match="unknown character_tags"):
        SampleRecord.from_dict(payload)
