"""Genre-literacy strategy library for SenseWeave composition.

Each strategy describes tendencies and affinities for a genre tradition,
influencing form, harmony, rhythm, synthesis, arrangement, and mix decisions
without hardcoding imitation.  Downstream modules read these parameters as
bias vectors rather than prescriptive rules.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal, Sequence

GenreId = Literal[
    "ambient_drone_generative",
    "minimalism",
    "jazz",
    "idm_electronic",
    "classical_orchestral",
    "musique_concrete",
    "spectral",
    "blues",
    "world_music",
    "post_rock_experimental",
]

REQUIRED_GENRES: frozenset[str] = frozenset(GenreId.__args__)  # type: ignore[attr-defined]

ArcPhaseName = Literal[
    "Divination",
    "Emergence",
    "Conversation",
    "Convergence",
    "Crystallization",
]


@dataclass(frozen=True)
class FormHint:
    preferred_families: tuple[str, ...]
    section_density: float
    through_composed_bias: float
    repetition_tolerance: float


@dataclass(frozen=True)
class HarmonyHint:
    modal_preferences: tuple[str, ...]
    harmonic_rhythm: str
    tension_vocabulary: tuple[str, ...]
    chromatic_tolerance: float


@dataclass(frozen=True)
class RhythmHint:
    groove_types: tuple[str, ...]
    subdivision_feel: str
    tempo_range: tuple[float, float]
    rubato_tolerance: float


@dataclass(frozen=True)
class SynthesisHint:
    timbral_character: tuple[str, ...]
    texture_density: float
    attack_preference: str
    spectral_focus: str


@dataclass(frozen=True)
class ArrangementHint:
    voice_count_range: tuple[int, int]
    density_curve: str
    staging_approach: str
    layering_style: str


@dataclass(frozen=True)
class MixHint:
    frequency_emphasis: str
    spatial_width: float
    reverb_character: str
    dynamic_range: str


@dataclass(frozen=True)
class GenreStrategy:
    genre_id: GenreId
    label: str
    form: FormHint
    harmony: HarmonyHint
    rhythm: RhythmHint
    synthesis: SynthesisHint
    arrangement: ArrangementHint
    mix: MixHint
    arc_affinity: dict[str, float]


_GENRE_STRATEGIES: dict[str, GenreStrategy] = {
    "ambient_drone_generative": GenreStrategy(
        genre_id="ambient_drone_generative",
        label="Ambient / Drone / Generative",
        form=FormHint(
            preferred_families=("ambient_arc", "through_composed"),
            section_density=0.3,
            through_composed_bias=0.85,
            repetition_tolerance=0.9,
        ),
        harmony=HarmonyHint(
            modal_preferences=("lydian", "dorian", "mixolydian"),
            harmonic_rhythm="glacial",
            tension_vocabulary=("pedal_tone", "slow_cluster", "spectral_drift"),
            chromatic_tolerance=0.4,
        ),
        rhythm=RhythmHint(
            groove_types=("straight", "lilt"),
            subdivision_feel="free",
            tempo_range=(40.0, 80.0),
            rubato_tolerance=0.9,
        ),
        synthesis=SynthesisHint(
            timbral_character=("pad", "breath", "resonance"),
            texture_density=0.35,
            attack_preference="slow",
            spectral_focus="low_mid",
        ),
        arrangement=ArrangementHint(
            voice_count_range=(1, 4),
            density_curve="plateau",
            staging_approach="slow_bloom",
            layering_style="additive",
        ),
        mix=MixHint(
            frequency_emphasis="sub_and_air",
            spatial_width=0.85,
            reverb_character="vast",
            dynamic_range="wide",
        ),
        arc_affinity={
            "Divination": 0.95,
            "Emergence": 0.8,
            "Conversation": 0.5,
            "Convergence": 0.7,
            "Crystallization": 0.92,
        },
    ),
    "minimalism": GenreStrategy(
        genre_id="minimalism",
        label="Minimalism",
        form=FormHint(
            preferred_families=("through_composed", "rondo_return", "ambient_arc"),
            section_density=0.4,
            through_composed_bias=0.7,
            repetition_tolerance=0.95,
        ),
        harmony=HarmonyHint(
            modal_preferences=("ionian", "dorian", "mixolydian"),
            harmonic_rhythm="slow_pulse",
            tension_vocabulary=("phase_shift", "additive_accent", "modal_interchange"),
            chromatic_tolerance=0.2,
        ),
        rhythm=RhythmHint(
            groove_types=("straight", "push"),
            subdivision_feel="steady_pulse",
            tempo_range=(80.0, 140.0),
            rubato_tolerance=0.15,
        ),
        synthesis=SynthesisHint(
            timbral_character=("bell", "pluck", "mallet"),
            texture_density=0.5,
            attack_preference="crisp",
            spectral_focus="mid",
        ),
        arrangement=ArrangementHint(
            voice_count_range=(2, 5),
            density_curve="gradual_build",
            staging_approach="phased_entry",
            layering_style="interlocking",
        ),
        mix=MixHint(
            frequency_emphasis="mid_presence",
            spatial_width=0.6,
            reverb_character="room",
            dynamic_range="moderate",
        ),
        arc_affinity={
            "Divination": 0.6,
            "Emergence": 0.9,
            "Conversation": 0.85,
            "Convergence": 0.75,
            "Crystallization": 0.7,
        },
    ),
    "jazz": GenreStrategy(
        genre_id="jazz",
        label="Jazz",
        form=FormHint(
            preferred_families=("aaba", "verse_chorus", "bridge"),
            section_density=0.65,
            through_composed_bias=0.35,
            repetition_tolerance=0.5,
        ),
        harmony=HarmonyHint(
            modal_preferences=("dorian", "mixolydian", "lydian", "aeolian"),
            harmonic_rhythm="walking",
            tension_vocabulary=("tritone_sub", "upper_extension", "chromatic_approach"),
            chromatic_tolerance=0.8,
        ),
        rhythm=RhythmHint(
            groove_types=("swing", "shuffle", "lilt"),
            subdivision_feel="triplet",
            tempo_range=(60.0, 200.0),
            rubato_tolerance=0.65,
        ),
        synthesis=SynthesisHint(
            timbral_character=("bowed", "pluck", "breath"),
            texture_density=0.55,
            attack_preference="articulate",
            spectral_focus="mid_high",
        ),
        arrangement=ArrangementHint(
            voice_count_range=(3, 6),
            density_curve="conversational",
            staging_approach="call_response",
            layering_style="polyphonic",
        ),
        mix=MixHint(
            frequency_emphasis="warm_presence",
            spatial_width=0.55,
            reverb_character="club",
            dynamic_range="wide",
        ),
        arc_affinity={
            "Divination": 0.5,
            "Emergence": 0.7,
            "Conversation": 0.95,
            "Convergence": 0.65,
            "Crystallization": 0.45,
        },
    ),
    "idm_electronic": GenreStrategy(
        genre_id="idm_electronic",
        label="IDM / Electronic",
        form=FormHint(
            preferred_families=("build_drop", "through_composed", "rondo_return"),
            section_density=0.7,
            through_composed_bias=0.55,
            repetition_tolerance=0.6,
        ),
        harmony=HarmonyHint(
            modal_preferences=("phrygian", "aeolian", "lydian"),
            harmonic_rhythm="erratic",
            tension_vocabulary=("glitch_rupture", "bit_crush", "granular_smear"),
            chromatic_tolerance=0.65,
        ),
        rhythm=RhythmHint(
            groove_types=("push", "straight", "shuffle"),
            subdivision_feel="fractured",
            tempo_range=(90.0, 170.0),
            rubato_tolerance=0.3,
        ),
        synthesis=SynthesisHint(
            timbral_character=("digital", "noise", "transient"),
            texture_density=0.65,
            attack_preference="sharp",
            spectral_focus="full_spectrum",
        ),
        arrangement=ArrangementHint(
            voice_count_range=(3, 7),
            density_curve="terraced",
            staging_approach="abrupt_cut",
            layering_style="collage",
        ),
        mix=MixHint(
            frequency_emphasis="sculpted_extremes",
            spatial_width=0.75,
            reverb_character="synthetic",
            dynamic_range="compressed",
        ),
        arc_affinity={
            "Divination": 0.4,
            "Emergence": 0.75,
            "Conversation": 0.7,
            "Convergence": 0.8,
            "Crystallization": 0.55,
        },
    ),
    "classical_orchestral": GenreStrategy(
        genre_id="classical_orchestral",
        label="Classical / Orchestral Form",
        form=FormHint(
            preferred_families=("rondo_return", "aaba", "afterglow", "bridge"),
            section_density=0.75,
            through_composed_bias=0.45,
            repetition_tolerance=0.55,
        ),
        harmony=HarmonyHint(
            modal_preferences=("ionian", "aeolian", "harmonic_minor"),
            harmonic_rhythm="periodic",
            tension_vocabulary=("dominant_preparation", "deceptive_cadence", "pedal_point"),
            chromatic_tolerance=0.55,
        ),
        rhythm=RhythmHint(
            groove_types=("straight", "lilt"),
            subdivision_feel="metered",
            tempo_range=(50.0, 160.0),
            rubato_tolerance=0.5,
        ),
        synthesis=SynthesisHint(
            timbral_character=("bowed", "choir", "bell"),
            texture_density=0.6,
            attack_preference="varied",
            spectral_focus="mid",
        ),
        arrangement=ArrangementHint(
            voice_count_range=(4, 7),
            density_curve="arc",
            staging_approach="orchestral_diverge",
            layering_style="tutti_soli",
        ),
        mix=MixHint(
            frequency_emphasis="balanced",
            spatial_width=0.7,
            reverb_character="hall",
            dynamic_range="very_wide",
        ),
        arc_affinity={
            "Divination": 0.55,
            "Emergence": 0.8,
            "Conversation": 0.75,
            "Convergence": 0.85,
            "Crystallization": 0.65,
        },
    ),
    "musique_concrete": GenreStrategy(
        genre_id="musique_concrete",
        label="Musique Concrete / Electroacoustic",
        form=FormHint(
            preferred_families=("through_composed", "ambient_arc"),
            section_density=0.5,
            through_composed_bias=0.9,
            repetition_tolerance=0.25,
        ),
        harmony=HarmonyHint(
            modal_preferences=("phrygian", "lydian"),
            harmonic_rhythm="gestural",
            tension_vocabulary=("found_sound", "morphology", "spectral_freeze"),
            chromatic_tolerance=0.9,
        ),
        rhythm=RhythmHint(
            groove_types=("lilt",),
            subdivision_feel="free",
            tempo_range=(0.0, 120.0),
            rubato_tolerance=0.95,
        ),
        synthesis=SynthesisHint(
            timbral_character=("noise", "breath", "resonance"),
            texture_density=0.45,
            attack_preference="organic",
            spectral_focus="full_spectrum",
        ),
        arrangement=ArrangementHint(
            voice_count_range=(1, 5),
            density_curve="event_driven",
            staging_approach="montage",
            layering_style="juxtaposed",
        ),
        mix=MixHint(
            frequency_emphasis="detail",
            spatial_width=0.9,
            reverb_character="space",
            dynamic_range="extreme",
        ),
        arc_affinity={
            "Divination": 0.85,
            "Emergence": 0.7,
            "Conversation": 0.55,
            "Convergence": 0.6,
            "Crystallization": 0.8,
        },
    ),
    "spectral": GenreStrategy(
        genre_id="spectral",
        label="Spectral Music",
        form=FormHint(
            preferred_families=("through_composed", "afterglow", "ambient_arc"),
            section_density=0.5,
            through_composed_bias=0.8,
            repetition_tolerance=0.35,
        ),
        harmony=HarmonyHint(
            modal_preferences=("lydian",),
            harmonic_rhythm="spectral_time",
            tension_vocabulary=("overtone_series", "spectral_fusion", "inharmonicity"),
            chromatic_tolerance=0.85,
        ),
        rhythm=RhythmHint(
            groove_types=("straight", "lilt"),
            subdivision_feel="durational",
            tempo_range=(40.0, 100.0),
            rubato_tolerance=0.7,
        ),
        synthesis=SynthesisHint(
            timbral_character=("resonance", "bowed", "gong"),
            texture_density=0.5,
            attack_preference="slow",
            spectral_focus="overtone",
        ),
        arrangement=ArrangementHint(
            voice_count_range=(3, 6),
            density_curve="tidal",
            staging_approach="spectral_blend",
            layering_style="fused",
        ),
        mix=MixHint(
            frequency_emphasis="harmonic_series",
            spatial_width=0.8,
            reverb_character="resonant",
            dynamic_range="wide",
        ),
        arc_affinity={
            "Divination": 0.75,
            "Emergence": 0.85,
            "Conversation": 0.65,
            "Convergence": 0.8,
            "Crystallization": 0.9,
        },
    ),
    "blues": GenreStrategy(
        genre_id="blues",
        label="Blues",
        form=FormHint(
            preferred_families=("verse_chorus", "aaba", "bridge"),
            section_density=0.6,
            through_composed_bias=0.2,
            repetition_tolerance=0.75,
        ),
        harmony=HarmonyHint(
            modal_preferences=("mixolydian", "dorian", "minor_pentatonic"),
            harmonic_rhythm="call_response",
            tension_vocabulary=("blue_note", "dominant_7th", "plagal_turn"),
            chromatic_tolerance=0.4,
        ),
        rhythm=RhythmHint(
            groove_types=("shuffle", "swing", "straight"),
            subdivision_feel="triplet",
            tempo_range=(60.0, 140.0),
            rubato_tolerance=0.55,
        ),
        synthesis=SynthesisHint(
            timbral_character=("pluck", "bowed", "breath"),
            texture_density=0.45,
            attack_preference="expressive",
            spectral_focus="mid_low",
        ),
        arrangement=ArrangementHint(
            voice_count_range=(2, 5),
            density_curve="call_response",
            staging_approach="lead_and_comp",
            layering_style="supportive",
        ),
        mix=MixHint(
            frequency_emphasis="warm_low_mid",
            spatial_width=0.45,
            reverb_character="room",
            dynamic_range="moderate",
        ),
        arc_affinity={
            "Divination": 0.45,
            "Emergence": 0.65,
            "Conversation": 0.9,
            "Convergence": 0.7,
            "Crystallization": 0.5,
        },
    ),
    "world_music": GenreStrategy(
        genre_id="world_music",
        label="World Music Concepts",
        form=FormHint(
            preferred_families=("rondo_return", "through_composed", "verse_chorus"),
            section_density=0.6,
            through_composed_bias=0.5,
            repetition_tolerance=0.7,
        ),
        harmony=HarmonyHint(
            modal_preferences=("phrygian", "dorian", "hirajoshi", "mixolydian"),
            harmonic_rhythm="cyclic",
            tension_vocabulary=("modal_ostinato", "drone_pivot", "microtonal_inflection"),
            chromatic_tolerance=0.5,
        ),
        rhythm=RhythmHint(
            groove_types=("straight", "push", "lilt"),
            subdivision_feel="polyrhythmic",
            tempo_range=(70.0, 160.0),
            rubato_tolerance=0.4,
        ),
        synthesis=SynthesisHint(
            timbral_character=("kotekan", "gong", "pluck", "bell"),
            texture_density=0.55,
            attack_preference="percussive",
            spectral_focus="mid",
        ),
        arrangement=ArrangementHint(
            voice_count_range=(3, 7),
            density_curve="cyclic",
            staging_approach="interlocking",
            layering_style="heterophonic",
        ),
        mix=MixHint(
            frequency_emphasis="mid_presence",
            spatial_width=0.6,
            reverb_character="natural",
            dynamic_range="moderate",
        ),
        arc_affinity={
            "Divination": 0.55,
            "Emergence": 0.75,
            "Conversation": 0.85,
            "Convergence": 0.7,
            "Crystallization": 0.6,
        },
    ),
    "post_rock_experimental": GenreStrategy(
        genre_id="post_rock_experimental",
        label="Post-Rock / Experimental Builds",
        form=FormHint(
            preferred_families=("build_drop", "through_composed", "afterglow"),
            section_density=0.55,
            through_composed_bias=0.65,
            repetition_tolerance=0.6,
        ),
        harmony=HarmonyHint(
            modal_preferences=("aeolian", "dorian", "lydian"),
            harmonic_rhythm="slow_swell",
            tension_vocabulary=("long_crescendo", "textural_saturation", "quiet_restart"),
            chromatic_tolerance=0.45,
        ),
        rhythm=RhythmHint(
            groove_types=("straight", "push", "pull"),
            subdivision_feel="driving",
            tempo_range=(80.0, 150.0),
            rubato_tolerance=0.35,
        ),
        synthesis=SynthesisHint(
            timbral_character=("bowed", "pluck", "noise", "pad"),
            texture_density=0.55,
            attack_preference="building",
            spectral_focus="low_mid",
        ),
        arrangement=ArrangementHint(
            voice_count_range=(2, 7),
            density_curve="crescendo",
            staging_approach="accumulative",
            layering_style="additive",
        ),
        mix=MixHint(
            frequency_emphasis="wall_of_sound",
            spatial_width=0.8,
            reverb_character="cavernous",
            dynamic_range="very_wide",
        ),
        arc_affinity={
            "Divination": 0.6,
            "Emergence": 0.85,
            "Conversation": 0.6,
            "Convergence": 0.9,
            "Crystallization": 0.7,
        },
    ),
}


def strategy_for_genre(genre_id: str) -> GenreStrategy:
    """Return the strategy for *genre_id*, raising ``KeyError`` if unknown."""
    return _GENRE_STRATEGIES[genre_id]


def all_strategies() -> dict[str, GenreStrategy]:
    """Return a shallow copy of the full strategy library."""
    return dict(_GENRE_STRATEGIES)


def genre_arc_affinity(genre_id: str, arc_phase: str) -> float:
    """Return the affinity score (0.0–1.0) of *genre_id* for *arc_phase*.

    Returns 0.0 for unknown phases rather than raising.
    """
    strategy = _GENRE_STRATEGIES[genre_id]
    return strategy.arc_affinity.get(arc_phase, 0.0)


def best_genres_for_phase(
    arc_phase: str,
    *,
    limit: int = 3,
    exclude: Sequence[str] = (),
) -> list[tuple[str, float]]:
    """Return genres ranked by affinity for *arc_phase*, highest first."""
    excluded = frozenset(exclude)
    scored = [
        (gid, strategy.arc_affinity.get(arc_phase, 0.0))
        for gid, strategy in _GENRE_STRATEGIES.items()
        if gid not in excluded
    ]
    scored.sort(key=lambda pair: pair[1], reverse=True)
    return scored[:limit]


def select_genre(
    *,
    arc_phase: str,
    cadence_state: str,
    groove_identity: str,
    recent_genres: Sequence[str] = (),
) -> str:
    """Choose a genre strategy that fits the current musical context.

    Balances arc-phase affinity against fatigue from recent genre use.
    """
    fatigue: dict[str, int] = {}
    for age, gid in enumerate(reversed(recent_genres), start=1):
        fatigue[gid] = fatigue.get(gid, 0) + max(1, 6 - age)

    best_id = ""
    best_score = -1.0
    for gid, strategy in _GENRE_STRATEGIES.items():
        affinity = strategy.arc_affinity.get(arc_phase, 0.0)

        if cadence_state in {"sleep", "wind_down"}:
            if strategy.rhythm.rubato_tolerance >= 0.5:
                affinity += 0.08
            if strategy.synthesis.texture_density > 0.6:
                affinity -= 0.06
        elif cadence_state == "away_practice":
            if strategy.harmony.chromatic_tolerance >= 0.5:
                affinity += 0.06

        groove_set = set(strategy.rhythm.groove_types)
        if groove_identity == "drift" and "lilt" in groove_set:
            affinity += 0.04
        elif groove_identity == "dance" and "swing" in groove_set:
            affinity += 0.04
        elif groove_identity == "pulse" and "straight" in groove_set:
            affinity += 0.03
        elif groove_identity == "broken" and "push" in groove_set:
            affinity += 0.04

        penalty = fatigue.get(gid, 0) * 0.04
        score = affinity - penalty
        if score > best_score:
            best_score = score
            best_id = gid
    return best_id


_ARC_PHASES: tuple[str, ...] = (
    "Divination",
    "Emergence",
    "Conversation",
    "Convergence",
    "Crystallization",
)


@dataclass(frozen=True)
class GenreSummary:
    genre_id: str
    label: str
    tempo_range: tuple[float, float]
    texture_density: float
    chromatic_tolerance: float
    voice_count_range: tuple[int, int]
    dominant_grooves: tuple[str, ...]
    top_arc_phases: tuple[str, ...]
    mood_signature: str


@dataclass(frozen=True)
class GenreBlend:
    left_id: str
    right_id: str
    weight: float
    tempo_range: tuple[float, float]
    texture_density: float
    chromatic_tolerance: float
    rubato_tolerance: float
    repetition_tolerance: float
    spatial_width: float
    shared_modes: tuple[str, ...]


def _clamp_unit(value: float) -> float:
    return max(0.0, min(1.0, value))


def _mood_signature(texture_density: float) -> str:
    if texture_density < 0.4:
        return "calm"
    if texture_density >= 0.6:
        return "intense"
    return "balanced"


def _top_arc_phases(strategy: GenreStrategy, *, limit: int = 2) -> tuple[str, ...]:
    scored = [(phase, strategy.arc_affinity.get(phase, 0.0)) for phase in _ARC_PHASES]
    scored.sort(key=lambda pair: (-pair[1], _ARC_PHASES.index(pair[0])))
    return tuple(phase for phase, _ in scored[:limit])


def summarize_strategy(genre_id: str) -> GenreSummary:
    """Return a stable, operator-readable summary for *genre_id*."""
    strategy = _GENRE_STRATEGIES[genre_id]
    grooves = strategy.rhythm.groove_types[:2]
    return GenreSummary(
        genre_id=strategy.genre_id,
        label=strategy.label,
        tempo_range=strategy.rhythm.tempo_range,
        texture_density=strategy.synthesis.texture_density,
        chromatic_tolerance=strategy.harmony.chromatic_tolerance,
        voice_count_range=strategy.arrangement.voice_count_range,
        dominant_grooves=tuple(grooves),
        top_arc_phases=_top_arc_phases(strategy),
        mood_signature=_mood_signature(strategy.synthesis.texture_density),
    )


def _arc_cosine(left: GenreStrategy, right: GenreStrategy) -> float:
    left_vec = [left.arc_affinity.get(phase, 0.0) for phase in _ARC_PHASES]
    right_vec = [right.arc_affinity.get(phase, 0.0) for phase in _ARC_PHASES]
    dot = sum(a * b for a, b in zip(left_vec, right_vec, strict=True))
    left_norm = math.sqrt(sum(a * a for a in left_vec))
    right_norm = math.sqrt(sum(b * b for b in right_vec))
    if left_norm == 0.0 or right_norm == 0.0:
        return 0.0
    return _clamp_unit(dot / (left_norm * right_norm))


def _jaccard(left: Sequence[str], right: Sequence[str]) -> float:
    left_set = set(left)
    right_set = set(right)
    union = left_set | right_set
    if not union:
        return 0.0
    return len(left_set & right_set) / len(union)


def genre_compatibility(left_id: str, right_id: str) -> float:
    """Return a bounded compatibility score in ``[0.0, 1.0]`` for two genres."""
    if left_id == right_id and left_id in _GENRE_STRATEGIES:
        return 1.0

    left = _GENRE_STRATEGIES[left_id]
    right = _GENRE_STRATEGIES[right_id]

    arc = _arc_cosine(left, right)
    modal = _jaccard(left.harmony.modal_preferences, right.harmony.modal_preferences)
    groove = _jaccard(left.rhythm.groove_types, right.rhythm.groove_types)
    texture_diff = abs(left.synthesis.texture_density - right.synthesis.texture_density)
    chroma_diff = abs(left.harmony.chromatic_tolerance - right.harmony.chromatic_tolerance)
    timbre = _clamp_unit(1.0 - (texture_diff + chroma_diff) / 2.0)

    score = (arc + modal + groove + timbre) / 4.0
    return _clamp_unit(score)


def blend_genre_strategies(
    left_id: str,
    right_id: str,
    *,
    weight: float = 0.5,
) -> GenreBlend:
    """Return a weighted blend of numeric hints between two genre strategies."""
    left = _GENRE_STRATEGIES[left_id]
    right = _GENRE_STRATEGIES[right_id]
    clamped = _clamp_unit(weight)

    def lerp(a: float, b: float) -> float:
        return a * (1.0 - clamped) + b * clamped

    tempo_range = (
        lerp(left.rhythm.tempo_range[0], right.rhythm.tempo_range[0]),
        lerp(left.rhythm.tempo_range[1], right.rhythm.tempo_range[1]),
    )
    shared = sorted(
        set(left.harmony.modal_preferences) & set(right.harmony.modal_preferences)
    )
    return GenreBlend(
        left_id=left_id,
        right_id=right_id,
        weight=clamped,
        tempo_range=tempo_range,
        texture_density=lerp(
            left.synthesis.texture_density, right.synthesis.texture_density
        ),
        chromatic_tolerance=lerp(
            left.harmony.chromatic_tolerance, right.harmony.chromatic_tolerance
        ),
        rubato_tolerance=lerp(
            left.rhythm.rubato_tolerance, right.rhythm.rubato_tolerance
        ),
        repetition_tolerance=lerp(
            left.form.repetition_tolerance, right.form.repetition_tolerance
        ),
        spatial_width=lerp(left.mix.spatial_width, right.mix.spatial_width),
        shared_modes=tuple(shared),
    )


def recommend_genre_sequence(
    arc_phases: Sequence[str],
    *,
    recent_genres: Sequence[str] = (),
    avoid_repeat: bool = True,
) -> list[str]:
    """Plan a genre per arc phase, honoring fatigue from prior selections."""
    rolling: list[str] = list(recent_genres)
    chosen: list[str] = []
    for phase in arc_phases:
        genre = select_genre(
            arc_phase=phase,
            cadence_state="occupied_day",
            groove_identity="pulse",
            recent_genres=tuple(rolling),
        )
        chosen.append(genre)
        if avoid_repeat:
            rolling.append(genre)
    return chosen
