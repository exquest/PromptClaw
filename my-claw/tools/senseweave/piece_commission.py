"""Up-front piece commissioning for score-tree composition."""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal, Sequence

from .procedural_arc import ArcDirective, directive_for_elapsed
from .rollout_controls import SenseWeaveFeatureFlags, load_feature_flags


FormClass = Literal["micro", "song", "extended", "suite"]
CompositionMode = Literal["hook_led", "hybrid", "through_composed"]
NarrativeScale = Literal["single_image", "scene", "journey", "ritual"]

FORM_CLASS_RANGES: dict[FormClass, tuple[float, float]] = {
    "micro": (30.0, 75.0),
    "song": (120.0, 270.0),
    "extended": (240.0, 420.0),
    "suite": (420.0, 720.0),
}


@dataclass(frozen=True)
class PieceCommission:
    form_class: FormClass
    composition_mode: CompositionMode
    duration_target_s: float
    sonic_world_count: int
    hook_pressure: float
    narrative_scale: NarrativeScale
    ending_family: str
    groove_identity: str
    reason_tags: tuple[str, ...]
    arc_directive: ArcDirective | None = None
    arc_elapsed_minutes: float = 0.0
    arc_cycle_minutes: float = 30.0


def _clamp(value: float, lower: float = 0.0, upper: float = 1.0) -> float:
    return max(lower, min(upper, value))


def _numeric_mapping(raw: object) -> dict[str, float]:
    if not isinstance(raw, Mapping):
        return {}
    values: dict[str, float] = {}
    for key, value in raw.items():
        try:
            values[str(key)] = float(value)
        except (TypeError, ValueError):
            continue
    return values


def _derive_feedback_scores(metrics: Mapping[str, float]) -> dict[str, float]:
    interval_variety = float(metrics.get("interval_variety", 0.0) or 0.0)
    pitch_range = float(metrics.get("pitch_range_semitones", metrics.get("register_spread", 0.0)) or 0.0)
    onset_density = float(metrics.get("onset_density", 0.0) or 0.0)
    repetition = float(metrics.get("repetition_score", 0.0) or 0.0)
    centroid = float(metrics.get("spectral_centroid_hz", 0.0) or 0.0)
    flatness = float(metrics.get("spectral_flatness", 0.0) or 0.0)
    roughness = float(metrics.get("roughness", 0.0) or 0.0)
    hook = float(metrics.get("hook_clarity", 0.0) or 0.0)
    cadence = float(metrics.get("cadence_strength", 0.0) or 0.0)
    development = float(metrics.get("development_score", 0.0) or 0.0)
    return {
        "static_score": _clamp(
            (1.0 - interval_variety) * 0.28
            + (1.0 - min(pitch_range / 12.0, 1.0)) * 0.24
            + (1.0 - min(onset_density / 2.0, 1.0)) * 0.24
            + repetition * 0.24
        ),
        "harsh_score": _clamp(
            _clamp((centroid - 2400.0) / 2600.0) * 0.42
            + flatness * 0.24
            + roughness * 0.34
        ),
        "muddy_score": _clamp(_clamp((1100.0 - centroid) / 1100.0) * 0.82 + (1.0 - flatness) * 0.1),
        "underdeveloped_score": _clamp((1.0 - development) * 0.52 + (1.0 - hook) * 0.28 + (1.0 - cadence) * 0.2),
    }


def _entry_feedback_scores(entry: object) -> dict[str, float]:
    feedback_raw = entry.get("feedback_scores") if isinstance(entry, Mapping) else getattr(entry, "feedback_scores", None)
    feedback = _numeric_mapping(feedback_raw)
    if feedback:
        return feedback

    metrics_raw = entry.get("ear_metrics") if isinstance(entry, Mapping) else getattr(entry, "ear_metrics", None)
    metrics = _numeric_mapping(metrics_raw)
    if not metrics:
        return {}
    return _derive_feedback_scores(metrics)


def _repertoire_feedback_scores(repertoire_entries: Sequence[object]) -> dict[str, float]:
    scores = [_entry_feedback_scores(entry) for entry in list(repertoire_entries)[-8:]]
    scores = [score for score in scores if score]
    if not scores:
        return {
            "static_score": 0.0,
            "harsh_score": 0.0,
            "muddy_score": 0.0,
            "underdeveloped_score": 0.0,
        }
    keys = ("static_score", "harsh_score", "muddy_score", "underdeveloped_score")
    return {
        key: round(sum(score.get(key, 0.0) for score in scores) / len(scores), 3)
        for key in keys
    }


def _feedback_reason_tags(feedback_scores: Mapping[str, float]) -> tuple[str, ...]:
    tags = []
    for name, key in (
        ("static", "static_score"),
        ("harsh", "harsh_score"),
        ("muddy", "muddy_score"),
        ("underdeveloped", "underdeveloped_score"),
    ):
        if float(feedback_scores.get(key, 0.0) or 0.0) >= 0.55:
            tags.append(f"ear_correct={name}")
    return tuple(tags)


def _narrative_scale(scale_score: float) -> NarrativeScale:
    if scale_score < 0.28:
        return "single_image"
    if scale_score < 0.58:
        return "scene"
    if scale_score < 0.82:
        return "journey"
    return "ritual"


def _ending_family(
    *,
    cadence_state: str,
    composition_mode: CompositionMode,
    scale_score: float,
) -> str:
    if cadence_state == "sleep":
        return "fade"
    if cadence_state == "wind_down":
        return "afterglow"
    if composition_mode == "through_composed" and scale_score > 0.8:
        return "loop_exit"
    if composition_mode == "hybrid":
        return "reprise_coda"
    if scale_score > 0.7:
        return "hard_cadence"
    return "afterglow"


def _groove_identity(*, cadence_state: str, day_phase: str, scale_score: float) -> str:
    if cadence_state in {"sleep", "wind_down"}:
        return "drift" if scale_score < 0.6 else "ritual_ostinato"
    if cadence_state == "away_practice":
        return "broken"
    if day_phase in {"wake_ramp", "morning"}:
        return "procession"
    if scale_score > 0.72:
        return "dance"
    return "pulse"


def commission_piece(
    *,
    cadence_state: str,
    day_phase: str,
    weekly_phase: str = "",
    attention_score: float = 0.0,
    narrative_pressure: float = 0.0,
    occupancy_state: str = "",
    repertoire_entries: Sequence[object] = (),
    song_num: int = 0,
    hour: int | None = None,
    flags: SenseWeaveFeatureFlags | None = None,
    elapsed_minutes: float = 0.0,
    cycle_minutes: float = 30.0,
) -> PieceCommission:
    """Choose the next piece class and composition mode before writing it."""

    active_flags = flags or load_feature_flags()
    arc_directive = directive_for_elapsed(
        elapsed_minutes=elapsed_minutes,
        cadence_state=cadence_state,
        audience_attention=attention_score,
        cycle_minutes=cycle_minutes,
    )
    score = 0.32
    attention = _clamp(float(attention_score or 0.0), 0.0, 1.0)
    pressure = _clamp(float(narrative_pressure or 0.0), 0.0, 1.0)
    score += pressure * 0.48
    score += attention * 0.18

    if cadence_state in {"sleep"}:
        score -= 0.3
    elif cadence_state in {"wind_down"}:
        score -= 0.08
    elif cadence_state in {"away_practice"}:
        score += 0.04
    elif cadence_state in {"occupied_day"}:
        score += 0.05

    if occupancy_state == "occupied_active":
        score += 0.08
    elif occupancy_state == "likely_asleep":
        score -= 0.18

    if hour is not None:
        if hour < 7:
            score -= 0.15
        elif hour < 11:
            score -= 0.05
        elif hour >= 21:
            score += 0.08
        elif hour >= 23:
            score += 0.12

    if weekly_phase in {"friday", "weekend"}:
        score += 0.05

    if repertoire_entries:
        score += min(0.08, len(repertoire_entries) / 200.0)
    feedback_scores = _repertoire_feedback_scores(repertoire_entries)
    static_score = feedback_scores["static_score"]
    harsh_score = feedback_scores["harsh_score"]
    muddy_score = feedback_scores["muddy_score"]
    underdeveloped_score = feedback_scores["underdeveloped_score"]
    score += static_score * 0.04
    score += muddy_score * 0.03
    score += underdeveloped_score * 0.08
    score -= harsh_score * 0.02

    score += ((song_num % 5) - 2) * 0.012
    if song_num <= 1 and cadence_state not in {"sleep", "wind_down"}:
        # Fresh boots need a committed, audible piece quickly; don't start the
        # room with a maximal suite before the runtime has established presence.
        score = min(score, 0.74)
    scale_score = _clamp(score, 0.0, 1.0)

    if scale_score < 0.23:
        form_class: FormClass = "micro"
    elif scale_score < 0.62:
        form_class = "song"
    elif scale_score < 0.84:
        form_class = "extended"
    else:
        form_class = "suite"
    if form_class == "suite" and not active_flags.long_form_suite:
        form_class = "extended"

    hook_pressure = _clamp(
        0.78
        - (0.34 if cadence_state == "away_practice" else 0.0)
        - (0.14 if form_class in {"extended", "suite"} else 0.0)
        + (0.1 if cadence_state == "occupied_day" else 0.0)
        - pressure * 0.22,
        0.0,
        1.0,
    )
    hook_pressure = _clamp(
        hook_pressure
        + static_score * 0.04
        - harsh_score * 0.08
        + underdeveloped_score * 0.08,
        0.0,
        1.0,
    )
    through_pressure = _clamp(
        pressure * 0.75
        + (0.18 if form_class in {"extended", "suite"} else 0.0)
        + static_score * 0.04
        + underdeveloped_score * 0.12,
        0.0,
        1.0,
    )

    if through_pressure >= 0.82:
        composition_mode: CompositionMode = "through_composed"
    elif hook_pressure >= 0.52:
        composition_mode = "hook_led"
    else:
        composition_mode = "hybrid"

    lo, hi = FORM_CLASS_RANGES[form_class]
    duration_target_s = round(lo + (hi - lo) * scale_score, 1)
    narrative_scale = _narrative_scale(scale_score)
    sonic_world_count = 1 if form_class in {"micro", "song"} else 2 if form_class == "extended" else 3
    if muddy_score >= 0.55:
        sonic_world_count = min(3, max(2, sonic_world_count))
    if harsh_score >= 0.55:
        sonic_world_count = max(1, sonic_world_count - 1)
    groove_identity = _groove_identity(
        cadence_state=cadence_state,
        day_phase=day_phase,
        scale_score=scale_score,
    )
    if static_score >= 0.55 and groove_identity == "drift":
        groove_identity = "pulse"
    elif static_score >= 0.55 and groove_identity == "pulse":
        groove_identity = "broken"

    reason_tags = (
        cadence_state or "unknown_cadence",
        day_phase or "unknown_day_phase",
        weekly_phase or "unknown_weekly_phase",
        occupancy_state or "unknown_occupancy",
        f"scale={scale_score:.2f}",
    ) + _feedback_reason_tags(feedback_scores)
    return PieceCommission(
        form_class=form_class,
        composition_mode=composition_mode,
        duration_target_s=duration_target_s,
        sonic_world_count=sonic_world_count,
        hook_pressure=round(hook_pressure, 3),
        narrative_scale=narrative_scale,
        ending_family=_ending_family(
            cadence_state=cadence_state,
            composition_mode=composition_mode,
            scale_score=scale_score,
        ),
        groove_identity=groove_identity,
        reason_tags=reason_tags,
        arc_directive=arc_directive,
        arc_elapsed_minutes=round(float(elapsed_minutes or 0.0), 3),
        arc_cycle_minutes=round(float(cycle_minutes or 30.0), 3),
    )
