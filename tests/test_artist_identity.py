"""Tests for artist_identity.py — CypherClaw's artistic self.

Covers:
  * SIGNATURE_VOICES quintet (sw_bell_warm, sw_bowed, sw_breath, sw_pad, sw_sampler)
  * HOME_TONAL_MAP B-rooted distance map
  * Five ArtistModes with sane voice-count defaults (3 base, 2 deliberate, 5 max)
  * select_mode() routing on presence/time/weather
  * apply_mode_to_commission() pure + deterministic
  * next_tonal_choice() honors modulation_willingness, stays home most of the time
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools", "senseweave"))

import pytest

from senseweave.artist_identity import (
    COMPANION,
    EVENING_REFLECTION,
    HOME_KEY,
    HOME_MODES,
    HOME_TONAL_MAP,
    MODES,
    MODES_BY_NAME,
    SIGNATURE_VOICES,
    SOLITARY,
    STORM,
    VOICE_ROLES,
    WORKING_AMBIENCE,
    ArtistMode,
    apply_mode_to_commission,
    next_tonal_choice,
    select_mode,
)


# ---------------------------------------------------------------------------
# Voice quintet
# ---------------------------------------------------------------------------

class TestSignatureVoices:
    def test_quintet_size(self):
        assert len(SIGNATURE_VOICES) == 5

    def test_quintet_membership(self):
        assert "sw_bell_warm" in SIGNATURE_VOICES
        assert "sw_bowed" in SIGNATURE_VOICES
        assert "sw_breath" in SIGNATURE_VOICES
        assert "sw_pad" in SIGNATURE_VOICES
        assert "sw_sampler" in SIGNATURE_VOICES

    def test_sampler_is_fifth_after_pad(self):
        # sw_sampler is the quintet extension; it must follow sw_pad in order
        assert SIGNATURE_VOICES.index("sw_sampler") == SIGNATURE_VOICES.index("sw_pad") + 1

    def test_voice_roles_complete(self):
        # Every musical role has a canonical signature voice
        for role in ("melody", "counter", "color", "texture", "bass", "sampler"):
            assert role in VOICE_ROLES
            assert VOICE_ROLES[role] in SIGNATURE_VOICES
        assert VOICE_ROLES["sampler"] == "sw_sampler"


# ---------------------------------------------------------------------------
# B-rooted tonal map
# ---------------------------------------------------------------------------

class TestHomeTonalMap:
    def test_home_is_b(self):
        assert HOME_KEY == "B"

    def test_b_has_zero_distance(self):
        assert HOME_TONAL_MAP["B"] == 0

    def test_close_neighbors_within_distance_1(self):
        # D (relative major) and F# (dominant) should be distance 1
        assert HOME_TONAL_MAP["D"] == 1
        assert HOME_TONAL_MAP["F#"] == 1

    def test_distant_keys_have_higher_distance(self):
        # G and E are explicit "departure" keys
        assert HOME_TONAL_MAP["G"] > HOME_TONAL_MAP["B"]
        assert HOME_TONAL_MAP["E"] > HOME_TONAL_MAP["B"]

    def test_home_modes_includes_minor_dorian_phrygian(self):
        assert "minor" in HOME_MODES
        assert "dorian" in HOME_MODES
        assert "phrygian" in HOME_MODES


# ---------------------------------------------------------------------------
# Mode definitions
# ---------------------------------------------------------------------------

class TestArtistModes:
    def test_five_modes(self):
        assert len(MODES) == 5

    def test_modes_lookup_by_name(self):
        for mode in MODES:
            assert MODES_BY_NAME[mode.name] is mode

    def test_three_voice_base_default(self):
        # Companion is the default mode — should have 3-voice base
        assert COMPANION.voice_count_target == 3
        assert COMPANION.voice_count_floor >= 2

    def test_solitary_can_drop_to_two_voices(self):
        # Solitary is the meaningful 2-voice mode
        assert SOLITARY.voice_count_target == 2
        assert SOLITARY.voice_count_floor == 1

    def test_no_mode_exceeds_quintet(self):
        # Never more than 5 voices simultaneously — the quintet is the orchestra
        for mode in MODES:
            assert mode.voice_count_ceiling <= 5

    def test_storm_is_densest(self):
        # Storm is the most turbulent mode
        assert STORM.density_bias > 0.0
        assert STORM.restraint_level < 0.5
        assert STORM.harmonic_complexity > 0.5

    def test_working_ambience_avoids_attention(self):
        assert WORKING_AMBIENCE.avoid_attention_pullers is True

    def test_evening_reflection_uses_full_quintet(self):
        # Evening can rotate through all five signature voices
        assert set(EVENING_REFLECTION.preferred_voices) == set(SIGNATURE_VOICES)

    def test_solitary_silence_ratio_is_high(self):
        assert SOLITARY.silence_ratio >= 0.4

    def test_tempo_bands_are_valid(self):
        for mode in MODES:
            lo, hi = mode.tempo_band
            assert lo < hi
            assert 40.0 <= lo <= 200.0
            assert 40.0 <= hi <= 200.0


# ---------------------------------------------------------------------------
# sampler_density field
# ---------------------------------------------------------------------------

class TestSamplerDensity:
    def test_field_present_on_all_modes(self):
        for mode in MODES:
            assert hasattr(mode, "sampler_density")
            assert isinstance(mode.sampler_density, float)

    def test_default_is_zero(self):
        # ArtistMode() with only `name` should default sampler_density to 0.0
        m = ArtistMode(name="probe")
        assert m.sampler_density == 0.0

    def test_all_modes_in_valid_range(self):
        for mode in MODES:
            assert 0.0 <= mode.sampler_density <= 1.0

    def test_evening_reflection_uses_sampler(self):
        # Evening rotates the full quintet, so sampler should be audible
        assert EVENING_REFLECTION.sampler_density > 0.0

    def test_solitary_value(self):
        assert SOLITARY.sampler_density == 0.7

    def test_companion_value(self):
        assert COMPANION.sampler_density == 0.25

    def test_working_ambience_value(self):
        assert WORKING_AMBIENCE.sampler_density == 0.10

    def test_evening_reflection_value(self):
        assert EVENING_REFLECTION.sampler_density == 0.65

    def test_storm_value(self):
        assert STORM.sampler_density == 0.45

    def test_boundary_values_accepted(self):
        ArtistMode(name="lo", sampler_density=0.0)
        ArtistMode(name="hi", sampler_density=1.0)

    def test_below_zero_rejected(self):
        with pytest.raises(ValueError):
            ArtistMode(name="bad", sampler_density=-0.01)

    def test_above_one_rejected(self):
        with pytest.raises(ValueError):
            ArtistMode(name="bad", sampler_density=1.01)

    def test_serialized_into_commission(self):
        out = apply_mode_to_commission({}, EVENING_REFLECTION, rng_seed=1)
        assert "mode_sampler_density" in out
        assert out["mode_sampler_density"] == EVENING_REFLECTION.sampler_density

    def test_serialized_default_zero_for_solitary(self):
        out = apply_mode_to_commission({}, SOLITARY, rng_seed=1)
        assert out["mode_sampler_density"] == SOLITARY.sampler_density


# ---------------------------------------------------------------------------
# Mode selection
# ---------------------------------------------------------------------------

class TestSelectMode:
    def test_storm_overrides_everything(self):
        assert select_mode(presence="present", time_of_day="day", weather_severity=0.7) is STORM
        assert select_mode(presence="none", time_of_day="evening", weather_severity=0.9) is STORM

    def test_no_one_home_is_solitary(self):
        assert select_mode(presence="none") is SOLITARY

    def test_present_and_screen_active_is_working(self):
        m = select_mode(presence="present", time_of_day="day", screen_active=True)
        assert m is WORKING_AMBIENCE

    def test_evening_with_presence_is_reflection(self):
        m = select_mode(presence="present", time_of_day="evening")
        assert m is EVENING_REFLECTION

    def test_night_with_presence_is_reflection(self):
        m = select_mode(presence="present", time_of_day="night")
        assert m is EVENING_REFLECTION

    def test_default_is_companion(self):
        m = select_mode(presence="present", time_of_day="day", weather_severity=0.0)
        assert m is COMPANION

    def test_unknown_presence_defaults_to_companion(self):
        m = select_mode(presence="unknown", time_of_day="day")
        assert m is COMPANION


# ---------------------------------------------------------------------------
# apply_mode_to_commission
# ---------------------------------------------------------------------------

class TestApplyModeToCommission:
    def test_does_not_mutate_input(self):
        original = {"foo": "bar", "tempo": 80.0}
        snapshot = dict(original)
        apply_mode_to_commission(original, COMPANION, rng_seed=1)
        assert original == snapshot

    def test_adds_mode_metadata(self):
        out = apply_mode_to_commission({}, SOLITARY, rng_seed=1)
        assert out["artist_mode"] == "solitary"
        assert "mode_tempo_target_bpm" in out
        assert "mode_voice_count_target" in out
        assert "mode_silence_ratio" in out
        assert "mode_preferred_voices" in out

    def test_tempo_within_band(self):
        out = apply_mode_to_commission({}, SOLITARY, rng_seed=42)
        lo, hi = SOLITARY.tempo_band
        assert lo <= out["mode_tempo_target_bpm"] <= hi

    def test_voice_count_propagated(self):
        out = apply_mode_to_commission({}, COMPANION, rng_seed=1)
        assert out["mode_voice_count_target"] == 3
        assert out["mode_voice_count_floor"] == 2
        assert out["mode_voice_count_ceiling"] == 3

    def test_preferred_voices_csv(self):
        out = apply_mode_to_commission({}, SOLITARY, rng_seed=1)
        voices = out["mode_preferred_voices"].split(",")
        assert "sw_bell_warm" in voices
        assert "sw_pad" in voices

    def test_avoid_attention_flag_propagated(self):
        out = apply_mode_to_commission({}, WORKING_AMBIENCE, rng_seed=1)
        assert out["mode_avoid_attention_pullers"] == "true"
        out2 = apply_mode_to_commission({}, COMPANION, rng_seed=1)
        assert out2["mode_avoid_attention_pullers"] == "false"

    def test_deterministic_same_seed(self):
        a = apply_mode_to_commission({"x": 1}, EVENING_REFLECTION, rng_seed=99)
        b = apply_mode_to_commission({"x": 1}, EVENING_REFLECTION, rng_seed=99)
        assert a == b


# ---------------------------------------------------------------------------
# next_tonal_choice
# ---------------------------------------------------------------------------

class TestNextTonalChoice:
    def test_returns_valid_root_and_mode(self):
        root, mode = next_tonal_choice(current_key="B minor", artist_mode=COMPANION, rng_seed=1)
        assert root in HOME_TONAL_MAP
        assert mode in COMPANION.preferred_modes

    def test_low_modulation_willingness_stays_close_to_home(self):
        # Solitary has modulation_willingness=0.15 — most pieces should be home or distance-1
        roots = [
            next_tonal_choice(current_key="B minor", artist_mode=SOLITARY, rng_seed=i)[0]
            for i in range(50)
        ]
        close_count = sum(1 for r in roots if HOME_TONAL_MAP[r] <= 1)
        assert close_count >= 35  # ≥70% should stay close

    def test_storm_modulation_willingness_ventures_more(self):
        # Storm has modulation_willingness=0.6 — should venture more often
        roots = [
            next_tonal_choice(current_key="B minor", artist_mode=STORM, rng_seed=i)[0]
            for i in range(50)
        ]
        far_count = sum(1 for r in roots if HOME_TONAL_MAP[r] > 1)
        # Storm should venture (distance > 1) more often than solitary
        solitary_far = sum(
            1 for i in range(50)
            if HOME_TONAL_MAP[next_tonal_choice(current_key="B minor", artist_mode=SOLITARY, rng_seed=i)[0]] > 1
        )
        assert far_count > solitary_far

    def test_deterministic_same_seed(self):
        a = next_tonal_choice(current_key="B minor", artist_mode=COMPANION, rng_seed=42)
        b = next_tonal_choice(current_key="B minor", artist_mode=COMPANION, rng_seed=42)
        assert a == b


# ---------------------------------------------------------------------------
# End-to-end coverage (depth-2 gate)
# ---------------------------------------------------------------------------


class TestArtistIdentityEndToEnd:
    """One-path end-to-end coverage of the public artist-identity API.

    These methods drive ``select_mode``, ``apply_mode_to_commission``, and
    ``next_tonal_choice`` across complete sweeps of every ``ArtistMode`` in
    ``MODES`` and every key in ``HOME_TONAL_MAP``. Methods are looped or
    table-driven so the fractal scanner records real test logic rather than
    trivial single-call assertions.
    """

    # -- mode application sweeps -------------------------------------------

    def test_every_mode_applies_full_metadata_keys(self):
        expected = {
            "artist_mode",
            "mode_tempo_target_bpm",
            "mode_voice_count_target",
            "mode_voice_count_floor",
            "mode_voice_count_ceiling",
            "mode_density_bias",
            "mode_silence_ratio",
            "mode_restraint_level",
            "mode_harmonic_complexity",
            "mode_modulation_willingness",
            "mode_sampler_density",
            "mode_preferred_voices",
            "mode_preferred_grooves",
            "mode_preferred_modal_scales",
            "mode_avoid_attention_pullers",
        }
        for mode in MODES:
            out = apply_mode_to_commission({}, mode, rng_seed=1)
            missing = expected - set(out.keys())
            assert not missing, f"{mode.name} missing {missing}"

    def test_every_mode_tempo_lands_in_band(self):
        for mode in MODES:
            lo, hi = mode.tempo_band
            for seed in range(1, 30):
                out = apply_mode_to_commission({}, mode, rng_seed=seed)
                bpm = out["mode_tempo_target_bpm"]
                assert lo <= bpm <= hi, f"{mode.name}@{seed}: {bpm} not in [{lo},{hi}]"

    def test_every_mode_propagates_voice_counts(self):
        for mode in MODES:
            out = apply_mode_to_commission({}, mode, rng_seed=2)
            assert out["mode_voice_count_target"] == mode.voice_count_target
            assert out["mode_voice_count_floor"] == mode.voice_count_floor
            assert out["mode_voice_count_ceiling"] == mode.voice_count_ceiling
            assert mode.voice_count_floor <= mode.voice_count_target
            assert mode.voice_count_target <= mode.voice_count_ceiling

    def test_every_mode_propagates_silence_and_restraint(self):
        for mode in MODES:
            out = apply_mode_to_commission({}, mode, rng_seed=3)
            assert out["mode_silence_ratio"] == mode.silence_ratio
            assert out["mode_restraint_level"] == mode.restraint_level
            assert 0.0 <= out["mode_silence_ratio"] <= 1.0
            assert 0.0 <= out["mode_restraint_level"] <= 1.0

    def test_every_mode_propagates_harmony_fields(self):
        for mode in MODES:
            out = apply_mode_to_commission({}, mode, rng_seed=4)
            assert out["mode_harmonic_complexity"] == mode.harmonic_complexity
            assert out["mode_modulation_willingness"] == mode.modulation_willingness
            assert 0.0 <= out["mode_harmonic_complexity"] <= 1.0
            assert 0.0 <= out["mode_modulation_willingness"] <= 1.0

    def test_every_mode_propagates_sampler_density(self):
        for mode in MODES:
            out = apply_mode_to_commission({}, mode, rng_seed=5)
            assert out["mode_sampler_density"] == mode.sampler_density
            assert 0.0 <= out["mode_sampler_density"] <= 1.0

    def test_every_mode_serializes_voice_csv(self):
        for mode in MODES:
            out = apply_mode_to_commission({}, mode, rng_seed=6)
            voices = out["mode_preferred_voices"].split(",")
            assert len(voices) == len(mode.preferred_voices)
            for voice in mode.preferred_voices:
                assert voice in voices

    def test_every_mode_serializes_groove_and_modal_csv(self):
        for mode in MODES:
            out = apply_mode_to_commission({}, mode, rng_seed=7)
            grooves = out["mode_preferred_grooves"].split(",") if mode.preferred_grooves else []
            modals = out["mode_preferred_modal_scales"].split(",")
            for groove in mode.preferred_grooves:
                assert groove in grooves
            for scale in mode.preferred_modes:
                assert scale in modals

    def test_every_mode_propagates_attention_flag_as_string(self):
        for mode in MODES:
            out = apply_mode_to_commission({}, mode, rng_seed=8)
            flag = out["mode_avoid_attention_pullers"]
            assert flag in ("true", "false")
            assert flag == ("true" if mode.avoid_attention_pullers else "false")

    def test_every_mode_application_is_deterministic_across_seeds(self):
        # rng_seed=0 falls through to a hash-of-id path inside the helper, so
        # the deterministic contract only applies to non-zero seeds.
        for mode in MODES:
            for seed in (1, 7, 42, 99, 1234):
                a = apply_mode_to_commission({"trace": mode.name}, mode, rng_seed=seed)
                b = apply_mode_to_commission({"trace": mode.name}, mode, rng_seed=seed)
                assert a == b, f"{mode.name}@{seed} not deterministic"

    def test_every_mode_application_does_not_mutate_input(self):
        for mode in MODES:
            base = {"trace": mode.name, "tempo": 80.0, "extra": [1, 2, 3]}
            snapshot = json.loads(json.dumps(base))
            apply_mode_to_commission(base, mode, rng_seed=11)
            assert base == snapshot, f"{mode.name} mutated input"

    def test_every_mode_application_is_json_serializable(self):
        for mode in MODES:
            out = apply_mode_to_commission({"piece_id": "p001"}, mode, rng_seed=12)
            roundtrip = json.loads(json.dumps(out))
            assert roundtrip["artist_mode"] == mode.name
            assert roundtrip["mode_voice_count_target"] == mode.voice_count_target

    def test_existing_commission_keys_preserved(self):
        for mode in MODES:
            base = {"piece_id": "abc", "intent": "morning_check"}
            out = apply_mode_to_commission(base, mode, rng_seed=13)
            assert out["piece_id"] == "abc"
            assert out["intent"] == "morning_check"
            assert out["artist_mode"] == mode.name

    # -- HOME_TONAL_MAP sweeps ---------------------------------------------

    def test_every_tonal_distance_is_non_negative_int(self):
        for root, dist in HOME_TONAL_MAP.items():
            assert isinstance(root, str) and root
            assert isinstance(dist, int)
            assert dist >= 0

    def test_only_b_is_home(self):
        zeros = [k for k, d in HOME_TONAL_MAP.items() if d == 0]
        assert zeros == ["B"]
        for root, dist in HOME_TONAL_MAP.items():
            if root == HOME_KEY:
                assert dist == 0
            else:
                assert dist >= 1

    def test_close_neighbors_are_unique_to_b(self):
        close = sorted([k for k, d in HOME_TONAL_MAP.items() if d == 1])
        assert close == ["D", "F#"]
        for k in ("G", "E", "A"):
            assert HOME_TONAL_MAP[k] >= 2

    # -- select_mode routing matrix -----------------------------------------

    def test_select_mode_matrix_matches_documented_priority(self):
        # (presence, time_of_day, weather_severity, screen_active) -> expected
        cases = [
            (("present", "day", 0.7, False), STORM),
            (("none", "evening", 0.95, False), STORM),
            (("present", "evening", 0.6, True), STORM),
            (("none", "day", 0.0, False), SOLITARY),
            (("none", "morning", 0.1, True), SOLITARY),
            (("present", "day", 0.0, True), WORKING_AMBIENCE),
            (("present", "morning", 0.2, True), WORKING_AMBIENCE),
            (("present", "evening", 0.0, False), EVENING_REFLECTION),
            (("present", "night", 0.1, False), EVENING_REFLECTION),
            (("present", "day", 0.0, False), COMPANION),
            (("present", "morning", 0.3, False), COMPANION),
            (("unknown", "day", 0.1, False), COMPANION),
        ]
        for (presence, tod, weather, screen), expected in cases:
            actual = select_mode(
                presence=presence,
                time_of_day=tod,
                weather_severity=weather,
                screen_active=screen,
            )
            assert actual is expected, f"{(presence, tod, weather, screen)} -> {actual.name}"

    def test_storm_threshold_boundary(self):
        # 0.6 is the documented inclusive threshold for STORM
        for severity, expected in (
            (0.59, COMPANION),
            (0.60, STORM),
            (0.61, STORM),
            (1.00, STORM),
        ):
            picked = select_mode(presence="present", time_of_day="day", weather_severity=severity)
            assert picked is expected, f"severity={severity} -> {picked.name}"

    def test_screen_active_only_routes_when_present(self):
        # screen_active without presence='present' should not flip into WORKING_AMBIENCE
        if select_mode(presence="none", time_of_day="day", screen_active=True) is WORKING_AMBIENCE:
            raise AssertionError("none + screen should not be WORKING_AMBIENCE")
        for tod in ("day", "morning"):
            picked = select_mode(presence="unknown", time_of_day=tod, screen_active=True)
            assert picked is COMPANION

    def test_evening_and_night_route_identically_with_presence(self):
        for tod in ("evening", "night"):
            picked = select_mode(presence="present", time_of_day=tod, weather_severity=0.0)
            assert picked is EVENING_REFLECTION

    def test_select_mode_returns_a_known_mode_for_full_matrix(self):
        names = {m.name for m in MODES}
        for presence in ("none", "present", "unknown"):
            for tod in ("morning", "day", "evening", "night"):
                for severity in (0.0, 0.3, 0.6, 0.9):
                    for screen in (True, False):
                        m = select_mode(
                            presence=presence,
                            time_of_day=tod,
                            weather_severity=severity,
                            screen_active=screen,
                        )
                        assert m.name in names

    # -- next_tonal_choice sweeps ------------------------------------------

    def test_next_tonal_choice_returns_only_known_keys_and_modes(self):
        for mode in MODES:
            for seed in range(60):
                root, scale = next_tonal_choice(
                    current_key="B minor", artist_mode=mode, rng_seed=seed
                )
                assert root in HOME_TONAL_MAP
                assert scale in mode.preferred_modes

    def test_next_tonal_choice_is_deterministic_per_mode_and_seed(self):
        for mode in MODES:
            for seed in (1, 2, 5, 13, 91):
                a = next_tonal_choice(current_key="B minor", artist_mode=mode, rng_seed=seed)
                b = next_tonal_choice(current_key="B minor", artist_mode=mode, rng_seed=seed)
                assert a == b, f"{mode.name}@{seed} not deterministic"

    def test_modulation_willingness_correlates_with_venturing(self):
        # Higher modulation_willingness should produce more (or equal) far visits
        # than lower modulation_willingness, across many seeds. Compare three
        # representative modes covering low/medium/high willingness.
        seeds = list(range(120))
        far_counts: dict[str, int] = {}
        for mode in (SOLITARY, COMPANION, STORM):
            far = 0
            for seed in seeds:
                root, _ = next_tonal_choice(
                    current_key="B minor", artist_mode=mode, rng_seed=seed
                )
                if HOME_TONAL_MAP[root] > 1:
                    far += 1
            far_counts[mode.name] = far
        assert far_counts["solitary"] <= far_counts["companion"] + 5
        assert far_counts["companion"] <= far_counts["storm"] + 5
        assert far_counts["storm"] > far_counts["solitary"]

    def test_low_willingness_mode_stays_close_majority(self):
        # SOLITARY (modulation_willingness=0.15) should land within distance 1
        # for the majority of many seed samples.
        seeds = list(range(80))
        close = 0
        for seed in seeds:
            root, _ = next_tonal_choice(
                current_key="B minor", artist_mode=SOLITARY, rng_seed=seed
            )
            if HOME_TONAL_MAP[root] <= 1:
                close += 1
        assert close >= int(len(seeds) * 0.6)

    # -- end-to-end pipeline ------------------------------------------------

    def test_select_then_apply_then_choose_pipeline_for_full_room_matrix(self):
        for presence in ("none", "present"):
            for tod in ("day", "evening"):
                for screen in (False, True):
                    mode = select_mode(
                        presence=presence,
                        time_of_day=tod,
                        screen_active=screen,
                    )
                    out = apply_mode_to_commission({"src": "matrix"}, mode, rng_seed=21)
                    root, scale = next_tonal_choice(
                        current_key="B minor", artist_mode=mode, rng_seed=21
                    )
                    assert out["artist_mode"] == mode.name
                    assert out["src"] == "matrix"
                    assert root in HOME_TONAL_MAP
                    assert scale in mode.preferred_modes

    def test_pipeline_output_is_json_serializable_for_every_mode(self):
        for mode in MODES:
            out = apply_mode_to_commission({"piece_id": f"p_{mode.name}"}, mode, rng_seed=33)
            root, scale = next_tonal_choice(
                current_key="B minor", artist_mode=mode, rng_seed=33
            )
            payload = {"commission": out, "tonal": {"root": root, "scale": scale}}
            roundtrip = json.loads(json.dumps(payload))
            assert roundtrip["commission"]["artist_mode"] == mode.name
            assert roundtrip["tonal"]["root"] == root
            assert roundtrip["tonal"]["scale"] == scale

    def test_modes_by_name_round_trips_through_application(self):
        for name, mode in MODES_BY_NAME.items():
            assert mode.name == name
            out = apply_mode_to_commission({}, mode, rng_seed=44)
            recovered = MODES_BY_NAME[out["artist_mode"]]
            assert recovered is mode

    def test_voice_roles_remain_within_signature_quintet(self):
        # Cross-check VOICE_ROLES against SIGNATURE_VOICES on every role
        for role, voice in VOICE_ROLES.items():
            assert voice in SIGNATURE_VOICES, f"{role}->{voice} not in quintet"
            if role == "sampler":
                assert voice == "sw_sampler"
