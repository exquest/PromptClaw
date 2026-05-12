"""Live EMSD context wiring for CypherClaw songs."""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Mapping, Sequence

from .artistic_identity import ArtisticIdentity
from .capstone_engine import CapstoneCyclePlan, CapstonePhasePlan, build_capstone_cycle
from .procedural_arc import ArcDirective, directive_for_elapsed


CANONICAL_ARC_PHASES: tuple[str, ...] = (
    "Divination",
    "Emergence",
    "Conversation",
    "Convergence",
    "Crystallization",
)

CANONICAL_DENSITY_BANDS: tuple[str, ...] = ("calm", "neutral", "intense")

_ARC_PHASE_BANDS: Mapping[str, str] = {
    "Divination": "opening",
    "Emergence": "opening",
    "Conversation": "dialogue",
    "Convergence": "resolution",
    "Crystallization": "resolution",
}


def _clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


@dataclass(frozen=True)
class EMSDLiveContext:
    arc: ArcDirective
    phase_plan: CapstonePhasePlan
    cycle: CapstoneCyclePlan
    density_bias: float

    @property
    def identity(self) -> ArtisticIdentity:
        return self.cycle.identity


def build_live_emsd_context(
    *,
    cadence_state: str,
    occupancy_state: str,
    family_name: str,
    progression_profile: str,
    patch_name: str,
    song_num: int,
    theramini_present: bool,
    repertoire_songs: Sequence[Mapping[str, object]],
    base_density_bias: float = 0.0,
    attention_score: float = 0.0,
    cpu_pressure: float = 0.0,
    now_seconds: float | None = None,
) -> EMSDLiveContext:
    """Build one typed EMSD runtime context for the current song."""

    now = time.time() if now_seconds is None else now_seconds
    arc = directive_for_elapsed(
        (now / 60.0) % 30.0,
        cadence_state=cadence_state,
        cpu_pressure=cpu_pressure,
        audience_attention=attention_score,
    )
    cycle = build_capstone_cycle(
        cadence_state=cadence_state,
        occupancy_state=occupancy_state,
        theramini_present=theramini_present,
        repertoire_songs=repertoire_songs,
    )
    phase_plan = next(
        (
            phase
            for phase in cycle.phases
            if phase.phase_name == arc.phase.name
        ),
        cycle.phases[0],
    )
    density_offset = (arc.density_target - 0.5) * 0.18
    if family_name != phase_plan.family_name:
        density_offset *= 0.75
    if patch_name != phase_plan.patch_name:
        density_offset *= 0.8
    if progression_profile == "experiment":
        density_offset += 0.03
    density_bias = _clamp(base_density_bias + density_offset, -0.25, 0.25)
    return EMSDLiveContext(
        arc=arc,
        phase_plan=phase_plan,
        cycle=cycle,
        density_bias=round(density_bias, 3),
    )


def composer_emsd_extras(context: EMSDLiveContext) -> dict[str, object]:
    """Flatten EMSD context into a composer-state payload."""

    dynamics = context.phase_plan.mix.dynamics
    production_metadata = {
        role: {
            **metadata,
            "frequency_lanes": list(metadata["frequency_lanes"]),
        }
        for role, metadata in context.phase_plan.mix.production_metadata.items()
    }
    return {
        "arc_phase": context.arc.phase.name,
        "arc_density_target": context.arc.density_target,
        "arc_mutation_rate": context.arc.mutation_rate,
        "arc_transition_intent": context.arc.phase.transition_intent,
        "arc_recovery_bias": context.arc.recovery_bias,
        "arc_max_active_roles": context.arc.max_active_roles,
        "mix_target_lufs": context.phase_plan.mix.target_lufs,
        "mix_peak_ceiling_dbtp": context.phase_plan.mix.peak_ceiling_dbtp,
        "mix_bus_comp_ratio": context.phase_plan.mix.bus_comp_ratio,
        "mix_theramini_duck_db": context.phase_plan.mix.theramini_duck_db,
        "mix_dynamic_range_db": dynamics.dynamic_range_db if dynamics else None,
        "mix_comp_ratio_phase": dynamics.comp_ratio if dynamics else None,
        "mix_comp_attack_ms": dynamics.comp_attack_ms if dynamics else None,
        "mix_comp_release_ms": dynamics.comp_release_ms if dynamics else None,
        "mix_transient_policy": dynamics.transient_policy if dynamics else None,
        "mix_role_frequency_lanes": {
            role: list(lanes)
            for role, lanes in context.phase_plan.mix.role_frequency_lanes.items()
        },
        "mix_production_metadata": production_metadata,
        "mix_deference_rules": [
            {
                "source": r.source,
                "trigger": r.trigger,
                "action": r.action,
                "duck_db": r.duck_db,
                "attack_ms": r.attack_ms,
                "release_ms": r.release_ms,
                "priority": r.priority,
            }
            for r in dynamics.deference_rules
        ] if dynamics else [],
        "sample_source": context.phase_plan.sampling.source.name,
        "sample_capture_path": context.phase_plan.sampling.source.capture_path,
        "sample_refresh_seconds": context.phase_plan.sampling.source.refresh_seconds,
        "sample_roles": list(context.phase_plan.sampling.source.musical_roles),
        "sample_transforms": list(context.phase_plan.sampling.transforms),
        "sample_density": context.phase_plan.sampling.density,
        "sample_buffer_seconds": context.phase_plan.sampling.buffer_seconds,
        "sample_trigger_threshold": context.phase_plan.sampling.trigger_threshold,
        "dsp_blocks": list(context.phase_plan.dsp.blocks),
        "dsp_source_focus": context.phase_plan.dsp.source_focus,
        "glyph_visual_bias": dict(context.phase_plan.dsp.visual_bias),
        "artistic_identity": context.identity.statement,
        "artistic_families": list(context.identity.signature_families),
        "artistic_patches": list(context.identity.signature_patches),
        "artistic_images": list(context.identity.signature_images),
        "emsd_density_bias": context.density_bias,
    }


@dataclass(frozen=True)
class EMSDPhaseSnapshot:
    arc_phase: str
    arc_phase_index: int
    arc_phase_band: str
    family_name: str
    patch_name: str
    sample_source: str
    arc_density_target: float
    arc_max_active_roles: int
    mix_target_lufs: float
    density_bias: float
    density_band: str
    artistic_identity: str


@dataclass(frozen=True)
class EMSDRuntimeReport:
    snapshots: tuple[EMSDPhaseSnapshot, ...]
    snapshot_count: int
    arc_phase_history: tuple[str, ...]
    phase_counts: Mapping[str, int]
    band_counts: Mapping[str, int]
    distinct_families: tuple[str, ...]
    distinct_patches: tuple[str, ...]
    distinct_sample_sources: tuple[str, ...]
    transitions: tuple[tuple[str, str], ...]
    mean_density_bias: float
    max_density_bias: float
    min_density_bias: float


def arc_phase_index(phase_name: str) -> int:
    """Return the canonical index of *phase_name* or -1 if unknown."""
    for index, name in enumerate(CANONICAL_ARC_PHASES):
        if name == phase_name:
            return index
    return -1


def arc_phase_band(phase_name: str) -> str:
    """Return the canonical opening/dialogue/resolution band for *phase_name*."""
    return _ARC_PHASE_BANDS.get(phase_name, "unclassified")


def density_pressure_band(density_bias: float) -> str:
    """Map a density bias value to its canonical pressure band."""
    if density_bias <= -0.05:
        return "calm"
    if density_bias >= 0.05:
        return "intense"
    return "neutral"


def build_phase_snapshot(context: EMSDLiveContext) -> EMSDPhaseSnapshot:
    """Build one typed phase snapshot from a live EMSD context."""
    arc = context.arc
    plan = context.phase_plan
    bias = context.density_bias
    phase_name = arc.phase.name
    return EMSDPhaseSnapshot(
        arc_phase=phase_name,
        arc_phase_index=arc_phase_index(phase_name),
        arc_phase_band=arc_phase_band(phase_name),
        family_name=plan.family_name,
        patch_name=plan.patch_name,
        sample_source=plan.sampling.source.name,
        arc_density_target=arc.density_target,
        arc_max_active_roles=arc.max_active_roles,
        mix_target_lufs=plan.mix.target_lufs,
        density_bias=bias,
        density_band=density_pressure_band(bias),
        artistic_identity=context.identity.statement,
    )


def build_runtime_report(
    snapshots: Sequence[EMSDPhaseSnapshot],
) -> EMSDRuntimeReport:
    """Aggregate a sequence of phase snapshots into one runtime report."""
    items = tuple(snapshots)
    if not items:
        raise ValueError("build_runtime_report requires at least one snapshot")

    history = tuple(snap.arc_phase for snap in items)

    phase_counts: dict[str, int] = {phase: 0 for phase in CANONICAL_ARC_PHASES}
    for phase in history:
        if phase in phase_counts:
            phase_counts[phase] += 1

    band_counts: dict[str, int] = {band: 0 for band in CANONICAL_DENSITY_BANDS}
    for snap in items:
        if snap.density_band in band_counts:
            band_counts[snap.density_band] += 1

    families: list[str] = []
    patches: list[str] = []
    sources: list[str] = []
    for snap in items:
        if snap.family_name not in families:
            families.append(snap.family_name)
        if snap.patch_name not in patches:
            patches.append(snap.patch_name)
        if snap.sample_source not in sources:
            sources.append(snap.sample_source)

    transitions: list[tuple[str, str]] = []
    for prev, curr in zip(history, history[1:]):
        if prev != curr:
            transitions.append((prev, curr))

    biases = [snap.density_bias for snap in items]
    mean_bias = round(sum(biases) / len(biases), 4)

    return EMSDRuntimeReport(
        snapshots=items,
        snapshot_count=len(items),
        arc_phase_history=history,
        phase_counts=phase_counts,
        band_counts=band_counts,
        distinct_families=tuple(families),
        distinct_patches=tuple(patches),
        distinct_sample_sources=tuple(sources),
        transitions=tuple(transitions),
        mean_density_bias=mean_bias,
        max_density_bias=round(max(biases), 4),
        min_density_bias=round(min(biases), 4),
    )


def summarize_runtime_report(report: EMSDRuntimeReport) -> dict[str, object]:
    """Return a JSON-safe operator summary of *report*."""
    snapshots_payload: list[dict[str, object]] = []
    for snap in report.snapshots:
        snapshots_payload.append(
            {
                "arc_phase": snap.arc_phase,
                "arc_phase_index": snap.arc_phase_index,
                "arc_phase_band": snap.arc_phase_band,
                "family_name": snap.family_name,
                "patch_name": snap.patch_name,
                "sample_source": snap.sample_source,
                "arc_density_target": snap.arc_density_target,
                "arc_max_active_roles": snap.arc_max_active_roles,
                "mix_target_lufs": snap.mix_target_lufs,
                "density_bias": snap.density_bias,
                "density_band": snap.density_band,
                "artistic_identity": snap.artistic_identity,
            }
        )
    return {
        "snapshot_count": report.snapshot_count,
        "arc_phase_history": list(report.arc_phase_history),
        "phase_counts": dict(report.phase_counts),
        "band_counts": dict(report.band_counts),
        "distinct_families": list(report.distinct_families),
        "distinct_patches": list(report.distinct_patches),
        "distinct_sample_sources": list(report.distinct_sample_sources),
        "transitions": [[prev, curr] for prev, curr in report.transitions],
        "mean_density_bias": report.mean_density_bias,
        "max_density_bias": report.max_density_bias,
        "min_density_bias": report.min_density_bias,
        "snapshots": snapshots_payload,
    }
