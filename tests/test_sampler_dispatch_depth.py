"""Depth-2 sampler-dispatch planning helpers - locked test surface for frac-0023."""
from __future__ import annotations

import dataclasses
import math
import os
import sys
import wave
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools", "senseweave"))

from senseweave.sampler_buffers import BufferLoader  # noqa: E402
from senseweave.sampler_dispatch import (  # noqa: E402
    FX_PRESETS_BY_MODE,
    SamplerDispatchPlan,
    SamplerDispatcher,
    build_s_new_args,
    build_sampler_dispatch_plan,
    grain_density_band,
    summarize_sampler_dispatch_plan,
)


class _RecordingOSC:
    def __init__(self) -> None:
        self.calls: list[tuple[str, list]] = []

    def send_message(self, address: str, args: list) -> None:
        self.calls.append((address, list(args)))


class _Record:
    def __init__(
        self,
        path: Path,
        *,
        buffer_id: int | None = None,
        gain_db: float = 0.0,
        pitch_hz: float | None = None,
        pitch_confidence: float = 0.0,
    ) -> None:
        self.path = path
        self.buffer_id = buffer_id
        self.gain_db = gain_db
        self.pitch_hz = pitch_hz
        self.pitch_confidence = pitch_confidence


def _write_wav(path: Path, *, frames: int = 4800, channels: int = 1) -> None:
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(channels)
        handle.setsampwidth(2)
        handle.setframerate(48000)
        handle.writeframes(b"\x00\x00" * frames * channels)


def test_grain_density_band_maps_values_to_named_bands() -> None:
    assert grain_density_band(0.0) == "sparse"
    assert grain_density_band(8.0) == "sparse"
    assert grain_density_band(8.01) == "moderate"
    assert grain_density_band(16.0) == "moderate"
    assert grain_density_band(16.01) == "dense"
    assert grain_density_band(28.0) == "dense"
    assert grain_density_band(28.01) == "saturated"


def test_build_sampler_dispatch_plan_resolves_loaded_record(tmp_path: Path) -> None:
    wav = tmp_path / "clip.wav"
    _write_wav(wav)
    record = _Record(
        wav,
        buffer_id=777,
        gain_db=6.0,
        pitch_hz=523.25,
        pitch_confidence=0.9,
    )

    plan = build_sampler_dispatch_plan(
        record,
        mode="storm",
        key_name="Bm",
        position=0.4,
        position_rate=0.2,
        grain_size_ms=140.0,
        density=18.0,
        pitch_transpose=None,
        amp=0.5,
        fx_send=0.35,
    )

    assert isinstance(plan, SamplerDispatchPlan)
    assert dataclasses.is_dataclass(plan)
    assert getattr(plan, "__dataclass_params__").frozen
    assert plan.sample_path == str(wav)
    assert plan.mode == "storm"
    assert plan.key_name == "Bm"
    assert plan.buffer_id == 777
    assert plan.buffer_loaded is True
    assert plan.density_band == "dense"
    assert plan.pitch_transpose == -1
    assert math.isclose(plan.effective_amp, 0.5 * (10.0 ** (6.0 / 20.0)), rel_tol=1e-9)
    assert dict(plan.fx_preset) == FX_PRESETS_BY_MODE["storm"]
    assert dict(plan.synth_arg_pairs) == {
        "bufnum": 777,
        "amp": plan.effective_amp,
        "grain_size_ms": 140.0,
        "density": 18.0,
        "position": 0.4,
        "position_rate": 0.2,
        "pitch_transpose_semitones": -1,
        "fx_send": 0.35,
    }


def test_build_s_new_args_uses_canonical_arg_order() -> None:
    args = build_s_new_args(
        node_id=2004,
        buffer_id=901,
        effective_amp=0.25,
        grain_size_ms=80.0,
        density=12.0,
        position=0.1,
        position_rate=0.75,
        pitch_transpose=-2.0,
        fx_send=0.4,
    )

    assert args == [
        "sw_sampler",
        2004,
        0,
        0,
        "bufnum",
        901,
        "amp",
        0.25,
        "grain_size_ms",
        80.0,
        "density",
        12.0,
        "position",
        0.1,
        "position_rate",
        0.75,
        "pitch_transpose_semitones",
        -2.0,
        "fx_send",
        0.4,
    ]


def test_summarize_sampler_dispatch_plan_returns_json_safe_summary(tmp_path: Path) -> None:
    wav = tmp_path / "clip.wav"
    _write_wav(wav)
    plan = build_sampler_dispatch_plan(
        _Record(wav, buffer_id=None, gain_db=-3.0, pitch_hz=440.0, pitch_confidence=0.9),
        mode="evening_reflection",
        key_name="Bm",
        position=0.25,
        position_rate=1.0,
        grain_size_ms=90.0,
        density=10.0,
        pitch_transpose=4.0,
        amp=0.4,
        fx_send=0.5,
    )

    summary = summarize_sampler_dispatch_plan(plan)

    assert summary == {
        "sample_path": str(wav),
        "mode": "evening_reflection",
        "key_name": "Bm",
        "buffer_state": "pending_load",
        "buffer_id": None,
        "density": 10.0,
        "density_band": "moderate",
        "grain_size_ms": 90.0,
        "position": 0.25,
        "position_rate": 1.0,
        "pitch_transpose": 4.0,
        "effective_amp": plan.effective_amp,
        "fx_send": 0.5,
        "fx_preset": FX_PRESETS_BY_MODE["evening_reflection"],
        "synth_args": dict(plan.synth_arg_pairs),
    }
    assert isinstance(summary["fx_preset"], dict)
    assert isinstance(summary["synth_args"], dict)


def test_sampler_dispatch_plan_drives_end_to_end_dispatch(tmp_path: Path) -> None:
    wav = tmp_path / "clip.wav"
    _write_wav(wav)
    osc = _RecordingOSC()
    dispatcher = SamplerDispatcher(
        osc,
        BufferLoader(osc, start_bufnum=500),
        start_node_id=3000,
    )
    record = _Record(wav, gain_db=0.0, pitch_hz=523.25, pitch_confidence=0.9)

    plan_before = build_sampler_dispatch_plan(
        record,
        mode="solitary",
        key_name="Bm",
        position=0.7,
        position_rate=0.5,
        grain_size_ms=120.0,
        density=14.0,
        pitch_transpose=None,
        amp=0.45,
        fx_send=0.3,
    )
    assert plan_before.buffer_loaded is False
    assert plan_before.buffer_id is None

    handle = dispatcher.dispatch_sample(
        record,
        intent=None,
        position=0.7,
        position_rate=0.5,
        grain_size_ms=120.0,
        density=14.0,
        pitch_transpose=plan_before.pitch_transpose,
        amp=0.45,
        fx_send=0.3,
    )

    plan_after = build_sampler_dispatch_plan(
        record,
        mode="solitary",
        key_name="Bm",
        position=0.7,
        position_rate=0.5,
        grain_size_ms=120.0,
        density=14.0,
        pitch_transpose=None,
        amp=0.45,
        fx_send=0.3,
    )
    s_new = next(call for call in osc.calls if call[0] == "/s_new")

    assert handle.buffer_id == 500
    assert plan_after.buffer_loaded is True
    assert plan_after.buffer_id == 500
    assert dict(zip(s_new[1][4::2], s_new[1][5::2])) == dict(plan_after.synth_arg_pairs)


def test_sampler_dispatch_reaches_depth_two() -> None:
    from sdp.fractal import classify_depth

    result = classify_depth("my-claw/tools/senseweave/sampler_dispatch.py")
    assert result.depth >= 2, result.reason
