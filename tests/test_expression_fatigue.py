"""Tests for the per-voice expression fatigue counter (CC-080)."""
from __future__ import annotations

import math
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools"))

from expression.fatigue import (
    FATIGUE_HALF_LIFE_SECONDS,
    FATIGUE_REDUCTION,
    FATIGUE_THRESHOLD,
    FatigueCounter,
    fatigue_decay_factor,
    fatigue_multiplier,
)


def test_half_life_matches_prd_thirty_seconds() -> None:
    # PRD §7.5.2 / CC-080: half-life ~30 seconds.
    assert FATIGUE_HALF_LIFE_SECONDS == 30.0


def test_decay_factor_is_one_for_zero_or_negative_elapsed() -> None:
    assert fatigue_decay_factor(0.0) == 1.0
    assert fatigue_decay_factor(-5.0) == 1.0


def test_decay_factor_at_one_half_life_is_one_half() -> None:
    assert math.isclose(fatigue_decay_factor(FATIGUE_HALF_LIFE_SECONDS), 0.5, rel_tol=1e-12)


def test_decay_factor_halves_each_half_life() -> None:
    # 30s: 1/2, 60s: 1/4, 90s: 1/8, 120s: 1/16.
    for n in range(1, 5):
        elapsed = n * FATIGUE_HALF_LIFE_SECONDS
        assert math.isclose(
            fatigue_decay_factor(elapsed), 0.5 ** n, rel_tol=1e-12
        )


def test_decay_factor_rejects_non_positive_half_life() -> None:
    with pytest.raises(ValueError):
        fatigue_decay_factor(1.0, half_life_seconds=0.0)
    with pytest.raises(ValueError):
        fatigue_decay_factor(1.0, half_life_seconds=-1.0)


def test_counter_initial_value_is_zero_for_unknown_voice() -> None:
    counter = FatigueCounter()
    assert counter.value("violin", now=0.0) == 0.0
    assert counter.value("violin", now=1000.0) == 0.0


def test_add_note_increments_counter_from_zero() -> None:
    counter = FatigueCounter()
    new_value = counter.add_note("violin", 0.4, now=0.0)
    assert new_value == 0.4
    assert counter.value("violin", now=0.0) == 0.4


def test_value_decays_with_thirty_second_half_life() -> None:
    counter = FatigueCounter()
    counter.add_note("violin", 1.0, now=0.0)

    # Synthetic single-note stream: no further input, just observe decay.
    assert math.isclose(counter.value("violin", now=30.0), 0.5, rel_tol=1e-12)
    assert math.isclose(counter.value("violin", now=60.0), 0.25, rel_tol=1e-12)
    assert math.isclose(counter.value("violin", now=90.0), 0.125, rel_tol=1e-12)


def test_value_is_non_mutating() -> None:
    counter = FatigueCounter()
    counter.add_note("violin", 1.0, now=0.0)
    # Reading at t=30 must not alter what we see at t=60.
    counter.value("violin", now=30.0)
    assert math.isclose(counter.value("violin", now=60.0), 0.25, rel_tol=1e-12)


def test_add_note_decays_existing_value_before_adding_new_load() -> None:
    counter = FatigueCounter()
    counter.add_note("violin", 1.0, now=0.0)
    # 30 seconds later: prior load decayed to 0.5, plus a new 0.4 note.
    new_value = counter.add_note("violin", 0.4, now=30.0)
    assert math.isclose(new_value, 0.5 + 0.4, rel_tol=1e-12)


def test_synthetic_note_stream_matches_closed_form_decay() -> None:
    # Drive the counter with a synthetic stream of notes at known times and
    # loads, then compare the final value against the closed-form sum of
    # each contribution decayed independently.
    counter = FatigueCounter()
    stream = [
        ("violin", 0.0, 0.5),
        ("violin", 10.0, 0.3),
        ("violin", 25.0, 0.7),
        ("violin", 55.0, 0.2),
    ]
    for voice, t, load in stream:
        counter.add_note(voice, load, now=t)

    observation_time = 90.0
    expected = sum(
        load * fatigue_decay_factor(observation_time - t)
        for _, t, load in stream
    )
    assert math.isclose(counter.value("violin", now=observation_time), expected, rel_tol=1e-12)


def test_counter_state_is_isolated_per_voice() -> None:
    counter = FatigueCounter()
    counter.add_note("violin", 1.0, now=0.0)
    counter.add_note("cello", 0.2, now=0.0)
    # Cello load must not leak into violin's counter (and vice versa).
    assert counter.value("violin", now=0.0) == 1.0
    assert counter.value("cello", now=0.0) == 0.2


def test_add_note_clips_negative_load_to_zero() -> None:
    # A note cannot reduce fatigue — that's what the decay envelope is for.
    counter = FatigueCounter()
    counter.add_note("violin", 0.5, now=0.0)
    new_value = counter.add_note("violin", -10.0, now=0.0)
    assert new_value == 0.5


def test_reset_clears_one_voice() -> None:
    counter = FatigueCounter()
    counter.add_note("violin", 1.0, now=0.0)
    counter.add_note("cello", 0.5, now=0.0)
    counter.reset("violin")
    assert counter.value("violin", now=0.0) == 0.0
    assert counter.value("cello", now=0.0) == 0.5


def test_reset_all_clears_every_voice() -> None:
    counter = FatigueCounter()
    counter.add_note("violin", 1.0, now=0.0)
    counter.add_note("cello", 0.5, now=0.0)
    counter.reset()
    assert counter.value("violin", now=0.0) == 0.0
    assert counter.value("cello", now=0.0) == 0.0


def test_custom_half_life_is_respected_end_to_end() -> None:
    counter = FatigueCounter(half_life_seconds=10.0)
    counter.add_note("violin", 1.0, now=0.0)
    assert math.isclose(counter.value("violin", now=10.0), 0.5, rel_tol=1e-12)
    assert math.isclose(counter.value("violin", now=20.0), 0.25, rel_tol=1e-12)


def test_counter_rejects_non_positive_half_life() -> None:
    with pytest.raises(ValueError):
        FatigueCounter(half_life_seconds=0.0)
    with pytest.raises(ValueError):
        FatigueCounter(half_life_seconds=-1.0)


def test_threshold_and_reduction_defaults_match_prd() -> None:
    # PRD §7.5.2 / CC-081: default threshold 0.7, default reduction 0.5.
    assert FATIGUE_THRESHOLD == 0.7
    assert FATIGUE_REDUCTION == 0.5


def test_multiplier_is_one_below_threshold() -> None:
    # Below 0.7 the voice is "fresh" — nominal expression magnitudes pass through.
    env = {"CYPHERCLAW_V2_FATIGUE": "1"}
    assert fatigue_multiplier(0.0, env=env) == 1.0
    assert fatigue_multiplier(0.5, env=env) == 1.0
    assert fatigue_multiplier(FATIGUE_THRESHOLD, env=env) == 1.0


def test_multiplier_reduces_above_threshold() -> None:
    # Just above the threshold: 1 - 0.5 * 0.70001 ≈ 0.65 — already a reduction.
    env = {"CYPHERCLAW_V2_FATIGUE": "1"}
    just_above = fatigue_multiplier(FATIGUE_THRESHOLD + 1e-6, env=env)
    assert just_above < 1.0

    # At a counter value of 1.0 the multiplier hits its floor of 0.5.
    assert math.isclose(fatigue_multiplier(1.0, env=env), 0.5, rel_tol=1e-12)


def test_multiplier_clamps_counter_at_one() -> None:
    # A counter value above 1.0 saturates — the multiplier does not keep falling.
    env = {"CYPHERCLAW_V2_FATIGUE": "1"}
    assert math.isclose(fatigue_multiplier(2.5, env=env), 0.5, rel_tol=1e-12)


def test_multiplier_honors_custom_threshold_and_reduction() -> None:
    # Custom threshold raises the cutoff; custom reduction changes the slope.
    env = {"CYPHERCLAW_V2_FATIGUE": "1"}
    assert fatigue_multiplier(0.8, threshold=0.9, env=env) == 1.0
    assert math.isclose(
        fatigue_multiplier(1.0, threshold=0.5, reduction=0.25, env=env),
        0.75,
        rel_tol=1e-12,
    )


def test_multiplier_applied_to_counter_value_above_and_below_threshold() -> None:
    # CC-081 acceptance: multiplier applied above threshold, not applied below.
    # We must enable the flag for this test as it's now gated by default.
    env = {"CYPHERCLAW_V2_FATIGUE": "1"}
    counter = FatigueCounter()
    counter.add_note("violin", 0.3, now=0.0)
    below = counter.value("violin", now=0.0)
    assert below < FATIGUE_THRESHOLD
    assert fatigue_multiplier(below, env=env) == 1.0

    counter.add_note("cello", 0.9, now=0.0)
    above = counter.value("cello", now=0.0)
    assert above > FATIGUE_THRESHOLD
    assert fatigue_multiplier(above, env=env) < 1.0


def test_long_silence_recovery_to_zero() -> None:
    # CC-082: Long silences allow the counter to recover toward 0.
    counter = FatigueCounter()
    counter.add_note("violin", 1.0, now=0.0)
    
    # 10 half-lives (300s) = 0.5^10 = 1/1024 approx 0.00097
    long_silence = 10 * FATIGUE_HALF_LIFE_SECONDS
    recovered_value = counter.value("violin", now=long_silence)
    
    assert recovered_value < 0.001
    assert recovered_value > 0.0
    assert math.isclose(recovered_value, 0.5 ** 10, rel_tol=1e-12)


def test_fatigue_feature_is_gated_by_env_flag() -> None:
    # CC-083: Default OFF returns 1.0 multiplier regardless of counter value.
    assert fatigue_multiplier(1.0, env={}) == 1.0
    assert fatigue_multiplier(1.0, env={"CYPHERCLAW_V2_FATIGUE": "0"}) == 1.0
    
    # Truthy values activate the reduction.
    for truthy in ("1", "true", "yes", "on", "enabled"):
        env = {"CYPHERCLAW_V2_FATIGUE": truthy}
        assert fatigue_multiplier(1.0, env=env) == 0.5


def test_fatigue_multiplier_respects_real_environment_by_default() -> None:
    # If no env dict is passed, it should check os.environ.
    import os
    from unittest.mock import patch
    
    with patch.dict(os.environ, {"CYPHERCLAW_V2_FATIGUE": "1"}):
        assert fatigue_multiplier(1.0) == 0.5
        
    with patch.dict(os.environ, {"CYPHERCLAW_V2_FATIGUE": "0"}):
        assert fatigue_multiplier(1.0) == 1.0
