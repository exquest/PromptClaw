"""R11 lung capacity: enforce breath windows for wind and voice lanes."""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from typing import Any

from cypherclaw.render.role_gate import (
    GRID_LOCKED_ROLES,
    metadata_is_grid_locked as _metadata_is_grid_locked,
)

from ...music_tracker import (
    TrackerLane,
    TrackerPattern,
    TrackerScene,
    TrackerSong,
    TrackerStep,
)

DEFAULT_LUNG_CAPACITY_SECONDS = 6.0
MIN_LUNG_CAPACITY_SECONDS = 4.0
MAX_LUNG_CAPACITY_SECONDS = 8.0
DEFAULT_BREATH_SECONDS = 0.25
_DEFAULT_TEMPO = 120.0
_DEFAULT_RPB = 4

_CAPACITY_KEYS = ("lung_capacity_s", "lung_capacity_seconds", "lung_capacity")
_DISABLED_CAPACITY_VALUES = {"", "none", "null", "off", "false", "0"}
_WIND_VOICE_MARKERS = (
    "breath",
    "choir",
    "voice",
    "vocal",
    "flute",
    "clarinet",
    "oboe",
    "bassoon",
    "sax",
    "trumpet",
    "trombone",
    "horn",
)


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _capacity_text(value: float) -> str:
    return f"{value:.1f}"


def _capacity_override(metadata: Mapping[str, object] | None) -> float | None:
    if not metadata:
        return None
    for key in _CAPACITY_KEYS:
        if key not in metadata:
            continue
        raw = metadata.get(key)
        text = str(raw).strip().lower()
        if text in _DISABLED_CAPACITY_VALUES:
            return None
        try:
            return _clamp(
                float(text),
                MIN_LUNG_CAPACITY_SECONDS,
                MAX_LUNG_CAPACITY_SECONDS,
            )
        except ValueError:
            return None
    return None


def _has_disabled_capacity(metadata: Mapping[str, object] | None) -> bool:
    if not metadata:
        return False
    return any(str(metadata.get(key, "")).strip().lower() in _DISABLED_CAPACITY_VALUES for key in _CAPACITY_KEYS)


def _is_wind_or_voice(voice: str) -> bool:
    normalized = voice.strip().lower()
    if normalized.startswith("sw_"):
        normalized = normalized[3:]
    return any(marker in normalized for marker in _WIND_VOICE_MARKERS)


def lung_capacity_seconds_for_voice(
    voice: str,
    metadata: Mapping[str, object] | None = None,
    *,
    default_seconds: float = DEFAULT_LUNG_CAPACITY_SECONDS,
) -> float | None:
    """Return the playable continuous-sound cap for *voice*, if it has one."""

    override = _capacity_override(metadata)
    if override is not None:
        return override
    if _has_disabled_capacity(metadata):
        return None
    if _is_wind_or_voice(voice):
        return _clamp(default_seconds, MIN_LUNG_CAPACITY_SECONDS, MAX_LUNG_CAPACITY_SECONDS)
    return None


def _seconds_to_rows(seconds: float, *, tempo_bpm: float, rows_per_beat: int) -> int:
    rows = seconds * tempo_bpm * max(1, rows_per_beat) / 60.0
    return max(1, int(round(rows)))


def _phrase_group_key(step: TrackerStep) -> str:
    for key in ("phrase_id", "phrase_index", "repeat_cycle"):
        value = step.metadata.get(key)
        if value:
            return f"{key}:{value}"
    return "lane"


def _terminal_index_by_step(steps: list[TrackerStep]) -> dict[int, int]:
    groups: dict[str, list[int]] = {}
    for idx, step in enumerate(steps):
        groups.setdefault(_phrase_group_key(step), []).append(idx)

    terminals: dict[int, int] = {}
    for indices in groups.values():
        if not indices:
            continue
        terminal = indices[-1]
        for idx in indices:
            terminals[idx] = terminal
    return terminals


def _is_breath(step: TrackerStep) -> bool:
    return (
        step.velocity <= 0.0
        and (
            step.scale_degree <= 0
            or step.metadata.get("breath_r6") == "true"
            or step.metadata.get("breath_lung_capacity") == "true"
        )
    )


def _find_existing_breath_after(steps: list[TrackerStep], terminal_idx: int) -> int | None:
    for idx in range(terminal_idx + 1, len(steps)):
        step = steps[idx]
        if _is_breath(step):
            return idx
        if step.velocity > 0.0:
            return None
    return None


def _can_internal_breath(step: TrackerStep, *, max_velocity: float) -> bool:
    return (
        step.velocity > 0.0
        and step.velocity <= max_velocity
        and not step.accent
        and not _metadata_is_grid_locked(step.metadata)
    )


def _lung_metadata(step: TrackerStep, *, capacity_seconds: float) -> dict[str, str]:
    return {
        **step.metadata,
        "breath_lung_capacity": "true",
        "lung_capacity_s": _capacity_text(capacity_seconds),
    }


def _tag_breath(
    step: TrackerStep,
    *,
    capacity_seconds: float,
    breath_rows: int,
) -> TrackerStep:
    return replace(
        step,
        length_rows=max(step.length_rows, breath_rows),
        scale_degree=0,
        velocity=0.0,
        metadata=_lung_metadata(step, capacity_seconds=capacity_seconds),
    )


def _inserted_breath_after(
    step: TrackerStep,
    *,
    capacity_seconds: float,
    breath_rows: int,
) -> TrackerStep:
    return TrackerStep(
        row=step.row + step.length_rows,
        length_rows=breath_rows,
        scale_degree=0,
        velocity=0.0,
        metadata={
            "breath_lung_capacity": "true",
            "lung_capacity_s": _capacity_text(capacity_seconds),
        },
    )


@dataclass(frozen=True)
class LungCapacityRule:
    """Limit continuous wind/voice playback and add breath windows as needed."""

    default_lung_capacity_seconds: float = DEFAULT_LUNG_CAPACITY_SECONDS
    breath_seconds: float = DEFAULT_BREATH_SECONDS
    internal_breath_max_velocity: float = 0.35

    rule_id = "R11"

    def applies_to(self, role: str, metadata: Mapping[str, object] | None = None) -> bool:
        normalized = role.strip().lower()
        return normalized not in GRID_LOCKED_ROLES and not _metadata_is_grid_locked(metadata)

    def lung_capacity_seconds(
        self,
        voice: str,
        metadata: Mapping[str, object] | None = None,
    ) -> float | None:
        return lung_capacity_seconds_for_voice(
            voice,
            metadata,
            default_seconds=self.default_lung_capacity_seconds,
        )

    def apply(
        self,
        score: Any,
        *,
        k: float,
        seeds: Mapping[str, int] | None,
        roles: frozenset[str] | None,
    ) -> Any:
        del seeds
        return apply_lung_capacity(score, k=k, roles=roles, rule=self)


def _apply_to_lane(
    lane: TrackerLane,
    *,
    k: float,
    roles: frozenset[str] | None,
    rule: LungCapacityRule,
    tempo_bpm: float,
    rows_per_beat: int,
) -> TrackerLane:
    normalized_role = lane.role.strip().lower()
    if roles is not None and normalized_role not in {r.strip().lower() for r in roles}:
        return lane
    if not rule.applies_to(lane.role, lane.metadata):
        return lane
    if not lane.steps:
        return lane

    capacity_seconds = rule.lung_capacity_seconds(lane.voice, lane.metadata)
    if capacity_seconds is None:
        return lane

    capacity_rows = float(_seconds_to_rows(
        capacity_seconds,
        tempo_bpm=tempo_bpm,
        rows_per_beat=rows_per_beat,
    ))
    capacity_rows = capacity_rows / max(0.001, k)
    breath_rows = _seconds_to_rows(
        rule.breath_seconds,
        tempo_bpm=tempo_bpm,
        rows_per_beat=rows_per_beat,
    )
    terminal_by_step = _terminal_index_by_step(lane.steps)
    forced_terminal_indices: set[int] = set()
    internal_breath_indices: set[int] = set()
    continuous_rows = 0.0
    last_end_row: int | None = None

    for idx, step in enumerate(lane.steps):
        if last_end_row is not None and step.row > last_end_row:
            continuous_rows = 0.0
        length_rows = max(0, step.length_rows)
        end_row = step.row + length_rows

        if step.velocity <= 0.0 or length_rows <= 0:
            continuous_rows = 0.0
            last_end_row = end_row
            continue

        if continuous_rows + length_rows > capacity_rows:
            if _can_internal_breath(step, max_velocity=rule.internal_breath_max_velocity):
                internal_breath_indices.add(idx)
                continuous_rows = 0.0
                last_end_row = end_row
                continue

            terminal_idx = terminal_by_step.get(idx)
            if terminal_idx is not None and not _metadata_is_grid_locked(
                lane.steps[terminal_idx].metadata,
            ):
                forced_terminal_indices.add(terminal_idx)

        continuous_rows += length_rows
        last_end_row = end_row
        if idx in forced_terminal_indices:
            continuous_rows = 0.0

    if not forced_terminal_indices and not internal_breath_indices:
        return lane

    breath_ext_indices: set[int] = set()
    insert_after_indices: set[int] = set()
    for terminal_idx in forced_terminal_indices:
        existing_breath_idx = _find_existing_breath_after(lane.steps, terminal_idx)
        if existing_breath_idx is None:
            insert_after_indices.add(terminal_idx)
        else:
            breath_ext_indices.add(existing_breath_idx)

    new_steps: list[TrackerStep] = []
    for idx, step in enumerate(lane.steps):
        if idx in internal_breath_indices or idx in breath_ext_indices:
            new_steps.append(_tag_breath(
                step,
                capacity_seconds=capacity_seconds,
                breath_rows=breath_rows,
            ))
        else:
            new_steps.append(step)

        if idx in insert_after_indices:
            new_steps.append(_inserted_breath_after(
                step,
                capacity_seconds=capacity_seconds,
                breath_rows=breath_rows,
            ))

    return replace(lane, steps=new_steps)


def _apply_to_pattern(
    pattern: TrackerPattern,
    *,
    k: float,
    roles: frozenset[str] | None,
    rule: LungCapacityRule,
    tempo_bpm: float,
    rows_per_beat: int,
) -> TrackerPattern:
    return replace(
        pattern,
        lanes=[
            _apply_to_lane(
                lane,
                k=k,
                roles=roles,
                rule=rule,
                tempo_bpm=tempo_bpm,
                rows_per_beat=rows_per_beat,
            )
            for lane in pattern.lanes
        ],
    )


def _apply_to_scene(
    scene: TrackerScene,
    *,
    k: float,
    roles: frozenset[str] | None,
    rule: LungCapacityRule,
) -> TrackerScene:
    return replace(
        scene,
        pattern=_apply_to_pattern(
            scene.pattern,
            k=k,
            roles=roles,
            rule=rule,
            tempo_bpm=scene.tempo_bpm,
            rows_per_beat=scene.rows_per_beat,
        ),
    )


def apply_lung_capacity(
    score: Any,
    *,
    k: float = 1.0,
    seeds: Mapping[str, int] | None = None,
    roles: frozenset[str] | None = None,
    rule: LungCapacityRule | None = None,
) -> Any:
    """Apply wind/voice lung-capacity breath insertion to tracker scenes or songs."""

    del seeds
    if k == 0.0:
        return score
    shaped_k = _clamp(k, 0.0, 1.0)
    if shaped_k == 0.0:
        return score
    active_rule = rule or LungCapacityRule()

    if isinstance(score, TrackerScene):
        return _apply_to_scene(score, k=shaped_k, roles=roles, rule=active_rule)
    if isinstance(score, TrackerSong):
        return replace(
            score,
            scenes=[
                _apply_to_scene(scene, k=shaped_k, roles=roles, rule=active_rule)
                for scene in score.scenes
            ],
        )
    if isinstance(score, TrackerPattern):
        return _apply_to_pattern(
            score,
            k=shaped_k,
            roles=roles,
            rule=active_rule,
            tempo_bpm=_DEFAULT_TEMPO,
            rows_per_beat=_DEFAULT_RPB,
        )
    return score


@dataclass(frozen=True)
class LaneBreathStat:
    """Per-lane breath outcome from one lung-capacity apply pass."""

    lane_name: str
    voice: str
    role: str
    capacity_seconds: float | None
    inserted_breath_count: int
    tagged_breath_count: int
    applies: bool


@dataclass(frozen=True)
class LungCapacityReport:
    """Aggregate lung-capacity outcome for one score."""

    score_kind: str
    total_inserted: int
    total_tagged: int
    lane_stats: tuple[LaneBreathStat, ...]


def lane_breath_stat(
    original: TrackerLane,
    rendered: TrackerLane,
    *,
    rule: LungCapacityRule,
) -> LaneBreathStat:
    """Compare *original* and *rendered* lanes and report breath changes."""

    capacity_seconds = rule.lung_capacity_seconds(rendered.voice, rendered.metadata)
    role_applies = rule.applies_to(rendered.role, rendered.metadata)
    applies = role_applies and capacity_seconds is not None

    original_by_row = {step.row: step for step in original.steps}
    inserted_count = 0
    tagged_count = 0
    for step in rendered.steps:
        if step.metadata.get("breath_lung_capacity") != "true":
            continue
        prior = original_by_row.get(step.row)
        if prior is None:
            inserted_count += 1
        elif prior.metadata.get("breath_lung_capacity") != "true":
            tagged_count += 1

    return LaneBreathStat(
        lane_name=rendered.name,
        voice=rendered.voice,
        role=rendered.role,
        capacity_seconds=capacity_seconds,
        inserted_breath_count=inserted_count,
        tagged_breath_count=tagged_count,
        applies=applies,
    )


def _score_kind(score: Any) -> str:
    if isinstance(score, TrackerScene):
        return "scene"
    if isinstance(score, TrackerSong):
        return "song"
    if isinstance(score, TrackerPattern):
        return "pattern"
    return "unsupported"


def _lane_pairs(
    score: Any,
    rendered: Any,
    kind: str,
) -> list[tuple[TrackerLane, TrackerLane]]:
    if kind == "scene":
        return list(zip(score.pattern.lanes, rendered.pattern.lanes))
    if kind == "song":
        pairs: list[tuple[TrackerLane, TrackerLane]] = []
        for orig_scene, rend_scene in zip(score.scenes, rendered.scenes):
            pairs.extend(zip(orig_scene.pattern.lanes, rend_scene.pattern.lanes))
        return pairs
    if kind == "pattern":
        return list(zip(score.lanes, rendered.lanes))
    return []


def analyze_lung_capacity(
    score: Any,
    *,
    k: float = 1.0,
    seeds: Mapping[str, int] | None = None,
    roles: frozenset[str] | None = None,
    rule: LungCapacityRule | None = None,
) -> tuple[Any, LungCapacityReport]:
    """Apply lung-capacity rule to *score* and return rendered + report."""

    active_rule = rule or LungCapacityRule()
    rendered = apply_lung_capacity(
        score,
        k=k,
        seeds=seeds,
        roles=roles,
        rule=active_rule,
    )

    kind = _score_kind(score)
    if kind == "unsupported":
        return rendered, LungCapacityReport(
            score_kind="unsupported",
            total_inserted=0,
            total_tagged=0,
            lane_stats=(),
        )

    stats: list[LaneBreathStat] = []
    total_inserted = 0
    total_tagged = 0
    for original_lane, rendered_lane in _lane_pairs(score, rendered, kind):
        stat = lane_breath_stat(original_lane, rendered_lane, rule=active_rule)
        stats.append(stat)
        total_inserted += stat.inserted_breath_count
        total_tagged += stat.tagged_breath_count

    return rendered, LungCapacityReport(
        score_kind=kind,
        total_inserted=total_inserted,
        total_tagged=total_tagged,
        lane_stats=tuple(stats),
    )


def summarize_lung_capacity_report(
    report: LungCapacityReport,
) -> dict[str, object]:
    """Return a JSON-safe operator summary of *report*."""

    lanes: list[dict[str, object]] = []
    applied_count = 0
    for stat in report.lane_stats:
        if stat.applies:
            applied_count += 1
        lanes.append(
            {
                "lane_name": stat.lane_name,
                "voice": stat.voice,
                "role": stat.role,
                "capacity_seconds": stat.capacity_seconds,
                "inserted_breath_count": stat.inserted_breath_count,
                "tagged_breath_count": stat.tagged_breath_count,
                "applies": stat.applies,
            }
        )
    return {
        "score_kind": report.score_kind,
        "total_inserted": report.total_inserted,
        "total_tagged": report.total_tagged,
        "lane_count": len(report.lane_stats),
        "applied_lane_count": applied_count,
        "lanes": lanes,
    }
