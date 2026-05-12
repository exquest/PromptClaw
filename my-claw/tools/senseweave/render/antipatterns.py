"""Anti-pattern detectors for SenseWeave rendered performances."""
from __future__ import annotations

import math
import statistics
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any


@dataclass(frozen=True)
class AntiPatternResult:
    """Result from one render anti-pattern detector."""

    name: str
    failed: bool
    detail: str
    value: float | None = None
    threshold: float | None = None
    severity: str = "fail"


Detector = tuple[str, Any]

GENERATED_CONTENT_DOMINANCE_RATIO_THRESHOLD = 0.3
GENERATED_CONTENT_DOMINANCE_CONSECUTIVE_DAYS = 7
GENERATED_CONTENT_DOMINANCE_WINDOW_SIZE = 50
SAMPLER_DOMINATING_RATIO_THRESHOLD = 0.6
SAMPLER_DOMINATING_CONSECUTIVE_LIMIT = 3
SAMPLER_SILENT_USAGE_FLOOR = 0.05
SAMPLER_SILENT_WINDOW_SIZE = 50
SAMPLER_SILENT_REFERENCE_DENSITY = 0.7

DEFAULT_SAMPLER_DENSITY_BY_MODE: Mapping[str, float] = {
    "solitary": 0.7,
    "companion": 0.25,
    "working_ambience": 0.10,
    "evening_reflection": 0.65,
    "storm": 0.45,
}

_CHI_SQUARE_95: dict[int, float] = {
    1: 3.841,
    2: 5.991,
    3: 7.815,
    4: 9.488,
    5: 11.070,
    6: 12.592,
    7: 14.067,
    8: 15.507,
    9: 16.919,
    10: 18.307,
}


def detect_quantization_ghosting(rendered: object) -> AntiPatternResult:
    """Fail when dynamics vary but timing stays effectively grid-quantized."""

    score = _score_mapping(rendered)
    velocities = _velocity_series(score)
    timing_ms = _series(
        score,
        "timing_deviations_ms",
        "timing_ms",
        "microtiming_ms",
        "onset_deviations_ms",
    )
    velocity_sigma = _stdev(velocities)
    timing_sigma = _stdev(timing_ms)
    failed = bool(velocities and timing_ms) and velocity_sigma > 0.0 and timing_sigma < 3.0
    return AntiPatternResult(
        name="quantization_ghosting",
        failed=failed,
        detail=(
            f"velocity_sigma={velocity_sigma:.3f}, "
            f"timing_sigma_ms={timing_sigma:.3f}"
        ),
        value=timing_sigma,
        threshold=3.0,
    )


def detect_dynamic_compression(rendered: object) -> AntiPatternResult:
    """Fail when the MIDI velocity range is narrower than 20 units."""

    velocities = _velocity_series(_score_mapping(rendered))
    velocity_range = max(velocities) - min(velocities) if velocities else 0.0
    failed = bool(velocities) and velocity_range < 20.0
    return AntiPatternResult(
        name="dynamic_compression",
        failed=failed,
        detail=f"velocity_range={velocity_range:.3f}",
        value=velocity_range,
        threshold=20.0,
    )


def detect_motif_ossification(rendered: object) -> AntiPatternResult:
    """Fail when repeated sections are too similar by grooving similarity."""

    score = _score_mapping(rendered)
    similarities = _series(
        score,
        "section_gs",
        "repeated_section_gs",
        "grooving_similarities",
        "gs_repeated_sections",
    )
    if not similarities:
        similarities = _section_similarities(score)
    failed = bool(similarities) and all(value > 0.95 for value in similarities)
    value = min(similarities) if similarities else None
    detail = "no repeated-section GS values"
    if similarities:
        detail = "section_gs=" + ",".join(f"{value:.3f}" for value in similarities)
    return AntiPatternResult(
        name="motif_ossification",
        failed=failed,
        detail=detail,
        value=value,
        threshold=0.95,
    )


def detect_random_as_expression(rendered: object) -> AntiPatternResult:
    """Fail when Ljung-Box does not reject white noise on tempo or velocity."""

    score = _score_mapping(rendered)
    tested: list[str] = []
    failed_series: list[str] = []
    statistics_parts: list[str] = []
    for label, values in (
        ("tempo_curve", _series(score, "tempo_curve", "tempos", "tempo_series")),
        ("velocities", _velocity_series(score)),
    ):
        result = _ljung_box(values)
        if result is None:
            continue
        tested.append(label)
        statistic, critical, lags, rejects_white_noise = result
        statistics_parts.append(
            f"{label}:Q={statistic:.3f}/crit={critical:.3f}/lags={lags}"
        )
        if not rejects_white_noise:
            failed_series.append(label)

    failed = bool(failed_series)
    if not tested:
        detail = "insufficient tempo/velocity data for Ljung-Box"
    else:
        detail = "; ".join(statistics_parts)
        if failed_series:
            detail += "; white_noise_not_rejected=" + ",".join(failed_series)
    return AntiPatternResult(
        name="random_as_expression",
        failed=failed,
        detail=detail,
    )


def detect_symmetric_arc_uncanny(rendered: object) -> AntiPatternResult:
    """Fail when phrase worm convex-hull areas vary by less than 5%."""

    score = _score_mapping(rendered)
    areas = _series(score, "worm_hull_areas", "phrase_worm_hull_areas")
    if not areas:
        areas = tuple(
            _convex_hull_area(points)
            for points in _phrase_worms(score)
        )

    shape_variance = _coefficient_of_variation(areas)
    failed = len(areas) > 1 and shape_variance < 0.05
    return AntiPatternResult(
        name="symmetric_arc_uncanny",
        failed=failed,
        detail=f"worm_hull_shape_variance={shape_variance:.3f}",
        value=shape_variance,
        threshold=0.05,
    )


def detect_dead_silence_failure(rendered: object) -> AntiPatternResult:
    """Fail when a two-minute melodic passage has no rest of at least 200 ms."""

    score = _score_mapping(rendered)
    duration_sec = _duration_seconds(score)
    rests_ms = _rests_ms(score)
    longest_rest = max(rests_ms) if rests_ms else 0.0
    failed = (
        duration_sec >= 120.0
        and _is_melodic(score)
        and longest_rest < 200.0
    )
    return AntiPatternResult(
        name="dead_silence_failure",
        failed=failed,
        detail=(
            f"duration_sec={duration_sec:.3f}, "
            f"longest_rest_ms={longest_rest:.3f}"
        ),
        value=longest_rest,
        threshold=200.0,
    )


def detect_generated_content_dominance(rendered: object) -> AntiPatternResult:
    """Warn when generated samples dominate sampler content.

    A current piece breach reports as severity="warning". Seven consecutive
    over-threshold days in the rolling 50-piece history escalate to
    severity="fail".
    """

    score = _score_mapping(rendered)
    current_ratio = _generated_content_ratio(score)
    per_piece_failed = (
        current_ratio is not None
        and current_ratio > GENERATED_CONTENT_DOMINANCE_RATIO_THRESHOLD
    )
    rolling_streak = _generated_content_dominance_streak(
        score.get("piece_history", score.get("recent_pieces"))
    )
    rolling_failed = (
        rolling_streak >= GENERATED_CONTENT_DOMINANCE_CONSECUTIVE_DAYS
    )

    if rolling_failed:
        severity = "fail"
    elif per_piece_failed:
        severity = "warning"
    else:
        severity = "ok"

    ratio_detail = "current_ratio=none"
    if current_ratio is not None:
        ratio_detail = f"current_ratio={current_ratio:.3f}"
    return AntiPatternResult(
        name="generated_content_dominance",
        failed=per_piece_failed or rolling_failed,
        detail=(
            f"{ratio_detail}, rolling_streak_days={rolling_streak}, "
            f"severity={severity}"
        ),
        value=current_ratio,
        threshold=GENERATED_CONTENT_DOMINANCE_RATIO_THRESHOLD,
        severity=severity,
    )


def detect_sampler_dominating(rendered: object) -> AntiPatternResult:
    """Fail when sampler events exceed 60% of total events in a piece.

    Reports as severity="warning" by default; escalates to severity="fail"
    once the consecutive-piece streak reaches
    :data:`SAMPLER_DOMINATING_CONSECUTIVE_LIMIT`.
    """

    score = _score_mapping(rendered)
    sampler_count = _first_number(
        score, "sampler_event_count", "sampler_events", "sampler_event_total"
    )
    total_count = _first_number(
        score, "total_event_count", "total_events", "event_count"
    )
    streak_value = _first_number(
        score, "sampler_dominating_streak", "consecutive_sampler_dominating"
    )
    streak = int(streak_value) if streak_value is not None else 0

    if sampler_count is None or total_count is None or total_count <= 0.0:
        return AntiPatternResult(
            name="sampler_dominating",
            failed=False,
            detail="no sampler/total event counts",
            severity="ok",
        )

    ratio = sampler_count / total_count
    over_threshold = ratio > SAMPLER_DOMINATING_RATIO_THRESHOLD
    if not over_threshold:
        severity = "ok"
    elif streak >= SAMPLER_DOMINATING_CONSECUTIVE_LIMIT:
        severity = "fail"
    else:
        severity = "warning"
    return AntiPatternResult(
        name="sampler_dominating",
        failed=over_threshold,
        detail=(
            f"sampler={int(sampler_count)}/total={int(total_count)}, "
            f"ratio={ratio:.3f}, streak={streak}, severity={severity}"
        ),
        value=ratio,
        threshold=SAMPLER_DOMINATING_RATIO_THRESHOLD,
        severity=severity,
    )


def detect_sampler_silent_quintet_member(rendered: object) -> AntiPatternResult:
    """Fail when sampler usage in the rolling 50-piece window is too low.

    Threshold is mode-weighted: it scales linearly with the average
    ``sampler_density`` across the window relative to the highest mode density
    (``solitary`` at 0.7), so low-density modes such as ``working_ambience``
    do not trip the detector.
    """

    score = _score_mapping(rendered)
    history = score.get("piece_history", score.get("recent_pieces"))
    if not isinstance(history, Sequence) or isinstance(history, (str, bytes)):
        return AntiPatternResult(
            name="sampler_silent_quintet_member",
            failed=False,
            detail="no piece history",
            severity="ok",
        )

    window: list[Mapping[str, object]] = [
        piece
        for piece in list(history)[-SAMPLER_SILENT_WINDOW_SIZE:]
        if isinstance(piece, Mapping)
    ]
    if not window:
        return AntiPatternResult(
            name="sampler_silent_quintet_member",
            failed=False,
            detail="empty piece history",
            severity="ok",
        )

    sampler_used_count = sum(1 for piece in window if bool(piece.get("sampler_used")))
    densities: list[float] = []
    for piece in window:
        density = _piece_density(piece)
        if density is not None:
            densities.append(density)

    mean_density = (
        sum(densities) / len(densities)
        if densities
        else SAMPLER_SILENT_REFERENCE_DENSITY
    )
    weight = mean_density / SAMPLER_SILENT_REFERENCE_DENSITY
    threshold = SAMPLER_SILENT_USAGE_FLOOR * weight
    usage = sampler_used_count / len(window)
    failed = usage < threshold
    return AntiPatternResult(
        name="sampler_silent_quintet_member",
        failed=failed,
        detail=(
            f"sampler_used={sampler_used_count}/{len(window)} "
            f"({usage:.3f}), mean_density={mean_density:.3f}, "
            f"threshold={threshold:.3f}"
        ),
        value=usage,
        threshold=threshold,
        severity="fail" if failed else "ok",
    )


def detect_antipatterns(rendered: object) -> tuple[AntiPatternResult, ...]:
    """Run the full anti-pattern battery."""

    return (
        detect_quantization_ghosting(rendered),
        detect_dynamic_compression(rendered),
        detect_motif_ossification(rendered),
        detect_random_as_expression(rendered),
        detect_symmetric_arc_uncanny(rendered),
        detect_dead_silence_failure(rendered),
        detect_generated_content_dominance(rendered),
        detect_sampler_dominating(rendered),
        detect_sampler_silent_quintet_member(rendered),
    )


def failing_antipatterns(rendered: object) -> tuple[AntiPatternResult, ...]:
    """Return only anti-pattern results that fail the render."""

    return tuple(result for result in detect_antipatterns(rendered) if result.failed)


def _score_mapping(rendered: object) -> Mapping[str, object]:
    if isinstance(rendered, Mapping):
        return rendered
    score = getattr(rendered, "score", None)
    if isinstance(score, Mapping):
        return score
    return {}


def _series(score: Mapping[str, object], *keys: str) -> tuple[float, ...]:
    for key in keys:
        if key not in score:
            continue
        values = _numeric_tuple(score[key])
        if values:
            return values
    return ()


def _numeric_tuple(value: object) -> tuple[float, ...]:
    if isinstance(value, bool):
        return ()
    if isinstance(value, (int, float)):
        return (float(value),)
    if isinstance(value, (str, bytes)):
        return ()
    if not isinstance(value, Iterable):
        return ()

    values: list[float] = []
    for item in value:
        if isinstance(item, bool):
            continue
        try:
            values.append(float(item))
        except (TypeError, ValueError):
            continue
    return tuple(values)


def _velocity_series(score: Mapping[str, object]) -> tuple[float, ...]:
    velocities = _series(score, "velocities", "velocity", "midi_velocities")
    if velocities and max(abs(value) for value in velocities) <= 1.0:
        return tuple(value * 127.0 for value in velocities)
    return velocities


def _stdev(values: Sequence[float]) -> float:
    if len(values) < 2:
        return 0.0
    return statistics.stdev(values)


def _section_similarities(score: Mapping[str, object]) -> tuple[float, ...]:
    sections = score.get("repeated_sections", score.get("sections"))
    if not isinstance(sections, Sequence) or isinstance(sections, (str, bytes)):
        return ()

    numeric_sections = [_numeric_tuple(section) for section in sections]
    numeric_sections = [section for section in numeric_sections if section]
    if len(numeric_sections) < 2:
        return ()
    return tuple(
        _grooving_similarity(left, right)
        for left, right in zip(numeric_sections, numeric_sections[1:])
    )


def _grooving_similarity(left: Sequence[float], right: Sequence[float]) -> float:
    length = min(len(left), len(right))
    if length == 0:
        return 0.0
    left_values = left[:length]
    right_values = right[:length]
    rmse = math.sqrt(
        sum((a - b) ** 2 for a, b in zip(left_values, right_values)) / length
    )
    combined = tuple(left_values) + tuple(right_values)
    scale = max(max(combined) - min(combined), 1.0)
    return max(0.0, min(1.0, 1.0 - (rmse / scale)))


def _ljung_box(values: Sequence[float]) -> tuple[float, float, int, bool] | None:
    n = len(values)
    if n < 8:
        return None
    mean = sum(values) / n
    centered = [value - mean for value in values]
    denominator = sum(value * value for value in centered)
    if denominator == 0.0:
        critical = _CHI_SQUARE_95[1]
        return math.inf, critical, 1, True

    lags = min(10, max(1, n // 5))
    q_stat = 0.0
    for lag in range(1, lags + 1):
        numerator = sum(
            centered[index] * centered[index - lag]
            for index in range(lag, n)
        )
        autocorrelation = numerator / denominator
        q_stat += (autocorrelation * autocorrelation) / (n - lag)
    q_stat *= n * (n + 2)
    critical = _CHI_SQUARE_95[lags]
    return q_stat, critical, lags, q_stat > critical


def _phrase_worms(score: Mapping[str, object]) -> tuple[tuple[tuple[float, float], ...], ...]:
    worms = score.get("phrase_worms", score.get("worm_phrases", score.get("worms")))
    if not isinstance(worms, Sequence) or isinstance(worms, (str, bytes)):
        return ()
    return tuple(points for points in (_points(worm) for worm in worms) if points)


def _points(worm: object) -> tuple[tuple[float, float], ...]:
    if not isinstance(worm, Sequence) or isinstance(worm, (str, bytes)):
        return ()

    points: list[tuple[float, float]] = []
    for item in worm:
        if isinstance(item, Mapping):
            x_value = item.get("tempo", item.get("x"))
            y_value = item.get("loudness", item.get("y"))
        elif isinstance(item, Sequence) and not isinstance(item, (str, bytes)):
            if len(item) < 2:
                continue
            x_value = item[0]
            y_value = item[1]
        else:
            continue
        try:
            points.append((float(x_value), float(y_value)))
        except (TypeError, ValueError):
            continue
    return tuple(points)


def _convex_hull_area(points: Sequence[tuple[float, float]]) -> float:
    unique = sorted(set(points))
    if len(unique) < 3:
        return 0.0

    def cross(
        origin: tuple[float, float],
        left: tuple[float, float],
        right: tuple[float, float],
    ) -> float:
        return (
            (left[0] - origin[0]) * (right[1] - origin[1])
            - (left[1] - origin[1]) * (right[0] - origin[0])
        )

    lower: list[tuple[float, float]] = []
    for point in unique:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], point) <= 0.0:
            lower.pop()
        lower.append(point)

    upper: list[tuple[float, float]] = []
    for point in reversed(unique):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], point) <= 0.0:
            upper.pop()
        upper.append(point)

    hull = lower[:-1] + upper[:-1]
    area = 0.0
    for index, point in enumerate(hull):
        next_point = hull[(index + 1) % len(hull)]
        area += point[0] * next_point[1] - next_point[0] * point[1]
    return abs(area) / 2.0


def _coefficient_of_variation(values: Sequence[float]) -> float:
    if len(values) < 2:
        return math.inf
    mean = sum(values) / len(values)
    if mean == 0.0:
        return 0.0 if all(value == 0.0 for value in values) else math.inf
    return statistics.pstdev(values) / abs(mean)


def _duration_seconds(score: Mapping[str, object]) -> float:
    seconds = _first_number(
        score,
        "duration_sec",
        "duration_seconds",
        "passage_duration_sec",
        "melodic_duration_sec",
    )
    if seconds is not None:
        return seconds
    milliseconds = _first_number(score, "duration_ms", "passage_duration_ms")
    if milliseconds is not None:
        return milliseconds / 1000.0
    return 0.0


def _first_number(score: Mapping[str, object], *keys: str) -> float | None:
    for key in keys:
        if key not in score:
            continue
        values = _numeric_tuple(score[key])
        if values:
            return values[0]
    return None


def _rests_ms(score: Mapping[str, object]) -> tuple[float, ...]:
    rests = _series(score, "rests_ms", "rest_durations_ms", "silences_ms")
    if rests:
        return rests
    rests_sec = _series(score, "rests_sec", "rest_durations_sec", "silences_sec")
    if rests_sec:
        return tuple(value * 1000.0 for value in rests_sec)
    return _series(score, "silence_ms", "max_silence_ms")


def _generated_content_ratio(score: Mapping[str, object]) -> float | None:
    counts = _generated_content_counts(score)
    if counts is None:
        return None
    generated, total = counts
    if total <= 0.0:
        return None
    return generated / total


def _generated_content_counts(
    score: Mapping[str, object],
) -> tuple[float, float] | None:
    samples_by_source = score.get("samples_by_source")
    if not isinstance(samples_by_source, Mapping):
        return None

    generated_values = _numeric_tuple(samples_by_source.get("generated"))
    total = _first_number(score, "total_sampler_events")
    if not generated_values or total is None:
        return None
    return generated_values[0], total


def _generated_content_dominance_streak(history: object) -> int:
    if not isinstance(history, Sequence) or isinstance(history, (str, bytes)):
        return 0

    window: list[Mapping[str, object]] = [
        piece
        for piece in list(history)[-GENERATED_CONTENT_DOMINANCE_WINDOW_SIZE:]
        if isinstance(piece, Mapping)
    ]
    if not window:
        return 0

    day_order: list[object] = []
    generated_by_day: dict[object, float] = {}
    total_by_day: dict[object, float] = {}
    ordinal_by_day: dict[object, int | None] = {}
    for index, piece in enumerate(window):
        counts = _generated_content_counts(piece)
        if counts is None:
            continue
        generated, total = counts
        day_key, ordinal = _piece_day(piece, index)
        if day_key not in generated_by_day:
            day_order.append(day_key)
            generated_by_day[day_key] = 0.0
            total_by_day[day_key] = 0.0
            ordinal_by_day[day_key] = ordinal
        generated_by_day[day_key] += generated
        total_by_day[day_key] += total

    if not day_order:
        return 0

    ordered_days = day_order
    if all(ordinal_by_day[day] is not None for day in day_order):
        ordered_days = sorted(day_order, key=lambda day: ordinal_by_day[day] or 0)

    streak = 0
    longest_streak = 0
    previous_ordinal: int | None = None
    for day in ordered_days:
        total = total_by_day[day]
        ratio = generated_by_day[day] / total if total > 0.0 else 0.0
        ordinal = ordinal_by_day[day]
        if ratio > GENERATED_CONTENT_DOMINANCE_RATIO_THRESHOLD:
            if (
                previous_ordinal is None
                or ordinal is None
                or ordinal == previous_ordinal + 1
            ):
                streak += 1
            else:
                streak = 1
            longest_streak = max(longest_streak, streak)
        else:
            streak = 0
        previous_ordinal = ordinal
    return longest_streak


def _piece_day(piece: Mapping[str, object], fallback_index: int) -> tuple[object, int | None]:
    for key in (
        "day",
        "date",
        "created_date",
        "rendered_date",
        "created_at",
        "timestamp",
    ):
        if key not in piece:
            continue
        raw_day = piece[key]
        ordinal = _day_ordinal(raw_day)
        if ordinal is not None:
            return ("ordinal", ordinal), ordinal
        return (key, str(raw_day)), None
    return ("index", fallback_index), fallback_index


def _day_ordinal(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, datetime):
        return value.date().toordinal()
    if isinstance(value, date):
        return value.toordinal()
    if isinstance(value, str):
        text = value.strip()
        for candidate in (text[:10], text):
            try:
                return date.fromisoformat(candidate).toordinal()
            except ValueError:
                continue
    return None


def _piece_density(piece: Mapping[str, object]) -> float | None:
    explicit = piece.get("sampler_density")
    if explicit is not None:
        try:
            return float(explicit)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            pass
    mode = piece.get("mode")
    if isinstance(mode, str):
        return DEFAULT_SAMPLER_DENSITY_BY_MODE.get(mode)
    return None


def _is_melodic(score: Mapping[str, object]) -> bool:
    is_melodic = score.get("is_melodic")
    if isinstance(is_melodic, bool):
        return is_melodic
    role = score.get("role", score.get("voice_role", "melody"))
    if not isinstance(role, str):
        return True
    return role.lower() in {"melody", "melodic", "lead", "solo"}


__all__ = [
    "AntiPatternResult",
    "DEFAULT_SAMPLER_DENSITY_BY_MODE",
    "GENERATED_CONTENT_DOMINANCE_CONSECUTIVE_DAYS",
    "GENERATED_CONTENT_DOMINANCE_RATIO_THRESHOLD",
    "GENERATED_CONTENT_DOMINANCE_WINDOW_SIZE",
    "SAMPLER_DOMINATING_CONSECUTIVE_LIMIT",
    "SAMPLER_DOMINATING_RATIO_THRESHOLD",
    "SAMPLER_SILENT_REFERENCE_DENSITY",
    "SAMPLER_SILENT_USAGE_FLOOR",
    "SAMPLER_SILENT_WINDOW_SIZE",
    "detect_antipatterns",
    "detect_dead_silence_failure",
    "detect_dynamic_compression",
    "detect_generated_content_dominance",
    "detect_motif_ossification",
    "detect_quantization_ghosting",
    "detect_random_as_expression",
    "detect_sampler_dominating",
    "detect_sampler_silent_quintet_member",
    "detect_symmetric_arc_uncanny",
    "failing_antipatterns",
]
