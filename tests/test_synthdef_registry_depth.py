"""Depth-2 SynthDef registry report helpers - locked test surface for frac-0028."""
from __future__ import annotations

import dataclasses
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools", "senseweave"))

from senseweave.synthdef_registry import (  # noqa: E402
    REQUIRED_METHODS,
    SYNTHDEF_REGISTRY,
    SynthDefRegistryReport,
    VoiceShape,
    build_synthdef_registry_report,
    build_voice_shape,
    covered_methods,
    fundamental_band,
    get_entry,
    live_voices,
    noise_band,
    quarantined_voices,
    register_band,
    resolve_voice,
    rolloff_band,
    summarize_synthdef_registry_report,
    voices_for_role,
)


def test_synthdef_registry_band_helpers_map_values_to_named_bands() -> None:
    # register_band — C3 = 130.8 Hz, C5 = 523.3 Hz
    assert register_band(0.0) == "low"
    assert register_band(65.4) == "low"
    assert register_band(130.79) == "low"
    assert register_band(130.8) == "mid"
    assert register_band(261.6) == "mid"
    assert register_band(523.29) == "mid"
    assert register_band(523.3) == "high"
    assert register_band(2093.0) == "high"

    # fundamental_band
    assert fundamental_band(0.0) == "weak"
    assert fundamental_band(0.39) == "weak"
    assert fundamental_band(0.4) == "balanced"
    assert fundamental_band(0.7) == "balanced"
    assert fundamental_band(0.701) == "strong"
    assert fundamental_band(1.0) == "strong"

    # noise_band
    assert noise_band(0.0) == "clean"
    assert noise_band(0.099) == "clean"
    assert noise_band(0.1) == "textured"
    assert noise_band(0.3) == "textured"
    assert noise_band(0.301) == "noisy"
    assert noise_band(1.0) == "noisy"

    # rolloff_band — db is negative or zero
    assert rolloff_band(0.0) == "gentle"
    assert rolloff_band(-1.5) == "gentle"
    assert rolloff_band(-2.999) == "gentle"
    assert rolloff_band(-3.0) == "moderate"
    assert rolloff_band(-4.5) == "moderate"
    assert rolloff_band(-6.0) == "moderate"
    assert rolloff_band(-6.001) == "steep"
    assert rolloff_band(-12.0) == "steep"


def test_build_voice_shape_resolves_entry_diagnostics() -> None:
    pluck = get_entry("pluck")
    shape = build_voice_shape(pluck)

    assert isinstance(shape, VoiceShape)
    assert dataclasses.is_dataclass(shape)
    assert getattr(shape, "__dataclass_params__").frozen

    assert shape.voice_name == "pluck"
    assert shape.synthdef_name == "sw_pluck"
    assert shape.synthesis_method == "subtractive"
    assert shape.timbral_tags == pluck.timbral_tags
    assert shape.safe_roles == pluck.safe_roles
    assert shape.register_min_hz == pluck.register.min_hz
    assert shape.register_max_hz == pluck.register.max_hz
    assert shape.octave_span == round(pluck.register.octave_span, 4)
    assert shape.register_band == register_band(pluck.register.min_hz)
    assert shape.bandwidth == pluck.spectral.bandwidth
    assert shape.fundamental_weight == pluck.spectral.fundamental_weight
    assert shape.fundamental_band == fundamental_band(pluck.spectral.fundamental_weight)
    assert shape.noise_floor == pluck.spectral.noise_floor
    assert shape.noise_band == noise_band(pluck.spectral.noise_floor)
    assert shape.harmonic_rolloff_db == pluck.spectral.harmonic_rolloff_db
    assert shape.rolloff_band == rolloff_band(pluck.spectral.harmonic_rolloff_db)
    assert shape.macro_control_count == len(pluck.macro_controls)
    assert shape.macro_control_names == tuple(c.name for c in pluck.macro_controls)
    assert shape.quarantined is False
    assert shape.quarantine_reason == ""
    assert shape.safe_substitute == ""
    assert shape.runtime_voice_name == "pluck"

    # Quarantined voice resolves runtime_voice_name to its substitute
    gong = get_entry("gong")
    gong_shape = build_voice_shape(gong)
    assert gong_shape.quarantined is True
    assert gong_shape.quarantine_reason == gong.quarantine_reason
    assert gong_shape.safe_substitute == "bowed"
    assert gong_shape.runtime_voice_name == "bowed"


def test_build_synthdef_registry_report_resolves_full_registry() -> None:
    report = build_synthdef_registry_report()

    assert isinstance(report, SynthDefRegistryReport)
    assert dataclasses.is_dataclass(report)
    assert getattr(report, "__dataclass_params__").frozen

    assert report.total_count == len(SYNTHDEF_REGISTRY)
    assert report.live_count == len(live_voices())
    assert report.quarantined_count == len(quarantined_voices())
    assert report.live_count + report.quarantined_count == report.total_count

    # Canonical method ordering
    assert report.methods == (
        "subtractive",
        "additive",
        "fm",
        "wavetable",
        "physical_model",
        "granular",
    )
    # Every canonical method appears in counts (today none are zero, but the key must be present)
    assert set(report.method_counts.keys()) == set(report.methods)
    assert tuple(report.method_counts.keys()) == report.methods
    assert report.method_counts["subtractive"] == 2
    assert report.method_counts["additive"] == 1
    assert report.method_counts["fm"] == 3
    assert report.method_counts["wavetable"] == 2
    assert report.method_counts["physical_model"] == 3
    assert report.method_counts["granular"] == 1

    assert tuple(report.live_method_counts.keys()) == report.methods
    assert report.live_method_counts["subtractive"] == 2
    assert report.live_method_counts["additive"] == 1
    # FM: kotekan live, gong + bell quarantined → 1 live
    assert report.live_method_counts["fm"] == 1
    # Wavetable: pad live, metal quarantined → 1 live
    assert report.live_method_counts["wavetable"] == 1
    # Physical model: bowed + tabla_tin live, tabla_ge quarantined → 2 live
    assert report.live_method_counts["physical_model"] == 2
    # Granular: grain quarantined → 0 live
    assert report.live_method_counts["granular"] == 0

    # Roles and role->live-voices map (ordered, live only)
    for role, names in report.role_live_voices.items():
        for name in names:
            entry = SYNTHDEF_REGISTRY[name]
            assert not entry.quarantined
            assert role in entry.safe_roles
    assert "melody" in report.roles
    assert "color" in report.roles
    # Quarantined voice names must not appear in any role bucket
    quarantined_names = {e.voice_name for e in quarantined_voices()}
    for names in report.role_live_voices.values():
        assert not (set(names) & quarantined_names)

    # Register band counts cover low/mid/high keys, including zeros
    assert tuple(report.register_band_counts.keys()) == ("low", "mid", "high")
    assert sum(report.register_band_counts.values()) == report.total_count

    # Lowest/highest register voices
    assert report.lowest_register_voice == "gong"  # 32.7 Hz
    assert report.highest_register_voice == "bell"  # 4186.0 Hz

    # Quarantine reasons in entry order, distinct
    assert isinstance(report.quarantine_reasons, tuple)
    assert len(report.quarantine_reasons) == len(set(report.quarantine_reasons))
    for reason in report.quarantine_reasons:
        assert any(e.quarantine_reason == reason for e in quarantined_voices())

    # Runtime voice map covers exactly the quarantined voices, in entry order
    quarantined_names_ordered = tuple(e.voice_name for e in quarantined_voices())
    assert tuple(report.runtime_voice_map.keys()) == quarantined_names_ordered
    for q_name, runtime_name in report.runtime_voice_map.items():
        assert runtime_name == resolve_voice(q_name).voice_name
        assert not SYNTHDEF_REGISTRY[runtime_name].quarantined

    # Missing methods — today the registry covers all six
    assert report.missing_required_methods == ()
    assert set(report.methods) == REQUIRED_METHODS

    # Voices tuple — one per registry entry, in declaration order
    assert len(report.voices) == report.total_count
    assert tuple(v.voice_name for v in report.voices) == tuple(SYNTHDEF_REGISTRY.keys())
    for shape in report.voices:
        assert isinstance(shape, VoiceShape)


def test_summarize_synthdef_registry_report_returns_json_safe_summary() -> None:
    report = build_synthdef_registry_report()
    summary = summarize_synthdef_registry_report(report)

    assert summary["total_count"] == report.total_count
    assert summary["live_count"] == report.live_count
    assert summary["quarantined_count"] == report.quarantined_count
    assert summary["methods"] == list(report.methods)
    assert summary["method_counts"] == dict(report.method_counts)
    assert summary["live_method_counts"] == dict(report.live_method_counts)
    assert summary["roles"] == list(report.roles)
    assert summary["role_live_voices"] == {
        role: list(names) for role, names in report.role_live_voices.items()
    }
    assert summary["register_band_counts"] == dict(report.register_band_counts)
    assert summary["lowest_register_voice"] == report.lowest_register_voice
    assert summary["highest_register_voice"] == report.highest_register_voice
    assert summary["quarantine_reasons"] == list(report.quarantine_reasons)
    assert summary["runtime_voice_map"] == dict(report.runtime_voice_map)
    assert summary["missing_required_methods"] == list(report.missing_required_methods)

    # voices list mirrors VoiceShape fields
    assert isinstance(summary["voices"], list)
    assert len(summary["voices"]) == len(report.voices)
    first = summary["voices"][0]
    first_shape = report.voices[0]
    assert first["voice_name"] == first_shape.voice_name  # type: ignore[index]
    assert first["synthdef_name"] == first_shape.synthdef_name  # type: ignore[index]
    assert first["synthesis_method"] == first_shape.synthesis_method  # type: ignore[index]
    assert first["timbral_tags"] == list(first_shape.timbral_tags)  # type: ignore[index]
    assert first["safe_roles"] == list(first_shape.safe_roles)  # type: ignore[index]
    assert first["register_min_hz"] == first_shape.register_min_hz  # type: ignore[index]
    assert first["register_max_hz"] == first_shape.register_max_hz  # type: ignore[index]
    assert first["octave_span"] == first_shape.octave_span  # type: ignore[index]
    assert first["register_band"] == first_shape.register_band  # type: ignore[index]
    assert first["bandwidth"] == first_shape.bandwidth  # type: ignore[index]
    assert first["fundamental_weight"] == first_shape.fundamental_weight  # type: ignore[index]
    assert first["fundamental_band"] == first_shape.fundamental_band  # type: ignore[index]
    assert first["noise_floor"] == first_shape.noise_floor  # type: ignore[index]
    assert first["noise_band"] == first_shape.noise_band  # type: ignore[index]
    assert first["harmonic_rolloff_db"] == first_shape.harmonic_rolloff_db  # type: ignore[index]
    assert first["rolloff_band"] == first_shape.rolloff_band  # type: ignore[index]
    assert first["macro_control_count"] == first_shape.macro_control_count  # type: ignore[index]
    assert first["macro_control_names"] == list(first_shape.macro_control_names)  # type: ignore[index]
    assert first["quarantined"] == first_shape.quarantined  # type: ignore[index]
    assert first["quarantine_reason"] == first_shape.quarantine_reason  # type: ignore[index]
    assert first["safe_substitute"] == first_shape.safe_substitute  # type: ignore[index]
    assert first["runtime_voice_name"] == first_shape.runtime_voice_name  # type: ignore[index]

    # JSON round-trip
    encoded = json.dumps(summary)
    decoded = json.loads(encoded)
    assert decoded["total_count"] == report.total_count


def test_synthdef_registry_report_agrees_with_existing_lookups() -> None:
    report = build_synthdef_registry_report()

    # Methods coverage agrees with covered_methods()
    assert set(report.methods) == covered_methods()
    assert report.missing_required_methods == ()

    # runtime_voice_map agrees with resolve_voice for every quarantined entry
    for entry in quarantined_voices():
        runtime = report.runtime_voice_map[entry.voice_name]
        assert runtime == resolve_voice(entry.voice_name).voice_name

    # role_live_voices agrees with voices_for_role for every reported role
    for role, names in report.role_live_voices.items():
        expected = tuple(e.voice_name for e in voices_for_role(role))
        assert names == expected

    # Live count agrees with live_voices()
    assert report.live_count == len(live_voices())
    assert report.quarantined_count == len(quarantined_voices())


def test_synthdef_registry_reaches_depth_two() -> None:
    from sdp.fractal import classify_depth

    result = classify_depth("my-claw/tools/senseweave/synthdef_registry.py")
    assert result.depth >= 2, result.reason
