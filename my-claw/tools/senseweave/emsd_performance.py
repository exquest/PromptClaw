"""Live EMSD playback shaping for tracker events."""
from __future__ import annotations

from dataclasses import dataclass
from math import pow
from typing import Sequence

from .emsd_runtime import EMSDLiveContext
from .mix_engine import VoiceMixTarget


def _clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def _db_to_amp(db: float) -> float:
    return pow(10.0, db / 20.0)


def _scaled_db_to_amp(db: float, scale: float) -> float:
    return _db_to_amp(db * scale)


@dataclass(frozen=True)
class PerformanceAdjustments:
    amp_multiplier: float = 1.0
    release_multiplier: float = 1.0
    brightness_multiplier: float = 1.0
    verb_add: float = 0.0
    dly_add: float = 0.0
    detune_add: float = 0.0
    highpass_hz: float = 0.0
    saturation_add: float = 0.0
    sample_capture_path: str = ""
    dsp_blocks: tuple[str, ...] = ()


@dataclass(frozen=True)
class PerformanceEventSpec:
    role: str
    voice_name: str
    frequency_hz: float
    theramini_active: bool = False


@dataclass(frozen=True)
class PerformanceEventSnapshot:
    role: str
    voice_name: str
    frequency_hz: float
    theramini_active: bool
    amp_multiplier: float
    amp_band: str
    release_multiplier: float
    release_band: str
    brightness_multiplier: float
    brightness_band: str
    space_amount: float
    space_band: str
    detune_add: float
    highpass_hz: float
    saturation_add: float
    sample_capture_path: str
    dsp_blocks: tuple[str, ...]


@dataclass(frozen=True)
class PerformanceAdjustmentReport:
    snapshots: tuple[PerformanceEventSnapshot, ...]
    snapshot_count: int
    roles: tuple[str, ...]
    voice_names: tuple[str, ...]
    dsp_blocks: tuple[str, ...]
    sample_capture_paths: tuple[str, ...]
    mean_amp_multiplier: float
    max_release_multiplier: float
    min_brightness_multiplier: float
    space_total: float
    frontline_ducked_count: int
    highpass_roles: tuple[str, ...]


def _voice_target_for_role(context: EMSDLiveContext, role: str) -> VoiceMixTarget | None:
    for target in context.phase_plan.mix.voice_targets:
        if target.role == role:
            return target
    return None


def render_adjustments_for_event(
    *,
    role: str,
    voice_name: str,
    frequency_hz: float,
    context: EMSDLiveContext | None,
    theramini_active: bool,
) -> PerformanceAdjustments:
    """Translate EMSD mix/sample/DSP plans into note-level render adjustments."""

    if context is None:
        return PerformanceAdjustments()

    mix = context.phase_plan.mix
    sample = context.phase_plan.sampling
    dsp = context.phase_plan.dsp
    target = _voice_target_for_role(context, role)

    amp = _scaled_db_to_amp(mix.target_lufs - (-16.0), 0.4)
    release = 1.0
    brightness = 1.0
    verb = 0.0
    dly = 0.0
    detune = 0.0
    highpass = 0.0
    saturation = 0.0

    if target is not None:
        amp *= _scaled_db_to_amp(target.level_db - (-12.0), 0.35)
        verb += target.reverb_send * 0.08
        dly += max(0.0, target.stereo_width - 0.3) * 0.01
        detune += max(0.0, target.stereo_width - 0.45) * 0.002
        if role != "bass":
            highpass = max(highpass, min(target.lane.low_hz * 0.35, 220.0))
        if frequency_hz > (target.lane.high_hz * 1.08):
            amp *= 0.88
            brightness *= 0.84
        elif frequency_hz < (target.lane.low_hz * 0.92):
            amp *= 0.94

    if theramini_active and role in {"melody", "counter", "color"} and mix.theramini_duck_db > 0.0:
        amp *= _db_to_amp(-mix.theramini_duck_db)

    source_type = sample.source.source_type
    if source_type == "outdoor":
        verb += 0.02
        brightness *= 0.94
    elif source_type == "instrument":
        dly += 0.008
        detune += 0.001
        if role in {"melody", "counter"}:
            amp *= 1.03
    elif source_type == "internal":
        saturation += 0.015
    elif source_type == "contact":
        saturation += 0.02
        release *= 0.94
    else:
        verb += 0.012

    for transform in sample.transforms:
        if transform in {"stretch", "spectral_freeze", "lowpass_resample"}:
            release *= 1.14
            brightness *= 0.88
            verb += 0.022
        elif transform in {"slice_rearrange", "pitch_window"}:
            dly += 0.006
            detune += 0.001
        elif transform == "granular_cloud":
            detune += 0.002
            verb += 0.015
            saturation += 0.01
        elif transform == "reverse_accents":
            saturation += 0.008
            amp *= 1.02

    for block in dsp.blocks:
        if block in {"spectral_smear", "long_convolution", "freeze_tail"}:
            release *= 1.08
            brightness *= 0.92
            verb += 0.02
        elif block == "parallel_delay":
            dly += 0.012
        elif block in {"cross_synthesis", "bin_shift"}:
            detune += 0.0015
            saturation += 0.015
        elif block == "comb_resonance" and role in {"counter", "color"}:
            brightness *= 1.04
        elif block == "lowpass_bloom":
            brightness *= 0.86
            release *= 1.1

    if voice_name in {"breath", "choir", "pad"}:
        verb += 0.01
    if voice_name in {"pluck", "metal", "bell"}:
        saturation += 0.01

    return PerformanceAdjustments(
        amp_multiplier=round(_clamp(amp, 0.45, 1.2), 3),
        release_multiplier=round(_clamp(release, 0.85, 1.4), 3),
        brightness_multiplier=round(_clamp(brightness, 0.65, 1.08), 3),
        verb_add=round(_clamp(verb, 0.0, 0.12), 3),
        dly_add=round(_clamp(dly, 0.0, 0.04), 3),
        detune_add=round(_clamp(detune, 0.0, 0.008), 4),
        highpass_hz=round(_clamp(highpass, 0.0, 220.0), 1),
        saturation_add=round(_clamp(saturation, 0.0, 0.08), 3),
        sample_capture_path=sample.source.capture_path,
        dsp_blocks=tuple(dsp.blocks),
    )


def amp_pressure_band(value: float) -> str:
    """Classify a resolved amplitude multiplier for operator summaries."""
    if value < 0.75:
        return "recessed"
    if value > 1.05:
        return "forward"
    return "balanced"


def release_shape_band(value: float) -> str:
    """Classify a resolved release multiplier for operator summaries."""
    if value < 0.95:
        return "tight"
    if value > 1.1:
        return "bloom"
    return "natural"


def brightness_shape_band(value: float) -> str:
    """Classify a resolved brightness multiplier for operator summaries."""
    if value < 0.9:
        return "muted"
    if value > 1.02:
        return "bright"
    return "clear"


def space_amount_band(value: float) -> str:
    """Classify combined verb/delay amount for operator summaries."""
    if value <= 0.02:
        return "dry"
    if value <= 0.07:
        return "open"
    return "washed"


def _ordered_unique(values: Sequence[str]) -> tuple[str, ...]:
    items: list[str] = []
    for value in values:
        if value not in items:
            items.append(value)
    return tuple(items)


def build_performance_event_snapshot(
    spec: PerformanceEventSpec,
    *,
    context: EMSDLiveContext | None,
) -> PerformanceEventSnapshot:
    """Resolve one event spec through the live EMSD adjustment path."""
    adjustment = render_adjustments_for_event(
        role=spec.role,
        voice_name=spec.voice_name,
        frequency_hz=spec.frequency_hz,
        context=context,
        theramini_active=spec.theramini_active,
    )
    space_amount = round(adjustment.verb_add + adjustment.dly_add, 4)
    return PerformanceEventSnapshot(
        role=spec.role,
        voice_name=spec.voice_name,
        frequency_hz=spec.frequency_hz,
        theramini_active=spec.theramini_active,
        amp_multiplier=adjustment.amp_multiplier,
        amp_band=amp_pressure_band(adjustment.amp_multiplier),
        release_multiplier=adjustment.release_multiplier,
        release_band=release_shape_band(adjustment.release_multiplier),
        brightness_multiplier=adjustment.brightness_multiplier,
        brightness_band=brightness_shape_band(adjustment.brightness_multiplier),
        space_amount=space_amount,
        space_band=space_amount_band(space_amount),
        detune_add=adjustment.detune_add,
        highpass_hz=adjustment.highpass_hz,
        saturation_add=adjustment.saturation_add,
        sample_capture_path=adjustment.sample_capture_path,
        dsp_blocks=adjustment.dsp_blocks,
    )


def build_performance_adjustment_report(
    snapshots: Sequence[PerformanceEventSnapshot],
) -> PerformanceAdjustmentReport:
    """Aggregate event snapshots into one operator-readable performance report."""
    items = tuple(snapshots)
    if not items:
        raise ValueError("build_performance_adjustment_report requires at least one snapshot")

    dsp_blocks: list[str] = []
    for snapshot in items:
        for block in snapshot.dsp_blocks:
            if block not in dsp_blocks:
                dsp_blocks.append(block)

    frontline_roles = {"melody", "counter", "color"}
    frontline_ducked = 0
    for snapshot in items:
        if (
            snapshot.theramini_active
            and snapshot.role in frontline_roles
            and snapshot.amp_multiplier < 1.0
        ):
            frontline_ducked += 1

    return PerformanceAdjustmentReport(
        snapshots=items,
        snapshot_count=len(items),
        roles=_ordered_unique([snapshot.role for snapshot in items]),
        voice_names=_ordered_unique([snapshot.voice_name for snapshot in items]),
        dsp_blocks=tuple(dsp_blocks),
        sample_capture_paths=_ordered_unique(
            [snapshot.sample_capture_path for snapshot in items if snapshot.sample_capture_path]
        ),
        mean_amp_multiplier=round(
            sum(snapshot.amp_multiplier for snapshot in items) / len(items),
            4,
        ),
        max_release_multiplier=round(
            max(snapshot.release_multiplier for snapshot in items),
            4,
        ),
        min_brightness_multiplier=round(
            min(snapshot.brightness_multiplier for snapshot in items),
            4,
        ),
        space_total=round(sum(snapshot.space_amount for snapshot in items), 4),
        frontline_ducked_count=frontline_ducked,
        highpass_roles=_ordered_unique(
            [snapshot.role for snapshot in items if snapshot.highpass_hz > 0.0]
        ),
    )


def summarize_performance_adjustment_report(
    report: PerformanceAdjustmentReport,
) -> dict[str, object]:
    """Return a JSON-safe operator summary of a performance adjustment report."""
    snapshots_payload: list[dict[str, object]] = []
    for snapshot in report.snapshots:
        snapshots_payload.append(
            {
                "role": snapshot.role,
                "voice_name": snapshot.voice_name,
                "frequency_hz": snapshot.frequency_hz,
                "theramini_active": snapshot.theramini_active,
                "amp_multiplier": snapshot.amp_multiplier,
                "amp_band": snapshot.amp_band,
                "release_multiplier": snapshot.release_multiplier,
                "release_band": snapshot.release_band,
                "brightness_multiplier": snapshot.brightness_multiplier,
                "brightness_band": snapshot.brightness_band,
                "space_amount": snapshot.space_amount,
                "space_band": snapshot.space_band,
                "detune_add": snapshot.detune_add,
                "highpass_hz": snapshot.highpass_hz,
                "saturation_add": snapshot.saturation_add,
                "sample_capture_path": snapshot.sample_capture_path,
                "dsp_blocks": list(snapshot.dsp_blocks),
            }
        )
    return {
        "snapshot_count": report.snapshot_count,
        "roles": list(report.roles),
        "voice_names": list(report.voice_names),
        "dsp_blocks": list(report.dsp_blocks),
        "sample_capture_paths": list(report.sample_capture_paths),
        "mean_amp_multiplier": report.mean_amp_multiplier,
        "max_release_multiplier": report.max_release_multiplier,
        "min_brightness_multiplier": report.min_brightness_multiplier,
        "space_total": report.space_total,
        "frontline_ducked_count": report.frontline_ducked_count,
        "highpass_roles": list(report.highpass_roles),
        "snapshots": snapshots_payload,
    }
