"""Tests for the verified sound palette and SynthDef registry."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools", "senseweave"))

from senseweave.synthdef_registry import (
    REQUIRED_METHODS,
    SYNTHDEF_REGISTRY,
    RegisterRange,
    covered_methods,
    entries_by_method,
    get_entry,
    live_voices,
    quarantined_voices,
    resolve_voice,
    voices_for_role,
)


# === Registry completeness ===


class TestRegistryCompleteness:
    def test_covers_all_required_synthesis_methods(self) -> None:
        assert REQUIRED_METHODS <= covered_methods()

    def test_at_least_one_voice_per_method(self) -> None:
        for method in REQUIRED_METHODS:
            assert len(entries_by_method(method)) >= 1, f"no entry for {method}"

    def test_subtractive_has_multiple_voices(self) -> None:
        subs = entries_by_method("subtractive")
        assert len(subs) >= 2
        names = {e.voice_name for e in subs}
        assert {"pluck", "breath"} <= names

    def test_fm_has_multiple_voices(self) -> None:
        fms = entries_by_method("fm")
        assert len(fms) >= 3
        names = {e.voice_name for e in fms}
        assert {"kotekan", "gong", "bell"} <= names

    def test_physical_model_has_multiple_voices(self) -> None:
        pms = entries_by_method("physical_model")
        assert len(pms) >= 3
        names = {e.voice_name for e in pms}
        assert {"bowed", "tabla_tin", "tabla_ge"} <= names

    def test_total_entry_count(self) -> None:
        assert len(SYNTHDEF_REGISTRY) == 13


# === Entry fields ===


class TestEntryFields:
    def test_every_entry_has_timbral_tags(self) -> None:
        for entry in SYNTHDEF_REGISTRY.values():
            assert len(entry.timbral_tags) >= 1, f"{entry.voice_name} has no tags"

    def test_every_entry_has_safe_roles(self) -> None:
        for entry in SYNTHDEF_REGISTRY.values():
            assert len(entry.safe_roles) >= 1, f"{entry.voice_name} has no roles"

    def test_every_entry_has_register_range(self) -> None:
        for entry in SYNTHDEF_REGISTRY.values():
            assert entry.register.min_hz > 0
            assert entry.register.max_hz > entry.register.min_hz
            assert entry.register.octave_span > 0

    def test_every_entry_has_macro_controls(self) -> None:
        for entry in SYNTHDEF_REGISTRY.values():
            names = {c.name for c in entry.macro_controls}
            assert {"freq", "amp", "attack", "release"} <= names, (
                f"{entry.voice_name} missing core controls"
            )

    def test_every_entry_has_spectral_profile(self) -> None:
        for entry in SYNTHDEF_REGISTRY.values():
            sp = entry.spectral
            assert 0.0 <= sp.fundamental_weight <= 1.0
            assert sp.harmonic_rolloff_db <= 0.0
            assert 0.0 <= sp.noise_floor <= 1.0
            assert sp.bandwidth in ("narrow", "medium", "wide")

    def test_synthdef_name_follows_sw_prefix(self) -> None:
        # `morph` is the §11 single-line timbre-morph voice; its SynthDef
        # ships as `\morph_voice` per the v2 spec rather than the `sw_`
        # prefix used by the original senseweave palette.
        non_sw_voices = {"morph"}
        for entry in SYNTHDEF_REGISTRY.values():
            if entry.voice_name in non_sw_voices:
                continue
            assert entry.synthdef_name.startswith("sw_"), (
                f"{entry.voice_name}: {entry.synthdef_name}"
            )


# === Register range ===


class TestRegisterRange:
    def test_octave_span_calculation(self) -> None:
        r = RegisterRange(110.0, 880.0)
        assert abs(r.octave_span - 3.0) < 0.01

    def test_zero_min_returns_zero_span(self) -> None:
        r = RegisterRange(0.0, 880.0)
        assert r.octave_span == 0.0

    def test_gong_is_lowest_register(self) -> None:
        gong = get_entry("gong")
        for entry in SYNTHDEF_REGISTRY.values():
            assert gong.register.min_hz <= entry.register.min_hz

    def test_bell_reaches_highest_register(self) -> None:
        bell = get_entry("bell")
        for entry in SYNTHDEF_REGISTRY.values():
            assert bell.register.max_hz >= entry.register.max_hz


# === Quarantine and fallbacks ===


class TestQuarantine:
    def test_quarantined_voices_identified(self) -> None:
        q = quarantined_voices()
        names = {e.voice_name for e in q}
        assert names == {"gong", "bell", "metal", "grain", "tabla_ge"}

    def test_quarantined_have_reason(self) -> None:
        for entry in quarantined_voices():
            assert entry.quarantine_reason, f"{entry.voice_name} missing reason"

    def test_quarantined_have_safe_substitute(self) -> None:
        for entry in quarantined_voices():
            assert entry.safe_substitute, f"{entry.voice_name} missing substitute"
            sub = SYNTHDEF_REGISTRY[entry.safe_substitute]
            assert not sub.quarantined, (
                f"{entry.voice_name} substitute {sub.voice_name} is also quarantined"
            )

    def test_resolve_voice_never_returns_quarantined(self) -> None:
        for name in SYNTHDEF_REGISTRY:
            resolved = resolve_voice(name)
            assert not resolved.quarantined, (
                f"resolve_voice({name!r}) returned quarantined {resolved.voice_name}"
            )

    def test_resolve_passes_through_live_voices(self) -> None:
        for entry in live_voices():
            assert resolve_voice(entry.voice_name) is entry

    def test_live_voices_excludes_quarantined(self) -> None:
        live = live_voices()
        for entry in live:
            assert not entry.quarantined

    def test_substitutes_match_voice_aliases(self) -> None:
        """Registry substitutes must agree with voice_aliases.py."""
        from senseweave.voice_aliases import RUNTIME_VOICE_ALIAS

        for entry in quarantined_voices():
            alias = RUNTIME_VOICE_ALIAS.get(entry.voice_name)
            if alias is not None:
                assert entry.safe_substitute == alias, (
                    f"{entry.voice_name}: registry says {entry.safe_substitute}, "
                    f"voice_aliases says {alias}"
                )


# === Role queries ===


class TestRoleQueries:
    def test_melody_voices_are_live(self) -> None:
        melody = voices_for_role("melody")
        assert len(melody) >= 2
        assert all(not e.quarantined for e in melody)

    def test_color_voices_include_breath(self) -> None:
        color = voices_for_role("color")
        names = {e.voice_name for e in color}
        assert "breath" in names

    def test_foundation_has_bowed(self) -> None:
        found = voices_for_role("foundation")
        names = {e.voice_name for e in found}
        assert "bowed" in names

    def test_quarantined_excluded_from_role_query(self) -> None:
        for role in ("melody", "bass", "counter", "color", "foundation", "rhythm", "figuration"):
            for entry in voices_for_role(role):
                assert not entry.quarantined


# === Lookup functions ===


class TestLookups:
    def test_get_entry_known_voice(self) -> None:
        e = get_entry("pluck")
        assert e.voice_name == "pluck"
        assert e.synthesis_method == "subtractive"

    def test_get_entry_unknown_raises(self) -> None:
        try:
            get_entry("theremin")
            assert False, "expected KeyError"
        except KeyError:
            pass

    def test_resolve_quarantined_gong_to_bowed(self) -> None:
        resolved = resolve_voice("gong")
        assert resolved.voice_name == "bowed"

    def test_resolve_quarantined_grain_to_breath(self) -> None:
        resolved = resolve_voice("grain")
        assert resolved.voice_name == "breath"

    def test_entries_by_method_returns_correct_type(self) -> None:
        for method in ("subtractive", "additive", "fm", "wavetable", "physical_model", "granular"):
            entries = entries_by_method(method)
            for e in entries:
                assert e.synthesis_method == method


# === Morph voice (T-047c) ===


class TestMorphVoice:
    def test_morph_voice_is_registered(self) -> None:
        entry = get_entry("morph")
        assert entry.synthdef_name == "morph_voice"

    def test_morph_voice_exposes_morph_x_control(self) -> None:
        entry = get_entry("morph")
        controls = {c.name: c for c in entry.macro_controls}
        assert "morph_x" in controls, "morph_x must be a controllable parameter"
        morph_x = controls["morph_x"]
        assert morph_x.default == 0.0
        assert morph_x.min_val == 0.0
        assert morph_x.max_val == 1.0

    def test_morph_voice_is_live_not_quarantined(self) -> None:
        entry = get_entry("morph")
        assert not entry.quarantined
        assert resolve_voice("morph") is entry


# === Palette consistency with sound_palette_lab ===


class TestPaletteConsistency:
    def test_registry_covers_all_voice_studies(self) -> None:
        """Every voice in sound_palette_lab.VOICE_STUDIES has a registry entry."""
        from senseweave.sound_palette_lab import VOICE_STUDIES

        study_names = {s.voice_name for s in VOICE_STUDIES}
        registry_names = set(SYNTHDEF_REGISTRY.keys())
        missing = study_names - registry_names
        assert not missing, f"voices in studies but not registry: {missing}"

    def test_synthesis_methods_agree(self) -> None:
        """Registry synthesis_method matches VoiceStudy synthesis_method."""
        from senseweave.sound_palette_lab import VOICE_STUDIES

        for study in VOICE_STUDIES:
            entry = SYNTHDEF_REGISTRY.get(study.voice_name)
            if entry is not None:
                assert entry.synthesis_method == study.synthesis_method, (
                    f"{study.voice_name}: study={study.synthesis_method}, "
                    f"registry={entry.synthesis_method}"
                )

    def test_timbral_tags_agree(self) -> None:
        """Registry timbral tags match VoiceStudy tags."""
        from senseweave.sound_palette_lab import VOICE_STUDIES

        for study in VOICE_STUDIES:
            entry = SYNTHDEF_REGISTRY.get(study.voice_name)
            if entry is not None:
                assert set(entry.timbral_tags) == set(study.timbral_tags), (
                    f"{study.voice_name}: tags differ"
                )
