"""Dispatch (SampleRecord, PerformanceIntent, params) to scsynth as `sw_sampler`.

`SamplerDispatcher.dispatch_sample` acquires the WAV buffer (via
`BufferLoader`) on demand, optionally pushes a per-mode preset onto the
shared sampler-effects synth, then sends `/s_new sw_sampler ...` with the
grain controls. It returns a `SamplerHandle` whose `release()` emits
`/n_set <node_id> gate 0` so the SynthDef's gate envelope releases its
tail cleanly.

The composer-facing API exposes two lifecycles on top of this core:
`play_sampler(record, duration_sec, ...)` for fire-and-forget grain
clouds (the dispatcher schedules its own gate release) and
`start_sampler(...)` / `stop_sampler(handle)` for sustained voices that
mirror the bowed/pad lifecycle.

`record.gain_db` is folded into the linear `amp` value (`amp * 10**(gain_db/20)`)
so quieter library samples keep parity with louder self-quotations.
`FX_PRESETS_BY_MODE` is the canonical per-mode preset table (T-020 / CCS-026)
covering all five ArtistModes; `get_fx_preset(mode)` performs a lookup with
`DEFAULT_FX_PRESET` fallback for unknown modes.
"""
from __future__ import annotations

import math
import threading
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol

try:
    from .harmonic_planner import _ROOT_TO_INDEX, key_root, scale_semitones_for_key
    from .sampler_buffers import BufferLoader
except ImportError:  # pragma: no cover - exercised when imported as root temp module
    from senseweave.harmonic_planner import _ROOT_TO_INDEX, key_root, scale_semitones_for_key
    from senseweave.sampler_buffers import BufferLoader

_PITCH_CONFIDENCE_FLOOR = 0.4


class _OSCSender(Protocol):
    def send_message(self, address: str, args: list) -> None: ...


class _Scheduler(Protocol):
    def schedule(self, delay_sec: float, action: Callable[[], None]) -> None: ...


class _TimerScheduler:
    """Default scheduler backed by `threading.Timer` for production use."""

    def schedule(self, delay_sec: float, action: Callable[[], None]) -> None:
        timer = threading.Timer(delay_sec, action)
        timer.daemon = True
        timer.start()


class _DispatchRecord(Protocol):
    """Subset of `SampleRecord` consumed by the dispatcher."""

    path: Any
    buffer_id: int | None
    gain_db: float


_FX_PRESET_KEYS: tuple[str, ...] = (
    "delay_time",
    "delay_feedback",
    "verb_mix",
    "freeze_amount",
    "comb_b_amount",
)

# Acceptable ranges (inclusive) per `sw_sampler_fx` SynthDef clip statements
# in synthesis/sampler_effects.scd. `delay_time` is tempo-clipped at runtime
# to a 1/4..1/2 measure window; the wider 0.0..2.0 bound here covers the
# 30..240 BPM tempo range the SynthDef supports.
_FX_PRESET_RANGES: dict[str, tuple[float, float]] = {
    "delay_time": (0.0, 2.0),
    "delay_feedback": (0.0, 0.85),
    "verb_mix": (0.0, 1.0),
    "freeze_amount": (0.0, 1.0),
    "comb_b_amount": (0.0, 1.0),
}

_SYNTH_ARG_KEYS: tuple[str, ...] = (
    "bufnum",
    "amp",
    "grain_size_ms",
    "density",
    "position",
    "position_rate",
    "pitch_transpose_semitones",
    "fx_send",
)


# Per-mode preset args applied to the `sw_sampler_fx` synth. Canonical T-020 /
# CCS-026 table covering all five ArtistModes: solitary and evening_reflection
# favour more reverb + delay; companion sits between them; working_ambience
# stays minimal so it does not crowd focused work; storm leans on freeze and
# comb-B for its dense, resonant character.
FX_PRESETS_BY_MODE: dict[str, dict[str, float]] = {
    "solitary": {
        "delay_time": 0.6,
        "delay_feedback": 0.65,
        "verb_mix": 0.45,
        "freeze_amount": 0.2,
        "comb_b_amount": 0.4,
    },
    "companion": {
        "delay_time": 0.5,
        "delay_feedback": 0.4,
        "verb_mix": 0.3,
        "freeze_amount": 0.0,
        "comb_b_amount": 0.15,
    },
    "working_ambience": {
        "delay_time": 0.3,
        "delay_feedback": 0.2,
        "verb_mix": 0.15,
        "freeze_amount": 0.0,
        "comb_b_amount": 0.1,
    },
    "evening_reflection": {
        "delay_time": 0.7,
        "delay_feedback": 0.55,
        "verb_mix": 0.5,
        "freeze_amount": 0.15,
        "comb_b_amount": 0.3,
    },
    "storm": {
        "delay_time": 0.25,
        "delay_feedback": 0.7,
        "verb_mix": 0.25,
        "freeze_amount": 0.55,
        "comb_b_amount": 0.6,
    },
}

# Fallback preset returned by `get_fx_preset` when a mode is not present in
# `FX_PRESETS_BY_MODE`. Mirrors `companion` — a moderate, neutral baseline
# that keeps the chain audible without favouring any one effect.
DEFAULT_FX_PRESET: dict[str, float] = dict(FX_PRESETS_BY_MODE["companion"])


@dataclass(frozen=True)
class SamplerDispatchPlan:
    """Resolved one-path view of a pending or loaded sampler dispatch."""

    sample_path: str
    mode: str
    key_name: str
    buffer_id: int | None
    buffer_loaded: bool
    position: float
    position_rate: float
    grain_size_ms: float
    density: float
    density_band: str
    pitch_transpose: float
    effective_amp: float
    fx_send: float
    fx_preset: tuple[tuple[str, float], ...]
    synth_arg_pairs: tuple[tuple[str, Any], ...]


def get_fx_preset(mode: str | None) -> dict[str, float]:
    """Return the FX preset for `mode`, falling back to `DEFAULT_FX_PRESET`.

    Returns a fresh dict copy so callers may mutate it without disturbing
    the canonical table. `dispatch_sample` does not use this helper (it
    intentionally skips the `/n_set` when a mode is unknown), but composer
    code that needs a guaranteed preset can call this directly.
    """
    if mode is not None:
        preset = FX_PRESETS_BY_MODE.get(mode)
        if preset is not None:
            return dict(preset)
    return dict(DEFAULT_FX_PRESET)


@dataclass
class SamplerHandle:
    """Handle for a live `sw_sampler` voice; `release()` opens its gate."""

    node_id: int
    buffer_id: int
    record: _DispatchRecord
    osc: _OSCSender
    released: bool = field(default=False)

    def release(self) -> None:
        if self.released:
            return
        self.osc.send_message("/n_set", [self.node_id, "gate", 0])
        self.released = True


def _amp_with_gain_db(amp: float, gain_db: float) -> float:
    return amp * (10.0 ** (gain_db / 20.0))


def grain_density_band(density: float) -> str:
    """Return an operator-readable band for grain density in grains/sec."""
    value = float(density)
    if value <= 8.0:
        return "sparse"
    if value <= 16.0:
        return "moderate"
    if value <= 28.0:
        return "dense"
    return "saturated"


def sampler_synth_arg_pairs(
    *,
    buffer_id: int | None,
    effective_amp: float,
    grain_size_ms: float,
    density: float,
    position: float,
    position_rate: float,
    pitch_transpose: float,
    fx_send: float,
) -> tuple[tuple[str, Any], ...]:
    """Return canonical ordered key/value pairs for `sw_sampler` controls."""
    values: dict[str, Any] = {
        "bufnum": buffer_id,
        "amp": effective_amp,
        "grain_size_ms": grain_size_ms,
        "density": density,
        "position": position,
        "position_rate": position_rate,
        "pitch_transpose_semitones": pitch_transpose,
        "fx_send": fx_send,
    }
    pairs: list[tuple[str, Any]] = []
    for key in _SYNTH_ARG_KEYS:
        pairs.append((key, values[key]))
    return tuple(pairs)


def build_s_new_args(
    *,
    node_id: int,
    buffer_id: int | None,
    effective_amp: float,
    grain_size_ms: float,
    density: float,
    position: float,
    position_rate: float,
    pitch_transpose: float,
    fx_send: float,
) -> list[Any]:
    """Build the complete `/s_new sw_sampler` argument list."""
    args: list[Any] = [
        "sw_sampler",
        node_id,
        0,  # action: add to head
        0,  # default target group
    ]
    for key, value in sampler_synth_arg_pairs(
        buffer_id=buffer_id,
        effective_amp=effective_amp,
        grain_size_ms=grain_size_ms,
        density=density,
        position=position,
        position_rate=position_rate,
        pitch_transpose=pitch_transpose,
        fx_send=fx_send,
    ):
        args.extend([key, value])
    return args


def build_sampler_dispatch_plan(
    record: _DispatchRecord,
    *,
    mode: str | None,
    key_name: str,
    position: float,
    position_rate: float,
    grain_size_ms: float,
    density: float,
    pitch_transpose: float | None,
    amp: float,
    fx_send: float,
) -> SamplerDispatchPlan:
    """Resolve the dispatch controls for `record` without sending OSC."""
    mode_name = mode if mode is not None else "default"
    buffer_id = getattr(record, "buffer_id", None)
    resolved_pitch = (
        float(transpose_to_key(record, key_name))
        if pitch_transpose is None
        else float(pitch_transpose)
    )
    effective_amp = _amp_with_gain_db(
        float(amp),
        float(getattr(record, "gain_db", 0.0) or 0.0),
    )
    preset = get_fx_preset(mode)
    fx_pairs = tuple(
        (key, float(preset[key]))
        for key in _FX_PRESET_KEYS
        if key in preset
    )
    synth_pairs = sampler_synth_arg_pairs(
        buffer_id=buffer_id,
        effective_amp=effective_amp,
        grain_size_ms=float(grain_size_ms),
        density=float(density),
        position=float(position),
        position_rate=float(position_rate),
        pitch_transpose=resolved_pitch,
        fx_send=float(fx_send),
    )
    return SamplerDispatchPlan(
        sample_path=str(getattr(record, "path", "")),
        mode=mode_name,
        key_name=key_name,
        buffer_id=buffer_id,
        buffer_loaded=buffer_id is not None,
        position=float(position),
        position_rate=float(position_rate),
        grain_size_ms=float(grain_size_ms),
        density=float(density),
        density_band=grain_density_band(density),
        pitch_transpose=resolved_pitch,
        effective_amp=effective_amp,
        fx_send=float(fx_send),
        fx_preset=fx_pairs,
        synth_arg_pairs=synth_pairs,
    )


def summarize_sampler_dispatch_plan(plan: SamplerDispatchPlan) -> dict[str, object]:
    """Return a JSON-safe operator summary for a sampler dispatch plan."""
    buffer_state = "loaded" if plan.buffer_loaded else "pending_load"
    fx_preset = {key: value for key, value in plan.fx_preset}
    synth_args = {key: value for key, value in plan.synth_arg_pairs}
    return {
        "sample_path": plan.sample_path,
        "mode": plan.mode,
        "key_name": plan.key_name,
        "buffer_state": buffer_state,
        "buffer_id": plan.buffer_id,
        "density": plan.density,
        "density_band": plan.density_band,
        "grain_size_ms": plan.grain_size_ms,
        "position": plan.position,
        "position_rate": plan.position_rate,
        "pitch_transpose": plan.pitch_transpose,
        "effective_amp": plan.effective_amp,
        "fx_send": plan.fx_send,
        "fx_preset": fx_preset,
        "synth_args": synth_args,
    }


def transpose_to_key(record: Any, key_name: str) -> int:
    """Integer semitone shift mapping `record.pitch_hz` to the nearest in-key pitch.

    `key_name` is parsed via `harmonic_planner` (B-rooted modes such as
    `Bm`, `B:dorian`, `B:phrygian` are the artist's home palette). When
    `record.pitch_confidence < 0.4` the sample is treated as atonal
    texture and 0 is returned. Returns the smallest absolute semitone
    offset, choosing the shorter direction across the octave wrap.
    """
    confidence = float(getattr(record, "pitch_confidence", 0.0) or 0.0)
    if confidence < _PITCH_CONFIDENCE_FLOOR:
        return 0

    pitch_hz = float(getattr(record, "pitch_hz", 0.0) or 0.0)
    if pitch_hz <= 0.0:
        return 0

    pitch_class = round(69 + 12 * math.log2(pitch_hz / 440.0)) % 12
    root_idx = _ROOT_TO_INDEX.get(key_root(key_name), _ROOT_TO_INDEX["B"])
    in_key_pcs = {(root_idx + s) % 12 for s in scale_semitones_for_key(key_name)}

    for distance in range(7):
        for offset in (-distance, distance) if distance else (0,):
            if (pitch_class + offset) % 12 in in_key_pcs:
                return offset
    return 0


class SamplerDispatcher:
    """Allocates node ids and ships sampler events to scsynth via OSC."""

    def __init__(
        self,
        osc: _OSCSender,
        buffer_loader: BufferLoader,
        *,
        start_node_id: int = 2000,
        scheduler: _Scheduler | None = None,
    ) -> None:
        self.osc = osc
        self.buffer_loader = buffer_loader
        self._next_node_id = start_node_id
        self._scheduler: _Scheduler = scheduler if scheduler is not None else _TimerScheduler()

    def _allocate_node_id(self) -> int:
        node_id = self._next_node_id
        self._next_node_id += 1
        return node_id

    def dispatch_sample(
        self,
        record: _DispatchRecord,
        intent: object,
        *,
        position: float,
        position_rate: float,
        grain_size_ms: float,
        density: float,
        pitch_transpose: float,
        amp: float,
        fx_send: float,
        mode: str | None = None,
        fx_node_id: int | None = None,
    ) -> SamplerHandle:
        """Acquire `record`'s buffer (if needed) and emit `/s_new sw_sampler`.

        Returns a `SamplerHandle` with the assigned node id; call
        `handle.release()` to send `/n_set gate 0` for envelope-tail release.
        """
        del intent  # reserved for tempo / dynamic shaping in later tasks

        if record.buffer_id is None:
            self.buffer_loader.on_sampler_load(record)
        else:
            self.buffer_loader.touch(record)
        bufnum = record.buffer_id
        if bufnum is None:
            raise RuntimeError("buffer acquisition failed to populate buffer_id")

        if mode is not None and fx_node_id is not None:
            preset = FX_PRESETS_BY_MODE.get(mode)
            if preset is not None:
                preset_args: list = [fx_node_id]
                for key in _FX_PRESET_KEYS:
                    if key in preset:
                        preset_args.extend([key, preset[key]])
                self.osc.send_message("/n_set", preset_args)

        node_id = self._allocate_node_id()
        effective_amp = _amp_with_gain_db(amp, getattr(record, "gain_db", 0.0))
        s_new_args = build_s_new_args(
            node_id=node_id,
            buffer_id=bufnum,
            effective_amp=effective_amp,
            grain_size_ms=grain_size_ms,
            density=density,
            position=position,
            position_rate=position_rate,
            pitch_transpose=pitch_transpose,
            fx_send=fx_send,
        )
        self.osc.send_message("/s_new", s_new_args)

        return SamplerHandle(
            node_id=node_id,
            buffer_id=bufnum,
            record=record,
            osc=self.osc,
        )

    def play_sampler(
        self,
        record: _DispatchRecord,
        duration_sec: float,
        *,
        intent: object = None,
        position: float,
        position_rate: float,
        grain_size_ms: float,
        density: float,
        pitch_transpose: float,
        amp: float,
        fx_send: float,
        mode: str | None = None,
        fx_node_id: int | None = None,
    ) -> SamplerHandle:
        """Fire-and-forget grain cloud: dispatch then schedule gate release at `duration_sec`."""
        if duration_sec <= 0:
            raise ValueError("duration_sec must be positive")
        handle = self.dispatch_sample(
            record,
            intent,
            position=position,
            position_rate=position_rate,
            grain_size_ms=grain_size_ms,
            density=density,
            pitch_transpose=pitch_transpose,
            amp=amp,
            fx_send=fx_send,
            mode=mode,
            fx_node_id=fx_node_id,
        )
        self._scheduler.schedule(duration_sec, handle.release)
        return handle

    def start_sampler(
        self,
        record: _DispatchRecord,
        *,
        intent: object = None,
        position: float,
        position_rate: float,
        grain_size_ms: float,
        density: float,
        pitch_transpose: float,
        amp: float,
        fx_send: float,
        mode: str | None = None,
        fx_node_id: int | None = None,
    ) -> SamplerHandle:
        """Sustained sampler voice; caller releases via `stop_sampler(handle)`."""
        return self.dispatch_sample(
            record,
            intent,
            position=position,
            position_rate=position_rate,
            grain_size_ms=grain_size_ms,
            density=density,
            pitch_transpose=pitch_transpose,
            amp=amp,
            fx_send=fx_send,
            mode=mode,
            fx_node_id=fx_node_id,
        )

    def stop_sampler(self, handle: SamplerHandle) -> None:
        """Release a sustained sampler voice started via `start_sampler`."""
        handle.release()
