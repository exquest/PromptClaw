"""Tests for sampler_dispatch — `/s_new sw_sampler` bundle and gate release."""
from __future__ import annotations

import math
import os
import sys
import wave
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools", "senseweave"))

from senseweave.sampler_buffers import BufferLoader
from senseweave.sampler_dispatch import (
    DEFAULT_FX_PRESET,
    FX_PRESETS_BY_MODE,
    EffectsBus,
    SamplerDispatcher,
    SamplerHandle,
    get_fx_preset,
    transpose_to_key,
)


class _RecordingOSC:
    def __init__(self) -> None:
        self.calls: list[tuple[str, list]] = []

    def send_message(self, address: str, args: list) -> None:
        self.calls.append((address, list(args)))


def _write_wav(path: Path, *, frames: int = 4800, channels: int = 1) -> None:
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(channels)
        handle.setsampwidth(2)
        handle.setframerate(48000)
        handle.writeframes(b"\x00\x00" * frames * channels)


class _Record:
    """SampleRecord stand-in carrying the dispatch-relevant fields.

    Mirrors the surface used by `BufferLoader` plus the `gain_db` field
    that the eventual `SampleRecord` (CCS-001) supplies.
    """

    def __init__(self, path: Path, *, gain_db: float = 0.0) -> None:
        self.path = path
        self.buffer_id: int | None = None
        self.gain_db = gain_db


def _build_dispatcher(tmp_path: Path) -> tuple[SamplerDispatcher, _RecordingOSC, _Record]:
    wav = tmp_path / "clip.wav"
    _write_wav(wav)
    osc = _RecordingOSC()
    loader = BufferLoader(osc, start_bufnum=400)
    dispatcher = SamplerDispatcher(osc, loader, start_node_id=2000)
    record = _Record(wav)
    return dispatcher, osc, record


def _params(**overrides: float) -> dict[str, float]:
    base: dict[str, float] = {
        "position": 0.25,
        "position_rate": 1.0,
        "grain_size_ms": 80.0,
        "density": 12.0,
        "pitch_transpose": 0.0,
        "amp": 0.5,
        "fx_send": 0.4,
    }
    base.update(overrides)
    return base


def test_dispatch_sample_loads_buffer_then_emits_s_new(tmp_path: Path) -> None:
    dispatcher, osc, record = _build_dispatcher(tmp_path)

    handle = dispatcher.dispatch_sample(record, intent=None, **_params())

    assert isinstance(handle, SamplerHandle)
    assert handle.buffer_id == 400
    assert record.buffer_id == 400
    addresses = [call[0] for call in osc.calls]
    assert addresses == ["/b_alloc", "/b_allocRead", "/s_new"]


def test_dispatch_sample_s_new_carries_full_arg_pairs(tmp_path: Path) -> None:
    dispatcher, osc, record = _build_dispatcher(tmp_path)

    handle = dispatcher.dispatch_sample(
        record,
        intent=None,
        **_params(position=0.7, density=18.0, pitch_transpose=-3.0, fx_send=0.6),
    )

    s_new = next(call for call in osc.calls if call[0] == "/s_new")
    args = s_new[1]
    assert args[0] == "sw_sampler"
    assert args[1] == handle.node_id
    assert args[2] == 0  # add-to-head action
    assert args[3] == 0  # default target group
    pairs = dict(zip(args[4::2], args[5::2]))
    assert pairs == {
        "bufnum": 400,
        "amp": 0.5,
        "grain_size_ms": 80.0,
        "density": 18.0,
        "position": 0.7,
        "position_rate": 1.0,
        "pitch_transpose_semitones": -3.0,
        "fx_send": 0.6,
    }


def test_dispatch_sample_correlates_gain_db_into_amp(tmp_path: Path) -> None:
    dispatcher, osc, record = _build_dispatcher(tmp_path)
    record.gain_db = 6.0

    dispatcher.dispatch_sample(record, intent=None, **_params(amp=0.5))

    s_new = next(call for call in osc.calls if call[0] == "/s_new")
    pairs = dict(zip(s_new[1][4::2], s_new[1][5::2]))
    expected = 0.5 * (10.0 ** (6.0 / 20.0))
    assert math.isclose(pairs["amp"], expected, rel_tol=1e-9)


def test_dispatch_sample_reuses_buffer_when_already_loaded(tmp_path: Path) -> None:
    dispatcher, osc, record = _build_dispatcher(tmp_path)
    dispatcher.dispatch_sample(record, intent=None, **_params())
    osc.calls.clear()

    dispatcher.dispatch_sample(record, intent=None, **_params(position=0.4))

    addresses = [call[0] for call in osc.calls]
    assert addresses == ["/s_new"]


def test_dispatch_sample_assigns_unique_node_ids(tmp_path: Path) -> None:
    dispatcher, _, record = _build_dispatcher(tmp_path)

    h1 = dispatcher.dispatch_sample(record, intent=None, **_params())
    h2 = dispatcher.dispatch_sample(record, intent=None, **_params())

    assert h1.node_id != h2.node_id
    assert h2.node_id == h1.node_id + 1


def test_handle_release_sends_n_set_gate_zero(tmp_path: Path) -> None:
    dispatcher, osc, record = _build_dispatcher(tmp_path)
    handle = dispatcher.dispatch_sample(record, intent=None, **_params())
    osc.calls.clear()

    handle.release()

    assert osc.calls == [("/n_set", [handle.node_id, "gate", 0])]


def test_handle_release_is_idempotent(tmp_path: Path) -> None:
    dispatcher, osc, record = _build_dispatcher(tmp_path)
    handle = dispatcher.dispatch_sample(record, intent=None, **_params())
    osc.calls.clear()

    handle.release()
    handle.release()

    assert len(osc.calls) == 1


def test_fx_presets_only_carry_supported_keys() -> None:
    allowed = {"delay_time", "delay_feedback", "verb_mix", "freeze_amount", "comb_b_amount"}
    for mode, preset in FX_PRESETS_BY_MODE.items():
        assert set(preset).issubset(allowed), f"{mode} carries unsupported keys"


def test_fx_presets_cover_all_five_artist_modes() -> None:
    assert set(FX_PRESETS_BY_MODE) == {
        "solitary",
        "companion",
        "working_ambience",
        "evening_reflection",
        "storm",
    }


def test_fx_presets_match_ccs_026_canonical_values() -> None:
    # CCS-026 / T-020 acceptance criteria: each mode's preset must match the
    # task-graph specification exactly so downstream composer code can rely on
    # the artistic shape (solitary/evening lush, working minimal, storm dense).
    assert FX_PRESETS_BY_MODE["solitary"] == {
        "delay_time": 0.6,
        "delay_feedback": 0.65,
        "verb_mix": 0.45,
        "freeze_amount": 0.2,
        "comb_b_amount": 0.4,
    }
    assert FX_PRESETS_BY_MODE["companion"] == {
        "delay_time": 0.5,
        "delay_feedback": 0.4,
        "verb_mix": 0.3,
        "freeze_amount": 0.0,
        "comb_b_amount": 0.15,
    }
    assert FX_PRESETS_BY_MODE["working_ambience"] == {
        "delay_time": 0.3,
        "delay_feedback": 0.2,
        "verb_mix": 0.15,
        "freeze_amount": 0.0,
        "comb_b_amount": 0.1,
    }
    assert FX_PRESETS_BY_MODE["evening_reflection"] == {
        "delay_time": 0.7,
        "delay_feedback": 0.55,
        "verb_mix": 0.5,
        "freeze_amount": 0.15,
        "comb_b_amount": 0.3,
    }
    assert FX_PRESETS_BY_MODE["storm"] == {
        "delay_time": 0.25,
        "delay_feedback": 0.7,
        "verb_mix": 0.25,
        "freeze_amount": 0.55,
        "comb_b_amount": 0.6,
    }


def test_fx_presets_within_synthdef_acceptable_ranges() -> None:
    # Bounds mirror the clip(...) statements in synthesis/sampler_effects.scd
    # so out-of-range edits to the table fail loudly instead of silently being
    # clamped at runtime.
    bounds: dict[str, tuple[float, float]] = {
        "delay_time": (0.0, 2.0),
        "delay_feedback": (0.0, 0.85),
        "verb_mix": (0.0, 1.0),
        "freeze_amount": (0.0, 1.0),
        "comb_b_amount": (0.0, 1.0),
    }
    for mode, preset in FX_PRESETS_BY_MODE.items():
        for key, value in preset.items():
            lo, hi = bounds[key]
            assert lo <= value <= hi, f"{mode}.{key}={value} outside [{lo},{hi}]"


def test_get_fx_preset_returns_known_mode() -> None:
    preset = get_fx_preset("storm")
    assert preset == FX_PRESETS_BY_MODE["storm"]


def test_get_fx_preset_returns_default_for_unknown_mode() -> None:
    assert get_fx_preset("not_a_real_mode") == DEFAULT_FX_PRESET


def test_get_fx_preset_returns_default_for_none() -> None:
    assert get_fx_preset(None) == DEFAULT_FX_PRESET


def test_get_fx_preset_returns_fresh_copy() -> None:
    # Mutating the returned dict must not corrupt the canonical table or
    # the default-fallback baseline.
    preset = get_fx_preset("solitary")
    preset["delay_time"] = 99.0
    assert FX_PRESETS_BY_MODE["solitary"]["delay_time"] == 0.6

    fallback = get_fx_preset("unknown")
    fallback["verb_mix"] = 99.0
    assert DEFAULT_FX_PRESET["verb_mix"] != 99.0


class _FakeScheduler:
    def __init__(self) -> None:
        self.tasks: list[tuple[float, object]] = []

    def schedule(self, delay_sec, action):
        self.tasks.append((delay_sec, action))

    def fire_all(self) -> None:
        for _, action in list(self.tasks):
            action()


def _build_dispatcher_with_scheduler(
    tmp_path: Path,
) -> tuple[SamplerDispatcher, _RecordingOSC, _Record, _FakeScheduler]:
    wav = tmp_path / "clip.wav"
    _write_wav(wav)
    osc = _RecordingOSC()
    loader = BufferLoader(osc, start_bufnum=400)
    sched = _FakeScheduler()
    dispatcher = SamplerDispatcher(osc, loader, start_node_id=2000, scheduler=sched)
    record = _Record(wav)
    return dispatcher, osc, record, sched


def test_play_sampler_dispatches_and_schedules_release(tmp_path: Path) -> None:
    dispatcher, osc, record, sched = _build_dispatcher_with_scheduler(tmp_path)

    handle = dispatcher.play_sampler(record, duration_sec=2.5, **_params())

    addresses = [call[0] for call in osc.calls]
    assert addresses == ["/b_alloc", "/b_allocRead", "/s_new"]
    assert len(sched.tasks) == 1
    delay, _action = sched.tasks[0]
    assert delay == 2.5

    sched.fire_all()
    assert ("/n_set", [handle.node_id, "gate", 0]) in osc.calls


def test_play_sampler_rejects_non_positive_duration(tmp_path: Path) -> None:
    dispatcher, _, record, _ = _build_dispatcher_with_scheduler(tmp_path)

    import pytest

    with pytest.raises(ValueError):
        dispatcher.play_sampler(record, duration_sec=0.0, **_params())


def test_start_sampler_returns_handle_and_stop_releases_gate(tmp_path: Path) -> None:
    dispatcher, osc, record, _ = _build_dispatcher_with_scheduler(tmp_path)

    handle = dispatcher.start_sampler(record, **_params())

    assert isinstance(handle, SamplerHandle)
    addresses = [call[0] for call in osc.calls]
    assert addresses == ["/b_alloc", "/b_allocRead", "/s_new"]

    dispatcher.stop_sampler(handle)
    assert osc.calls[-1] == ("/n_set", [handle.node_id, "gate", 0])


def test_play_and_start_sampler_run_concurrently_without_collision(tmp_path: Path) -> None:
    """Both lifecycles share dispatch_sample; node ids stay unique and the same
    record-buffer is reused rather than re-allocated for the second voice."""
    dispatcher, osc, record, sched = _build_dispatcher_with_scheduler(tmp_path)

    fire_and_forget = dispatcher.play_sampler(record, duration_sec=1.0, **_params())
    sustained = dispatcher.start_sampler(record, **_params(position=0.6))

    assert fire_and_forget.node_id != sustained.node_id
    assert fire_and_forget.buffer_id == sustained.buffer_id == 400

    s_news = [call for call in osc.calls if call[0] == "/s_new"]
    assert len(s_news) == 2
    node_ids = {s_news[0][1][1], s_news[1][1][1]}
    assert node_ids == {fire_and_forget.node_id, sustained.node_id}

    sched.fire_all()
    dispatcher.stop_sampler(sustained)

    gate_releases = [
        call for call in osc.calls
        if call[0] == "/n_set" and len(call[1]) == 3 and call[1][1] == "gate"
    ]
    released_nodes = {call[1][0] for call in gate_releases}
    assert released_nodes == {fire_and_forget.node_id, sustained.node_id}


def _bus_n_set_pairs(osc: _RecordingOSC, fx_node_id: int) -> dict[str, float]:
    n_set = next(
        call for call in osc.calls
        if call[0] == "/n_set" and call[1] and call[1][0] == fx_node_id
    )
    return dict(zip(n_set[1][1::2], n_set[1][2::2]))


def test_effects_bus_apply_mode_emits_preset_n_set() -> None:
    osc = _RecordingOSC()
    bus = EffectsBus(osc, fx_node_id=99)

    changed = bus.apply_mode("solitary")

    assert changed is True
    assert bus.current_mode == "solitary"
    assert _bus_n_set_pairs(osc, 99) == FX_PRESETS_BY_MODE["solitary"]


def test_effects_bus_apply_mode_is_idempotent_for_same_mode() -> None:
    osc = _RecordingOSC()
    bus = EffectsBus(osc, fx_node_id=99)

    bus.apply_mode("companion")
    osc.calls.clear()

    changed = bus.apply_mode("companion")

    assert changed is False
    assert osc.calls == []


def test_effects_bus_mode_change_pushes_new_preset() -> None:
    osc = _RecordingOSC()
    bus = EffectsBus(osc, fx_node_id=99)

    bus.apply_mode("working_ambience")
    osc.calls.clear()

    changed = bus.apply_mode("storm")

    assert changed is True
    assert bus.current_mode == "storm"
    assert _bus_n_set_pairs(osc, 99) == FX_PRESETS_BY_MODE["storm"]


def test_effects_bus_unknown_mode_falls_back_to_default_preset() -> None:
    osc = _RecordingOSC()
    bus = EffectsBus(osc, fx_node_id=99)

    bus.apply_mode("not_a_real_mode")

    assert _bus_n_set_pairs(osc, 99) == DEFAULT_FX_PRESET


def test_effects_bus_solitary_yields_higher_reverb_and_delay_than_working() -> None:
    # Artistic-intent assertion: the effects-bus apply path must deliver
    # CCS-026's character — solitary is lush, working_ambience is restrained.
    osc = _RecordingOSC()
    bus = EffectsBus(osc, fx_node_id=99)

    bus.apply_mode("solitary")
    solitary = _bus_n_set_pairs(osc, 99)
    osc.calls.clear()
    bus.apply_mode("working_ambience")
    working = _bus_n_set_pairs(osc, 99)

    assert solitary["verb_mix"] > working["verb_mix"]
    assert solitary["delay_feedback"] > working["delay_feedback"]
    assert solitary["delay_time"] > working["delay_time"]


def test_effects_bus_evening_yields_higher_reverb_and_delay_than_working() -> None:
    osc = _RecordingOSC()
    bus = EffectsBus(osc, fx_node_id=99)

    bus.apply_mode("evening_reflection")
    evening = _bus_n_set_pairs(osc, 99)
    osc.calls.clear()
    bus.apply_mode("working_ambience")
    working = _bus_n_set_pairs(osc, 99)

    assert evening["verb_mix"] > working["verb_mix"]
    assert evening["delay_feedback"] > working["delay_feedback"]
    assert evening["delay_time"] > working["delay_time"]


def test_effects_bus_working_ambience_yields_minimal_effects() -> None:
    # working_ambience must be the quietest preset on every effect axis,
    # so it stays out of the way of focused work.
    osc = _RecordingOSC()
    bus = EffectsBus(osc, fx_node_id=99)

    bus.apply_mode("working_ambience")
    working = _bus_n_set_pairs(osc, 99)

    for other in ("solitary", "companion", "evening_reflection", "storm"):
        osc.calls.clear()
        bus.apply_mode(other)
        other_pairs = _bus_n_set_pairs(osc, 99)
        for key in ("verb_mix", "delay_feedback", "freeze_amount", "comb_b_amount"):
            assert working[key] <= other_pairs[key], (
                f"working_ambience.{key} should be <= {other}.{key}"
            )


def test_effects_bus_storm_yields_high_freeze_and_heavy_comb_b() -> None:
    # storm leans on freeze + comb-B for its dense, resonant character —
    # both should top every other preset on those axes.
    osc = _RecordingOSC()
    bus = EffectsBus(osc, fx_node_id=99)

    bus.apply_mode("storm")
    storm = _bus_n_set_pairs(osc, 99)
    assert storm["freeze_amount"] >= 0.5
    assert storm["comb_b_amount"] >= 0.5

    for other in ("solitary", "companion", "working_ambience", "evening_reflection"):
        osc.calls.clear()
        bus.apply_mode(other)
        other_pairs = _bus_n_set_pairs(osc, 99)
        assert storm["freeze_amount"] > other_pairs["freeze_amount"]
        assert storm["comb_b_amount"] > other_pairs["comb_b_amount"]


def test_effects_bus_current_preset_is_a_fresh_copy() -> None:
    osc = _RecordingOSC()
    bus = EffectsBus(osc, fx_node_id=99)
    bus.apply_mode("solitary")

    snapshot = bus.current_preset
    assert snapshot == FX_PRESETS_BY_MODE["solitary"]
    assert snapshot is not None
    snapshot["verb_mix"] = 99.0
    assert FX_PRESETS_BY_MODE["solitary"]["verb_mix"] == 0.45
    assert bus.current_preset is not None
    assert bus.current_preset["verb_mix"] == 0.45


class _PitchedRecord:
    def __init__(self, pitch_hz: float, pitch_confidence: float = 0.9) -> None:
        self.pitch_hz = pitch_hz
        self.pitch_confidence = pitch_confidence


def test_transpose_to_key_in_key_pitch_returns_zero() -> None:
    # B aeolian = B C# D E F# G A; A4 (440 Hz) is in scale.
    assert transpose_to_key(_PitchedRecord(440.0), "Bm") == 0


def test_transpose_to_key_picks_nearest_in_key_pitch() -> None:
    # B aeolian pitch classes: {11, 1, 2, 4, 6, 7, 9}. C5 (~523.25) is pc 0;
    # nearest in-key is B (pc 11), one semitone down.
    assert transpose_to_key(_PitchedRecord(523.25), "Bm") == -1


def test_transpose_to_key_octave_wrap_prefers_short_path() -> None:
    # C5 in B major scale {11, 1, 3, 4, 6, 8, 10}: B is one semitone down (-1)
    # via wrap, not 11 semitones up. Verifies wrap handling.
    assert transpose_to_key(_PitchedRecord(523.25), "B") == -1


def test_transpose_to_key_low_confidence_returns_zero() -> None:
    # Out-of-key pitch but low confidence — atonal texture, no transposition.
    assert transpose_to_key(_PitchedRecord(523.25, pitch_confidence=0.39), "Bm") == 0


def test_transpose_to_key_confidence_at_threshold_transposes() -> None:
    # Confidence exactly 0.4 still transposes (>= floor).
    assert transpose_to_key(_PitchedRecord(523.25, pitch_confidence=0.4), "Bm") == -1


def test_transpose_to_key_zero_pitch_returns_zero() -> None:
    assert transpose_to_key(_PitchedRecord(0.0, pitch_confidence=1.0), "Bm") == 0


def test_transpose_to_key_c_major_known_combination() -> None:
    # C# (~277.18) → C major scale {0,2,4,5,7,9,11}: nearest is C (-1) or D (+1);
    # algorithm prefers the negative direction on ties.
    assert transpose_to_key(_PitchedRecord(277.18), "C") == -1


def test_transpose_to_key_handles_higher_octave() -> None:
    # A6 (1760 Hz) in B aeolian — A is in scale, no transposition.
    assert transpose_to_key(_PitchedRecord(1760.0), "Bm") == 0
