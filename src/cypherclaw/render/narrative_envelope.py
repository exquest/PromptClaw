"""Narrative beat to SectionEnvelope coupling.

Maps procedural arc state (phase, density, dynamic, timbre) and section
function into populated SectionEnvelope instances so dramatic arcs drive
section-level musical parameters.
"""
from __future__ import annotations

from dataclasses import dataclass
from .events import Breakpoint, SectionEnvelope


@dataclass(frozen=True)
class ToneVector:
    darkness: float = 0.5
    energy: float = 0.5
    warmth: float = 0.5
    density: float = 0.5


@dataclass(frozen=True)
class NarrativeBeat:
    arc_phase: str
    section_function: str
    tension_target: float
    tone: ToneVector


_DYNAMIC_ENERGY: dict[str, float] = {
    "pp": 0.12,
    "p": 0.25,
    "mp": 0.42,
    "mf": 0.58,
    "f": 0.78,
    "ff": 0.92,
}

_TIMBRE_WARMTH: dict[str, float] = {
    "sparse": 0.2,
    "warm": 0.65,
    "complex": 0.5,
    "bright": 0.35,
    "pure": 0.7,
}

_PHASE_TENSION_SHAPES: dict[str, tuple[Breakpoint, ...]] = {
    "Divination": ((0.0, 0.08), (0.5, 0.15), (1.0, 0.25)),
    "Emergence": ((0.0, 0.18), (0.5, 0.35), (1.0, 0.50)),
    "Conversation": ((0.0, 0.50), (0.3, 0.65), (0.7, 0.72), (1.0, 0.60)),
    "Convergence": ((0.0, 0.60), (0.35, 0.85), (0.7, 0.65), (1.0, 0.45)),
    "Crystallization": ((0.0, 0.35), (0.3, 0.22), (0.7, 0.12), (1.0, 0.06)),
}

_FUNCTION_TENSION_MODIFIER: dict[str, tuple[float, float]] = {
    "invocation": (-0.05, 0.0),
    "statement": (0.0, 0.0),
    "arrival": (0.05, 0.05),
    "lift": (0.05, 0.08),
    "development": (0.08, 0.12),
    "turn": (0.10, 0.15),
    "contrast": (0.06, 0.10),
    "bridge": (-0.02, -0.15),
    "release": (-0.05, -0.25),
    "recap": (0.10, -0.38),
    "resolution": (0.05, -0.40),
    "coda": (0.08, -0.42),
    "residue": (-0.02, -0.40),
}

_PHASE_TEMPO_SCALE: dict[str, float] = {
    "Divination": 0.92,
    "Emergence": 0.97,
    "Conversation": 1.05,
    "Convergence": 1.02,
    "Crystallization": 0.88,
}


def _clamp(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, value))


def _modify_breakpoints(
    base: tuple[Breakpoint, ...],
    start_offset: float,
    end_offset: float,
) -> tuple[Breakpoint, ...]:
    n = len(base)
    result: list[Breakpoint] = []
    for i, (pos, val) in enumerate(base):
        t = i / max(1, n - 1)
        offset = start_offset + (end_offset - start_offset) * t
        result.append((pos, _clamp(val + offset)))
    return tuple(result)


def envelope_for_beat(beat: NarrativeBeat) -> SectionEnvelope:
    phase = beat.arc_phase
    if phase not in _PHASE_TENSION_SHAPES:
        phase = "Emergence"

    func = beat.section_function
    start_mod, end_mod = _FUNCTION_TENSION_MODIFIER.get(func, (0.0, 0.0))

    tension_base = _PHASE_TENSION_SHAPES[phase]
    tension_points = _modify_breakpoints(tension_base, start_mod, end_mod)

    density = _clamp(beat.tone.density, 0.05, 0.95)
    brightness = _clamp((1.0 - beat.tone.darkness) * 0.7 + beat.tone.energy * 0.3)
    dynamic = _clamp(beat.tone.energy * 0.7 + (1.0 - beat.tone.darkness) * 0.2 + beat.tone.warmth * 0.1)
    tempo = max(0.5, _PHASE_TEMPO_SCALE.get(phase, 1.0))

    return SectionEnvelope(
        tempo_base=tempo,
        density_target=density,
        dynamic_plane=dynamic,
        brightness=brightness,
        tension_trajectory=tension_points,
    )


def tone_from_narrative(
    *,
    arc_phase: str,
    mood: float,
    creative_energy: float,
    curiosity: float,
    density_target: float,
    dynamic_target: str,
    timbre_target: str,
) -> ToneVector:
    darkness = _clamp(0.5 - mood * 0.5)
    energy_base = _DYNAMIC_ENERGY.get(dynamic_target, 0.5)
    energy = _clamp(creative_energy * 0.6 + energy_base * 0.4)
    warmth = _TIMBRE_WARMTH.get(timbre_target, 0.5)
    density = _clamp(density_target)
    return ToneVector(
        darkness=darkness,
        energy=energy,
        warmth=warmth,
        density=density,
    )


def beat_from_directive(
    directive: object,
    section_function: str,
) -> NarrativeBeat:
    phase_name = getattr(getattr(directive, "phase", None), "name", "Emergence")
    density = float(getattr(directive, "density_target", 0.5) or 0.5)
    dynamic = str(getattr(directive, "dynamic_target", "mf") or "mf")
    timbre = str(getattr(directive, "timbre_target", "warm") or "warm")
    compression = float(getattr(directive, "compression_target", 0.3) or 0.3)

    tone = tone_from_narrative(
        arc_phase=phase_name,
        mood=0.0,
        creative_energy=_clamp(1.0 - compression),
        curiosity=0.5,
        density_target=density,
        dynamic_target=dynamic,
        timbre_target=timbre,
    )

    tension_base = _clamp(density * 0.6 + _DYNAMIC_ENERGY.get(dynamic, 0.5) * 0.4)

    return NarrativeBeat(
        arc_phase=phase_name,
        section_function=section_function,
        tension_target=tension_base,
        tone=tone,
    )
