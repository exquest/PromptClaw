"""Environmental sampling plans for CypherClaw's EMSD track."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SampleSource:
    name: str
    capture_path: str
    source_type: str
    refresh_seconds: int
    musical_roles: tuple[str, ...]
    hardware_label: str = ""


@dataclass(frozen=True)
class SamplePlan:
    source: SampleSource
    transforms: tuple[str, ...]
    density: float
    buffer_seconds: float
    trigger_threshold: float
    study_focus: str
    section_function: str = ""
    cadence_state: str = ""


@dataclass(frozen=True)
class SampleBank:
    source: SampleSource
    freshness_seconds: int
    fallback_sources: tuple[str, ...]


SAMPLE_SOURCES: dict[str, SampleSource] = {
    "room_mic": SampleSource(
        "room_mic",
        "/tmp/room_capture.wav",
        "air",
        45,
        ("texture", "gesture", "presence"),
        "room/Perform-VE condenser",
    ),
    "garden_mic": SampleSource("garden_mic", "/tmp/garden_capture.wav", "outdoor", 90, ("texture", "drone", "weather")),
    "contact_mic": SampleSource("contact_mic", "/tmp/contact_capture.wav", "contact", 20, ("rhythm", "impulse", "body")),
    "theramini_in": SampleSource("theramini_in", "/tmp/theramini_capture.wav", "instrument", 30, ("melody", "counter", "echo")),
    "self_bus": SampleSource("self_bus", "/tmp/self_capture.wav", "internal", 60, ("remix", "memory", "freeze")),
}

SAMPLE_SOURCE_ALIASES: dict[str, str] = {
    "perform_ve_condenser": "room_mic",
    "room_perform_ve": "room_mic",
}

SAMPLE_FALLBACKS: dict[str, tuple[str, ...]] = {
    "garden_mic": ("room_mic", "contact_mic", "self_bus"),
    "theramini_in": ("contact_mic", "room_mic", "self_bus"),
    "room_mic": ("contact_mic", "self_bus"),
    "contact_mic": ("room_mic", "self_bus"),
    "self_bus": ("room_mic", "contact_mic"),
}


def canonical_sample_source_name(name: str) -> str:
    return SAMPLE_SOURCE_ALIASES.get(name, name)


def sample_source(name: str) -> SampleSource:
    return SAMPLE_SOURCES[canonical_sample_source_name(name)]


def sample_bank(name: str) -> SampleBank:
    source = sample_source(name)
    return SampleBank(
        source=source,
        freshness_seconds=int(source.refresh_seconds * 1.5),
        fallback_sources=SAMPLE_FALLBACKS.get(source.name, ()),
    )


def _ordered_unique(values: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(values))


_SECTION_TRANSFORMS: dict[str, tuple[str, ...]] = {
    "invocation": ("stretch", "spectral_freeze"),
    "statement": ("slice_rearrange", "pitch_window"),
    "lift": ("slice_rearrange", "granular_cloud", "pitch_window"),
    "arrival": ("slice_rearrange", "granular_cloud", "reverse_accents", "pitch_window"),
    "refrain": ("slice_rearrange", "pitch_window"),
    "development": (
        "slice_rearrange",
        "stretch",
        "spectral_freeze",
        "granular_cloud",
        "reverse_accents",
        "pitch_window",
    ),
    "turn": ("stretch", "reverse_accents", "pitch_window"),
    "instrumental_response": ("slice_rearrange", "granular_cloud", "reverse_accents"),
    "recap": ("slice_rearrange", "stretch", "pitch_window"),
    "coda": ("stretch", "spectral_freeze"),
    "residue": ("stretch", "spectral_freeze"),
}

_SECTION_DENSITY_BIAS: dict[str, float] = {
    "invocation": -0.04,
    "development": 0.12,
    "turn": 0.04,
    "instrumental_response": 0.08,
    "recap": -0.02,
    "coda": -0.06,
    "residue": -0.08,
}


def _section_focus(section_function: str) -> str:
    if section_function == "development":
        return "slice the source into grains, reversals, freezes, and pitch windows"
    if section_function in {"coda", "residue", "invocation"}:
        return "stretch and freeze the source into a long memory layer"
    if section_function in {"turn", "instrumental_response"}:
        return "answer the section with reversed and windowed sample gestures"
    return "capture gesture and redistribute it musically"


def plan_environmental_sampling(
    *,
    source_name: str,
    cadence_state: str,
    intensity: float = 0.5,
    section_function: str = "",
) -> SamplePlan:
    source = sample_source(source_name)
    if cadence_state == "sleep":
        transforms: tuple[str, ...] = ("stretch", "spectral_freeze")
        density = 0.12 + intensity * 0.08
        buffer_seconds = 24.0
        threshold = 0.22
        focus = "retain environment, remove edges, and stretch time"
    elif cadence_state == "away_practice":
        transforms = ("slice_rearrange", "granular_cloud", "reverse_accents")
        density = 0.42 + intensity * 0.22
        buffer_seconds = 14.0
        threshold = 0.12
        focus = "treat the room as mutable source material"
    elif cadence_state == "wind_down":
        transforms = ("stretch", "lowpass_resample")
        density = 0.18 + intensity * 0.09
        buffer_seconds = 18.0
        threshold = 0.18
        focus = "thin the source and leave only the soft body"
    else:
        transforms = ("slice_rearrange", "pitch_window")
        density = 0.24 + intensity * 0.15
        buffer_seconds = 12.0
        threshold = 0.15
        focus = "capture gesture and redistribute it musically"
    if source.source_type == "contact":
        threshold *= 1.3
        density *= 0.85
    function_key = section_function.strip().lower()
    if function_key:
        transforms = _ordered_unique(transforms + _SECTION_TRANSFORMS.get(function_key, ()))
        density += _SECTION_DENSITY_BIAS.get(function_key, 0.0)
        focus = _section_focus(function_key)
    return SamplePlan(
        source=source,
        transforms=transforms,
        density=round(max(0.04, min(density, 0.95)), 3),
        buffer_seconds=round(buffer_seconds, 1),
        trigger_threshold=round(threshold, 3),
        study_focus=focus,
        section_function=function_key,
        cadence_state=cadence_state,
    )


@dataclass(frozen=True)
class SamplePlanReport:
    source_name: str
    hardware_label: str
    source_type: str
    capture_path: str
    refresh_seconds: int
    freshness_seconds: int
    fallback_sources: tuple[str, ...]
    cadence_state: str
    section_function: str
    transforms: tuple[str, ...]
    transform_count: int
    density: float
    density_band: str
    buffer_seconds: float
    trigger_threshold: float
    threshold_band: str
    intensity: float
    intensity_band: str
    study_focus: str


def density_band(value: float) -> str:
    if value <= 0.20:
        return "sparse"
    if value <= 0.45:
        return "moderate"
    if value <= 0.70:
        return "dense"
    return "saturated"


def threshold_band(value: float) -> str:
    if value <= 0.12:
        return "hair"
    if value <= 0.18:
        return "soft"
    if value <= 0.24:
        return "firm"
    return "guarded"


def intensity_band(value: float) -> str:
    if value <= 0.34:
        return "subtle"
    if value <= 0.67:
        return "balanced"
    return "vivid"


def _clamp_unit(value: float) -> float:
    if value < 0.0:
        return 0.0
    if value > 1.0:
        return 1.0
    return value


def build_sample_plan_report(
    plan: SamplePlan,
    *,
    intensity: float = 0.5,
) -> SamplePlanReport:
    bank = sample_bank(plan.source.name)
    if intensity < 0.0 or intensity > 1.0:
        intensity = _clamp_unit(intensity)
    return SamplePlanReport(
        source_name=plan.source.name,
        hardware_label=plan.source.hardware_label,
        source_type=plan.source.source_type,
        capture_path=plan.source.capture_path,
        refresh_seconds=plan.source.refresh_seconds,
        freshness_seconds=bank.freshness_seconds,
        fallback_sources=bank.fallback_sources,
        cadence_state=plan.cadence_state,
        section_function=plan.section_function,
        transforms=plan.transforms,
        transform_count=len(plan.transforms),
        density=plan.density,
        density_band=density_band(plan.density),
        buffer_seconds=plan.buffer_seconds,
        trigger_threshold=plan.trigger_threshold,
        threshold_band=threshold_band(plan.trigger_threshold),
        intensity=intensity,
        intensity_band=intensity_band(intensity),
        study_focus=plan.study_focus,
    )


def summarize_sample_plan_report(report: SamplePlanReport) -> dict[str, object]:
    return {
        "source_name": report.source_name,
        "hardware_label": report.hardware_label,
        "source_type": report.source_type,
        "capture_path": report.capture_path,
        "refresh_seconds": report.refresh_seconds,
        "freshness_seconds": report.freshness_seconds,
        "fallback_sources": list(report.fallback_sources),
        "cadence_state": report.cadence_state,
        "section_function": report.section_function,
        "transforms": list(report.transforms),
        "transform_count": report.transform_count,
        "density": report.density,
        "density_band": report.density_band,
        "buffer_seconds": report.buffer_seconds,
        "trigger_threshold": report.trigger_threshold,
        "threshold_band": report.threshold_band,
        "intensity": report.intensity,
        "intensity_band": report.intensity_band,
        "study_focus": report.study_focus,
    }
