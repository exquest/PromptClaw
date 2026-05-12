"""Production-course knowledge base for runtime composition choices."""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Mapping

from .procedural_arc import ARC_PHASES


REQUIRED_CHAPTER_IDS: tuple[str, ...] = (
    "mode_scale",
    "harmonic_function",
    "meter_groove",
    "counterpoint_relation",
    "synthesis_architecture",
    "mix_role",
    "spatial_intent",
    "genre_strategy",
    "phase_profile",
    "transition_type",
)

REQUIRED_PHASE_NAMES: tuple[str, ...] = (
    "Divination",
    "Emergence",
    "Conversation",
    "Convergence",
    "Crystallization",
)


@dataclass(frozen=True)
class ProductionCourseConcept:
    stable_id: str
    chapter_id: str
    value: str
    title: str
    summary: str


@dataclass(frozen=True)
class ProductionCourseChapter:
    stable_id: str
    chapter_id: str
    title: str
    summary: str
    concepts: tuple[ProductionCourseConcept, ...]


@dataclass(frozen=True)
class CourseSummary:
    """Operator-readable view of one section's resolved production course."""

    chapter_count: int
    transition_type: str
    mix_role: str
    summary_titles: tuple[str, ...]


@dataclass(frozen=True)
class ChapterDigest:
    """Short description of one course chapter and its first concept values."""

    chapter_id: str
    title: str
    concept_count: int
    sample_values: tuple[str, ...]


@dataclass(frozen=True)
class ArcPhaseSnapshot:
    """Arc phase profile fields plus a coarse density bucket."""

    phase_name: str
    density: float
    mutation_rate: float
    transition_intent: str
    dominant_quality: str


@dataclass(frozen=True)
class CourseArcPlan:
    """Planned per-section courses and their parallel transition types."""

    courses: tuple[Mapping[str, str], ...]
    transition_types: tuple[str, ...]


@dataclass(frozen=True)
class ArcPhaseProfile:
    stable_id: str
    phase_name: str
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


def _slug(value: str) -> str:
    return value.lower().replace("_", "-").replace(" ", "-")


def _concept(
    chapter_id: str,
    value: str,
    title: str,
    summary: str,
) -> ProductionCourseConcept:
    return ProductionCourseConcept(
        stable_id=f"production-course.{chapter_id}.{_slug(value)}",
        chapter_id=chapter_id,
        value=value,
        title=title,
        summary=summary,
    )


def _chapter(
    chapter_id: str,
    title: str,
    summary: str,
    concepts: tuple[ProductionCourseConcept, ...],
) -> ProductionCourseChapter:
    return ProductionCourseChapter(
        stable_id=f"production-course.chapter.{chapter_id}",
        chapter_id=chapter_id,
        title=title,
        summary=summary,
        concepts=concepts,
    )


COURSE_CHAPTERS: tuple[ProductionCourseChapter, ...] = (
    _chapter(
        "mode_scale",
        "Mode and Scale",
        "Harmonic color for the section.",
        (
            _concept("mode_scale", "open", "Open", "Nonfunctional interval fields."),
            _concept("mode_scale", "modal", "Modal", "Modal center with clear color."),
            _concept("mode_scale", "functional", "Functional", "Directed tonal motion."),
            _concept("mode_scale", "chromatic", "Chromatic", "Heightened color motion."),
            _concept("mode_scale", "static", "Static", "Stable or suspended pitch field."),
        ),
    ),
    _chapter(
        "harmonic_function",
        "Harmonic Function",
        "Role of the section inside the progression.",
        (
            _concept("harmonic_function", "tonic", "Tonic", "Home or arrival area."),
            _concept(
                "harmonic_function",
                "predominant",
                "Predominant",
                "Preparation away from home.",
            ),
            _concept("harmonic_function", "dominant", "Dominant", "Return pressure."),
            _concept("harmonic_function", "borrowed", "Borrowed", "Modal mixture."),
            _concept("harmonic_function", "plagal", "Plagal", "Soft return motion."),
            _concept("harmonic_function", "authentic", "Authentic", "Decisive close."),
        ),
    ),
    _chapter(
        "meter_groove",
        "Meter and Groove",
        "Rhythmic behavior for the section.",
        (
            _concept("meter_groove", "free", "Free", "Unmetered or floating motion."),
            _concept("meter_groove", "pulse", "Pulse", "Readable recurring beat."),
            _concept("meter_groove", "groove", "Groove", "Interlocking rhythmic drive."),
            _concept(
                "meter_groove",
                "polyrhythm",
                "Polyrhythm",
                "Layered competing meters.",
            ),
            _concept("meter_groove", "drone", "Drone", "Sustained time field."),
        ),
    ),
    _chapter(
        "counterpoint_relation",
        "Counterpoint Relation",
        "How section voices relate to the primary motif.",
        (
            _concept(
                "counterpoint_relation",
                "unison_shadow",
                "Unison Shadow",
                "Double or ghost the motif.",
            ),
            _concept(
                "counterpoint_relation",
                "parallel_thirds",
                "Parallel Thirds",
                "Support with consonant parallel motion.",
            ),
            _concept(
                "counterpoint_relation",
                "contrary_motion",
                "Contrary Motion",
                "Answer by moving in opposition.",
            ),
            _concept(
                "counterpoint_relation",
                "oblique_pedal",
                "Oblique Pedal",
                "Hold one voice while another moves.",
            ),
            _concept(
                "counterpoint_relation",
                "imitative_canon",
                "Imitative Canon",
                "Recall material through staggered imitation.",
            ),
        ),
    ),
    _chapter(
        "synthesis_architecture",
        "Synthesis Architecture",
        "Primary synthesis family for the section.",
        (
            _concept(
                "synthesis_architecture",
                "spectral",
                "Spectral",
                "Tone built from partials.",
            ),
            _concept(
                "synthesis_architecture",
                "fm",
                "FM",
                "Modulated tone with clear growth potential.",
            ),
            _concept(
                "synthesis_architecture",
                "subtractive",
                "Subtractive",
                "Filtered harmonic source.",
            ),
            _concept(
                "synthesis_architecture",
                "additive",
                "Additive",
                "Layered sine or partial construction.",
            ),
            _concept(
                "synthesis_architecture",
                "granular",
                "Granular",
                "Clouded grains or residue texture.",
            ),
        ),
    ),
    _chapter(
        "mix_role",
        "Mix Role",
        "Foreground responsibility of a section.",
        (
            _concept("mix_role", "ambient", "Ambient", "Frame the space."),
            _concept("mix_role", "lead", "Lead", "Carry the primary identity."),
            _concept("mix_role", "foreground", "Foreground", "Assert the main event."),
            _concept("mix_role", "ensemble", "Ensemble", "Share focus across voices."),
            _concept("mix_role", "support", "Support", "Reinforce without leading."),
            _concept("mix_role", "lead_recall", "Lead Recall", "Return the lead idea."),
            _concept("mix_role", "background", "Background", "Leave residue behind."),
        ),
    ),
    _chapter(
        "spatial_intent",
        "Spatial Intent",
        "Placement and depth intent.",
        (
            _concept("spatial_intent", "wide", "Wide", "Open horizontal image."),
            _concept("spatial_intent", "clear", "Clear", "Readable centered image."),
            _concept("spatial_intent", "focused", "Focused", "Narrow direct image."),
            _concept("spatial_intent", "intimate", "Intimate", "Close and present."),
            _concept("spatial_intent", "expansive", "Expansive", "Deep release field."),
        ),
    ),
    _chapter(
        "genre_strategy",
        "Genre Strategy",
        "Production approach that turns groove identity into arrangement behavior.",
        (
            _concept(
                "genre_strategy",
                "ambient_drone",
                "Ambient Drone",
                "Sustain color and slow change.",
            ),
            _concept(
                "genre_strategy",
                "minimalist_process",
                "Minimalist Process",
                "Let repetition reveal form.",
            ),
            _concept(
                "genre_strategy",
                "experimental_collage",
                "Experimental Collage",
                "Assemble contrast through edits.",
            ),
            _concept(
                "genre_strategy",
                "rhythmic_pattern",
                "Rhythmic Pattern",
                "Lead with pattern energy.",
            ),
            _concept(
                "genre_strategy",
                "processional_modal",
                "Processional Modal",
                "Move through repeated modal steps.",
            ),
            _concept(
                "genre_strategy",
                "ritualistic_ostinato",
                "Ritualistic Ostinato",
                "Anchor the arc with repeated cells.",
            ),
        ),
    ),
    _chapter(
        "phase_profile",
        "Phase Profile",
        "Production arc phase assigned to the section.",
        tuple(
            _concept(
                "phase_profile",
                phase_name,
                phase_name,
                f"{phase_name} production arc profile.",
            )
            for phase_name in REQUIRED_PHASE_NAMES
        ),
    ),
    _chapter(
        "transition_type",
        "Transition Type",
        "How this section hands off to the next section.",
        (
            _concept(
                "transition_type",
                "seamless",
                "Seamless",
                "Continue without an audible boundary.",
            ),
            _concept(
                "transition_type",
                "modulation",
                "Modulation",
                "Change harmonic role across the boundary.",
            ),
            _concept("transition_type", "breath", "Breath", "Leave a short gap."),
            _concept("transition_type", "crossfade", "Crossfade", "Overlap layers."),
            _concept("transition_type", "terminal", "Terminal", "End the piece."),
        ),
    ),
)

ARC_PHASE_PROFILES: tuple[ArcPhaseProfile, ...] = tuple(
    ArcPhaseProfile(
        stable_id=f"production-course.phase.{_slug(phase.name)}",
        phase_name=phase.name,
        density=phase.density,
        mutation_rate=phase.mutation_rate,
        transition_intent=phase.transition_intent,
        dynamic=phase.dynamic,
        harmonic=phase.harmonic,
        rhythm=phase.rhythm,
        timbre=phase.timbre,
        spatial=phase.spatial,
        compression=phase.compression,
        senseweave=phase.senseweave,
        synthesis=phase.synthesis,
    )
    for phase in ARC_PHASES
)

_CHAPTERS_BY_ID = {chapter.chapter_id: chapter for chapter in COURSE_CHAPTERS}
_CONCEPTS_BY_CHAPTER_VALUE = {
    (concept.chapter_id, concept.value): concept
    for chapter in COURSE_CHAPTERS
    for concept in chapter.concepts
}
_PHASE_PROFILES_BY_NAME = {
    profile.phase_name: profile for profile in ARC_PHASE_PROFILES
}

_COUNTERPOINT_BY_FUNCTION = {
    "invocation": "unison_shadow",
    "statement": "unison_shadow",
    "lift": "parallel_thirds",
    "arrival": "parallel_thirds",
    "refrain": "parallel_thirds",
    "development": "contrary_motion",
    "instrumental_response": "contrary_motion",
    "turn": "oblique_pedal",
    "recap": "imitative_canon",
    "coda": "imitative_canon",
    "residue": "unison_shadow",
}

_MIX_ROLE_BY_FUNCTION = {
    "invocation": "ambient",
    "statement": "lead",
    "lift": "foreground",
    "arrival": "foreground",
    "refrain": "lead",
    "development": "ensemble",
    "instrumental_response": "ensemble",
    "turn": "support",
    "recap": "lead_recall",
    "coda": "background",
    "residue": "background",
}

_GENRE_STRATEGY_BY_GROOVE = {
    "drift": "ambient_drone",
    "pulse": "minimalist_process",
    "broken": "experimental_collage",
    "dance": "rhythmic_pattern",
    "procession": "processional_modal",
    "ritual_ostinato": "ritualistic_ostinato",
}

_DEFAULT_VALUES = {
    "mode_scale": "modal",
    "harmonic_function": "tonic",
    "meter_groove": "pulse",
    "counterpoint_relation": "parallel_thirds",
    "synthesis_architecture": "subtractive",
    "mix_role": "support",
    "spatial_intent": "clear",
    "genre_strategy": "minimalist_process",
    "phase_profile": "Emergence",
    "transition_type": "crossfade",
}


def load_course_chapters() -> tuple[ProductionCourseChapter, ...]:
    """Return the typed production-course chapter catalog."""
    return COURSE_CHAPTERS


def load_arc_phase_profiles() -> tuple[ArcPhaseProfile, ...]:
    """Return the phase profiles available to runtime composers."""
    return ARC_PHASE_PROFILES


def course_chapter(chapter_id: str) -> ProductionCourseChapter | None:
    return _CHAPTERS_BY_ID.get(chapter_id)


def course_concept(
    chapter_id: str,
    value: str,
) -> ProductionCourseConcept | None:
    return _CONCEPTS_BY_CHAPTER_VALUE.get((chapter_id, value))


def arc_phase_profile(phase_name: str) -> ArcPhaseProfile | None:
    return _PHASE_PROFILES_BY_NAME.get(phase_name)


def _known_value(chapter_id: str, value: str) -> str:
    if course_concept(chapter_id, value) is not None:
        return value
    return _DEFAULT_VALUES[chapter_id]


def transition_type_for_section(
    *,
    function: str,
    harmonic_role: str,
    next_function: str | None,
    next_harmonic_role: str | None,
) -> str:
    if next_function is None:
        return "terminal"
    if function == next_function:
        return "seamless"
    if harmonic_role != next_harmonic_role:
        return "modulation"
    if next_function in ("invocation", "turn", "coda", "residue"):
        return "breath"
    return "crossfade"


def course_for_section(
    *,
    function: str,
    harmonic_role: str,
    arc_metadata: Mapping[str, str],
    groove_identity: str,
    next_function: str | None,
    next_harmonic_role: str | None,
) -> dict[str, str]:
    """Build runtime production-course metadata for one composed section."""
    phase_name = _known_value(
        "phase_profile",
        str(arc_metadata.get("arc_phase", "") or "Emergence"),
    )
    course = {
        "mode_scale": _known_value(
            "mode_scale",
            str(arc_metadata.get("arc_harmonic", "") or "modal"),
        ),
        "harmonic_function": _known_value("harmonic_function", harmonic_role),
        "meter_groove": _known_value(
            "meter_groove",
            str(arc_metadata.get("arc_rhythm", "") or "pulse"),
        ),
        "counterpoint_relation": _known_value(
            "counterpoint_relation",
            _COUNTERPOINT_BY_FUNCTION.get(function, "parallel_thirds"),
        ),
        "synthesis_architecture": _known_value(
            "synthesis_architecture",
            str(arc_metadata.get("arc_synthesis", "") or "subtractive"),
        ),
        "mix_role": _known_value(
            "mix_role",
            _MIX_ROLE_BY_FUNCTION.get(function, "support"),
        ),
        "spatial_intent": _known_value(
            "spatial_intent",
            str(arc_metadata.get("arc_spatial", "") or "clear"),
        ),
        "genre_strategy": _known_value(
            "genre_strategy",
            _GENRE_STRATEGY_BY_GROOVE.get(groove_identity, "minimalist_process"),
        ),
        "phase_profile": phase_name,
        "transition_type": _known_value(
            "transition_type",
            transition_type_for_section(
                function=function,
                harmonic_role=harmonic_role,
                next_function=next_function,
                next_harmonic_role=next_harmonic_role,
            ),
        ),
    }
    return {chapter_id: course[chapter_id] for chapter_id in REQUIRED_CHAPTER_IDS}


def summarize_course(course: Mapping[str, str]) -> CourseSummary:
    """Return an operator-readable summary of one resolved section course."""
    titles: list[str] = []
    for chapter_id in REQUIRED_CHAPTER_IDS:
        value = course.get(chapter_id, "")
        concept = course_concept(chapter_id, value)
        if concept is not None:
            titles.append(concept.title)
    return CourseSummary(
        chapter_count=len(REQUIRED_CHAPTER_IDS),
        transition_type=course.get("transition_type", ""),
        mix_role=course.get("mix_role", ""),
        summary_titles=tuple(titles),
    )


def chapter_digest(chapter_id: str) -> ChapterDigest:
    """Return a short digest of the named chapter and its first concept values."""
    chapter = course_chapter(chapter_id)
    if chapter is None:
        raise KeyError(chapter_id)
    sample_values = tuple(concept.value for concept in chapter.concepts[:3])
    return ChapterDigest(
        chapter_id=chapter.chapter_id,
        title=chapter.title,
        concept_count=len(chapter.concepts),
        sample_values=sample_values,
    )


def catalog_digest() -> tuple[ChapterDigest, ...]:
    """Return per-chapter digests for every required chapter in declared order."""
    digests: list[ChapterDigest] = []
    for chapter_id in REQUIRED_CHAPTER_IDS:
        digests.append(chapter_digest(chapter_id))
    return tuple(digests)


def arc_phase_snapshot(phase_name: str) -> ArcPhaseSnapshot:
    """Return the arc phase profile with a coarse density bucket."""
    profile = arc_phase_profile(phase_name)
    if profile is None:
        raise KeyError(phase_name)
    if profile.density < 0.4:
        dominant_quality = "sparse"
    elif profile.density >= 0.7:
        dominant_quality = "dense"
    else:
        dominant_quality = "balanced"
    return ArcPhaseSnapshot(
        phase_name=profile.phase_name,
        density=profile.density,
        mutation_rate=profile.mutation_rate,
        transition_intent=profile.transition_intent,
        dominant_quality=dominant_quality,
    )


def plan_course_arc(
    sections: Iterable[Mapping[str, object]],
) -> CourseArcPlan:
    """Build per-section courses for an arc, terminating the final transition."""
    section_list = list(sections)
    courses: list[Mapping[str, str]] = []
    transitions: list[str] = []
    for index, section in enumerate(section_list):
        next_section = (
            section_list[index + 1] if index + 1 < len(section_list) else None
        )
        next_function = (
            None if next_section is None else str(next_section["function"])
        )
        next_harmonic_role = (
            None
            if next_section is None
            else str(next_section["harmonic_role"])
        )
        arc_metadata_raw = section.get("arc_metadata", {})
        arc_metadata = {
            str(k): str(v) for k, v in dict(arc_metadata_raw).items()
        }
        course = course_for_section(
            function=str(section["function"]),
            harmonic_role=str(section["harmonic_role"]),
            arc_metadata=arc_metadata,
            groove_identity=str(section["groove_identity"]),
            next_function=next_function,
            next_harmonic_role=next_harmonic_role,
        )
        courses.append(course)
        transitions.append(course["transition_type"])
    return CourseArcPlan(
        courses=tuple(courses),
        transition_types=tuple(transitions),
    )


def arc_phase_snapshots() -> tuple[ArcPhaseSnapshot, ...]:
    """Return density-bucketed snapshots for every required arc phase."""
    snapshots: list[ArcPhaseSnapshot] = []
    for phase_name in REQUIRED_PHASE_NAMES:
        snapshots.append(arc_phase_snapshot(phase_name))
    return tuple(snapshots)


def course_titles(course: Mapping[str, str]) -> tuple[str, ...]:
    """Return resolved concept titles for a course in declared chapter order."""
    titles: list[str] = []
    for chapter_id in REQUIRED_CHAPTER_IDS:
        concept = course_concept(chapter_id, course.get(chapter_id, ""))
        if concept is not None:
            titles.append(concept.title)
    return tuple(titles)


def validate_course(course: Mapping[str, str]) -> tuple[str, ...]:
    """Return sorted chapter ids whose course value is missing or unknown."""
    issues: list[str] = []
    for chapter_id in REQUIRED_CHAPTER_IDS:
        value = course.get(chapter_id, "")
        if not value or course_concept(chapter_id, value) is None:
            issues.append(chapter_id)
    return tuple(sorted(issues))
