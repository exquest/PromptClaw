"""Synthesis-architecture strategy registry.

Maps each synthesis family to its production role affinities, safe parameter
ranges, arc-phase preferences, and fallback chain.  Score-tree sections and
tracker scenes use this registry to request a synthesis architecture by
production role or arc phase.  The depth-2 diagnostic helpers turn the same
in-memory registry into typed profile and report summaries for operators and
tests without adding a second selection path.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


ArchitectureId = Literal[
    "subtractive",
    "fm",
    "additive",
    "granular",
    "physical_model",
    "spectral",
]

REQUIRED_ARCHITECTURES: frozenset[str] = frozenset(
    ArchitectureId.__args__,  # type: ignore[attr-defined]
)

ArcPhaseName = Literal[
    "Divination",
    "Emergence",
    "Conversation",
    "Convergence",
    "Crystallization",
]

REQUIRED_PHASES: frozenset[str] = frozenset(
    ArcPhaseName.__args__,  # type: ignore[attr-defined]
)

_CANONICAL_PHASES: tuple[str, ...] = ArcPhaseName.__args__  # type: ignore[attr-defined]


@dataclass(frozen=True)
class SafeRange:
    """One controllable parameter with its safe operating bounds."""

    name: str
    default: float
    min_val: float
    max_val: float


@dataclass(frozen=True)
class ArchitectureStrategy:
    """Complete strategy record for one synthesis architecture."""

    architecture_id: str
    label: str
    summary: str
    role_tags: tuple[str, ...]
    macro_controls: tuple[SafeRange, ...]
    arc_affinity: dict[str, float]
    fallback: str


@dataclass(frozen=True)
class ArchitectureProfile:
    """Resolved diagnostic view of one synthesis architecture."""

    architecture_id: str
    label: str
    summary: str
    role_tags: tuple[str, ...]
    macro_control_count: int
    macro_control_names: tuple[str, ...]
    default_controls: dict[str, float]
    control_span_bands: dict[str, str]
    best_phase: str
    best_phase_affinity: float
    high_affinity_phases: tuple[str, ...]
    affinity_bands: dict[str, str]
    fallback: str
    fallback_chain: tuple[str, ...]
    role_count: int


@dataclass(frozen=True)
class ArchitectureRegistryReport:
    """Aggregate diagnostic view of the synthesis architecture registry."""

    total_count: int
    architecture_ids: tuple[str, ...]
    phases: tuple[str, ...]
    phase_winners: dict[str, str]
    phase_architectures: dict[str, tuple[str, ...]]
    roles: tuple[str, ...]
    role_architectures: dict[str, tuple[str, ...]]
    fallback_map: dict[str, str]
    missing_required_architectures: tuple[str, ...]
    missing_required_phases: tuple[str, ...]
    macro_control_counts: dict[str, int]
    profiles: tuple[ArchitectureProfile, ...]


_STRATEGIES: tuple[ArchitectureStrategy, ...] = (
    ArchitectureStrategy(
        architecture_id="subtractive",
        label="Subtractive",
        summary="Filtered harmonic source; strong midrange presence.",
        role_tags=("melody", "bass", "counter", "figuration"),
        macro_controls=(
            SafeRange("cutoff", 0.6, 0.0, 1.0),
            SafeRange("resonance", 0.3, 0.0, 1.0),
            SafeRange("envelope_depth", 0.5, 0.0, 1.0),
            SafeRange("drive", 0.0, 0.0, 1.0),
        ),
        arc_affinity={
            "Divination": 0.2,
            "Emergence": 0.6,
            "Conversation": 0.9,
            "Convergence": 0.5,
            "Crystallization": 0.15,
        },
        fallback="additive",
    ),
    ArchitectureStrategy(
        architecture_id="fm",
        label="FM",
        summary="Modulated tone with clear growth potential and metallic overtones.",
        role_tags=("melody", "bass", "counter", "figuration"),
        macro_controls=(
            SafeRange("mod_index", 0.5, 0.0, 1.0),
            SafeRange("ratio", 0.5, 0.0, 1.0),
            SafeRange("feedback", 0.0, 0.0, 0.8),
            SafeRange("brightness", 0.5, 0.0, 1.0),
        ),
        arc_affinity={
            "Divination": 0.3,
            "Emergence": 0.9,
            "Conversation": 0.6,
            "Convergence": 0.55,
            "Crystallization": 0.2,
        },
        fallback="subtractive",
    ),
    ArchitectureStrategy(
        architecture_id="additive",
        label="Additive",
        summary="Layered sine or partial construction; smooth timbral morphing.",
        role_tags=("melody", "color", "counter"),
        macro_controls=(
            SafeRange("partial_count", 0.5, 0.0, 1.0),
            SafeRange("spread", 0.4, 0.0, 1.0),
            SafeRange("rolloff", 0.5, 0.0, 1.0),
            SafeRange("detune", 0.0, 0.0, 1.0),
        ),
        arc_affinity={
            "Divination": 0.5,
            "Emergence": 0.4,
            "Conversation": 0.5,
            "Convergence": 0.9,
            "Crystallization": 0.35,
        },
        fallback="fm",
    ),
    ArchitectureStrategy(
        architecture_id="granular",
        label="Granular",
        summary="Clouded grains or residue texture; dissolves pitched material.",
        role_tags=("color", "foundation"),
        macro_controls=(
            SafeRange("grain_size", 0.05, 0.001, 0.5),
            SafeRange("density", 0.5, 0.0, 1.0),
            SafeRange("scatter", 0.3, 0.0, 1.0),
            SafeRange("pitch_jitter", 0.1, 0.0, 1.0),
        ),
        arc_affinity={
            "Divination": 0.7,
            "Emergence": 0.3,
            "Conversation": 0.2,
            "Convergence": 0.4,
            "Crystallization": 0.9,
        },
        fallback="spectral",
    ),
    ArchitectureStrategy(
        architecture_id="physical_model",
        label="Physical Modeling",
        summary="Waveguide or modal resonance; organic response to excitation.",
        role_tags=("melody", "bass", "counter", "foundation", "rhythm"),
        macro_controls=(
            SafeRange("excitation", 0.5, 0.0, 1.0),
            SafeRange("damping", 0.4, 0.0, 1.0),
            SafeRange("brightness", 0.5, 0.0, 1.0),
            SafeRange("body_size", 0.5, 0.0, 1.0),
        ),
        arc_affinity={
            "Divination": 0.35,
            "Emergence": 0.55,
            "Conversation": 0.7,
            "Convergence": 0.6,
            "Crystallization": 0.3,
        },
        fallback="subtractive",
    ),
    ArchitectureStrategy(
        architecture_id="spectral",
        label="Spectral / FFT",
        summary="Tone built from partials via FFT analysis; ethereal texture.",
        role_tags=("color", "foundation"),
        macro_controls=(
            SafeRange("fft_size", 0.5, 0.0, 1.0),
            SafeRange("freeze", 0.0, 0.0, 1.0),
            SafeRange("stretch", 0.5, 0.0, 1.0),
            SafeRange("spectral_shift", 0.0, -1.0, 1.0),
        ),
        arc_affinity={
            "Divination": 0.9,
            "Emergence": 0.4,
            "Conversation": 0.25,
            "Convergence": 0.45,
            "Crystallization": 0.7,
        },
        fallback="granular",
    ),
)


ARCHITECTURE_REGISTRY: dict[str, ArchitectureStrategy] = {
    s.architecture_id: s for s in _STRATEGIES
}


def get_strategy(architecture_id: str) -> ArchitectureStrategy:
    """Look up a strategy by architecture id.  Raises KeyError if unknown."""
    return ARCHITECTURE_REGISTRY[architecture_id]


def strategies_for_role(role: str) -> tuple[ArchitectureStrategy, ...]:
    """Return all architectures whose role_tags include *role*."""
    return tuple(s for s in _STRATEGIES if role in s.role_tags)


def architectures_for_phase(
    phase: str,
    *,
    threshold: float = 0.0,
) -> tuple[ArchitectureStrategy, ...]:
    """Return architectures with affinity above *threshold* for *phase*, highest first."""
    ranked = sorted(
        (s for s in _STRATEGIES if s.arc_affinity.get(phase, 0.0) > threshold),
        key=lambda s: s.arc_affinity.get(phase, 0.0),
        reverse=True,
    )
    return tuple(ranked)


def best_architecture_for_phase(phase: str) -> ArchitectureStrategy:
    """Return the single architecture with the highest affinity for *phase*."""
    return max(_STRATEGIES, key=lambda s: s.arc_affinity.get(phase, 0.0))


def resolve_architecture(architecture_id: str) -> ArchitectureStrategy:
    """Return the strategy, falling back if *architecture_id* is unknown."""
    if architecture_id in ARCHITECTURE_REGISTRY:
        return ARCHITECTURE_REGISTRY[architecture_id]
    for strategy in _STRATEGIES:
        if strategy.fallback == architecture_id:
            return strategy
    return ARCHITECTURE_REGISTRY["subtractive"]


def covered_architectures() -> frozenset[str]:
    """Set of architecture IDs represented in the registry."""
    return frozenset(s.architecture_id for s in _STRATEGIES)


def affinity_band(value: float) -> str:
    """Map an arc-affinity value to a stable named band."""
    if value < 0.4:
        return "low"
    if value < 0.7:
        return "medium"
    return "high"


def control_span_band(control: SafeRange) -> str:
    """Map a safe-control range width to a stable named band."""
    width = control.max_val - control.min_val
    if width <= 0.5:
        return "narrow"
    if width <= 1.0:
        return "standard"
    return "wide"


def fallback_chain(architecture_id: str) -> tuple[str, ...]:
    """Resolve an architecture and follow registered fallbacks until a cycle."""
    current = resolve_architecture(architecture_id)
    chain: list[str] = []
    seen: set[str] = set()
    while current.architecture_id not in seen:
        chain.append(current.architecture_id)
        seen.add(current.architecture_id)
        if current.fallback not in ARCHITECTURE_REGISTRY:
            break
        current = ARCHITECTURE_REGISTRY[current.fallback]
    return tuple(chain)


def build_architecture_profile(strategy: ArchitectureStrategy) -> ArchitectureProfile:
    """Build a typed diagnostic profile for one architecture strategy."""
    macro_names: list[str] = []
    defaults: dict[str, float] = {}
    span_bands: dict[str, str] = {}
    for control in strategy.macro_controls:
        macro_names.append(control.name)
        defaults[control.name] = control.default
        span_bands[control.name] = control_span_band(control)

    best_phase = _CANONICAL_PHASES[0]
    best_affinity = strategy.arc_affinity.get(best_phase, 0.0)
    high_phases: list[str] = []
    affinity_bands: dict[str, str] = {}
    for phase in _CANONICAL_PHASES:
        affinity = strategy.arc_affinity.get(phase, 0.0)
        if affinity > best_affinity:
            best_phase = phase
            best_affinity = affinity
        if affinity >= 0.7:
            high_phases.append(phase)
        affinity_bands[phase] = affinity_band(affinity)

    return ArchitectureProfile(
        architecture_id=strategy.architecture_id,
        label=strategy.label,
        summary=strategy.summary,
        role_tags=strategy.role_tags,
        macro_control_count=len(strategy.macro_controls),
        macro_control_names=tuple(macro_names),
        default_controls=defaults,
        control_span_bands=span_bands,
        best_phase=best_phase,
        best_phase_affinity=best_affinity,
        high_affinity_phases=tuple(high_phases),
        affinity_bands=affinity_bands,
        fallback=strategy.fallback,
        fallback_chain=fallback_chain(strategy.architecture_id),
        role_count=len(strategy.role_tags),
    )


def build_architecture_registry_report() -> ArchitectureRegistryReport:
    """Build the registry-wide :class:`ArchitectureRegistryReport`."""
    profiles = tuple(build_architecture_profile(strategy) for strategy in _STRATEGIES)
    architecture_ids = tuple(profile.architecture_id for profile in profiles)

    phase_winners: dict[str, str] = {}
    phase_architectures: dict[str, tuple[str, ...]] = {}
    for phase in _CANONICAL_PHASES:
        phase_winners[phase] = best_architecture_for_phase(phase).architecture_id
        phase_architectures[phase] = tuple(
            strategy.architecture_id for strategy in architectures_for_phase(phase)
        )

    role_order: list[str] = []
    for strategy in _STRATEGIES:
        for role in strategy.role_tags:
            if role not in role_order:
                role_order.append(role)

    role_architectures: dict[str, tuple[str, ...]] = {}
    for role in role_order:
        role_architectures[role] = tuple(
            strategy.architecture_id for strategy in strategies_for_role(role)
        )

    missing_phases: list[str] = []
    for phase in _CANONICAL_PHASES:
        if any(phase not in strategy.arc_affinity for strategy in _STRATEGIES):
            missing_phases.append(phase)

    return ArchitectureRegistryReport(
        total_count=len(_STRATEGIES),
        architecture_ids=architecture_ids,
        phases=_CANONICAL_PHASES,
        phase_winners=phase_winners,
        phase_architectures=phase_architectures,
        roles=tuple(role_order),
        role_architectures=role_architectures,
        fallback_map={
            strategy.architecture_id: strategy.fallback for strategy in _STRATEGIES
        },
        missing_required_architectures=tuple(
            sorted(REQUIRED_ARCHITECTURES - set(architecture_ids))
        ),
        missing_required_phases=tuple(missing_phases),
        macro_control_counts={
            profile.architecture_id: profile.macro_control_count
            for profile in profiles
        },
        profiles=profiles,
    )


def summarize_architecture_registry_report(
    report: ArchitectureRegistryReport,
) -> dict[str, object]:
    """Render an architecture registry report as a JSON-safe summary."""
    profiles_payload: list[dict[str, object]] = []
    for profile in report.profiles:
        profiles_payload.append(
            {
                "architecture_id": profile.architecture_id,
                "label": profile.label,
                "summary": profile.summary,
                "role_tags": list(profile.role_tags),
                "macro_control_count": profile.macro_control_count,
                "macro_control_names": list(profile.macro_control_names),
                "default_controls": dict(profile.default_controls),
                "control_span_bands": dict(profile.control_span_bands),
                "best_phase": profile.best_phase,
                "best_phase_affinity": profile.best_phase_affinity,
                "high_affinity_phases": list(profile.high_affinity_phases),
                "affinity_bands": dict(profile.affinity_bands),
                "fallback": profile.fallback,
                "fallback_chain": list(profile.fallback_chain),
                "role_count": profile.role_count,
            }
        )
    return {
        "total_count": report.total_count,
        "architecture_ids": list(report.architecture_ids),
        "phases": list(report.phases),
        "phase_winners": dict(report.phase_winners),
        "phase_architectures": {
            phase: list(ids) for phase, ids in report.phase_architectures.items()
        },
        "roles": list(report.roles),
        "role_architectures": {
            role: list(ids) for role, ids in report.role_architectures.items()
        },
        "fallback_map": dict(report.fallback_map),
        "missing_required_architectures": list(
            report.missing_required_architectures
        ),
        "missing_required_phases": list(report.missing_required_phases),
        "macro_control_counts": dict(report.macro_control_counts),
        "profiles": profiles_payload,
    }
