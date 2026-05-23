"""Tests for the shared `affective_state_bus` control-bus provisioning."""
from __future__ import annotations

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
    AffectiveStateBusWriter,
    affective_state_bus_c_set_args,
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
    writer = AffectiveStateBusWriter()
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
    writer = AffectiveStateBusWriter()
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
    writer = AffectiveStateBusWriter()
    osc = _RecordingOSC()

    writer.update("violin", 0.7, now=0.0)
    writer.update("cello", 0.3, now=5.0)

    # 'violin' is stale at now=5.0 + window, 'cello' is still fresh.
    max_pooled = writer.flush(osc, now=6.0)

    assert len(osc.messages) == 1
    assert osc.messages[0][1] == [AFFECTIVE_STATE_BUS_INDEX, 0.3]
    assert max_pooled == 0.3


def test_writer_clamps_per_sample_inputs_so_bus_writes_stay_in_unit_range() -> None:
    writer = AffectiveStateBusWriter()
    osc = _RecordingOSC()

    writer.update("violin", 1.5, now=0.0)
    writer.update("cello", -0.5, now=0.0)

    writer.flush(osc, now=0.5)

    for _, args in osc.messages:
        assert AFFECTIVE_STATE_BUS_MIN <= args[1] <= AFFECTIVE_STATE_BUS_MAX


def test_writer_with_no_contributors_emits_no_writes() -> None:
    writer = AffectiveStateBusWriter()
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
