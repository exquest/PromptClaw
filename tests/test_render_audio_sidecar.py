"""Tests for exported render-audio JSON sidecars."""
from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools"))

from senseweave.render import (  # noqa: E402
    PerformedPart,
    audio_metadata_sidecar_path,
    read_audio_metadata_sidecar,
    write_audio_metadata_sidecar,
)


def test_write_audio_metadata_sidecar_records_rule_stack_provenance(tmp_path: Path) -> None:
    audio_path = tmp_path / "exports" / "piece.wav"
    audio_path.parent.mkdir()
    audio_path.write_bytes(b"RIFFfake WAVE")
    delta_path = tmp_path / "exports" / "piece.delta.json"
    performed = PerformedPart(
        score={},
        applied_rules=("R1", "R6"),
        quantities={"R1": 1.0, "R2": 0.0, "R6": 0.45},
        metadata={"intent_tags": "withhold"},
    )

    sidecar_path = write_audio_metadata_sidecar(
        audio_path,
        performed_part=performed,
        events=[
            {
                "event_id": "evt-1",
                "phrase_id": "phrase-a",
                "section_id": "intro",
                "pitch": 64,
                "rule_stack": ["R1", "R6"],
                "seed_path": [7, 11],
            }
        ],
        performance_intents={"phrase-a": {"intent_tag": "withhold"}},
        section_envelopes={"intro": {"tempo_base": 112.0}},
        seeds={"root": 7, "microtiming": 11},
        delta_track_path=delta_path,
        extra_metadata={"renderer": "unit-test"},
    )

    assert sidecar_path == audio_path.with_suffix(".meta.json")
    payload = json.loads(sidecar_path.read_text())
    assert payload["schema_version"] == "render-audio-sidecar/v1"
    assert payload["audio_path"] == str(audio_path)
    assert payload["rule_stack"] == ["R1", "R6"]
    assert payload["rule_quantities"] == {"R1": 1.0, "R2": 0.0, "R6": 0.45}
    assert payload["rule_stack_provenance"] == {
        "applied_rules": ["R1", "R6"],
        "quantities": {"R1": 1.0, "R2": 0.0, "R6": 0.45},
        "metadata": {"intent_tags": "withhold"},
    }
    assert payload["events"][0]["rule_stack"] == ["R1", "R6"]
    assert payload["events"][0]["seed_path"] == [7, 11]
    assert payload["performance_intents"] == {"phrase-a": {"intent_tag": "withhold"}}
    assert payload["section_envelopes"] == {"intro": {"tempo_base": 112.0}}
    assert payload["seeds"] == {"microtiming": 11, "root": 7}
    assert payload["delta_track_path"] == str(delta_path)
    assert payload["metadata"] == {"renderer": "unit-test"}


def test_sidecar_writer_falls_back_to_render_pass_rule_stack_for_events(tmp_path: Path) -> None:
    @dataclass(frozen=True)
    class BareEvent:
        event_id: str
        seed_path: tuple[int, ...]

    audio_path = tmp_path / "take.wav"
    audio_path.write_bytes(b"RIFFfake WAVE")

    write_audio_metadata_sidecar(
        audio_path,
        rule_stack=("R3", "R4"),
        rule_quantities={"R3": 0.8, "R4": 1.0},
        events=[BareEvent(event_id="evt-bare", seed_path=(3, 4))],
    )

    payload = read_audio_metadata_sidecar(audio_path)
    assert payload["events"] == [
        {
            "event_id": "evt-bare",
            "seed_path": [3, 4],
            "rule_stack": ["R3", "R4"],
        }
    ]
    assert payload["rule_stack"] == ["R3", "R4"]


def test_audio_metadata_sidecar_path_replaces_audio_suffix() -> None:
    assert audio_metadata_sidecar_path("render.wav") == Path("render.meta.json")
    assert audio_metadata_sidecar_path("render") == Path("render.meta.json")
