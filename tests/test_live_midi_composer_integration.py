"""Tests for T-053c composer publishing into the live MIDI emitter queue."""

from __future__ import annotations

import importlib
import re
import sys
import types
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from cypherclaw import live_midi_emitter as midi


REPO_ROOT = Path(__file__).resolve().parent.parent
TOOLS_DIR = REPO_ROOT / "my-claw" / "tools"
DUET_COMPOSER_PATH = TOOLS_DIR / "duet_composer.py"

if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))


class _FakeOsc:
    def __init__(self) -> None:
        self.messages: list[tuple[str, list[Any]]] = []

    def send_message(self, address: str, args: list[Any]) -> None:
        self.messages.append((address, args))


class _FakePublisher:
    def __init__(self) -> None:
        self.events: list[midi.LiveMidiEvent] = []

    def publish(self, event: midi.LiveMidiEvent) -> tuple[midi.LiveMidiEvent, ...]:
        self.events.append(event)
        return ()


def _load_duet_composer(monkeypatch: pytest.MonkeyPatch) -> Any:
    pythonosc = types.ModuleType("pythonosc")
    udp_client = types.ModuleType("pythonosc.udp_client")

    class SimpleUDPClient:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            self.messages: list[tuple[str, list[Any]]] = []

        def send_message(self, address: str, args: list[Any]) -> None:
            self.messages.append((address, args))

    udp_client.SimpleUDPClient = SimpleUDPClient
    pythonosc.udp_client = udp_client
    monkeypatch.setitem(sys.modules, "pythonosc", pythonosc)
    monkeypatch.setitem(sys.modules, "pythonosc.udp_client", udp_client)
    monkeypatch.delitem(sys.modules, "duet_composer", raising=False)
    return importlib.import_module("duet_composer")


def test_play_voice_publishes_note_events_with_scene_and_tuning_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    duet_composer = _load_duet_composer(monkeypatch)
    publisher = _FakePublisher()
    osc = _FakeOsc()
    monkeypatch.setattr(duet_composer, "_live_midi_publisher", publisher)
    monkeypatch.setattr(duet_composer, "c", osc)
    monkeypatch.setattr(duet_composer, "next_nid", lambda: 60123)
    monkeypatch.setattr(duet_composer.time, "time", lambda: 1000.0)

    duet_composer.play_voice(
        "pluck",
        261.625565,
        0.12,
        0.5,
        role="melody",
        scene="Theme",
        tuning="just_intonation_5_limit",
        live_midi_metadata={"row": 4, "lane_name": "lead"},
    )

    assert [event.event_type for event in publisher.events] == [
        midi.MIDI_EVENT_NOTE_ON,
        midi.MIDI_EVENT_NOTE_OFF,
    ]
    note_on, note_off = publisher.events
    assert note_on.data1 == 60
    assert note_on.data2 == 64
    assert note_on.voice == "pluck"
    assert note_on.scene == "Theme"
    assert note_on.tuning == "just_intonation_5_limit"
    assert note_on.metadata == {
        "duration_seconds": 0.5,
        "frequency_hz": 261.626,
        "lane_name": "lead",
        "role": "melody",
        "row": 4,
    }
    assert note_off.data1 == 60
    assert note_off.data2 == 0
    assert note_off.voice == "pluck"
    assert note_off.scene == "Theme"
    assert note_off.tuning == "just_intonation_5_limit"
    assert note_off.ts == pytest.approx(1000.5)
    assert osc.messages[0][0] == "/s_new"


def test_tracker_row_automation_publishes_control_changes_with_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    duet_composer = _load_duet_composer(monkeypatch)
    publisher = _FakePublisher()
    monkeypatch.setattr(duet_composer, "_live_midi_publisher", publisher)
    monkeypatch.setattr(duet_composer.time, "time", lambda: 2000.0)
    scene = SimpleNamespace(
        name="Bridge",
        metadata={"tuning_system_name": "gamelan_slendro"},
    )
    state = {
        "automation": {
            "density": 0.5,
            "master_amp": 1.2,
            "reverb_send": -0.1,
        }
    }

    duet_composer._publish_live_midi_controls_for_tracker_row(scene, 16, state)

    assert [
        (event.event_type, event.data1, event.data2)
        for event in publisher.events
    ] == [
        (midi.MIDI_EVENT_CONTROL_CHANGE, 20, 64),
        (midi.MIDI_EVENT_CONTROL_CHANGE, 7, 127),
        (midi.MIDI_EVENT_CONTROL_CHANGE, 91, 0),
    ]
    assert {event.voice for event in publisher.events} == {"master"}
    assert {event.scene for event in publisher.events} == {"Bridge"}
    assert {event.tuning for event in publisher.events} == {"gamelan_slendro"}
    assert publisher.events[0].metadata == {
        "control_name": "density",
        "control_scope": "scene_automation",
        "raw_value": 0.5,
        "row": 16,
    }


def test_tracker_playback_wires_scene_tuning_context_to_play_voice() -> None:
    source = DUET_COMPOSER_PATH.read_text(encoding="utf-8")
    play_match = re.search(
        r"def _play_tracker_event\(event: ScheduledTrackerEvent\) -> None:"
        r"[\s\S]*?def _on_scene_start",
        source,
    )
    row_match = re.search(
        r"def _on_tracker_row\(scene, row: int, state: dict\) -> None:"
        r"[\s\S]*?result = schedule_song",
        source,
    )

    assert play_match, "could not locate _play_tracker_event block"
    assert row_match, "could not locate _on_tracker_row block"
    play_block = play_match.group(0)
    row_block = row_match.group(0)

    assert "scene=event.scene_name" in play_block
    assert "tuning=_tuning_context_from_scene_metadata(event.scene_metadata)" in play_block
    assert "live_midi_metadata=" in play_block
    assert "_publish_live_midi_controls_for_tracker_row(scene, row, state)" in row_block
