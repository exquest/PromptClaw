"""Tests for the shared `affective_state_bus` control-bus provisioning."""
from __future__ import annotations

import math
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools", "senseweave"))

from senseweave.affective_state_bus import (
    AFFECTIVE_STATE_BUS_CHANNELS,
    AFFECTIVE_STATE_BUS_DECAY_SECONDS,
    AFFECTIVE_STATE_BUS_INDEX,
    AFFECTIVE_STATE_BUS_INTENSITY_WEIGHTS,
    AFFECTIVE_STATE_BUS_MAX,
    AFFECTIVE_STATE_BUS_MIN,
    AFFECTIVE_STATE_BUS_WINDOW_SECONDS,
    CYPHERCLAW_V2_COUPLING_ENV,
    AffectiveStateBusWriter,
    affective_state_bus_c_set_args,
    affective_state_bus_decay,
    coupling_enabled,
    seed_affective_state_bus,
    voice_expression_intensity,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
SCD_PATH = (
    REPO_ROOT
    / "my-claw"
    / "tools"
    / "senseweave"
    / "synthesis"
    / "affective_state_bus.scd"
)


class _RecordingOSC:
    def __init__(self) -> None:
        self.messages: list[tuple[str, list]] = []

    def send_message(self, address: str, args: list) -> None:
        self.messages.append((address, list(args)))


def test_bus_constants_are_stable_and_within_prd_contract() -> None:
    assert isinstance(AFFECTIVE_STATE_BUS_INDEX, int)
    assert AFFECTIVE_STATE_BUS_INDEX >= 0
    assert AFFECTIVE_STATE_BUS_CHANNELS == 1
    assert AFFECTIVE_STATE_BUS_MIN == 0.0
    assert AFFECTIVE_STATE_BUS_MAX == 1.0
    assert AFFECTIVE_STATE_BUS_DECAY_SECONDS == 5.0


def test_c_set_args_clamps_to_bus_range() -> None:
    assert affective_state_bus_c_set_args(0.0) == [AFFECTIVE_STATE_BUS_INDEX, 0.0]
    assert affective_state_bus_c_set_args(0.42) == [AFFECTIVE_STATE_BUS_INDEX, 0.42]
    assert affective_state_bus_c_set_args(2.0) == [AFFECTIVE_STATE_BUS_INDEX, 1.0]
    assert affective_state_bus_c_set_args(-1.0) == [AFFECTIVE_STATE_BUS_INDEX, 0.0]


def test_seed_sends_c_set_and_returns_seeded_value() -> None:
    osc = _RecordingOSC()
    value = seed_affective_state_bus(osc, 0.3)
    assert value == 0.3
    assert osc.messages == [("/c_set", [AFFECTIVE_STATE_BUS_INDEX, 0.3])]


def test_seed_clamps_out_of_range_value_before_sending() -> None:
    osc = _RecordingOSC()
    value = seed_affective_state_bus(osc, 1.7)
    assert value == 1.0
    assert osc.messages == [("/c_set", [AFFECTIVE_STATE_BUS_INDEX, 1.0])]


def test_affective_state_bus_scd_exists_and_provisions_bus() -> None:
    assert SCD_PATH.exists(), f"missing SuperCollider stub: {SCD_PATH}"
    text = SCD_PATH.read_text(encoding="utf-8")

    # The bus index, channel count, and range must agree with the Python helper.
    index_match = re.search(r"~affectiveStateBusIndex\s*=\s*(\d+)", text)
    assert index_match is not None, "stub must declare ~affectiveStateBusIndex"
    assert int(index_match.group(1)) == AFFECTIVE_STATE_BUS_INDEX

    channels_match = re.search(r"~affectiveStateBusChannels\s*=\s*(\d+)", text)
    assert channels_match is not None, "stub must declare ~affectiveStateBusChannels"
    assert int(channels_match.group(1)) == AFFECTIVE_STATE_BUS_CHANNELS


def test_affective_state_bus_scd_demonstrates_reader_side_wiring() -> None:
    text = SCD_PATH.read_text(encoding="utf-8")

    # Reader-side wiring per voice: In.kr from the shared bus, clipped.
    assert "In.kr(~affectiveStateBusIndex" in text, (
        "stub must demonstrate the reader-side wiring via In.kr on the shared bus"
    )

    # Per-voice coupling multiplier from PRD §7.5.2 (CC-072).
    assert "SynthDef(\\sw_affective_state_reader" in text, (
        "stub must declare the reference reader SynthDef so voice synthdefs "
        "have a per-voice wiring template"
    )
    assert "coupling_strength" in text
    assert "nominal_depth" in text
    assert "1.0 + (coupling * affect)" in text or "1 + (coupling * affect)" in text, (
        "stub must apply the (1 + coupling * affect) multiplier from CC-072"
    )


# --- T-002 / CC-071: per-voice rolling-window writer -----------------------


def test_window_seconds_matches_prd_two_second_rolling_window() -> None:
    # PRD §7.5.2: rolling-window estimate averaged over the last ~2 seconds.
    assert AFFECTIVE_STATE_BUS_WINDOW_SECONDS == 2.0


def test_intensity_weights_cover_the_four_prd_channels_and_sum_to_one() -> None:
    assert set(AFFECTIVE_STATE_BUS_INTENSITY_WEIGHTS.keys()) == {
        "vibrato_depth",
        "tremolo_depth",
        "dynamics",
        "pitch_bend_extent",
    }
    assert sum(AFFECTIVE_STATE_BUS_INTENSITY_WEIGHTS.values()) == 1.0


def test_voice_expression_intensity_weighted_sum_clamped_to_unit_range() -> None:
    assert voice_expression_intensity() == 0.0
    assert voice_expression_intensity(
        vibrato_depth=1.0,
        tremolo_depth=1.0,
        dynamics=1.0,
        pitch_bend_extent=1.0,
    ) == 1.0
    # Equal-weight contributions: a single channel at 1.0 yields 0.25.
    assert voice_expression_intensity(vibrato_depth=1.0) == 0.25
    # Out-of-range inputs are clamped per-channel before weighting.
    assert voice_expression_intensity(vibrato_depth=2.0) == 0.25
    assert voice_expression_intensity(dynamics=-1.0) == 0.0


def test_writer_flush_emits_one_c_set_per_active_voice_within_unit_range() -> None:
    writer = AffectiveStateBusWriter(enabled=True)
    osc = _RecordingOSC()

    writer.update("violin", 0.4, now=0.0)
    writer.update("cello", 0.8, now=0.0)
    writer.update("violin", 0.6, now=1.0)
    writer.update("cello", 0.2, now=1.0)

    max_pooled = writer.flush(osc, now=1.0)

    # Per-voice writes — one OSC message per active voice this tick.
    assert len(osc.messages) == 2
    addresses = {address for address, _ in osc.messages}
    assert addresses == {"/c_set"}
    written_values = [args[1] for _, args in osc.messages]
    for _, args in osc.messages:
        assert args[0] == AFFECTIVE_STATE_BUS_INDEX
        assert AFFECTIVE_STATE_BUS_MIN <= args[1] <= AFFECTIVE_STATE_BUS_MAX

    assert written_values[-1] == max(written_values)  # bus settles at max-pool
    assert max_pooled == max(written_values) == 0.5  # cello mean = (0.8+0.2)/2


def test_writer_prunes_samples_older_than_rolling_window() -> None:
    writer = AffectiveStateBusWriter(enabled=True)
    osc = _RecordingOSC()

    # Old samples that should fall off a 2-second window at now=10.0.
    writer.update("violin", 1.0, now=0.0)
    writer.update("violin", 1.0, now=5.0)
    writer.update("violin", 0.2, now=9.5)

    assert writer.voice_window_mean("violin", now=10.0) == 0.2

    writer.flush(osc, now=10.0)
    assert len(osc.messages) == 1
    assert osc.messages[0][1] == [AFFECTIVE_STATE_BUS_INDEX, 0.2]


def test_writer_drops_voices_whose_window_empties_after_pruning() -> None:
    writer = AffectiveStateBusWriter(enabled=True)
    osc = _RecordingOSC()

    writer.update("violin", 0.7, now=0.0)
    writer.update("cello", 0.3, now=5.0)

    # 'violin' is stale at now=5.0 + window, 'cello' is still fresh.
    max_pooled = writer.flush(osc, now=6.0)

    assert len(osc.messages) == 1
    assert osc.messages[0][1] == [AFFECTIVE_STATE_BUS_INDEX, 0.3]
    assert max_pooled == 0.3


def test_writer_clamps_per_sample_inputs_so_bus_writes_stay_in_unit_range() -> None:
    writer = AffectiveStateBusWriter(enabled=True)
    osc = _RecordingOSC()

    writer.update("violin", 1.5, now=0.0)
    writer.update("cello", -0.5, now=0.0)

    writer.flush(osc, now=0.5)

    for _, args in osc.messages:
        assert AFFECTIVE_STATE_BUS_MIN <= args[1] <= AFFECTIVE_STATE_BUS_MAX


def test_writer_with_no_contributors_emits_no_writes() -> None:
    writer = AffectiveStateBusWriter(enabled=True)
    osc = _RecordingOSC()

    max_pooled = writer.flush(osc, now=10.0)

    assert osc.messages == []
    assert max_pooled == 0.0


def test_writer_rejects_non_positive_window_seconds() -> None:
    import pytest

    with pytest.raises(ValueError):
        AffectiveStateBusWriter(window_seconds=0.0)
    with pytest.raises(ValueError):
        AffectiveStateBusWriter(window_seconds=-1.0)


# --- T-004 / PRD §7.5.2: slow-decay-toward-0 with ~5s time constant -------


def test_decay_returns_initial_when_no_time_has_passed() -> None:
    assert affective_state_bus_decay(0.8, 0.0) == 0.8
    assert affective_state_bus_decay(0.5, -1.0) == 0.5


def test_decay_at_one_time_constant_is_initial_over_e() -> None:
    # Exponential decay: value(tau) == initial / e.
    initial = 1.0
    decayed = affective_state_bus_decay(initial, AFFECTIVE_STATE_BUS_DECAY_SECONDS)
    expected = initial * math.exp(-1.0)
    assert math.isclose(decayed, expected, rel_tol=1e-9)


def test_decay_clamps_output_into_bus_range() -> None:
    # Out-of-range initial is clamped before applying the decay envelope.
    assert affective_state_bus_decay(2.0, 0.0) == AFFECTIVE_STATE_BUS_MAX
    assert affective_state_bus_decay(-1.0, 1.0) == AFFECTIVE_STATE_BUS_MIN
    # Output stays in [0, 1] for any positive elapsed time.
    for elapsed in (0.0, 1.0, 5.0, 50.0):
        v = affective_state_bus_decay(1.0, elapsed)
        assert AFFECTIVE_STATE_BUS_MIN <= v <= AFFECTIVE_STATE_BUS_MAX


def test_decay_is_monotonically_decreasing_toward_zero() -> None:
    samples = [
        affective_state_bus_decay(1.0, t)
        for t in (0.0, 1.0, 2.5, 5.0, 10.0, 30.0)
    ]
    for prev, curr in zip(samples, samples[1:]):
        assert curr < prev
    # 6 time constants ≈ 0.25% of initial — effectively zero.
    assert affective_state_bus_decay(1.0, 6 * AFFECTIVE_STATE_BUS_DECAY_SECONDS) < 0.01


def test_decay_rejects_non_positive_tau() -> None:
    import pytest

    with pytest.raises(ValueError):
        affective_state_bus_decay(1.0, 1.0, tau=0.0)
    with pytest.raises(ValueError):
        affective_state_bus_decay(1.0, 1.0, tau=-1.0)


def test_writer_seed_records_value_and_emits_c_set() -> None:
    writer = AffectiveStateBusWriter(enabled=True)
    osc = _RecordingOSC()

    seeded = writer.seed(osc, 0.9, now=0.0)

    assert seeded == 0.9
    assert osc.messages == [("/c_set", [AFFECTIVE_STATE_BUS_INDEX, 0.9])]


def test_writer_seeded_bus_decays_toward_zero_with_five_second_time_constant() -> None:
    writer = AffectiveStateBusWriter(enabled=True)
    osc = _RecordingOSC()

    writer.seed(osc, 1.0, now=0.0)
    osc.messages.clear()

    # One time constant later: value should be ~1/e.
    bus_after_tau = writer.flush(osc, now=AFFECTIVE_STATE_BUS_DECAY_SECONDS)
    assert math.isclose(bus_after_tau, math.exp(-1.0), rel_tol=1e-9)
    assert len(osc.messages) == 1
    address, args = osc.messages[0]
    assert address == "/c_set"
    assert args[0] == AFFECTIVE_STATE_BUS_INDEX
    assert math.isclose(args[1], math.exp(-1.0), rel_tol=1e-9)


def test_writer_decay_is_path_independent_across_multiple_flushes() -> None:
    # Flushing in small increments and flushing once after the same elapsed
    # time must reach the same decayed value (modulo float epsilon), because
    # exp(-(a+b)/tau) == exp(-a/tau) * exp(-b/tau).
    one_shot = AffectiveStateBusWriter()
    one_shot_osc = _RecordingOSC()
    one_shot.seed(one_shot_osc, 1.0, now=0.0)
    one_shot_value = one_shot.flush(one_shot_osc, now=10.0)

    stepped = AffectiveStateBusWriter()
    stepped_osc = _RecordingOSC()
    stepped.seed(stepped_osc, 1.0, now=0.0)
    for t in (1.0, 2.5, 4.0, 7.5, 10.0):
        stepped_value = stepped.flush(stepped_osc, now=t)

    assert math.isclose(one_shot_value, stepped_value, rel_tol=1e-12)


def test_writer_decay_resets_when_a_contributor_re_engages() -> None:
    writer = AffectiveStateBusWriter(enabled=True)
    osc = _RecordingOSC()

    writer.seed(osc, 1.0, now=0.0)
    writer.flush(osc, now=5.0)  # decayed toward 1/e
    osc.messages.clear()

    # A fresh contributor at intensity 0.6 should pin the bus to that value
    # on the next flush — the decay envelope only applies in absentia.
    writer.update("violin", 0.6, now=5.5)
    bus = writer.flush(osc, now=5.5)
    assert bus == 0.6
    assert osc.messages[-1] == ("/c_set", [AFFECTIVE_STATE_BUS_INDEX, 0.6])


def test_writer_rejects_non_positive_decay_tau_seconds() -> None:
    import pytest

    with pytest.raises(ValueError):
        AffectiveStateBusWriter(decay_tau_seconds=0.0)
    with pytest.raises(ValueError):
        AffectiveStateBusWriter(decay_tau_seconds=-1.0)


def test_affective_state_bus_scd_declares_decay_time_constant() -> None:
    text = SCD_PATH.read_text(encoding="utf-8")

    decay_match = re.search(r"~affectiveStateBusDecaySeconds\s*=\s*([0-9.]+)", text)
    assert decay_match is not None, (
        "stub must declare ~affectiveStateBusDecaySeconds for T-004"
    )
    assert float(decay_match.group(1)) == AFFECTIVE_STATE_BUS_DECAY_SECONDS

    assert "SynthDef(\\sw_affective_state_decay" in text, (
        "stub must declare the slow-decay SynthDef so the bus drifts to 0 "
        "when no voice is writing"
    )


# --- T-005 / CC-074: CYPHERCLAW_V2_COUPLING env flag, default OFF ----------


def test_coupling_env_var_name_matches_prd_contract() -> None:
    # CC-074 / PRD §15: the flag is named exactly CYPHERCLAW_V2_COUPLING.
    assert CYPHERCLAW_V2_COUPLING_ENV == "CYPHERCLAW_V2_COUPLING"


def test_coupling_defaults_off_when_env_unset() -> None:
    assert coupling_enabled(env={}) is False


def test_coupling_defaults_off_when_env_is_empty_string() -> None:
    assert coupling_enabled(env={CYPHERCLAW_V2_COUPLING_ENV: ""}) is False


def test_coupling_enabled_for_truthy_values() -> None:
    for value in ("1", "true", "TRUE", "Yes", "on", " enabled "):
        assert coupling_enabled(env={CYPHERCLAW_V2_COUPLING_ENV: value}) is True, value


def test_coupling_disabled_for_falsy_or_garbage_values() -> None:
    for value in ("0", "false", "no", "off", "disabled", "maybe", "2"):
        assert coupling_enabled(env={CYPHERCLAW_V2_COUPLING_ENV: value}) is False, value


def test_writer_defaults_to_env_flag_state(monkeypatch) -> None:
    monkeypatch.delenv(CYPHERCLAW_V2_COUPLING_ENV, raising=False)
    assert AffectiveStateBusWriter().enabled is False

    monkeypatch.setenv(CYPHERCLAW_V2_COUPLING_ENV, "1")
    assert AffectiveStateBusWriter().enabled is True

    monkeypatch.setenv(CYPHERCLAW_V2_COUPLING_ENV, "0")
    assert AffectiveStateBusWriter().enabled is False


def test_writer_explicit_enabled_overrides_env(monkeypatch) -> None:
    monkeypatch.setenv(CYPHERCLAW_V2_COUPLING_ENV, "1")
    assert AffectiveStateBusWriter(enabled=False).enabled is False

    monkeypatch.delenv(CYPHERCLAW_V2_COUPLING_ENV, raising=False)
    assert AffectiveStateBusWriter(enabled=True).enabled is True


def test_disabled_writer_emits_no_osc_traffic_on_update_seed_or_flush() -> None:
    writer = AffectiveStateBusWriter(enabled=False)
    osc = _RecordingOSC()

    writer.update("violin", 0.8, now=0.0)
    writer.seed(osc, 0.9, now=0.0)
    bus = writer.flush(osc, now=1.0)

    assert osc.messages == []
    assert bus == 0.0


def test_disabled_writer_drops_samples_so_re_enable_does_not_leak_history() -> None:
    # Buffering samples while OFF and then flushing as ON would cause a
    # surprise burst when an operator flips the flag. The contract is that
    # OFF means the feature is dormant — no hidden state accumulates.
    writer = AffectiveStateBusWriter(enabled=False)
    osc = _RecordingOSC()

    for t in range(5):
        writer.update("violin", 0.9, now=float(t))

    writer.enabled = True
    bus = writer.flush(osc, now=5.0)

    assert osc.messages == []
    assert bus == 0.0


def test_default_module_behavior_with_no_env_matches_off_state(monkeypatch) -> None:
    # CC-074 acceptance: "default behavior matches OFF state" — i.e. with
    # no env var set, constructing a writer and driving it through a
    # normal tick must produce zero OSC writes.
    monkeypatch.delenv(CYPHERCLAW_V2_COUPLING_ENV, raising=False)
    writer = AffectiveStateBusWriter()
    osc = _RecordingOSC()

    writer.seed(osc, 0.7, now=0.0)
    writer.update("violin", 0.6, now=0.5)
    writer.update("cello", 0.4, now=0.5)
    bus = writer.flush(osc, now=1.0)

    assert osc.messages == []
    assert bus == 0.0
