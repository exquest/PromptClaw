"""Tests for CypherClaw v2 per-voice reverb space profiles (T-043)."""

from __future__ import annotations

import dataclasses
import json
import re
from pathlib import Path
from typing import Any

from cypherclaw.midi_loader import FaithfulMidiEvent
from cypherclaw.midi_scene import FaithfulRenderSettings, build_faithful_midi_scene
from cypherclaw.space_reverb import (
    SPACE_PROFILE_SOURCE,
    VOICE_REVERB_PROFILES,
    VoiceReverbProfile,
    build_voice_s_new_args,
    get_voice_reverb_profile,
    iter_voice_reverb_profiles,
    summarize_voice_reverb_profiles,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
SPACES_DIR = (
    REPO_ROOT / "my-claw" / "tools" / "senseweave" / "synthesis" / "spaces"
)
VOICES_DIR = (
    REPO_ROOT / "my-claw" / "tools" / "senseweave" / "synthesis" / "voices"
)
MASTER_SMOOTH_PATH = (
    REPO_ROOT
    / "my-claw"
    / "tools"
    / "senseweave"
    / "synthesis"
    / "master_smooth.scd"
)

EXPECTED_VOICE_ORDER = (
    "pluck",
    "breath",
    "choir",
    "kotekan",
    "pad",
    "bowed",
    "tabla_tin",
)

EXPECTED_SPACE_IDS = {
    "pluck": "small_wooden_room",
    "breath": "glass_bell_jar",
    "choir": "stone_cathedral",
    "kotekan": "humid_forest_canopy",
    "pad": "marble_empty_hall",
    "bowed": "damp_cave_wall",
    "tabla_tin": "dusk_garden",
}

EXPECTED_BUS_IDS = {
    "pluck": 16,
    "breath": 17,
    "choir": 18,
    "kotekan": 19,
    "pad": 20,
    "bowed": 21,
    "tabla_tin": 22,
}

EXPECTED_QUOTE_SNIPPETS = {
    "pluck": "small wooden room with hard floorboards",
    "breath": "glass bell jar at sea level",
    "choir": "stone cathedral with high vaulted ceilings",
    "kotekan": "dense forest canopy on a humid day",
    "pad": "large, empty hall with marble floors",
    "bowed": "damp cave wall",
    "tabla_tin": "outdoor garden at dusk",
}

PARAMETER_KEYS = (
    "verb_mix",
    "room_size",
    "damping",
    "predelay_ms",
    "decay_s",
    "early_reflection_level",
    "flutter_feedback",
)


def _assert_json_safe(value: Any) -> None:
    assert not isinstance(value, tuple), f"tuple leaked into JSON summary: {value!r}"
    if isinstance(value, dict):
        for key, child in value.items():
            assert isinstance(key, str)
            _assert_json_safe(child)
    elif isinstance(value, list):
        for child in value:
            _assert_json_safe(child)


def _master_smooth_arg_block(source: str) -> str:
    match = re.search(
        r"SynthDef\(\\sw_master_smooth,\s*\{\s*\|(?P<args>.*?)\|",
        source,
        flags=re.DOTALL,
    )
    assert match, "could not locate sw_master_smooth argument block"
    return match.group("args")


def _master_smooth_fx_bus_defaults(source: str) -> dict[str, int]:
    block = _master_smooth_arg_block(source)
    return {
        voice: int(bus)
        for voice, bus in re.findall(r"\bfx_bus_([a-z_]+)\s*=\s*(\d+)\b", block)
    }


def _master_smooth_fx_bus_reads(source: str) -> set[str]:
    return set(
        re.findall(r"\bIn\.ar\(\s*fx_bus_([a-z_]+)\s*,\s*2\s*\)", source)
    )


def test_profiles_cover_all_cypherclaw_space_voices_with_unique_buses() -> None:
    assert tuple(VOICE_REVERB_PROFILES) == EXPECTED_VOICE_ORDER
    assert tuple(profile.voice for profile in iter_voice_reverb_profiles()) == (
        EXPECTED_VOICE_ORDER
    )

    seen_space_ids: set[str] = set()
    seen_bus_ids: set[int] = set()
    for voice, profile in VOICE_REVERB_PROFILES.items():
        assert isinstance(profile, VoiceReverbProfile)
        assert dataclasses.is_dataclass(profile)
        assert getattr(profile, "__dataclass_params__").frozen
        assert profile.voice == voice
        assert profile.space_id == EXPECTED_SPACE_IDS[voice]
        assert profile.fx_bus_id == EXPECTED_BUS_IDS[voice]
        assert profile.source == SPACE_PROFILE_SOURCE
        assert profile.synthdef_name == f"cc_space_{profile.space_id}"
        assert EXPECTED_QUOTE_SNIPPETS[voice] in profile.rationale
        assert profile.space_doc_path == (
            f"my-claw/tools/senseweave/synthesis/spaces/{profile.space_id}.scd"
        )
        seen_space_ids.add(profile.space_id)
        seen_bus_ids.add(profile.fx_bus_id)

    assert len(seen_space_ids) == len(EXPECTED_VOICE_ORDER)
    assert seen_bus_ids == set(range(16, 23))
    assert get_voice_reverb_profile("sw_breath").voice == "breath"
    assert get_voice_reverb_profile("unknown_voice").voice == "pluck"


def test_profile_parameters_are_bounded_and_json_safe() -> None:
    summary = summarize_voice_reverb_profiles()
    _assert_json_safe(summary)
    decoded = json.loads(json.dumps(summary))
    assert decoded["source"] == SPACE_PROFILE_SOURCE
    assert decoded["voice_order"] == list(EXPECTED_VOICE_ORDER)

    for profile in iter_voice_reverb_profiles():
        params = dict(profile.parameters)
        assert tuple(params) == PARAMETER_KEYS
        assert 0.0 <= params["verb_mix"] <= 1.0
        assert 0.0 <= params["room_size"] <= 1.0
        assert 0.0 <= params["damping"] <= 1.0
        assert 0.0 <= params["predelay_ms"] <= 80.0
        assert 0.2 <= params["decay_s"] <= 8.0
        assert 0.0 <= params["early_reflection_level"] <= 1.0
        assert 0.0 <= params["flutter_feedback"] <= 1.0

    profiles = VOICE_REVERB_PROFILES
    assert dict(profiles["choir"].parameters)["decay_s"] > 5.0
    assert dict(profiles["choir"].parameters)["room_size"] > 0.9
    assert dict(profiles["pluck"].parameters)["decay_s"] < 1.0
    assert dict(profiles["breath"].parameters)["early_reflection_level"] > 0.8
    assert dict(profiles["kotekan"].parameters)["flutter_feedback"] > 0.6
    assert dict(profiles["bowed"].parameters)["damping"] > 0.6
    assert dict(profiles["tabla_tin"].parameters)["room_size"] < 0.55


def test_each_profile_has_space_source_file_with_rationale_and_parameters() -> None:
    for profile in iter_voice_reverb_profiles():
        path = REPO_ROOT / profile.space_doc_path
        assert path.is_file(), f"missing space source file: {path}"
        text = path.read_text(encoding="utf-8")

        assert f"SynthDef(\\{profile.synthdef_name}" in text
        assert f"// Voice: {profile.voice}" in text
        assert f"// Space: {profile.space_id}" in text
        assert f"// FX bus: {profile.fx_bus_id}" in text
        assert f"// Rationale: {profile.rationale}" in text
        assert EXPECTED_QUOTE_SNIPPETS[profile.voice] in text
        assert "FreeVerb.ar" in text
        assert "Out.ar(out_bus" in text

        for key, value in profile.parameters:
            pattern = rf"\b{re.escape(key)}\s*=\s*{re.escape(str(value))}\b"
            assert re.search(pattern, text), (
                f"{profile.space_id}.scd must document default {key}={value}"
            )


def test_faithful_render_space_metadata_uses_shared_reverb_profiles() -> None:
    events = tuple(
        FaithfulMidiEvent(pitch=60 + index, duration=120, velocity=90)
        for index in range(len(EXPECTED_VOICE_ORDER))
    )
    scene = build_faithful_midi_scene(
        events,
        render_settings=FaithfulRenderSettings(
            arc_phase="Listen",
            voice_sequence=EXPECTED_VOICE_ORDER,
        ),
    )

    steps = scene.to_dict()["pattern"]["lanes"][0]["steps"]
    for step, voice in zip(steps, EXPECTED_VOICE_ORDER, strict=True):
        profile = VOICE_REVERB_PROFILES[voice]
        render_space = step["render_space"]

        assert render_space["voice"] == voice
        assert render_space["space_id"] == profile.space_id
        assert render_space["fx_bus_id"] == profile.fx_bus_id
        assert render_space["reverb_profile"] == dict(profile.parameters)
        assert render_space["description"] == profile.description
        assert render_space["source"] == SPACE_PROFILE_SOURCE
        assert step["metadata"]["render_space_id"] == profile.space_id
        assert step["metadata"]["render_fx_bus_id"] == str(profile.fx_bus_id)


def test_each_voice_routes_only_to_its_assigned_fx_bus() -> None:
    """T-044: per-voice OSC args carry `fx_bus_id` and reach only the
    matching FX return bus declared in the voice's reverb profile.
    """
    routings: dict[str, int] = {}
    seen_buses: dict[int, str] = {}

    for voice in EXPECTED_VOICE_ORDER:
        args = build_voice_s_new_args(
            voice,
            node_id=70000,
            freq=440.0,
            amp=0.1,
            attack=0.02,
            release=0.8,
        )

        # The synthdef name leads the s_new arg list.
        assert args[0] == f"sw_{voice}", (
            f"voice {voice!r} must spawn sw_{voice}, got {args[0]!r}"
        )
        assert args[1] == 70000
        assert args.count("fx_bus_id") == 1, (
            f"voice {voice!r} must declare exactly one fx_bus_id routing"
        )

        bus = args[args.index("fx_bus_id") + 1]
        expected_bus = VOICE_REVERB_PROFILES[voice].fx_bus_id
        assert bus == expected_bus, (
            f"voice {voice!r} routed to bus {bus}, expected {expected_bus}"
        )
        assert bus == EXPECTED_BUS_IDS[voice]

        # Each voice's signal reaches ONLY its assigned FX bus.
        assert bus not in seen_buses, (
            f"voices {voice!r} and {seen_buses[bus]!r} share FX bus {bus}"
        )
        seen_buses[bus] = voice
        routings[voice] = bus

    assert routings == EXPECTED_BUS_IDS


def test_voice_routing_args_default_to_profile_pluck_for_unknown_voice() -> None:
    """Unknown voice names fall back to the pluck profile and its bus 16."""
    args = build_voice_s_new_args(
        "unknown_voice",
        node_id=70001,
        freq=220.0,
    )
    assert args[0] == "sw_pluck"
    assert args[args.index("fx_bus_id") + 1] == VOICE_REVERB_PROFILES["pluck"].fx_bus_id


def test_voice_synthdefs_declare_fx_bus_id_routing_contract() -> None:
    """T-044: each voice synthdef source declares `fx_bus_id` with the
    matching default from its `VoiceReverbProfile` and routes a parallel
    send into that bus via `Out.ar(fx_bus_id, ...)`.

    The `.scd` source under `synthesis/voices/` is the per-voice routing
    contract that `build_voice_s_new_args` writes via OSC. Without
    `fx_bus_id` declared as a SynthDef control, the OSC `/s_new` arg has
    no effect and the voice's signal never reaches its assigned FX
    return bus. This pins the contract so that regression is caught at
    test time rather than at scsynth runtime.
    """
    for voice, profile in VOICE_REVERB_PROFILES.items():
        scd_path = VOICES_DIR / f"sw_{voice}.scd"
        assert scd_path.is_file(), f"missing voice synthdef source: {scd_path}"
        text = scd_path.read_text(encoding="utf-8")

        assert f"SynthDef(\\sw_{voice}" in text, (
            f"voice {voice!r} stub must declare SynthDef \\sw_{voice}"
        )

        # `fx_bus_id` is declared as a control with the profile's bus id.
        pattern = rf"\bfx_bus_id\s*=\s*{profile.fx_bus_id}\b"
        assert re.search(pattern, text), (
            f"voice {voice!r} stub must declare fx_bus_id={profile.fx_bus_id} "
            f"to match its VoiceReverbProfile"
        )

        # The signal must reach the FX bus via Out.ar / OffsetOut.ar.
        send_pattern = r"\b(?:Out|OffsetOut)\.ar\(\s*fx_bus_id\s*,"
        assert re.search(send_pattern, text), (
            f"voice {voice!r} stub must route through Out.ar(fx_bus_id, ...)"
        )

        # And the dry signal must still reach the master via out_bus.
        dry_pattern = r"\b(?:Out|OffsetOut)\.ar\(\s*out_bus\s*,"
        assert re.search(dry_pattern, text), (
            f"voice {voice!r} stub must keep a dry Out.ar(out_bus, ...) tap"
        )


def test_voice_synthdef_fx_bus_ids_are_pairwise_unique() -> None:
    """Each voice .scd routes to a distinct FX bus — no two voices share
    the same return path."""
    declared: dict[int, str] = {}
    for voice, profile in VOICE_REVERB_PROFILES.items():
        scd_path = VOICES_DIR / f"sw_{voice}.scd"
        text = scd_path.read_text(encoding="utf-8")
        match = re.search(r"\bfx_bus_id\s*=\s*(\d+)\b", text)
        assert match, f"voice {voice!r} stub missing fx_bus_id default"
        bus = int(match.group(1))
        assert bus == profile.fx_bus_id
        assert bus not in declared, (
            f"voices {voice!r} and {declared[bus]!r} share FX bus {bus}"
        )
        declared[bus] = voice
    assert set(declared.values()) == set(VOICE_REVERB_PROFILES)


def test_master_smooth_fx_returns_match_voice_reverb_profiles() -> None:
    """T-044d: master_smooth must collect every canonical voice FX bus.

    Voice synthdefs and `build_voice_s_new_args(...)` now emit buses 16..22
    from `VOICE_REVERB_PROFILES`. The master bus source must read the same
    set exactly once, otherwise a smoke render can write to an uncollected bus
    while stale legacy bus reads still make the graph look populated.
    """
    source = MASTER_SMOOTH_PATH.read_text(encoding="utf-8")
    expected = {
        voice: profile.fx_bus_id for voice, profile in VOICE_REVERB_PROFILES.items()
    }

    defaults = _master_smooth_fx_bus_defaults(source)
    assert defaults == expected
    assert _master_smooth_fx_bus_reads(source) == set(expected)


def test_smoke_render_voice_fx_bus_ids_are_collected_by_master_smooth() -> None:
    """T-044d smoke render: every emitted voice bus reaches master_smooth."""
    source = MASTER_SMOOTH_PATH.read_text(encoding="utf-8")
    master_bus_ids = set(_master_smooth_fx_bus_defaults(source).values())
    emitted: dict[str, int] = {}

    for voice, profile in VOICE_REVERB_PROFILES.items():
        args = build_voice_s_new_args(
            voice,
            node_id=70000,
            freq=220.0,
            amp=0.1,
            attack=0.02,
            release=0.8,
        )

        assert args[0] == f"sw_{voice}"
        assert args.count("fx_bus_id") == 1
        emitted_bus = args[args.index("fx_bus_id") + 1]
        assert emitted_bus == profile.fx_bus_id
        emitted[voice] = int(emitted_bus)

    assert emitted == {
        voice: profile.fx_bus_id for voice, profile in VOICE_REVERB_PROFILES.items()
    }
    assert set(emitted.values()) == master_bus_ids


def test_spaces_directory_contains_only_expected_algorithmic_sources() -> None:
    expected_files = sorted(
        f"{profile.space_id}.scd" for profile in iter_voice_reverb_profiles()
    )
    assert sorted(path.name for path in SPACES_DIR.iterdir()) == expected_files

    forbidden_suffixes = {".wav", ".aif", ".aiff", ".flac", ".scsyndef"}
    binary_assets = [
        path
        for path in SPACES_DIR.rglob("*")
        if path.is_file() and path.suffix.lower() in forbidden_suffixes
    ]
    assert binary_assets == []
