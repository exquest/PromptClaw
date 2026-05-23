"""Tests for faithful MIDI scene mapping (T-017b)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from cypherclaw import composer_vocabulary_bridge
from cypherclaw import midi_intake_daemon as intake
from cypherclaw.midi_loader import FaithfulMidiEvent
from cypherclaw.midi_scene import (
    FaithfulRenderSettings,
    MoodMode,
    REQUIRED_MOOD_METADATA_FIELDS,
    REQUIRED_TUNING_METADATA_FIELDS,
    SUPPORTED_MOOD_MODES,
    SUPPORTED_MORPH_CURVES,
    build_faithful_midi_scene,
    parse_mood_mode,
    validate_faithful_scene_metadata,
)
from cypherclaw.space_reverb import VOICE_REVERB_PROFILES


def _varlen(value: int) -> bytes:
    if value < 0:
        raise ValueError("varlen value must be non-negative")
    parts = [value & 0x7F]
    value >>= 7
    while value:
        parts.insert(0, 0x80 | (value & 0x7F))
        value >>= 7
    return bytes(parts)


def _note_on(channel: int, note: int, velocity: int = 96) -> bytes:
    return bytes([0x90 | channel, note, velocity])


def _note_off(channel: int, note: int) -> bytes:
    return bytes([0x80 | channel, note, 0])


def _track_chunk(events: list[tuple[int, bytes]]) -> bytes:
    track = bytearray()
    last_tick = 0
    ordered = sorted(enumerate(events), key=lambda item: (item[1][0], item[0]))
    for _index, (tick, message) in ordered:
        track.extend(_varlen(tick - last_tick))
        track.extend(message)
        last_tick = tick
    track.extend(_varlen(0))
    track.extend(b"\xff\x2f\x00")
    return b"MTrk" + len(track).to_bytes(4, "big") + bytes(track)


def _write_midi(
    path: Path,
    tracks: list[list[tuple[int, bytes]]],
    *,
    division: int = 96,
) -> None:
    header = (
        intake.MIDI_HEADER_MAGIC
        + (6).to_bytes(4, "big")
        + (1 if len(tracks) > 1 else 0).to_bytes(2, "big")
        + len(tracks).to_bytes(2, "big")
        + division.to_bytes(2, "big")
    )
    path.write_bytes(header + b"".join(_track_chunk(track) for track in tracks))


def _assert_no_vocabulary_metadata(payload: object) -> None:
    if isinstance(payload, dict):
        for key, value in payload.items():
            assert not str(key).startswith("vocabulary_")
            _assert_no_vocabulary_metadata(value)
    elif isinstance(payload, list):
        for value in payload:
            _assert_no_vocabulary_metadata(value)


def test_build_faithful_midi_scene_preserves_pitch_sequence_and_rhythm() -> None:
    events = (
        FaithfulMidiEvent(pitch=60, duration=120, velocity=96),
        FaithfulMidiEvent(pitch=64, duration=240, velocity=64),
        FaithfulMidiEvent(pitch=67, duration=120, velocity=127),
    )

    scene = build_faithful_midi_scene(
        events,
        name="Imported Line",
        source_name="line.mid",
        ticks_per_beat=120,
        rows_per_beat=4,
        key="D:dorian",
        tempo_bpm=108.0,
    )
    payload = scene.to_dict()

    assert payload["name"] == "Imported Line"
    assert payload["key"] == "D:dorian"
    assert payload["tempo_bpm"] == 108.0
    assert payload["rows_per_beat"] == 4
    assert payload["metadata"]["mode"] == "faithful_transmission"
    assert payload["metadata"]["source_transform"] == "midi_whole_file_scene"
    assert payload["metadata"]["source_name"] == "line.mid"
    assert payload["metadata"]["source_event_count"] == "3"
    assert payload["metadata"]["source_duration_ticks"] == "480"
    assert payload["pattern"]["rows"] == 16
    assert payload["constraints"] == {
        "max_polyphony": 1,
        "allowed_roles": ["melody"],
    }

    lane = payload["pattern"]["lanes"][0]
    assert lane["name"] == "faithful_midi"
    assert lane["role"] == "melody"
    assert lane["voice"] == "pluck"
    steps = lane["steps"]
    assert [step["pitch"] for step in steps] == [60, 64, 67]
    assert [step["duration_ticks"] for step in steps] == [120, 240, 120]
    assert [step["row"] for step in steps] == [0, 4, 12]
    assert [step["length_rows"] for step in steps] == [4, 8, 4]
    assert [step["metadata"]["faithful_sequence_index"] for step in steps] == [
        "0",
        "1",
        "2",
    ]
    assert steps[0]["velocity"] == pytest.approx(96 / 127)
    assert steps[1]["velocity"] == pytest.approx(64 / 127)
    assert steps[2]["velocity"] == pytest.approx(1.0)
    _assert_no_vocabulary_metadata(payload)


def test_build_faithful_midi_scene_handles_empty_events_and_bad_timing() -> None:
    scene = build_faithful_midi_scene(
        (),
        source_name="empty.mid",
        ticks_per_beat=0,
        rows_per_beat=0,
    )
    payload = scene.to_dict()

    assert payload["rows_per_beat"] == 1
    assert payload["pattern"]["rows"] == 0
    assert payload["pattern"]["lanes"] == [
        {
            "name": "faithful_midi",
            "role": "melody",
            "voice": "pluck",
            "steps": [],
            "metadata": {"lane_source": "faithful_midi"},
        }
    ]
    assert payload["metadata"]["source_name"] == "empty.mid"
    assert payload["metadata"]["source_event_count"] == "0"
    assert payload["metadata"]["source_duration_ticks"] == "0"
    _assert_no_vocabulary_metadata(payload)


def test_process_midi_file_faithful_mode_writes_scene_without_fragment_selection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / "faithful.mid"
    _write_midi(
        target,
        [
            [
                (0, _note_on(0, 60, 96)),
                (96, _note_off(0, 60)),
                (96, _note_on(0, 62, 48)),
                (288, _note_off(0, 62)),
            ],
        ],
        division=96,
    )

    def fail_extract(_path: Path | str) -> dict[str, object]:
        raise AssertionError("faithful mode must bypass fragment extraction")

    def fail_fragment_selection(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("faithful mode must bypass fragment selection")

    monkeypatch.setattr(intake, "extract_midi_fragments", fail_extract)
    monkeypatch.setattr(
        composer_vocabulary_bridge,
        "plan_vocabulary_citations",
        fail_fragment_selection,
    )

    event = intake.process_midi_file(target, faithful_transmission=True)

    manifest_path = Path(str(event["destination"])).with_suffix(".mid.json")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    scene = manifest["faithful_scene"]
    steps = scene["pattern"]["lanes"][0]["steps"]

    assert manifest["mode"] == "faithful_transmission"
    assert manifest["faithful_events"] == [
        {"pitch": 60, "duration": 96, "velocity": 96},
        {"pitch": 62, "duration": 192, "velocity": 48},
    ]
    assert manifest["fragments"] == intake.empty_midi_fragments()
    assert scene["metadata"]["source_name"] == "faithful.mid"
    assert scene["metadata"]["source_event_count"] == "2"
    assert scene["metadata"]["source_duration_ticks"] == "288"
    assert [step["pitch"] for step in steps] == [60, 62]
    assert [step["duration_ticks"] for step in steps] == [96, 192]
    assert [step["row"] for step in steps] == [0, 4]
    assert [step["length_rows"] for step in steps] == [4, 8]
    _assert_no_vocabulary_metadata(scene)


def test_process_midi_file_default_mode_omits_faithful_scene(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / "fragments.mid"
    _write_midi(
        target,
        [
            [
                (0, _note_on(0, 60, 96)),
                (96, _note_off(0, 60)),
            ],
        ],
    )
    fragments = {
        "melodic_motifs": [{"notes": [60]}],
        "rhythm_cells": [],
        "chord_progressions": [],
        "groove_patterns": [],
    }

    monkeypatch.setattr(intake, "extract_midi_fragments", lambda _path: fragments)

    event = intake.process_midi_file(target)

    manifest_path = Path(str(event["destination"])).with_suffix(".mid.json")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["mode"] == "fragment_extraction"
    assert manifest["fragments"] == fragments
    assert "faithful_events" not in manifest
    assert "faithful_scene" not in manifest


def test_build_faithful_midi_scene_applies_cypherclaw_render_settings() -> None:
    events = (
        FaithfulMidiEvent(pitch=60, duration=120, velocity=96),
        FaithfulMidiEvent(pitch=64, duration=240, velocity=64),
        FaithfulMidiEvent(pitch=67, duration=120, velocity=127),
    )
    render_settings = FaithfulRenderSettings(
        arc_phase="Divination",
        tonal_center_midi=60,
        tonal_center_hz=261.625565,
        voice_sequence=("pluck", "bowed", "breath"),
    )

    scene = build_faithful_midi_scene(
        events,
        ticks_per_beat=120,
        rows_per_beat=4,
        render_settings=render_settings,
    )
    payload = scene.to_dict()
    steps = payload["pattern"]["lanes"][0]["steps"]

    assert payload["metadata"]["tuning_system_name"] == "just_intonation_5_limit"
    assert payload["metadata"]["arc_phase"] == "Divination"
    assert payload["metadata"]["voice_assignment_policy"] == "sequence"
    assert payload["metadata"]["voice_sequence"] == "pluck,bowed,breath"
    assert payload["metadata"]["space_mode"] == "matched"
    assert [step["pitch"] for step in steps] == [60, 64, 67]
    assert [step["duration_ticks"] for step in steps] == [120, 240, 120]
    assert [step["row"] for step in steps] == [0, 4, 12]
    assert [step["length_rows"] for step in steps] == [4, 8, 4]
    assert [step["render_voice"] for step in steps] == ["pluck", "bowed", "breath"]
    assert [step["render_synth"] for step in steps] == [
        "sw_pluck",
        "sw_bowed",
        "sw_breath",
    ]
    assert steps[0]["render_pitch_hz"] == pytest.approx(261.625565)
    assert steps[1]["render_pitch_hz"] == pytest.approx(327.03195625)
    assert steps[2]["render_pitch_hz"] == pytest.approx(392.4383475)
    assert steps[0]["render_space"]["space_id"] == "small_wooden_room"
    assert steps[0]["render_space"]["fx_bus_id"] == 16
    assert steps[1]["render_space"]["space_id"] == "damp_cave_wall"
    assert steps[1]["render_space"]["fx_bus_id"] == 21
    assert steps[2]["render_space"]["space_id"] == "glass_bell_jar"
    assert steps[2]["render_space"]["fx_bus_id"] == 17


def test_build_faithful_midi_scene_selects_slendro_for_motion_phase() -> None:
    events = (
        FaithfulMidiEvent(pitch=60, duration=96, velocity=90),
        FaithfulMidiEvent(pitch=62, duration=192, velocity=90),
        FaithfulMidiEvent(pitch=64, duration=96, velocity=90),
    )

    scene = build_faithful_midi_scene(
        events,
        ticks_per_beat=96,
        rows_per_beat=4,
        render_settings=FaithfulRenderSettings(
            arc_phase="Conversation",
            tonal_center_midi=60,
            tonal_center_hz=261.625565,
            voice_sequence=("kotekan",),
        ),
    )
    payload = scene.to_dict()
    steps = payload["pattern"]["lanes"][0]["steps"]

    assert payload["metadata"]["tuning_system_name"] == "gamelan_slendro"
    assert [step["pitch"] for step in steps] == [60, 62, 64]
    assert [step["duration_ticks"] for step in steps] == [96, 192, 96]
    assert [step["render_voice"] for step in steps] == [
        "kotekan",
        "kotekan",
        "kotekan",
    ]
    assert [step["render_space"]["space_id"] for step in steps] == [
        "humid_forest_canopy",
        "humid_forest_canopy",
        "humid_forest_canopy",
    ]
    assert steps[0]["render_pitch_hz"] == pytest.approx(261.625565)
    assert steps[1]["render_pitch_hz"] == pytest.approx(
        261.625565 * (2 ** (240.0 / 1200.0))
    )
    assert steps[2]["render_pitch_hz"] == pytest.approx(
        261.625565 * (2 ** (480.0 / 1200.0))
    )


def test_build_faithful_midi_scene_safely_falls_back_for_unknown_render_settings() -> None:
    render_settings = FaithfulRenderSettings(
        arc_phase="Unknown",
        tonal_center_midi=60,
        tonal_center_hz=-1.0,
        voice_sequence=("swamp_harp",),
    )
    scene = build_faithful_midi_scene(
        (FaithfulMidiEvent(pitch=69, duration=120, velocity=88),),
        render_settings=render_settings,
    )
    payload = scene.to_dict()
    step = payload["pattern"]["lanes"][0]["steps"][0]

    assert payload["metadata"]["tuning_system_name"] == "twelve_tet"
    assert step["pitch"] == 69
    assert step["duration_ticks"] == 120
    assert step["render_voice"] == "pluck"
    assert step["metadata"]["requested_render_voice"] == "swamp_harp"
    assert step["render_synth"] == "sw_pluck"
    assert step["render_space"]["space_id"] == "small_wooden_room"
    assert step["render_pitch_hz"] == pytest.approx(440.0)

    empty_scene = build_faithful_midi_scene((), render_settings=render_settings)
    empty_payload = empty_scene.to_dict()
    assert empty_payload["pattern"]["rows"] == 0
    assert empty_payload["pattern"]["lanes"][0]["steps"] == []
    assert empty_payload["metadata"]["source_event_count"] == "0"
    assert empty_payload["metadata"]["tuning_system_name"] == "twelve_tet"


def test_process_midi_file_faithful_manifest_includes_cypherclaw_render_settings(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / "rendered-faithful.mid"
    _write_midi(
        target,
        [
            [
                (0, _note_on(0, 60, 96)),
                (96, _note_off(0, 60)),
            ],
        ],
        division=96,
    )

    def fail_extract(_path: Path | str) -> dict[str, object]:
        raise AssertionError("faithful mode must bypass fragment extraction")

    monkeypatch.setattr(intake, "extract_midi_fragments", fail_extract)

    event = intake.process_midi_file(target, faithful_transmission=True)

    manifest_path = Path(str(event["destination"])).with_suffix(".mid.json")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    scene = manifest["faithful_scene"]
    step = scene["pattern"]["lanes"][0]["steps"][0]

    assert manifest["mode"] == "faithful_transmission"
    assert manifest["faithful_events"] == [
        {"pitch": 60, "duration": 96, "velocity": 96},
    ]
    assert manifest["fragments"] == intake.empty_midi_fragments()
    assert scene["metadata"]["tuning_system_name"] == "just_intonation_5_limit"
    assert scene["metadata"]["arc_phase"] == "Listen"
    assert scene["metadata"]["space_mode"] == "matched"
    assert step["pitch"] == 60
    assert step["duration_ticks"] == 96
    assert step["render_pitch_hz"] == pytest.approx(261.625565)
    assert step["render_voice"] == "pluck"
    assert step["render_synth"] == "sw_pluck"
    assert step["render_space"]["space_id"] == "small_wooden_room"
    assert step["render_space"]["fx_bus_id"] == 16
    _assert_no_vocabulary_metadata(scene)


def test_scene_metadata_carries_tuning_morph_fields_and_validates() -> None:
    events = (FaithfulMidiEvent(pitch=60, duration=96, velocity=96),)
    scene = build_faithful_midi_scene(
        events,
        render_settings=FaithfulRenderSettings(
            arc_phase="Divination",
            tuning_system_name="just_intonation_5_limit",
            tuning_morph_target_name="gamelan_slendro",
            tuning_morph_curve="ease-in",
        ),
    )
    payload = scene.to_dict()
    metadata = payload["metadata"]

    for field_name in REQUIRED_TUNING_METADATA_FIELDS:
        assert field_name in metadata, field_name
    assert metadata["tuning_system_name"] == "just_intonation_5_limit"
    assert metadata["tuning_morph_target_name"] == "gamelan_slendro"
    assert metadata["tuning_morph_curve"] == "ease_in"

    # Sample scene JSON serialization preserves all three fields.
    reloaded = json.loads(json.dumps(payload))
    for field_name in REQUIRED_TUNING_METADATA_FIELDS:
        assert field_name in reloaded["metadata"]

    validate_faithful_scene_metadata(reloaded["metadata"])


def test_scene_metadata_defaults_to_empty_morph_target_and_linear_curve() -> None:
    scene = build_faithful_midi_scene(
        (FaithfulMidiEvent(pitch=60, duration=96, velocity=96),),
    )
    metadata = scene.to_dict()["metadata"]

    assert metadata["tuning_morph_target_name"] == ""
    assert metadata["tuning_morph_curve"] == "linear"
    validate_faithful_scene_metadata(metadata)


def test_scene_metadata_defaults_to_matched_mood_mode_and_validates() -> None:
    scene = build_faithful_midi_scene(
        (FaithfulMidiEvent(pitch=60, duration=96, velocity=96),),
    )

    payload = scene.to_dict()
    reloaded = json.loads(json.dumps(payload))
    metadata = reloaded["metadata"]
    step_metadata = reloaded["pattern"]["lanes"][0]["steps"][0]["metadata"]

    assert metadata["mood_mode"] == "matched"
    assert step_metadata["mood_mode"] == "matched"
    validate_faithful_scene_metadata(metadata)


def test_mood_mode_parser_accepts_enum_values_aliases_and_fallback() -> None:
    assert set(SUPPORTED_MOOD_MODES) == {
        "matched",
        "expressive",
        "house-bound",
    }
    assert parse_mood_mode(MoodMode.MATCHED) is MoodMode.MATCHED
    assert parse_mood_mode("expressive") is MoodMode.EXPRESSIVE
    assert parse_mood_mode("house-bound") is MoodMode.HOUSE_BOUND
    assert parse_mood_mode("house_bound") is MoodMode.HOUSE_BOUND
    assert parse_mood_mode("house bound") is MoodMode.HOUSE_BOUND
    assert parse_mood_mode("unknown") is MoodMode.MATCHED
    assert parse_mood_mode("") is MoodMode.MATCHED
    assert parse_mood_mode(None) is MoodMode.MATCHED


@pytest.mark.parametrize(
    ("requested", "expected"),
    (
        (MoodMode.EXPRESSIVE, "expressive"),
        ("house_bound", "house-bound"),
    ),
)
def test_scene_metadata_round_trips_explicit_mood_modes(
    requested: MoodMode | str,
    expected: str,
) -> None:
    scene = build_faithful_midi_scene(
        (FaithfulMidiEvent(pitch=60, duration=96, velocity=96),),
        render_settings=FaithfulRenderSettings(mood_mode=requested),
    )

    reloaded = json.loads(json.dumps(scene.to_dict()))
    metadata = reloaded["metadata"]
    step_metadata = reloaded["pattern"]["lanes"][0]["steps"][0]["metadata"]

    assert metadata["mood_mode"] == expected
    assert step_metadata["mood_mode"] == expected
    validate_faithful_scene_metadata(metadata)


def test_faithful_scene_render_space_follows_mood_mode_resolver() -> None:
    events = (
        FaithfulMidiEvent(pitch=60, duration=96, velocity=96),
        FaithfulMidiEvent(pitch=62, duration=96, velocity=88),
        FaithfulMidiEvent(pitch=64, duration=96, velocity=80),
    )
    voice_sequence = ("pluck", "breath", "choir")
    cases = (
        (
            "matched",
            ("pluck", "breath", "choir"),
        ),
        (
            "expressive",
            ("kotekan", "pad", "bowed"),
        ),
        (
            "house-bound",
            ("tabla_tin", "tabla_tin", "tabla_tin"),
        ),
    )

    for mood_mode, expected_space_voices in cases:
        scene = build_faithful_midi_scene(
            events,
            render_settings=FaithfulRenderSettings(
                mood_mode=mood_mode,
                active_house="house_garden",
                voice_sequence=voice_sequence,
            ),
        )
        payload = scene.to_dict()
        steps = payload["pattern"]["lanes"][0]["steps"]

        assert payload["metadata"]["mood_mode"] == mood_mode
        assert payload["metadata"]["active_house"] == "house_garden"
        assert [step["render_voice"] for step in steps] == list(voice_sequence)

        for step, expected_space_voice in zip(
            steps,
            expected_space_voices,
            strict=True,
        ):
            profile = VOICE_REVERB_PROFILES[expected_space_voice]

            assert step["render_space"]["voice"] == expected_space_voice
            assert step["render_space"]["space_id"] == profile.space_id
            assert step["render_space"]["fx_bus_id"] == profile.fx_bus_id
            assert step["metadata"]["render_space_voice"] == expected_space_voice
            assert step["metadata"]["render_space_id"] == profile.space_id
            assert step["metadata"]["render_fx_bus_id"] == str(profile.fx_bus_id)
            assert step["metadata"]["mood_mode"] == mood_mode
            assert step["metadata"]["active_house"] == "house_garden"


def test_validate_faithful_scene_metadata_rejects_missing_and_bad_curve() -> None:
    base = {
        "tuning_system_name": "twelve_tet",
        "tuning_morph_target_name": "",
        "tuning_morph_curve": "linear",
        "mood_mode": "matched",
    }
    validate_faithful_scene_metadata(base)
    for missing in REQUIRED_TUNING_METADATA_FIELDS:
        broken = {k: v for k, v in base.items() if k != missing}
        with pytest.raises(ValueError):
            validate_faithful_scene_metadata(broken)
    bad_curve = {**base, "tuning_morph_curve": "bouncy"}
    with pytest.raises(ValueError):
        validate_faithful_scene_metadata(bad_curve)


def test_validate_faithful_scene_metadata_rejects_missing_and_bad_mood_mode() -> None:
    base = {
        "tuning_system_name": "twelve_tet",
        "tuning_morph_target_name": "",
        "tuning_morph_curve": "linear",
        "mood_mode": "matched",
    }
    validate_faithful_scene_metadata(base)
    for missing in REQUIRED_MOOD_METADATA_FIELDS:
        broken = {k: v for k, v in base.items() if k != missing}
        with pytest.raises(ValueError):
            validate_faithful_scene_metadata(broken)
    bad_mood_mode = {**base, "mood_mode": "restless"}
    with pytest.raises(ValueError):
        validate_faithful_scene_metadata(bad_mood_mode)


def test_supported_morph_curves_match_prd() -> None:
    assert set(SUPPORTED_MORPH_CURVES) == {
        "linear",
        "ease_in",
        "ease_out",
        "sigmoid",
    }
