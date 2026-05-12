"""Tests for installation-aware acoustic ecology policies."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools", "senseweave"))

from senseweave.acoustic_ecology import (
    AcousticEcologyPolicy,
    resolve_acoustic_ecology,
    resolve_ecology_mode,
)

# ── Sleep ceiling enforcement ────────────────────────────────────

SLEEP_MAX_LOUDNESS_DB = 40.0
SLEEP_MAX_ONSET_DENSITY = 0.5
SLEEP_MAX_CENTROID_HZ = 800.0
SLEEP_DENSITY_CEILING = 0.15
SLEEP_MAX_VOICES = 2

WIND_DOWN_MAX_LOUDNESS_DB = 48.0
WIND_DOWN_MAX_ONSET_DENSITY = 1.5
WIND_DOWN_MAX_CENTROID_HZ = 1200.0
WIND_DOWN_DENSITY_CEILING = 0.35
WIND_DOWN_MAX_VOICES = 3


def _sleep_policy(**overrides: object) -> AcousticEcologyPolicy:
    defaults = {
        "occupancy_state": "likely_asleep",
        "cadence_state": "sleep",
        "day_phase": "late_night",
        "room_activity": "quiet",
        "attention_state": "ambient",
        "dwell_time_s": 3600.0,
        "hour": 2,
    }
    defaults.update(overrides)
    return resolve_acoustic_ecology(**defaults)  # type: ignore[arg-type]


def _wind_down_policy(**overrides: object) -> AcousticEcologyPolicy:
    defaults = {
        "occupancy_state": "occupied_quiet",
        "cadence_state": "wind_down",
        "day_phase": "pre_sleep",
        "room_activity": "quiet",
        "attention_state": "ambient",
        "dwell_time_s": 1800.0,
        "hour": 22,
    }
    defaults.update(overrides)
    return resolve_acoustic_ecology(**defaults)  # type: ignore[arg-type]


# ── AC-1: Sleep ceilings are never exceeded ──────────────────────


def test_sleep_loudness_ceiling() -> None:
    policy = _sleep_policy()
    assert policy.max_loudness_db <= SLEEP_MAX_LOUDNESS_DB


def test_sleep_onset_density_ceiling() -> None:
    policy = _sleep_policy()
    assert policy.max_onset_density <= SLEEP_MAX_ONSET_DENSITY


def test_sleep_spectral_centroid_ceiling() -> None:
    policy = _sleep_policy()
    assert policy.max_spectral_centroid_hz <= SLEEP_MAX_CENTROID_HZ


def test_sleep_density_ceiling() -> None:
    policy = _sleep_policy()
    assert policy.density_ceiling <= SLEEP_DENSITY_CEILING


def test_sleep_voice_ceiling() -> None:
    policy = _sleep_policy()
    assert policy.max_voices <= SLEEP_MAX_VOICES


def test_sleep_ceiling_regardless_of_room_activity() -> None:
    """Even if room is somehow 'active' during sleep, ceilings hold."""
    policy = _sleep_policy(room_activity="active")
    assert policy.max_loudness_db <= SLEEP_MAX_LOUDNESS_DB
    assert policy.max_onset_density <= SLEEP_MAX_ONSET_DENSITY
    assert policy.max_spectral_centroid_hz <= SLEEP_MAX_CENTROID_HZ
    assert policy.density_ceiling <= SLEEP_DENSITY_CEILING


# ── AC-2: Wind-down ceilings are never exceeded ─────────────────


def test_wind_down_loudness_ceiling() -> None:
    policy = _wind_down_policy()
    assert policy.max_loudness_db <= WIND_DOWN_MAX_LOUDNESS_DB


def test_wind_down_onset_density_ceiling() -> None:
    policy = _wind_down_policy()
    assert policy.max_onset_density <= WIND_DOWN_MAX_ONSET_DENSITY


def test_wind_down_spectral_centroid_ceiling() -> None:
    policy = _wind_down_policy()
    assert policy.max_spectral_centroid_hz <= WIND_DOWN_MAX_CENTROID_HZ


def test_wind_down_density_ceiling() -> None:
    policy = _wind_down_policy()
    assert policy.density_ceiling <= WIND_DOWN_DENSITY_CEILING


def test_wind_down_voice_ceiling() -> None:
    policy = _wind_down_policy()
    assert policy.max_voices <= WIND_DOWN_MAX_VOICES


# ── AC-3: Ecology mode resolution ───────────────────────────────


def test_sleep_mode_from_likely_asleep() -> None:
    mode = resolve_ecology_mode(
        occupancy_state="likely_asleep",
        cadence_state="occupied_day",
        attention_state="ambient",
        room_activity="quiet",
    )
    assert mode == "sleep"


def test_sleep_mode_from_cadence_sleep() -> None:
    mode = resolve_ecology_mode(
        occupancy_state="occupied_quiet",
        cadence_state="sleep",
        attention_state="ambient",
        room_activity="quiet",
    )
    assert mode == "sleep"


def test_wind_down_mode() -> None:
    mode = resolve_ecology_mode(
        occupancy_state="occupied_quiet",
        cadence_state="wind_down",
        attention_state="ambient",
        room_activity="quiet",
    )
    assert mode == "wind_down"


def test_performance_overrides_wind_down() -> None:
    """Performance attention trumps wind_down cadence."""
    mode = resolve_ecology_mode(
        occupancy_state="occupied_active",
        cadence_state="wind_down",
        attention_state="performance",
        room_activity="active",
    )
    assert mode == "performance"


def test_away_practice_mode() -> None:
    mode = resolve_ecology_mode(
        occupancy_state="likely_away",
        cadence_state="away_practice",
        attention_state="ambient",
        room_activity="quiet",
    )
    assert mode == "away_practice"


def test_active_day_mode() -> None:
    mode = resolve_ecology_mode(
        occupancy_state="occupied_active",
        cadence_state="occupied_day",
        attention_state="attending",
        room_activity="active",
    )
    assert mode == "active_day"


def test_uncertain_presence_falls_to_quiet_occupied() -> None:
    mode = resolve_ecology_mode(
        occupancy_state="uncertain",
        cadence_state="occupied_day",
        attention_state="ambient",
        room_activity="quiet",
    )
    assert mode == "quiet_occupied"


def test_wake_ramp_maps_to_quiet_occupied() -> None:
    mode = resolve_ecology_mode(
        occupancy_state="occupied_quiet",
        cadence_state="wake_ramp",
        attention_state="ambient",
        room_activity="quiet",
    )
    assert mode == "quiet_occupied"


# ── AC-4: Environmental/keynote privilege ────────────────────────


def test_sleep_privileges_keynote_sounds() -> None:
    policy = _sleep_policy()
    assert policy.keynote_privilege > 0.5
    assert policy.generated_material_weight < 0.3


def test_wind_down_privileges_keynote_over_generated() -> None:
    policy = _wind_down_policy()
    assert policy.keynote_privilege > 0.4
    assert policy.generated_material_weight < 0.5


def test_away_practice_privileges_generated_material() -> None:
    policy = resolve_acoustic_ecology(
        occupancy_state="likely_away",
        cadence_state="away_practice",
        day_phase="mid_morning",
        room_activity="quiet",
        attention_state="ambient",
        dwell_time_s=0.0,
        hour=10,
    )
    assert policy.generated_material_weight > policy.keynote_privilege


def test_performance_mode_prefers_instrument_sources() -> None:
    policy = resolve_acoustic_ecology(
        occupancy_state="occupied_active",
        cadence_state="occupied_day",
        day_phase="late_afternoon",
        room_activity="active",
        attention_state="performance",
        dwell_time_s=300.0,
        hour=17,
    )
    assert policy.preferred_sources[0] == "theramini_in"


# ── AC-5: Source preferences by mode ────────────────────────────


def test_sleep_prefers_ambient_sources() -> None:
    policy = _sleep_policy()
    assert "room_mic" in policy.preferred_sources[:2]
    assert "self_bus" not in policy.preferred_sources[:2]


def test_away_practice_prefers_self_bus() -> None:
    policy = resolve_acoustic_ecology(
        occupancy_state="likely_away",
        cadence_state="away_practice",
        day_phase="mid_morning",
        room_activity="quiet",
        attention_state="ambient",
        dwell_time_s=0.0,
        hour=10,
    )
    assert policy.preferred_sources[0] == "self_bus"


# ── AC-6: Dwell time shaping ────────────────────────────────────


def test_short_dwell_softens_ceilings() -> None:
    """Fresh arrival gets slightly lower ceilings than settled occupant."""
    fresh = resolve_acoustic_ecology(
        occupancy_state="occupied_active",
        cadence_state="occupied_day",
        day_phase="mid_morning",
        room_activity="moderate",
        attention_state="attending",
        dwell_time_s=30.0,
        hour=10,
    )
    settled = resolve_acoustic_ecology(
        occupancy_state="occupied_active",
        cadence_state="occupied_day",
        day_phase="mid_morning",
        room_activity="moderate",
        attention_state="attending",
        dwell_time_s=3600.0,
        hour=10,
    )
    assert fresh.max_loudness_db <= settled.max_loudness_db
    assert fresh.density_ceiling <= settled.density_ceiling


# ── AC-7: Room activity shaping ─────────────────────────────────


def test_active_room_increases_keynote_privilege() -> None:
    quiet_room = resolve_acoustic_ecology(
        occupancy_state="occupied_active",
        cadence_state="occupied_day",
        day_phase="mid_morning",
        room_activity="quiet",
        attention_state="attending",
        dwell_time_s=600.0,
        hour=10,
    )
    active_room = resolve_acoustic_ecology(
        occupancy_state="occupied_active",
        cadence_state="occupied_day",
        day_phase="mid_morning",
        room_activity="active",
        attention_state="attending",
        dwell_time_s=600.0,
        hour=10,
    )
    assert active_room.keynote_privilege > quiet_room.keynote_privilege
    assert active_room.generated_material_weight < quiet_room.generated_material_weight


# ── AC-8: Day phase shaping ─────────────────────────────────────


def test_late_night_phase_tightens_brightness_even_if_not_sleep() -> None:
    """Late night occupied_day still has lower brightness than mid_morning."""
    late_night = resolve_acoustic_ecology(
        occupancy_state="occupied_quiet",
        cadence_state="occupied_day",
        day_phase="late_night",
        room_activity="quiet",
        attention_state="ambient",
        dwell_time_s=600.0,
        hour=3,
    )
    mid_morning = resolve_acoustic_ecology(
        occupancy_state="occupied_quiet",
        cadence_state="occupied_day",
        day_phase="mid_morning",
        room_activity="quiet",
        attention_state="ambient",
        dwell_time_s=600.0,
        hour=10,
    )
    assert late_night.max_spectral_centroid_hz < mid_morning.max_spectral_centroid_hz


# ── AC-9: Silence windows ───────────────────────────────────────


def test_sleep_has_largest_silence_windows() -> None:
    policy = _sleep_policy()
    assert policy.silence_probability >= 0.6
    assert policy.min_silence_gap_s >= 30.0


def test_away_practice_has_smallest_silence_windows() -> None:
    policy = resolve_acoustic_ecology(
        occupancy_state="likely_away",
        cadence_state="away_practice",
        day_phase="mid_morning",
        room_activity="quiet",
        attention_state="ambient",
        dwell_time_s=0.0,
        hour=10,
    )
    assert policy.silence_probability <= 0.2
    assert policy.min_silence_gap_s <= 10.0


# ── AC-10: Policy is frozen dataclass ───────────────────────────


def test_policy_is_immutable() -> None:
    policy = _sleep_policy()
    try:
        policy.max_loudness_db = 100.0  # type: ignore[misc]
        raise AssertionError("Should have raised FrozenInstanceError")
    except AttributeError:
        pass  # expected for frozen dataclass


# ── AC-11: All ecology modes produce valid policies ──────────────


def test_all_modes_produce_valid_positive_values() -> None:
    scenarios = [
        {"occupancy_state": "likely_asleep", "cadence_state": "sleep",
         "day_phase": "late_night", "room_activity": "quiet",
         "attention_state": "ambient", "dwell_time_s": 3600.0, "hour": 2},
        {"occupancy_state": "occupied_quiet", "cadence_state": "wind_down",
         "day_phase": "pre_sleep", "room_activity": "quiet",
         "attention_state": "ambient", "dwell_time_s": 1800.0, "hour": 22},
        {"occupancy_state": "occupied_active", "cadence_state": "occupied_day",
         "day_phase": "mid_morning", "room_activity": "active",
         "attention_state": "attending", "dwell_time_s": 600.0, "hour": 10},
        {"occupancy_state": "likely_away", "cadence_state": "away_practice",
         "day_phase": "mid_morning", "room_activity": "quiet",
         "attention_state": "ambient", "dwell_time_s": 0.0, "hour": 10},
        {"occupancy_state": "occupied_active", "cadence_state": "occupied_day",
         "day_phase": "late_afternoon", "room_activity": "active",
         "attention_state": "performance", "dwell_time_s": 300.0, "hour": 17},
        {"occupancy_state": "uncertain", "cadence_state": "occupied_day",
         "day_phase": "afternoon_dip", "room_activity": "quiet",
         "attention_state": "ambient", "dwell_time_s": 120.0, "hour": 14},
    ]
    for kwargs in scenarios:
        policy = resolve_acoustic_ecology(**kwargs)  # type: ignore[arg-type]
        assert policy.max_loudness_db > 0.0, f"bad loudness for {kwargs}"
        assert policy.max_onset_density > 0.0, f"bad density for {kwargs}"
        assert policy.max_spectral_centroid_hz > 0.0, f"bad centroid for {kwargs}"
        assert 0.0 <= policy.silence_probability <= 1.0, f"bad silence_prob for {kwargs}"
        assert policy.min_silence_gap_s >= 0.0, f"bad min_gap for {kwargs}"
        assert policy.max_silence_gap_s >= policy.min_silence_gap_s, f"bad gap order for {kwargs}"
        assert 0.0 <= policy.keynote_privilege <= 1.0, f"bad keynote for {kwargs}"
        assert 0.0 <= policy.generated_material_weight <= 1.0, f"bad gen_weight for {kwargs}"
        assert 0.0 <= policy.density_ceiling <= 1.0, f"bad density_ceiling for {kwargs}"
        assert policy.max_voices >= 1, f"bad voices for {kwargs}"
        assert len(policy.preferred_sources) > 0, f"no sources for {kwargs}"
        assert len(policy.reasons) > 0, f"no reasons for {kwargs}"


# ── AC-12: Performance during wind-down hours ────────────────────


def test_performance_during_wind_down_hours_is_not_wind_down_constrained() -> None:
    """Active performance overrides wind-down but stays below full active_day."""
    perf = resolve_acoustic_ecology(
        occupancy_state="occupied_active",
        cadence_state="wind_down",
        day_phase="pre_sleep",
        room_activity="active",
        attention_state="performance",
        dwell_time_s=300.0,
        hour=23,
    )
    wind = _wind_down_policy()
    assert perf.ecology_mode == "performance"
    assert perf.max_loudness_db > wind.max_loudness_db
    assert perf.density_ceiling > wind.density_ceiling


class TestAcousticEcologyEndToEnd:
    """Depth-2 coverage for context -> policy acoustic ecology flows."""

    def test_daily_context_sequence_resolves_expected_modes(self) -> None:
        scenarios = [
            ("sleep", _sleep_policy()),
            ("wind_down", _wind_down_policy()),
            ("quiet_occupied", resolve_acoustic_ecology(
                occupancy_state="occupied_quiet",
                cadence_state="wake_ramp",
                day_phase="morning_activation",
                room_activity="quiet",
                attention_state="ambient",
                dwell_time_s=90.0,
                hour=7,
            )),
            ("active_day", resolve_acoustic_ecology(
                occupancy_state="occupied_active",
                cadence_state="occupied_day",
                day_phase="mid_morning",
                room_activity="moderate",
                attention_state="attending",
                dwell_time_s=600.0,
                hour=10,
            )),
            ("performance", resolve_acoustic_ecology(
                occupancy_state="occupied_active",
                cadence_state="wind_down",
                day_phase="pre_sleep",
                room_activity="active",
                attention_state="performance",
                dwell_time_s=300.0,
                hour=23,
            )),
            ("away_practice", resolve_acoustic_ecology(
                occupancy_state="likely_away",
                cadence_state="away_practice",
                day_phase="mid_morning",
                room_activity="quiet",
                attention_state="ambient",
                dwell_time_s=0.0,
                hour=10,
            )),
        ]
        for expected_mode, policy in scenarios:
            assert policy.ecology_mode == expected_mode
            assert policy.reasons[0] == f"ecology_mode={expected_mode}"

    def test_mode_resolution_priority_table(self) -> None:
        scenarios = [
            ({"occupancy_state": "likely_asleep", "cadence_state": "wind_down",
              "attention_state": "performance", "room_activity": "active"}, "sleep"),
            ({"occupancy_state": "occupied_active", "cadence_state": "wind_down",
              "attention_state": "ambient", "room_activity": "active"}, "wind_down"),
            ({"occupancy_state": "likely_away", "cadence_state": "away_practice",
              "attention_state": "performance", "room_activity": "quiet"}, "performance"),
            ({"occupancy_state": "likely_away", "cadence_state": "occupied_day",
              "attention_state": "ambient", "room_activity": "quiet"}, "away_practice"),
            ({"occupancy_state": "occupied_active", "cadence_state": "occupied_day",
              "attention_state": "attending", "room_activity": "moderate"}, "active_day"),
        ]
        for kwargs, expected_mode in scenarios:
            mode = resolve_ecology_mode(**kwargs)  # type: ignore[arg-type]
            assert mode == expected_mode

    def test_source_leaders_match_each_ecology_mode(self) -> None:
        scenarios = [
            (_sleep_policy(), "room_mic"),
            (_wind_down_policy(), "room_mic"),
            (resolve_acoustic_ecology(
                occupancy_state="occupied_quiet",
                cadence_state="occupied_day",
                day_phase="mid_morning",
                room_activity="quiet",
                attention_state="ambient",
                dwell_time_s=600.0,
                hour=10,
            ), "room_mic"),
            (resolve_acoustic_ecology(
                occupancy_state="occupied_active",
                cadence_state="occupied_day",
                day_phase="mid_morning",
                room_activity="active",
                attention_state="attending",
                dwell_time_s=600.0,
                hour=10,
            ), "room_mic"),
            (resolve_acoustic_ecology(
                occupancy_state="likely_away",
                cadence_state="away_practice",
                day_phase="mid_morning",
                room_activity="quiet",
                attention_state="ambient",
                dwell_time_s=600.0,
                hour=10,
            ), "self_bus"),
            (resolve_acoustic_ecology(
                occupancy_state="occupied_active",
                cadence_state="occupied_day",
                day_phase="late_afternoon",
                room_activity="active",
                attention_state="performance",
                dwell_time_s=600.0,
                hour=17,
            ), "theramini_in"),
        ]
        for policy, expected_source in scenarios:
            assert policy.preferred_sources[0] == expected_source
            assert len(policy.preferred_sources) == len(set(policy.preferred_sources))

    def test_policy_weights_stay_normalized_for_daily_scenarios(self) -> None:
        scenarios = [_sleep_policy(), _wind_down_policy()]
        for hour, phase in [(8, "morning_activation"), (12, "midday"), (17, "late_afternoon")]:
            scenarios.append(resolve_acoustic_ecology(
                occupancy_state="occupied_active",
                cadence_state="occupied_day",
                day_phase=phase,
                room_activity="moderate",
                attention_state="attending",
                dwell_time_s=900.0,
                hour=hour,
            ))
        for policy in scenarios:
            assert 0.0 <= policy.keynote_privilege <= 1.0
            assert 0.0 <= policy.generated_material_weight <= 1.0
            assert 0.0 <= policy.density_ceiling <= 1.0

    def test_silence_windows_are_ordered_for_all_modes(self) -> None:
        policies = [
            _sleep_policy(),
            _wind_down_policy(),
            resolve_acoustic_ecology(
                occupancy_state="occupied_quiet",
                cadence_state="occupied_day",
                day_phase="mid_morning",
                room_activity="quiet",
                attention_state="ambient",
                dwell_time_s=600.0,
                hour=10,
            ),
            resolve_acoustic_ecology(
                occupancy_state="occupied_active",
                cadence_state="occupied_day",
                day_phase="mid_morning",
                room_activity="active",
                attention_state="attending",
                dwell_time_s=600.0,
                hour=10,
            ),
            resolve_acoustic_ecology(
                occupancy_state="likely_away",
                cadence_state="away_practice",
                day_phase="mid_morning",
                room_activity="quiet",
                attention_state="ambient",
                dwell_time_s=600.0,
                hour=10,
            ),
        ]
        for policy in policies:
            assert 0.0 <= policy.silence_probability <= 1.0
            assert policy.min_silence_gap_s <= policy.max_silence_gap_s
            assert policy.min_silence_gap_s >= 0.0

    def test_sleep_hard_ceiling_table_is_enforced(self) -> None:
        policy = _sleep_policy(room_activity="active", dwell_time_s=7200.0)
        ceilings = {
            "max_loudness_db": SLEEP_MAX_LOUDNESS_DB,
            "max_onset_density": SLEEP_MAX_ONSET_DENSITY,
            "max_spectral_centroid_hz": SLEEP_MAX_CENTROID_HZ,
            "density_ceiling": SLEEP_DENSITY_CEILING,
            "max_voices": SLEEP_MAX_VOICES,
        }
        for field_name, ceiling in ceilings.items():
            assert getattr(policy, field_name) <= ceiling

    def test_wind_down_hard_ceiling_table_is_enforced(self) -> None:
        policy = _wind_down_policy(room_activity="active", dwell_time_s=7200.0)
        ceilings = {
            "max_loudness_db": WIND_DOWN_MAX_LOUDNESS_DB,
            "max_onset_density": WIND_DOWN_MAX_ONSET_DENSITY,
            "max_spectral_centroid_hz": WIND_DOWN_MAX_CENTROID_HZ,
            "density_ceiling": WIND_DOWN_DENSITY_CEILING,
            "max_voices": WIND_DOWN_MAX_VOICES,
        }
        for field_name, ceiling in ceilings.items():
            assert getattr(policy, field_name) <= ceiling

    def test_sleep_caps_survive_room_activity_sweep(self) -> None:
        for activity in ["quiet", "moderate", "active"]:
            policy = _sleep_policy(room_activity=activity, dwell_time_s=7200.0)
            assert policy.max_loudness_db <= SLEEP_MAX_LOUDNESS_DB
            assert policy.max_spectral_centroid_hz <= SLEEP_MAX_CENTROID_HZ
            assert policy.max_voices <= SLEEP_MAX_VOICES

    def test_wind_down_caps_survive_room_activity_sweep(self) -> None:
        for activity in ["quiet", "moderate", "active"]:
            policy = _wind_down_policy(room_activity=activity, dwell_time_s=7200.0)
            assert policy.max_loudness_db <= WIND_DOWN_MAX_LOUDNESS_DB
            assert policy.max_spectral_centroid_hz <= WIND_DOWN_MAX_CENTROID_HZ
            assert policy.max_voices <= WIND_DOWN_MAX_VOICES

    def test_day_phase_brightness_tightens_late_contexts(self) -> None:
        baseline = resolve_acoustic_ecology(
            occupancy_state="occupied_quiet",
            cadence_state="occupied_day",
            day_phase="mid_morning",
            room_activity="quiet",
            attention_state="ambient",
            dwell_time_s=600.0,
            hour=10,
        )
        for phase in ["late_night", "pre_dawn", "afternoon_dip", "pre_sleep"]:
            policy = resolve_acoustic_ecology(
                occupancy_state="occupied_quiet",
                cadence_state="occupied_day",
                day_phase=phase,
                room_activity="quiet",
                attention_state="ambient",
                dwell_time_s=600.0,
                hour=3,
            )
            assert policy.max_spectral_centroid_hz < baseline.max_spectral_centroid_hz

    def test_unknown_day_phase_uses_neutral_brightness_path(self) -> None:
        baseline = resolve_acoustic_ecology(
            occupancy_state="occupied_active",
            cadence_state="occupied_day",
            day_phase="mid_morning",
            room_activity="moderate",
            attention_state="attending",
            dwell_time_s=600.0,
            hour=10,
        )
        unknown = resolve_acoustic_ecology(
            occupancy_state="occupied_active",
            cadence_state="occupied_day",
            day_phase="unlisted_phase",
            room_activity="moderate",
            attention_state="attending",
            dwell_time_s=600.0,
            hour=10,
        )
        for field_name in ["max_spectral_centroid_hz", "max_loudness_db", "density_ceiling"]:
            assert getattr(unknown, field_name) == getattr(baseline, field_name)

    def test_dwell_time_relaxes_non_hard_modes_in_order(self) -> None:
        policies = []
        for dwell in [30.0, 600.0, 3600.0]:
            policies.append(resolve_acoustic_ecology(
                occupancy_state="occupied_active",
                cadence_state="occupied_day",
                day_phase="mid_morning",
                room_activity="moderate",
                attention_state="attending",
                dwell_time_s=dwell,
                hour=10,
            ))
        assert policies[0].max_loudness_db < policies[1].max_loudness_db
        assert policies[1].max_loudness_db < policies[2].max_loudness_db
        assert policies[0].density_ceiling < policies[2].density_ceiling

    def test_dwell_time_does_not_relax_sleep_or_wind_down_caps(self) -> None:
        scenarios = [
            (_sleep_policy(dwell_time_s=30.0), _sleep_policy(dwell_time_s=7200.0)),
            (_wind_down_policy(dwell_time_s=30.0), _wind_down_policy(dwell_time_s=7200.0)),
        ]
        for fresh, settled in scenarios:
            assert fresh.max_loudness_db == settled.max_loudness_db
            assert fresh.density_ceiling == settled.density_ceiling
            assert fresh.max_voices == settled.max_voices

    def test_room_activity_shifts_keynote_and_generated_weights(self) -> None:
        policies = []
        for activity in ["quiet", "moderate", "active"]:
            policies.append(resolve_acoustic_ecology(
                occupancy_state="occupied_active",
                cadence_state="occupied_day",
                day_phase="mid_morning",
                room_activity=activity,
                attention_state="attending",
                dwell_time_s=600.0,
                hour=10,
            ))
        assert policies[0].keynote_privilege < policies[1].keynote_privilege
        assert policies[1].keynote_privilege < policies[2].keynote_privilege
        assert policies[0].generated_material_weight > policies[2].generated_material_weight

    def test_room_activity_reason_metadata_records_modifier(self) -> None:
        for activity in ["moderate", "active"]:
            policy = resolve_acoustic_ecology(
                occupancy_state="occupied_active",
                cadence_state="occupied_day",
                day_phase="mid_morning",
                room_activity=activity,
                attention_state="attending",
                dwell_time_s=600.0,
                hour=10,
            )
            assert f"room_activity={activity}" in policy.reasons

    def test_day_phase_reason_metadata_records_modifier(self) -> None:
        for phase in ["late_night", "pre_dawn", "pre_sleep"]:
            policy = resolve_acoustic_ecology(
                occupancy_state="occupied_quiet",
                cadence_state="occupied_day",
                day_phase=phase,
                room_activity="quiet",
                attention_state="ambient",
                dwell_time_s=600.0,
                hour=3,
            )
            assert any(reason.startswith("day_phase_centroid_scale=") for reason in policy.reasons)

    def test_dwell_reason_metadata_records_non_nominal_modifiers(self) -> None:
        for dwell_time_s in [30.0, 3600.0]:
            policy = resolve_acoustic_ecology(
                occupancy_state="occupied_active",
                cadence_state="occupied_day",
                day_phase="mid_morning",
                room_activity="quiet",
                attention_state="attending",
                dwell_time_s=dwell_time_s,
                hour=10,
            )
            assert any(reason.startswith("dwell_modifier=") for reason in policy.reasons)

    def test_conservative_presence_contexts_stay_quiet_occupied(self) -> None:
        scenarios = [
            {"occupancy_state": "uncertain", "cadence_state": "occupied_day"},
            {"occupancy_state": "occupied_quiet", "cadence_state": "wake_ramp"},
        ]
        for scenario in scenarios:
            policy = resolve_acoustic_ecology(
                occupancy_state=scenario["occupancy_state"],
                cadence_state=scenario["cadence_state"],
                day_phase="morning_activation",
                room_activity="quiet",
                attention_state="ambient",
                dwell_time_s=60.0,
                hour=7,
            )
            assert policy.ecology_mode == "quiet_occupied"
            assert policy.generated_material_weight > policy.keynote_privilege

    def test_performance_overrides_wind_down_but_stays_bounded(self) -> None:
        performance = resolve_acoustic_ecology(
            occupancy_state="occupied_active",
            cadence_state="wind_down",
            day_phase="pre_sleep",
            room_activity="active",
            attention_state="performance",
            dwell_time_s=300.0,
            hour=23,
        )
        comparisons = [_wind_down_policy(), resolve_acoustic_ecology(
            occupancy_state="likely_away",
            cadence_state="away_practice",
            day_phase="mid_morning",
            room_activity="quiet",
            attention_state="ambient",
            dwell_time_s=3600.0,
            hour=10,
        )]
        for policy in comparisons:
            assert performance.ecology_mode != "wind_down"
            assert performance.max_loudness_db > comparisons[0].max_loudness_db
            assert performance.max_loudness_db < comparisons[1].max_loudness_db
            assert policy.max_loudness_db > 0.0

    def test_keynote_privilege_tracks_environmental_modes(self) -> None:
        policies = [_sleep_policy(), _wind_down_policy(), resolve_acoustic_ecology(
            occupancy_state="occupied_active",
            cadence_state="occupied_day",
            day_phase="mid_morning",
            room_activity="active",
            attention_state="attending",
            dwell_time_s=600.0,
            hour=10,
        ), resolve_acoustic_ecology(
            occupancy_state="likely_away",
            cadence_state="away_practice",
            day_phase="mid_morning",
            room_activity="quiet",
            attention_state="ambient",
            dwell_time_s=600.0,
            hour=10,
        )]
        for earlier, later in zip(policies, policies[1:]):
            assert earlier.keynote_privilege > later.keynote_privilege

    def test_away_practice_has_highest_generated_material_weight(self) -> None:
        policies = [
            _sleep_policy(),
            _wind_down_policy(),
            resolve_acoustic_ecology(
                occupancy_state="occupied_quiet",
                cadence_state="occupied_day",
                day_phase="mid_morning",
                room_activity="quiet",
                attention_state="ambient",
                dwell_time_s=600.0,
                hour=10,
            ),
            resolve_acoustic_ecology(
                occupancy_state="likely_away",
                cadence_state="away_practice",
                day_phase="mid_morning",
                room_activity="quiet",
                attention_state="ambient",
                dwell_time_s=600.0,
                hour=10,
            ),
        ]
        away_weight = policies[-1].generated_material_weight
        for policy in policies[:-1]:
            assert away_weight > policy.generated_material_weight

    def test_policy_dataclass_fields_are_populated(self) -> None:
        policy = resolve_acoustic_ecology(
            occupancy_state="occupied_active",
            cadence_state="occupied_day",
            day_phase="mid_morning",
            room_activity="active",
            attention_state="attending",
            dwell_time_s=600.0,
            hour=10,
        )
        for field_name in AcousticEcologyPolicy.__dataclass_fields__:
            value = getattr(policy, field_name)
            assert value is not None

    def test_reasons_begin_with_resolved_mode_for_mode_table(self) -> None:
        for mode, policy in [
            ("sleep", _sleep_policy()),
            ("wind_down", _wind_down_policy()),
            ("away_practice", resolve_acoustic_ecology(
                occupancy_state="likely_away",
                cadence_state="away_practice",
                day_phase="mid_morning",
                room_activity="quiet",
                attention_state="ambient",
                dwell_time_s=600.0,
                hour=10,
            )),
        ]:
            assert policy.reasons[0] == f"ecology_mode={mode}"
            assert len(policy.reasons) >= 1

    def test_source_lists_are_unique_and_nonempty(self) -> None:
        policies = [_sleep_policy(), _wind_down_policy()]
        for attention_state in ["ambient", "attending", "performance"]:
            policies.append(resolve_acoustic_ecology(
                occupancy_state="occupied_active",
                cadence_state="occupied_day",
                day_phase="mid_morning",
                room_activity="active",
                attention_state=attention_state,
                dwell_time_s=600.0,
                hour=10,
            ))
        for policy in policies:
            assert len(policy.preferred_sources) > 0
            assert len(policy.preferred_sources) == len(set(policy.preferred_sources))

    def test_loudness_ceilings_increase_from_sleep_to_away(self) -> None:
        policies = [_sleep_policy(), _wind_down_policy(), resolve_acoustic_ecology(
            occupancy_state="occupied_quiet",
            cadence_state="occupied_day",
            day_phase="mid_morning",
            room_activity="quiet",
            attention_state="ambient",
            dwell_time_s=600.0,
            hour=10,
        ), resolve_acoustic_ecology(
            occupancy_state="likely_away",
            cadence_state="away_practice",
            day_phase="mid_morning",
            room_activity="quiet",
            attention_state="ambient",
            dwell_time_s=600.0,
            hour=10,
        )]
        for quieter, louder in zip(policies, policies[1:]):
            assert quieter.max_loudness_db < louder.max_loudness_db

    def test_voice_counts_match_mode_intensity_table(self) -> None:
        policies = [
            ("sleep", _sleep_policy(), SLEEP_MAX_VOICES),
            ("wind_down", _wind_down_policy(), WIND_DOWN_MAX_VOICES),
            ("quiet_occupied", resolve_acoustic_ecology(
                occupancy_state="occupied_quiet",
                cadence_state="occupied_day",
                day_phase="mid_morning",
                room_activity="quiet",
                attention_state="ambient",
                dwell_time_s=600.0,
                hour=10,
            ), 4),
            ("away_practice", resolve_acoustic_ecology(
                occupancy_state="likely_away",
                cadence_state="away_practice",
                day_phase="mid_morning",
                room_activity="quiet",
                attention_state="ambient",
                dwell_time_s=600.0,
                hour=10,
            ), 6),
        ]
        for expected_mode, policy, expected_voices in policies:
            assert policy.ecology_mode == expected_mode
            assert policy.max_voices == expected_voices

    def test_contexts_produce_distinct_policy_profiles(self) -> None:
        profiles = []
        for policy in [_sleep_policy(), _wind_down_policy(), resolve_acoustic_ecology(
            occupancy_state="occupied_active",
            cadence_state="occupied_day",
            day_phase="mid_morning",
            room_activity="active",
            attention_state="attending",
            dwell_time_s=600.0,
            hour=10,
        ), resolve_acoustic_ecology(
            occupancy_state="likely_away",
            cadence_state="away_practice",
            day_phase="mid_morning",
            room_activity="quiet",
            attention_state="ambient",
            dwell_time_s=600.0,
            hour=10,
        )]:
            profiles.append((
                policy.ecology_mode,
                policy.max_loudness_db,
                policy.density_ceiling,
                policy.preferred_sources[0],
            ))
        assert len(set(profiles)) == len(profiles)

    def test_silence_windows_shrink_from_sleep_to_away(self) -> None:
        policies = [_sleep_policy(), _wind_down_policy(), resolve_acoustic_ecology(
            occupancy_state="occupied_quiet",
            cadence_state="occupied_day",
            day_phase="mid_morning",
            room_activity="quiet",
            attention_state="ambient",
            dwell_time_s=600.0,
            hour=10,
        ), resolve_acoustic_ecology(
            occupancy_state="likely_away",
            cadence_state="away_practice",
            day_phase="mid_morning",
            room_activity="quiet",
            attention_state="ambient",
            dwell_time_s=600.0,
            hour=10,
        )]
        for earlier, later in zip(policies, policies[1:]):
            assert earlier.silence_probability > later.silence_probability
            assert earlier.max_silence_gap_s > later.max_silence_gap_s

    def test_keynote_modes_prioritize_environmental_sources(self) -> None:
        for policy in [_sleep_policy(), _wind_down_policy()]:
            first_sources = set(policy.preferred_sources[:3])
            assert first_sources <= {"room_mic", "garden_mic", "contact_mic"}
            assert policy.keynote_privilege > policy.generated_material_weight

    def test_away_practice_prioritizes_generated_self_bus_flow(self) -> None:
        for hour in [9, 12, 15]:
            policy = resolve_acoustic_ecology(
                occupancy_state="likely_away",
                cadence_state="away_practice",
                day_phase="mid_morning",
                room_activity="quiet",
                attention_state="ambient",
                dwell_time_s=3600.0,
                hour=hour,
            )
            assert policy.preferred_sources[0] == "self_bus"
            assert policy.generated_material_weight > policy.keynote_privilege
