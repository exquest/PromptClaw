"""Pre-performance self-critique and bounded revision passes.

Generates an offline preview of a score, analyzes it with the ear engine,
and optionally requests one bounded rewrite pass when quality metrics fail.
The rewrite preserves piece identity (key, mood, tempo) while varying
melodic material via a different variation seed.

Course-driven critique maps production-course chapter concepts to concrete
ear-engine metrics so that failure reports name the course concept behind
each threshold violation and revision targets specify which musical
dimensions are open for adjustment.

Stdlib only — no numpy.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

from .ear_engine import _EarEvent, _analyze_events
from .generative_scores import Score, score_from_mood, score_to_frequencies
from .rollout_controls import SenseWeaveFeatureFlags, load_feature_flags

# ---------------------------------------------------------------------------
# Default quality thresholds
# ---------------------------------------------------------------------------
# Format: metric_name -> (direction, value)
#   direction "min" means the metric must be >= value to pass.
#   direction "max" means the metric must be <= value to pass.

DEFAULT_THRESHOLDS: dict[str, tuple[str, float]] = {
    "underdeveloped_score": ("max", 0.7),
    "static_score": ("max", 0.7),
    "development_score": ("min", 0.25),
    "hook_clarity": ("min", 0.2),
}

COURSE_METRIC_MAP: dict[tuple[str, str], dict[str, tuple[str, float]]] = {
    ("mode_scale", "static"): {"static_score": ("max", 0.4)},
    ("mode_scale", "chromatic"): {"interval_variety": ("min", 0.4)},
    ("mode_scale", "functional"): {"cadence_strength": ("min", 0.2)},
    ("harmonic_function", "dominant"): {"cadence_strength": ("min", 0.35)},
    ("harmonic_function", "authentic"): {"cadence_strength": ("min", 0.3)},
    ("harmonic_function", "tonic"): {"static_score": ("max", 0.6)},
    ("meter_groove", "groove"): {"onset_density": ("min", 1.5)},
    ("meter_groove", "pulse"): {"onset_density": ("min", 0.8)},
    ("meter_groove", "free"): {"onset_density": ("max", 3.0)},
    ("meter_groove", "drone"): {"static_score": ("max", 0.85)},
    ("counterpoint_relation", "imitative_canon"): {"repetition_score": ("min", 0.3)},
    ("counterpoint_relation", "contrary_motion"): {"interval_variety": ("min", 0.35)},
    ("synthesis_architecture", "granular"): {"onset_density": ("min", 1.0)},
    ("mix_role", "lead"): {"hook_clarity": ("min", 0.3)},
    ("mix_role", "foreground"): {"hook_clarity": ("min", 0.25)},
    ("mix_role", "ambient"): {"static_score": ("max", 0.8)},
    ("spatial_intent", "wide"): {"pitch_range_semitones": ("min", 8.0)},
    ("spatial_intent", "intimate"): {"pitch_range_semitones": ("max", 18.0)},
    ("genre_strategy", "ambient_drone"): {
        "static_score": ("max", 0.85),
        "onset_density": ("max", 2.0),
    },
    ("genre_strategy", "rhythmic_pattern"): {"onset_density": ("min", 1.5)},
    ("genre_strategy", "minimalist_process"): {"repetition_score": ("min", 0.2)},
    ("transition_type", "modulation"): {"cadence_strength": ("min", 0.25)},
    ("transition_type", "breath"): {"onset_density": ("max", 3.5)},
    ("phase_profile", "Crystallization"): {"development_score": ("min", 0.35)},
    ("phase_profile", "Emergence"): {"underdeveloped_score": ("max", 0.6)},
}

_CHAPTER_TO_DIMENSION: dict[str, str] = {
    "mode_scale": "harmony",
    "harmonic_function": "harmony",
    "meter_groove": "rhythm",
    "counterpoint_relation": "form",
    "synthesis_architecture": "strategy",
    "mix_role": "mix",
    "spatial_intent": "register",
    "genre_strategy": "strategy",
    "phase_profile": "form",
    "transition_type": "form",
}


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CourseFailure:
    """A single course-concept-to-metric failure."""

    chapter_id: str
    concept_value: str
    metric_name: str
    direction: str
    threshold: float
    actual: float


@dataclass(frozen=True)
class CritiqueReport:
    """Result of analyzing a score against quality thresholds."""

    metrics: dict[str, float]
    passed: bool
    failed_metrics: tuple[str, ...]


@dataclass(frozen=True)
class CourseCritiqueReport(CritiqueReport):
    """Critique report extended with course-concept failure attribution."""

    course_failures: tuple[CourseFailure, ...] = ()


@dataclass(frozen=True)
class RevisionTargets:
    """Which musical dimensions are open for bounded revision."""

    adjust_form: bool = False
    adjust_harmony: bool = False
    adjust_rhythm: bool = False
    adjust_register: bool = False
    adjust_mix: bool = False
    adjust_strategy: bool = False


@dataclass(frozen=True)
class RevisionResult:
    """Result of the critique-and-revise pipeline."""

    original_score: Score
    original_metrics: dict[str, float]
    revised_score: Score | None
    revised_metrics: dict[str, float] | None
    improved_metrics: tuple[str, ...]
    identity_preserved: bool
    revision_used: bool
    course_failures: tuple[CourseFailure, ...] = ()
    revision_targets: RevisionTargets | None = None

    @property
    def final_score(self) -> Score:
        """Return whichever score was selected."""
        if self.revision_used and self.revised_score is not None:
            return self.revised_score
        return self.original_score


# ---------------------------------------------------------------------------
# Preview: offline fast render → ear engine metrics
# ---------------------------------------------------------------------------


def preview_score(score: Score) -> dict[str, float]:
    """Convert a Score to frequency events and analyze with the ear engine.

    This is the offline preview render: no audio is played, but the score is
    converted to frequency/duration pairs and fed through the same analysis
    pipeline that evaluates live performance.
    """
    freq_phrases = score_to_frequencies(score)
    events: list[_EarEvent] = []
    cursor = 0.0
    for phrase_freqs in freq_phrases:
        for freq_hz, dur_sec in phrase_freqs:
            if freq_hz > 0.0 and dur_sec > 0.0:
                events.append(
                    _EarEvent(
                        frequency_hz=freq_hz,
                        duration_s=dur_sec,
                        amplitude=1.0,
                        accent=False,
                        start_s=cursor,
                    )
                )
                cursor += dur_sec
    return _analyze_events(events)


# ---------------------------------------------------------------------------
# Critique: compare preview metrics against thresholds
# ---------------------------------------------------------------------------


def _check_thresholds(
    metrics: dict[str, float],
    thresholds: Mapping[str, tuple[str, float]],
) -> tuple[str, ...]:
    """Return tuple of metric names that failed their thresholds."""
    failures: list[str] = []
    for metric_name, (direction, threshold) in thresholds.items():
        value = metrics.get(metric_name, 0.0)
        if direction == "min" and value < threshold:
            failures.append(metric_name)
        elif direction == "max" and value > threshold:
            failures.append(metric_name)
    return tuple(failures)


def critique_score(
    score: Score,
    thresholds: Mapping[str, tuple[str, float]] | None = None,
) -> CritiqueReport:
    """Analyze a score offline and gate it against quality thresholds.

    Returns a CritiqueReport with the metrics, pass/fail status, and which
    metrics failed.
    """
    effective_thresholds = dict(thresholds) if thresholds is not None else dict(DEFAULT_THRESHOLDS)
    metrics = preview_score(score)
    failed = _check_thresholds(metrics, effective_thresholds)
    return CritiqueReport(
        metrics=metrics,
        passed=len(failed) == 0,
        failed_metrics=failed,
    )


# ---------------------------------------------------------------------------
# Course-aware thresholds and critique
# ---------------------------------------------------------------------------


def thresholds_for_course(
    course: dict[str, str],
) -> dict[str, tuple[str, float]]:
    """Build quality thresholds by merging course-concept overrides into defaults.

    For each chapter/value in the section's production_course, looks up
    COURSE_METRIC_MAP and merges. When the same metric appears from multiple
    course concepts, the stricter threshold wins.
    """
    merged = dict(DEFAULT_THRESHOLDS)
    for chapter_id, value in course.items():
        overrides = COURSE_METRIC_MAP.get((chapter_id, value))
        if overrides is None:
            continue
        for metric_name, (direction, threshold) in overrides.items():
            if metric_name not in merged:
                merged[metric_name] = (direction, threshold)
                continue
            existing_dir, existing_val = merged[metric_name]
            if existing_dir != direction:
                merged[metric_name] = (direction, threshold)
                continue
            if direction == "min" and threshold > existing_val:
                merged[metric_name] = (direction, threshold)
            elif direction == "max" and threshold < existing_val:
                merged[metric_name] = (direction, threshold)
    return merged


def _attribute_course_failures(
    metrics: dict[str, float],
    course: dict[str, str],
    failed_metrics: tuple[str, ...],
) -> tuple[CourseFailure, ...]:
    """Map failed metrics back to the course concepts that contributed them."""
    failures: list[CourseFailure] = []
    for chapter_id, value in course.items():
        overrides = COURSE_METRIC_MAP.get((chapter_id, value))
        if overrides is None:
            continue
        for metric_name, (direction, threshold) in overrides.items():
            if metric_name in failed_metrics:
                failures.append(
                    CourseFailure(
                        chapter_id=chapter_id,
                        concept_value=value,
                        metric_name=metric_name,
                        direction=direction,
                        threshold=threshold,
                        actual=metrics.get(metric_name, 0.0),
                    )
                )
    return tuple(failures)


def critique_score_with_course(
    score: Score,
    course: dict[str, str],
) -> CourseCritiqueReport:
    """Analyze a score using course-aware thresholds and attribute failures."""
    effective_thresholds = thresholds_for_course(course)
    metrics = preview_score(score)
    failed = _check_thresholds(metrics, effective_thresholds)
    course_failures = _attribute_course_failures(metrics, course, failed)
    return CourseCritiqueReport(
        metrics=metrics,
        passed=len(failed) == 0,
        failed_metrics=failed,
        course_failures=course_failures,
    )


def revision_targets_from_failures(
    course_failures: tuple[CourseFailure, ...],
) -> RevisionTargets:
    """Determine which musical dimensions are open for revision."""
    dimensions: set[str] = set()
    for failure in course_failures:
        dim = _CHAPTER_TO_DIMENSION.get(failure.chapter_id)
        if dim is not None:
            dimensions.add(dim)
    return RevisionTargets(
        adjust_form="form" in dimensions,
        adjust_harmony="harmony" in dimensions,
        adjust_rhythm="rhythm" in dimensions,
        adjust_register="register" in dimensions,
        adjust_mix="mix" in dimensions,
        adjust_strategy="strategy" in dimensions,
    )


# ---------------------------------------------------------------------------
# Revise: one bounded rewrite pass
# ---------------------------------------------------------------------------


def _identity_matches(original: Score, revised: Score) -> bool:
    """Check that key, mood, and tempo are preserved."""
    return (
        original.key == revised.key
        and original.mood == revised.mood
        and original.tempo_bpm == revised.tempo_bpm
    )


def _find_improvements(
    original_metrics: dict[str, float],
    revised_metrics: dict[str, float],
    failed_metrics: Sequence[str],
    thresholds: Mapping[str, tuple[str, float]],
) -> tuple[str, ...]:
    """Return which failed metrics improved in the revision."""
    improved: list[str] = []
    for metric_name in failed_metrics:
        direction, _threshold = thresholds[metric_name]
        original_value = original_metrics.get(metric_name, 0.0)
        revised_value = revised_metrics.get(metric_name, 0.0)
        if direction == "min" and revised_value > original_value:
            improved.append(metric_name)
        elif direction == "max" and revised_value < original_value:
            improved.append(metric_name)
    return tuple(improved)


def revise_score(
    mood: dict,
    *,
    thresholds: Mapping[str, tuple[str, float]] | None = None,
    song_num: int = 0,
    family: str = "default",
    cadence_state: str = "",
    patch_name: str = "",
    progression_profile: str = "",
    memory_fragments: Sequence[Mapping[str, object]] | None = None,
    repertoire_hint: Mapping[str, object] | None = None,
    flags: SenseWeaveFeatureFlags | None = None,
    course: dict[str, str] | None = None,
) -> RevisionResult:
    """Generate a score, critique it, and optionally revise once.

    If the initial score passes all thresholds, it is returned immediately.
    Otherwise, one rewrite pass is attempted with a different variation seed.
    The revision is accepted only if it improves at least one failed metric
    while preserving piece identity (key, mood, tempo).

    When *course* is provided, thresholds are derived from production-course
    concepts and failure reports name the specific course concept behind
    each violation.
    """
    active_flags = flags or load_feature_flags()
    if course is not None and thresholds is None:
        effective_thresholds = thresholds_for_course(course)
    else:
        effective_thresholds = dict(thresholds) if thresholds is not None else dict(DEFAULT_THRESHOLDS)

    # Determine the variation seed for the original
    original_seed = song_num if song_num else 1

    # Generate and critique the original score
    common_kwargs: dict = {
        "family": family,
        "cadence_state": cadence_state,
        "patch_name": patch_name,
        "progression_profile": progression_profile,
        "memory_fragments": memory_fragments,
        "repertoire_hint": repertoire_hint,
    }
    original_score = score_from_mood(mood, song_num=original_seed, **common_kwargs)

    if not active_flags.preview_render:
        return RevisionResult(
            original_score=original_score,
            original_metrics={},
            revised_score=None,
            revised_metrics=None,
            improved_metrics=(),
            identity_preserved=True,
            revision_used=False,
        )

    if not active_flags.self_critique:
        return RevisionResult(
            original_score=original_score,
            original_metrics=preview_score(original_score),
            revised_score=None,
            revised_metrics=None,
            improved_metrics=(),
            identity_preserved=True,
            revision_used=False,
        )

    original_report = critique_score(original_score, effective_thresholds)

    # Attribute failures to course concepts when course is provided
    course_failures: tuple[CourseFailure, ...] = ()
    revision_tgts: RevisionTargets | None = None
    if course and not original_report.passed:
        course_failures = _attribute_course_failures(
            original_report.metrics, course, original_report.failed_metrics
        )
        revision_tgts = revision_targets_from_failures(course_failures)

    if original_report.passed:
        return RevisionResult(
            original_score=original_score,
            original_metrics=original_report.metrics,
            revised_score=None,
            revised_metrics=None,
            improved_metrics=(),
            identity_preserved=True,
            revision_used=False,
            course_failures=(),
            revision_targets=None,
        )

    # One bounded rewrite pass with incremented seed
    revised_score = score_from_mood(mood, song_num=original_seed + 1, **common_kwargs)
    revised_metrics = preview_score(revised_score)

    # Check identity preservation between original and revision
    identity_ok = _identity_matches(original_score, revised_score)

    # Find which failed metrics improved
    improved: tuple[str, ...] = ()
    if identity_ok:
        improved = _find_improvements(
            original_report.metrics,
            revised_metrics,
            original_report.failed_metrics,
            effective_thresholds,
        )

    # Accept revision only if identity preserved and at least one metric improved
    use_revision = identity_ok and len(improved) > 0

    return RevisionResult(
        original_score=original_score,
        original_metrics=original_report.metrics,
        revised_score=revised_score,
        revised_metrics=revised_metrics,
        improved_metrics=improved,
        identity_preserved=True,
        revision_used=use_revision,
        course_failures=course_failures,
        revision_targets=revision_tgts,
    )
