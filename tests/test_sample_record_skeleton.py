"""Skeleton-level instantiation and field-type tests for SampleRecord core identity fields."""
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


CORE_IDENTITY_FIELDS = ("sample_id", "path", "source", "captured_at")


def _make_skeleton(
    *,
    sample_id: str = "s-001",
    path: Path = Path("/tmp/sample.wav"),
    source: str = "library",
    captured_at: datetime | None = None,
) -> SampleRecord:
    return SampleRecord(
        character_tags=frozenset(),
        sample_id=sample_id,
        path=path,
        source=source,
        captured_at=captured_at or datetime(2026, 4, 25, 18, 39, 59, tzinfo=timezone.utc),
    )


def test_sample_record_is_a_dataclass() -> None:
    assert dataclasses.is_dataclass(SampleRecord)


def test_sample_record_declares_core_identity_fields() -> None:
    field_names = {f.name for f in dataclasses.fields(SampleRecord)}
    for name in CORE_IDENTITY_FIELDS:
        assert name in field_names, f"missing core identity field: {name}"


def test_sample_record_instantiates_with_core_identity_fields() -> None:
    captured = datetime(2026, 4, 25, 18, 39, 59, tzinfo=timezone.utc)
    record = _make_skeleton(
        sample_id="abc123",
        path=Path("/data/samples/library/abc123.wav"),
        source="library",
        captured_at=captured,
    )
    assert record.sample_id == "abc123"
    assert record.path == Path("/data/samples/library/abc123.wav")
    assert record.source == "library"
    assert record.captured_at == captured


def test_sample_id_field_is_string_type() -> None:
    record = _make_skeleton(sample_id="uuid-string")
    assert isinstance(record.sample_id, str)


def test_path_field_is_path_type() -> None:
    record = _make_skeleton(path=Path("/data/samples/self/x.wav"))
    assert isinstance(record.path, Path)


def test_source_field_is_string_type() -> None:
    record = _make_skeleton(source="self")
    assert isinstance(record.source, str)


def test_captured_at_field_is_datetime_type() -> None:
    record = _make_skeleton(captured_at=datetime(2026, 4, 25, tzinfo=timezone.utc))
    assert isinstance(record.captured_at, datetime)


def test_sample_record_is_frozen() -> None:
    record = _make_skeleton()
    with pytest.raises(dataclasses.FrozenInstanceError):
        record.sample_id = "mutated"  # type: ignore[misc]


def test_sample_record_equality_by_core_identity_fields() -> None:
    captured = datetime(2026, 4, 25, 18, 39, 59, tzinfo=timezone.utc)
    a = _make_skeleton(sample_id="x", path=Path("/p.wav"), source="library", captured_at=captured)
    b = _make_skeleton(sample_id="x", path=Path("/p.wav"), source="library", captured_at=captured)
    assert a == b


def _write_pcm_wav(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    samples = (0, 8_000, -8_000, 4_000, -4_000, 0)
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


class SampleRecordSkeletonEndToEndTests:
    """End-to-end coverage for sample-record core identity fields."""

    __test__ = True

    def test_core_identity_persists_filters_and_round_trips_json_diagnostic(
        self, tmp_path: Path
    ) -> None:
        audio_path = _write_pcm_wav(tmp_path / "samples" / "library" / "core.wav")
        captured_at = datetime(2026, 5, 3, 15, 45, tzinfo=timezone.utc)
        original = SampleRecord(
            character_tags=frozenset({"warm", "harmonic"}),
            sample_id="sample-skeleton-001",
            path=audio_path,
            source="library",
            captured_at=captured_at,
        )

        payload = original.to_dict()
        assert payload["sample_id"] == "sample-skeleton-001"
        assert payload["path"] == str(audio_path)
        assert payload["source"] == "library"
        assert payload["captured_at"] == "2026-05-03T15:45:00+00:00"

        restored = SampleRecord.from_dict(json.loads(json.dumps(payload)))
        assert restored == original
        assert restored.path == audio_path
        assert restored.captured_at == captured_at

        with SampleLibrary(tmp_path / "library") as library:
            sample_id = library.add(restored)
            found = library.find(
                source="library",
                character_all=["warm", "harmonic"],
                limit=1,
            )

        assert sample_id == "sample-skeleton-001"
        assert len(found) == 1
        stored = found[0]
        assert stored.sample_id == original.sample_id
        assert stored.path == audio_path
        assert stored.source == "library"
        assert stored.captured_at == captured_at
        assert stored.character_tags == frozenset({"warm", "harmonic"})

        diagnostic = {
            "sample_id": stored.sample_id,
            "path": str(stored.path),
            "source": stored.source,
            "captured_at": stored.captured_at.isoformat()
            if stored.captured_at is not None
            else None,
            "identity_fields": {
                "has_sample_id": bool(stored.sample_id),
                "path_suffix": Path(stored.path).suffix if stored.path else "",
                "source": stored.source,
            },
        }
        round_tripped = json.loads(json.dumps(diagnostic, sort_keys=True))

        assert round_tripped == diagnostic
        assert round_tripped["identity_fields"]["has_sample_id"] is True
        assert round_tripped["identity_fields"]["path_suffix"] == ".wav"
        assert round_tripped["captured_at"] == "2026-05-03T15:45:00+00:00"
