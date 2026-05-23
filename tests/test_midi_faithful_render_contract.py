"""Regression tests for faithful-transmission render contracts (T-017d)."""

from __future__ import annotations

import pytest

from cypherclaw.midi_loader import FaithfulMidiEvent
from cypherclaw.midi_scene import FaithfulRenderSettings, build_faithful_midi_scene


def test_faithful_render_preserves_source_pitch_and_rhythm_with_render_metadata() -> None:
    events = (
        FaithfulMidiEvent(pitch=60, duration=91, velocity=100),
        FaithfulMidiEvent(pitch=64, duration=182, velocity=80),
        FaithfulMidiEvent(pitch=67, duration=273, velocity=60),
    )

    scene = build_faithful_midi_scene(
        events,
        ticks_per_beat=91,
        rows_per_beat=4,
        render_settings=FaithfulRenderSettings(
            arc_phase="Divination",
            tonal_center_midi=60,
            tonal_center_hz=261.625565,
            voice_sequence=("choir", "pad", "bowed"),
        ),
    )

    payload = scene.to_dict()
    steps = payload["pattern"]["lanes"][0]["steps"]

    assert payload["pattern"]["rows"] == 24
    assert [step["pitch"] for step in steps] == [60, 64, 67]
    assert [step["duration_ticks"] for step in steps] == [91, 182, 273]
    assert [step["row"] for step in steps] == [0, 4, 12]
    assert [step["length_rows"] for step in steps] == [4, 8, 12]
    assert [step["metadata"]["source_midi_pitch"] for step in steps] == [
        "60",
        "64",
        "67",
    ]
    assert [step["metadata"]["source_duration_ticks"] for step in steps] == [
        "91",
        "182",
        "273",
    ]
    assert [step["metadata"]["faithful_sequence_index"] for step in steps] == [
        "0",
        "1",
        "2",
    ]
    assert [step["render_voice"] for step in steps] == ["choir", "pad", "bowed"]
    assert [step["render_synth"] for step in steps] == [
        "sw_choir",
        "sw_pad",
        "sw_bowed",
    ]
    assert steps[0]["render_pitch_hz"] == pytest.approx(261.625565)
    assert steps[1]["render_pitch_hz"] == pytest.approx(261.625565 * 5 / 4)
    assert steps[2]["render_pitch_hz"] == pytest.approx(261.625565 * 3 / 2)


def test_faithful_render_applies_explicit_tuning_without_rewriting_source_fields() -> None:
    events = (
        FaithfulMidiEvent(pitch=60, duration=100, velocity=96),
        FaithfulMidiEvent(pitch=61, duration=150, velocity=96),
        FaithfulMidiEvent(pitch=62, duration=200, velocity=96),
        FaithfulMidiEvent(pitch=64, duration=250, velocity=96),
    )

    scene = build_faithful_midi_scene(
        events,
        ticks_per_beat=100,
        rows_per_beat=4,
        render_settings=FaithfulRenderSettings(
            arc_phase="Divination",
            tonal_center_midi=60,
            tonal_center_hz=261.625565,
            tuning_system_name="gamelan slendro",
            voice_sequence=("kotekan",),
        ),
    )

    payload = scene.to_dict()
    steps = payload["pattern"]["lanes"][0]["steps"]

    assert payload["metadata"]["tuning_system_name"] == "gamelan_slendro"
    assert payload["metadata"]["arc_phase"] == "Divination"
    assert [step["pitch"] for step in steps] == [60, 61, 62, 64]
    assert [step["duration_ticks"] for step in steps] == [100, 150, 200, 250]
    assert [step["row"] for step in steps] == [0, 4, 10, 18]
    assert [step["length_rows"] for step in steps] == [4, 6, 8, 10]
    assert [step["metadata"]["tuning_system_name"] for step in steps] == [
        "gamelan_slendro",
        "gamelan_slendro",
        "gamelan_slendro",
        "gamelan_slendro",
    ]
    assert steps[0]["render_pitch_hz"] == pytest.approx(261.625565)
    assert steps[1]["render_pitch_hz"] == pytest.approx(261.625565)
    assert steps[2]["render_pitch_hz"] == pytest.approx(
        261.625565 * (2 ** (240.0 / 1200.0))
    )
    assert steps[3]["render_pitch_hz"] == pytest.approx(
        261.625565 * (2 ** (480.0 / 1200.0))
    )


def test_faithful_render_assigns_voice_synth_and_matched_space_sequence() -> None:
    events = tuple(
        FaithfulMidiEvent(pitch=60 + index, duration=120, velocity=90)
        for index in range(8)
    )
    voice_sequence = (
        "pluck",
        "breath",
        "choir",
        "kotekan",
        "pad",
        "bowed",
        "tabla_tin",
        "sw_breath",
    )

    scene = build_faithful_midi_scene(
        events,
        render_settings=FaithfulRenderSettings(
            arc_phase="Listen",
            voice_sequence=voice_sequence,
        ),
    )

    payload = scene.to_dict()
    steps = payload["pattern"]["lanes"][0]["steps"]

    expected_voices = [
        "pluck",
        "breath",
        "choir",
        "kotekan",
        "pad",
        "bowed",
        "tabla_tin",
        "breath",
    ]
    expected_synths = [
        "sw_pluck",
        "sw_breath",
        "sw_choir",
        "sw_kotekan",
        "sw_pad",
        "sw_bowed",
        "sw_tabla_tin",
        "sw_breath",
    ]
    expected_spaces = [
        ("small_wooden_room", 16),
        ("glass_bell_jar", 17),
        ("stone_cathedral", 18),
        ("humid_forest_canopy", 19),
        ("marble_empty_hall", 20),
        ("damp_cave_wall", 21),
        ("dusk_garden", 22),
        ("glass_bell_jar", 17),
    ]

    assert payload["metadata"]["voice_assignment_policy"] == "sequence"
    assert payload["metadata"]["voice_sequence"] == ",".join(voice_sequence)
    assert [step["render_voice"] for step in steps] == expected_voices
    assert [step["render_synth"] for step in steps] == expected_synths
    assert [step["metadata"]["requested_render_voice"] for step in steps] == [
        *voice_sequence[:-1],
        "sw_breath",
    ]
    assert [step["metadata"]["render_voice"] for step in steps] == expected_voices

    for step, expected_voice, (expected_space_id, expected_bus_id) in zip(
        steps,
        expected_voices,
        expected_spaces,
        strict=True,
    ):
        assert step["render_space"]["voice"] == expected_voice
        assert step["render_space"]["space_id"] == expected_space_id
        assert step["render_space"]["fx_bus_id"] == expected_bus_id
        assert step["metadata"]["render_space_id"] == expected_space_id
        assert step["metadata"]["render_fx_bus_id"] == str(expected_bus_id)
        assert step["metadata"]["space_mode"] == "matched"
