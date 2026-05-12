"""Tests for the audio export provenance integration."""
from __future__ import annotations

import json
import os
import sys
import wave
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools"))

from senseweave.ixml_chunk_writer import read_ixml  # noqa: E402
from senseweave.render import (  # noqa: E402
    ExportResult,
    PerformedPart,
    export_audio,
    read_audio_metadata_sidecar,
)

SAMPLE_RATE = 16000


def _make_wav(path: Path, *, frames: int = 1600) -> None:
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(SAMPLE_RATE)
        handle.writeframes(b"\x00\x00" * frames)


def test_export_audio_writes_sidecar_and_ixml_from_performed_part(tmp_path: Path) -> None:
    wav = tmp_path / "piece.wav"
    _make_wav(wav)

    performed = PerformedPart(
        score={},
        applied_rules=("R1", "R6"),
        quantities={"R1": 1.0, "R2": 0.0, "R6": 0.45},
        metadata={"intent_tags": "withhold"},
    )

    result = export_audio(
        wav,
        performed_part=performed,
        seeds={"root": 7},
        extra_metadata={"renderer": "test"},
    )

    assert isinstance(result, ExportResult)
    assert result.audio_path == wav
    assert result.sidecar_path == wav.with_suffix(".meta.json")
    assert result.sidecar_path.exists()

    sidecar = read_audio_metadata_sidecar(wav)
    assert set(sidecar) == {
        "audio_path",
        "delta_track_path",
        "events",
        "metadata",
        "performance_intents",
        "rule_quantities",
        "rule_stack",
        "rule_stack_provenance",
        "schema_version",
        "section_envelopes",
        "seeds",
    }
    assert sidecar["schema_version"] == "render-audio-sidecar/v1"
    assert set(sidecar["rule_stack_provenance"]) == {
        "applied_rules",
        "metadata",
        "quantities",
    }
    assert sidecar["rule_stack"] == ["R1", "R6"]
    assert sidecar["rule_quantities"] == {"R1": 1.0, "R2": 0.0, "R6": 0.45}
    assert sidecar["seeds"] == {"root": 7}

    ixml = read_ixml(wav)
    assert ixml == result.ixml_keys
    assert ixml["rule_stack"] == "R1,R6"
    quantities = json.loads(ixml["rule_quantities"])
    assert quantities == {"R1": 1.0, "R2": 0.0, "R6": 0.45}


def test_export_audio_with_explicit_rule_stack(tmp_path: Path) -> None:
    wav = tmp_path / "take.wav"
    _make_wav(wav)

    export_audio(
        wav,
        rule_stack=["R3", "R4"],
        rule_quantities={"R3": 0.8, "R4": 1.0},
    )

    sidecar = read_audio_metadata_sidecar(wav)
    assert sidecar["rule_stack"] == ["R3", "R4"]

    ixml = read_ixml(wav)
    assert ixml["rule_stack"] == "R3,R4"
    assert json.loads(ixml["rule_quantities"]) == {"R3": 0.8, "R4": 1.0}


def test_export_audio_ixml_extra_merged(tmp_path: Path) -> None:
    wav = tmp_path / "extra.wav"
    _make_wav(wav)

    result = export_audio(
        wav,
        performed_part=PerformedPart(
            score={}, applied_rules=("R1",), quantities={"R1": 1.0},
        ),
        ixml_extra={"scene": "forest", "sensor_id": "mic-01"},
    )

    ixml = read_ixml(wav)
    assert ixml == result.ixml_keys
    assert ixml["rule_stack"] == "R1"
    assert ixml["scene"] == "forest"
    assert ixml["sensor_id"] == "mic-01"


def test_export_audio_empty_rule_stack(tmp_path: Path) -> None:
    wav = tmp_path / "empty.wav"
    _make_wav(wav)

    export_audio(wav)

    sidecar = read_audio_metadata_sidecar(wav)
    assert sidecar["rule_stack"] == []

    ixml = read_ixml(wav)
    assert "rule_stack" not in ixml


def test_export_audio_wav_still_readable(tmp_path: Path) -> None:
    wav = tmp_path / "check.wav"
    _make_wav(wav, frames=SAMPLE_RATE)

    export_audio(
        wav,
        performed_part=PerformedPart(
            score={}, applied_rules=("R1", "R2"), quantities={"R1": 1.0, "R2": 0.5},
        ),
    )

    with wave.open(str(wav), "rb") as handle:
        assert handle.getnchannels() == 1
        assert handle.getframerate() == SAMPLE_RATE
        assert handle.getnframes() == SAMPLE_RATE


def test_export_audio_events_inherit_rule_stack(tmp_path: Path) -> None:
    wav = tmp_path / "events.wav"
    _make_wav(wav)

    performed = PerformedPart(
        score={}, applied_rules=("R5",), quantities={"R5": 0.7},
    )

    export_audio(
        wav,
        performed_part=performed,
        events=[{"event_id": "e1", "pitch": 60}],
    )

    sidecar = read_audio_metadata_sidecar(wav)
    assert sidecar["events"][0]["rule_stack"] == ["R5"]
