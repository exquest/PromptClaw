"""Tests for deterministic SenseWeave render replay."""
from __future__ import annotations

import hashlib
import json
import os
import sys
import wave
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools"))

from cypherclaw.render.events import Event  # noqa: E402
from senseweave.render import (  # noqa: E402
    PerformedPart,
    audio_delta_track_path,
    export_audio,
    read_audio_metadata_sidecar,
    replay,
)

SAMPLE_RATE = 16000


def _make_wav(path: Path, *, frames: int = 1600) -> None:
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(SAMPLE_RATE)
        handle.writeframes(b"\x00\x00" * frames)


def _score_events() -> list[Event]:
    return [
        Event(
            event_id="evt-1",
            phrase_id="phrase-a",
            section_id="intro",
            voice_id="lead",
            role="melody",
            pitch=64,
            nominal_beat=0.0,
            nominal_dur_beats=1.0,
            intent_tag="build",
        ),
        Event(
            event_id="evt-2",
            phrase_id="phrase-a",
            section_id="intro",
            voice_id="lead",
            role="melody",
            pitch=67,
            nominal_beat=1.0,
            nominal_dur_beats=0.5,
            intent_tag="build",
        ),
    ]


def _delta_track() -> list[dict[str, Any]]:
    return [
        {
            "event_id": "evt-1",
            "onset_sec": 0.012,
            "dur_sec": 0.73125,
            "velocity": 0.82,
            "timing_deviation_ms": 3.2,
            "articulation": "legato",
            "sensor_tempo_scale": 1.03,
            "sensor_amp_scale": 0.94,
            "sensor_brightness": 0.2,
            "rule_stack": ["R7", "R8"],
            "seed_path": [17, 1],
        },
        {
            "event_id": "evt-2",
            "onset_sec": 0.498,
            "dur_sec": 0.205,
            "velocity": 0.58,
            "timing_deviation_ms": -1.4,
            "articulation": "staccato",
            "sensor_tempo_scale": 0.99,
            "sensor_amp_scale": 1.07,
            "sensor_brightness": -0.15,
            "rule_stack": ["R7", "R8"],
            "seed_path": [17, 2],
        },
    ]


def _event_sequence_hash(events: Sequence[Any]) -> str:
    payload = [
        event.to_json_dict() if isinstance(event, Event) else event
        for event in events
    ]
    encoded = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    return hashlib.sha256(encoded).hexdigest()


def _score_payload(events: Sequence[Event]) -> dict[str, list[dict[str, Any]]]:
    payload: list[dict[str, Any]] = []
    for event in events:
        event_payload = event.to_json_dict()
        if not event_payload.get("event_id"):
            raise ValueError("score event payloads must include event_id")
        payload.append(event_payload)
    return {"events": payload}


def _performed_part_diagnostic(performed_part: PerformedPart) -> dict[str, Any]:
    event_payloads: list[dict[str, Any]] = []
    for event in performed_part.score:
        if isinstance(event, Event):
            event_payloads.append(event.to_json_dict())
        elif isinstance(event, Mapping):
            event_payloads.append(dict(event))
        else:
            event_payloads.append({"value": str(event)})
    return {
        "applied_rules": list(performed_part.applied_rules),
        "event_hash": _event_sequence_hash(performed_part.score),
        "events": event_payloads,
        "metadata": dict(performed_part.metadata),
    }


def test_replay_reproduces_identical_event_sequence_hash() -> None:
    seeds = {"composition_seed": 17, "interpretation_seed": 23}
    score = _score_events()
    deltas = _delta_track()

    original = replay(score, seeds, deltas)
    rerendered = replay(score, seeds, deltas)

    assert _event_sequence_hash(rerendered.score) == _event_sequence_hash(original.score)
    first, second = rerendered.score
    assert first.timing_deviation_ms == 3.2
    assert first.velocity == 0.82
    assert first.articulation == "legato"
    assert second.timing_deviation_ms == -1.4
    assert second.velocity == 0.58
    assert second.articulation == "staccato"
    assert rerendered.applied_rules == ("R7", "R8")


def test_export_audio_persists_delta_track_for_replay(tmp_path: Path) -> None:
    wav = tmp_path / "piece.wav"
    _make_wav(wav)
    seeds = {"composition_seed": 17, "interpretation_seed": 23}
    score = _score_events()
    deltas = _delta_track()
    original = replay(score, seeds, deltas)

    export_audio(
        wav,
        performed_part=PerformedPart(
            score=original.score,
            applied_rules=original.applied_rules,
            quantities={},
        ),
        events=original.score,
        seeds=seeds,
        delta_track=deltas,
    )

    expected_delta_path = audio_delta_track_path(wav)
    sidecar = read_audio_metadata_sidecar(wav)
    assert sidecar["delta_track_path"] == str(expected_delta_path)
    assert json.loads(expected_delta_path.read_text()) == deltas

    replayed = replay(score, seeds, expected_delta_path)
    assert _event_sequence_hash(replayed.score) == _event_sequence_hash(original.score)


class RenderReplayEndToEndTests:
    """End-to-end deterministic replay lifecycle across the public surface."""

    __test__ = True

    def test_mapping_score_sidecar_delta_audio_export_and_diagnostics_round_trip(
        self,
        tmp_path: Path,
    ) -> None:
        wav = tmp_path / "render-replay.wav"
        _make_wav(wav)
        seeds = {"composition_seed": 101, "interpretation_seed": 202}
        score_events = _score_events()
        score_payload = _score_payload(score_events)
        delta_entries = [
            {
                "event_id": "evt-1",
                "pitch": 999,
                "role": "perc",
                "nominal_beat": 99.0,
                "onset_sec": 0.125,
                "dur_sec": 0.875,
                "velocity": 0.77,
                "timing_deviation_ms": 4.5,
                "articulation": "tenuto",
                "sensor_tempo_scale": 1.04,
                "sensor_amp_scale": 0.91,
                "sensor_brightness": 0.35,
                "rule_stack": ["R7", "R8", "R7"],
                "seed_path": [101, 1],
                "metadata": {"capture": "sidecar", "take": 1},
            },
            {
                "event_id": "evt-2",
                "pitch": 1001,
                "role": "ostinato",
                "nominal_beat": 100.0,
                "onset_sec": 0.512,
                "dur_sec": 0.375,
                "velocity": 0.61,
                "timing_deviation_ms": -2.25,
                "articulation": "marcato",
                "sensor_tempo_scale": 0.97,
                "sensor_amp_scale": 1.08,
                "sensor_brightness": -0.2,
                "rule_stack": ["R8", "R12"],
                "seed_path": [101, 2],
                "metadata": {"capture": "sidecar", "take": 1},
            },
        ]
        delta_sidecar = {
            "schema_version": "render-audio-sidecar/v1",
            "events": delta_entries,
        }

        rendered = replay(score_payload, seeds, delta_sidecar)

        assert isinstance(rendered, PerformedPart)
        assert rendered.applied_rules == ("R7", "R8", "R12")
        assert rendered.metadata == {
            "composition_seed": "101",
            "interpretation_seed": "202",
        }
        assert all(isinstance(event, Event) for event in rendered.score)
        assert all(event.score_fields_locked for event in rendered.score)

        first, second = rendered.score
        assert first.event_id == "evt-1"
        assert first.pitch == 64
        assert first.role == "melody"
        assert first.nominal_beat == 0.0
        assert first.onset_sec == 0.125
        assert first.dur_sec == 0.875
        assert first.velocity == 0.77
        assert first.timing_deviation_ms == 4.5
        assert first.articulation == "tenuto"
        assert first.sensor_tempo_scale == 1.04
        assert first.sensor_amp_scale == 0.91
        assert first.sensor_brightness == 0.35
        assert first.rule_stack == ["R7", "R8", "R7"]
        assert first.seed_path == (101, 1)
        assert first.metadata == {"capture": "sidecar", "take": "1"}

        assert second.event_id == "evt-2"
        assert second.pitch == 67
        assert second.role == "melody"
        assert second.nominal_beat == 1.0
        assert second.onset_sec == 0.512
        assert second.dur_sec == 0.375
        assert second.velocity == 0.61
        assert second.timing_deviation_ms == -2.25
        assert second.articulation == "marcato"
        assert second.sensor_tempo_scale == 0.97
        assert second.sensor_amp_scale == 1.08
        assert second.sensor_brightness == -0.2
        assert second.rule_stack == ["R8", "R12"]
        assert second.seed_path == (101, 2)

        diagnostic = _performed_part_diagnostic(rendered)
        diagnostic_round_trip = json.loads(json.dumps(diagnostic, sort_keys=True))
        assert diagnostic_round_trip["applied_rules"] == ["R7", "R8", "R12"]
        assert diagnostic_round_trip["metadata"]["composition_seed"] == "101"
        assert [event["event_id"] for event in diagnostic_round_trip["events"]] == [
            "evt-1",
            "evt-2",
        ]

        export_audio(
            wav,
            performed_part=rendered,
            events=rendered.score,
            seeds=seeds,
            delta_track=delta_entries,
            extra_metadata={"diagnostic": "render-replay-e2e"},
        )

        expected_delta_path = audio_delta_track_path(wav)
        sidecar = read_audio_metadata_sidecar(wav)
        assert sidecar["schema_version"] == "render-audio-sidecar/v1"
        assert sidecar["rule_stack"] == ["R7", "R8", "R12"]
        assert sidecar["delta_track_path"] == str(expected_delta_path)
        assert sidecar["metadata"] == {"diagnostic": "render-replay-e2e"}
        assert [event["event_id"] for event in sidecar["events"]] == [
            "evt-1",
            "evt-2",
        ]
        assert json.loads(expected_delta_path.read_text(encoding="utf-8")) == delta_entries

        replayed_from_path = replay(score_payload, seeds, expected_delta_path)
        assert _event_sequence_hash(replayed_from_path.score) == diagnostic["event_hash"]
