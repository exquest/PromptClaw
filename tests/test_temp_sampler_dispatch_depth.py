"""Depth-2 planning helpers for root temp_sampler_dispatch [frac-0052]."""
from __future__ import annotations

import dataclasses
import importlib
import json
import math
import sys
import wave
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "my-claw" / "tools"
for candidate in (ROOT, TOOLS, TOOLS / "senseweave"):
    text = str(candidate)
    if text not in sys.path:
        sys.path.insert(0, text)

from senseweave.sampler_buffers import BufferLoader  # noqa: E402


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


def _module() -> ModuleType:
    return importlib.import_module("temp_sampler_dispatch")


def test_temp_sampler_dispatch_imports_with_planning_surface() -> None:
    module = _module()

    for name in (
        "SamplerDispatchPlan",
        "grain_density_band",
        "sampler_synth_arg_pairs",
        "build_s_new_args",
        "build_sampler_dispatch_plan",
        "summarize_sampler_dispatch_plan",
    ):
        assert hasattr(module, name)


def test_grain_density_band_maps_values_to_named_bands() -> None:
    module = _module()

    assert module.grain_density_band(0.0) == "sparse"
    assert module.grain_density_band(8.0) == "sparse"
    assert module.grain_density_band(8.01) == "moderate"
    assert module.grain_density_band(16.0) == "moderate"
    assert module.grain_density_band(16.01) == "dense"
    assert module.grain_density_band(28.0) == "dense"
    assert module.grain_density_band(28.01) == "saturated"


def test_build_sampler_dispatch_plan_resolves_loaded_record(tmp_path: Path) -> None:
    module = _module()
    wav = tmp_path / "clip.wav"
    _write_wav(wav)
    record = _Record(
        wav,
        buffer_id=777,
        gain_db=6.0,
        pitch_hz=523.25,
        pitch_confidence=0.9,
    )

    plan = module.build_sampler_dispatch_plan(
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

    assert isinstance(plan, module.SamplerDispatchPlan)
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
    assert dict(plan.fx_preset) == module.FX_PRESETS_BY_MODE["storm"]
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
    module = _module()

    args = module.build_s_new_args(
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
    module = _module()
    wav = tmp_path / "clip.wav"
    _write_wav(wav)
    plan = module.build_sampler_dispatch_plan(
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

    summary = module.summarize_sampler_dispatch_plan(plan)

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
        "fx_preset": module.FX_PRESETS_BY_MODE["evening_reflection"],
        "synth_args": dict(plan.synth_arg_pairs),
    }
    json.dumps(summary)


def test_sampler_dispatch_plan_drives_end_to_end_dispatch(tmp_path: Path) -> None:
    module = _module()
    wav = tmp_path / "clip.wav"
    _write_wav(wav)
    osc = _RecordingOSC()
    dispatcher = module.SamplerDispatcher(
        osc,
        BufferLoader(osc, start_bufnum=500),
        start_node_id=3000,
    )
    record = _Record(wav, gain_db=0.0, pitch_hz=523.25, pitch_confidence=0.9)

    plan_before = module.build_sampler_dispatch_plan(
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

    plan_after = module.build_sampler_dispatch_plan(
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


def test_temp_sampler_dispatch_reaches_depth_two() -> None:
    from sdp.fractal import classify_depth

    result = classify_depth("temp_sampler_dispatch.py")
    assert result.depth >= 2, result.reason
