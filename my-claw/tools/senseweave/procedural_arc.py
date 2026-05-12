"""Long-form procedural arc helpers for CypherClaw."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ArcPhase:
    name: str
    start_minute: float
    end_minute: float
    density: float
    mutation_rate: float
    transition_intent: str
    dynamic: str
    harmonic: str
    rhythm: str
    timbre: str
    spatial: str
    compression: float
    senseweave: float
    synthesis: str

    def production_targets(self) -> dict[str, float | str]:
        return {
            "phase": self.name,
            "density": self.density,
            "dynamic": self.dynamic,
            "harmonic": self.harmonic,
            "rhythm": self.rhythm,
            "timbre": self.timbre,
            "spatial": self.spatial,
            "compression": self.compression,
            "senseweave": self.senseweave,
            "synthesis": self.synthesis,
        }


@dataclass(frozen=True)
class ArcDirective:
    phase: ArcPhase
    density_target: float
    mutation_rate: float
    max_active_roles: int
    recovery_bias: float
    dynamic_target: str
    harmonic_target: str
    rhythm_target: str
    timbre_target: str
    spatial_target: str
    compression_target: float
    senseweave_target: float
    synthesis_target: str


ARC_PHASES: tuple[ArcPhase, ...] = (
    ArcPhase("Divination", 0.0, 5.0, 0.24, 0.18, "listen before speaking", "p", "open", "free", "sparse", "wide", 0.1, 0.8, "spectral"),
    ArcPhase("Emergence", 5.0, 12.0, 0.42, 0.32, "let pattern appear", "mp", "modal", "pulse", "warm", "clear", 0.3, 0.6, "fm"),
    ArcPhase("Conversation", 12.0, 20.0, 0.78, 0.56, "hold the ensemble in dialogue", "mf", "functional", "groove", "complex", "focused", 0.5, 0.4, "subtractive"),
    ArcPhase("Convergence", 20.0, 26.0, 0.54, 0.34, "return transformed material", "f", "chromatic", "polyrhythm", "bright", "intimate", 0.6, 0.2, "additive"),
    ArcPhase("Crystallization", 26.0, 30.0, 0.28, 0.16, "leave the distilled residue", "pp", "static", "drone", "pure", "expansive", 0.2, 0.9, "granular"),
)


def phase_for_elapsed(elapsed_minutes: float, *, cycle_minutes: float = 30.0) -> ArcPhase:
    wrapped = elapsed_minutes % cycle_minutes
    scaled = wrapped * (30.0 / cycle_minutes)
    for phase in ARC_PHASES:
        if phase.start_minute <= scaled < phase.end_minute:
            return phase
    return ARC_PHASES[-1]


def directive_for_elapsed(
    elapsed_minutes: float,
    *,
    cadence_state: str,
    cpu_pressure: float = 0.0,
    audience_attention: float = 0.0,
    cycle_minutes: float = 30.0,
) -> ArcDirective:
    phase = phase_for_elapsed(elapsed_minutes, cycle_minutes=cycle_minutes)
    density = phase.density
    mutation = phase.mutation_rate
    if cadence_state in {"sleep", "wind_down"}:
        density *= 0.7
        mutation *= 0.65
    if cadence_state == "away_practice":
        mutation *= 1.25
    if audience_attention > 0.65 and phase.name == "Conversation":
        density *= 1.08
    recovery_bias = min(1.0, max(0.0, cpu_pressure))
    density *= max(0.45, 1.0 - recovery_bias * 0.5)
    mutation *= max(0.5, 1.0 - recovery_bias * 0.35)
    max_roles = 4 if phase.name == "Conversation" else 3 if phase.name in {"Emergence", "Convergence"} else 2
    if recovery_bias >= 0.75:
        max_roles = max(1, max_roles - 1)
    return ArcDirective(
        phase=phase,
        density_target=round(density, 3),
        mutation_rate=round(mutation, 3),
        max_active_roles=max_roles,
        recovery_bias=round(recovery_bias, 3),
        dynamic_target=phase.dynamic,
        harmonic_target=phase.harmonic,
        rhythm_target=phase.rhythm,
        timbre_target=phase.timbre,
        spatial_target=phase.spatial,
        compression_target=phase.compression,
        senseweave_target=phase.senseweave,
        synthesis_target=phase.synthesis,
    )
