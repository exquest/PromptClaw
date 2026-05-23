"""Runtime scheduling for tracker scenes.

This module is the timing owner for tracker-driven playback. It converts
planned tracker scenes into timed event emissions and writes lightweight
runtime state for click/event correlation.
"""
from __future__ import annotations

import json
import os
import time
import logging
from dataclasses import dataclass, field, fields as dc_fields, replace
from pathlib import Path
from typing import Any, Callable

from cypherclaw.render.events import Event

from .generative_scores import _scale_degree_to_freq, role_octave_shift_for_patch
from .music_tracker import (
    TrackerLane,
    TrackerScene,
    TrackerSong,
    metric_modulated_duration_seconds,
    metric_modulated_row_durations_seconds,
)

TRACKER_RUNTIME_STATE = "/tmp/tracker_runtime_state.json"

_ROLE_GAIN = {
    "bass": 0.17,
    "melody": 0.16,
    "counter": 0.11,
    "color": 0.08,
    "rhythm": 0.13,
    "sample": 0.1,
}

_VOICE_FALLBACK: dict[str, str] = {
    # Texture lanes default to `pad`; keep a soft fallback so widened casts
    # cannot turn quiet scenes into an unbroken drone if a routing hint slips through.
    "pad": "breath",
    # `sw_grain` leaks on the live box and accumulates into broadband static.
    # Keep the character selection metadata, but route playback to a safe texture
    # voice until the underlying SynthDef is fixed.
    "grain": "breath",
}

_ROLE_VOICE_FALLBACK = {
    "bass": "bowed",
    "counter": "choir",
    "color": "breath",
    "melody": "pluck",
    "sample": "sample_grain",
}

_logger = logging.getLogger(__name__)

_SENSOR_BOUNDS: dict[str, tuple[float, float]] = {
    "sensor_tempo_scale": (0.92, 1.08),
    "sensor_amp_scale": (0.80, 1.20),
    "sensor_brightness": (-1.0, 1.0),
}

_SENSOR_NEUTRAL: dict[str, float] = {
    "sensor_tempo_scale": 1.0,
    "sensor_amp_scale": 1.0,
    "sensor_brightness": 0.0,
}


def _clamp_sensor(name: str, value: float) -> float:
    lower, upper = _SENSOR_BOUNDS[name]
    clamped = round(max(lower, min(upper, value)), 4)
    if clamped != round(value, 4):
        _logger.warning("sensor %s clamped: %.4f -> %.4f", name, value, clamped)
    return clamped


@dataclass(frozen=True)
class ScheduledTrackerEvent:
    """One emitted event from a tracker scene."""

    song_title: str
    scene_name: str
    lane_name: str
    row: int
    voice: str
    role: str
    frequency_hz: float
    duration_seconds: float
    amplitude: float
    accent: bool
    sensor_tempo_scale: float = 1.0
    sensor_amp_scale: float = 1.0
    sensor_brightness: float = 0.0
    metadata: dict[str, str] = field(default_factory=dict)
    scene_metadata: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class ScheduleResult:
    """Runtime outcome for a scheduled scene or song."""

    completed: bool
    rows_processed: int
    events_emitted: int


def _apply_sensor_modulation(
    event: ScheduledTrackerEvent,
    sensor_values: dict[str, float],
) -> ScheduledTrackerEvent:
    return replace(
        event,
        sensor_tempo_scale=_clamp_sensor(
            "sensor_tempo_scale", sensor_values.get("sensor_tempo_scale", 1.0),
        ),
        sensor_amp_scale=_clamp_sensor(
            "sensor_amp_scale", sensor_values.get("sensor_amp_scale", 1.0),
        ),
        sensor_brightness=_clamp_sensor(
            "sensor_brightness", sensor_values.get("sensor_brightness", 0.0),
        ),
    )


def _row_duration_seconds(scene: TrackerScene) -> float:
    row_durations = metric_modulated_row_durations_seconds(scene)
    if row_durations:
        return row_durations[0]
    return 60.0 / scene.tempo_bpm / scene.rows_per_beat


def _voice_for_lane(lane: TrackerLane) -> str:
    if lane.voice in _VOICE_FALLBACK:
        return _VOICE_FALLBACK[lane.voice]
    if lane.voice:
        return lane.voice
    return _ROLE_VOICE_FALLBACK.get(lane.role, lane.voice)


def _amplitude_for_lane(role: str, velocity: float, accent: bool) -> float:
    base = _ROLE_GAIN.get(role, 0.09)
    amplitude = base * velocity
    if accent:
        amplitude *= 1.15
    return round(min(amplitude, 0.24), 3)


def build_scene_events(
    scene: TrackerScene,
    *,
    song_title: str = "CypherClaw Tracker",
) -> list[ScheduledTrackerEvent]:
    """Convert tracker steps into sorted runtime events."""

    patch_name = scene.metadata.get("patch_name", "")
    events: list[ScheduledTrackerEvent] = []
    lane_order = {lane.name: index for index, lane in enumerate(scene.pattern.lanes)}
    for lane in scene.pattern.lanes:
        voice = _voice_for_lane(lane)
        for step in lane.steps:
            octave_shift = step.octave_shift + role_octave_shift_for_patch(lane.role, patch_name)
            events.append(
                ScheduledTrackerEvent(
                    song_title=song_title,
                    scene_name=scene.name,
                    lane_name=lane.name,
                    row=step.row,
                    voice=voice,
                    role=lane.role,
                    frequency_hz=round(
                        _scale_degree_to_freq(scene.key, step.scale_degree, octave_shift),
                        3,
                    ),
                    duration_seconds=round(
                        metric_modulated_duration_seconds(
                            scene,
                            start_row=step.row,
                            length_rows=step.length_rows,
                        ),
                        4,
                    ),
                    amplitude=_amplitude_for_lane(lane.role, step.velocity, step.accent),
                    accent=step.accent,
                    metadata=dict(step.metadata),
                    scene_metadata=dict(scene.metadata),
                )
            )
    return sorted(
        events,
        key=lambda event: (event.row, lane_order.get(event.lane_name, 0), event.frequency_hz),
    )


def _active_lanes_at_row(scene: TrackerScene, row: int) -> list[str]:
    active: list[str] = []
    for lane in scene.pattern.lanes:
        if any(step.row <= row < (step.row + step.length_rows) for step in lane.steps):
            active.append(lane.name)
    return active


def _automation_lane_value_at_row(lane: object, row: int) -> float:
    default = float(getattr(lane, "default", 0.0) or 0.0)
    points = list(getattr(lane, "points", ()) or ())
    if not points:
        return round(default, 3)

    parsed: list[tuple[int, float]] = []
    for point_row, value in points:
        try:
            parsed.append((int(point_row), float(value)))
        except (TypeError, ValueError):
            continue
    if not parsed:
        return round(default, 3)

    parsed.sort(key=lambda point: point[0])
    if row <= parsed[0][0]:
        return round(parsed[0][1], 3)
    if row >= parsed[-1][0]:
        return round(parsed[-1][1], 3)

    for left, right in zip(parsed, parsed[1:]):
        left_row, left_value = left
        right_row, right_value = right
        if not (left_row <= row <= right_row):
            continue
        if right_row == left_row:
            return round(right_value, 3)
        position = (row - left_row) / (right_row - left_row)
        return round(left_value + ((right_value - left_value) * position), 3)
    return round(default, 3)


def _automation_values_at_row(scene: TrackerScene, row: int) -> dict[str, float]:
    return {
        str(lane.name): _automation_lane_value_at_row(lane, row)
        for lane in getattr(scene.pattern, "automation", ())
    }


def interpolate_automation_at_row(scene: TrackerScene, row: int) -> dict[str, float]:
    """Public API — return interpolated automation values for *row* in *scene*."""
    return _automation_values_at_row(scene, row)


def _event_gate_bucket(event: ScheduledTrackerEvent) -> int:
    seed = f"{event.scene_name}:{event.lane_name}:{event.row}:{event.frequency_hz:.3f}"
    return sum((index + 1) * ord(char) for index, char in enumerate(seed))


def _event_allowed_by_density(event: ScheduledTrackerEvent, density: float | None) -> bool:
    if density is None:
        return True
    if density >= 0.65:
        return True
    if event.role in {"bass", "melody", "rhythm"}:
        return True
    if density < 0.18:
        return False
    if event.accent and density >= 0.28:
        return True

    bucket = _event_gate_bucket(event)
    if density < 0.32:
        return bucket % 4 == 0
    if density < 0.48:
        return bucket % 3 != 0
    return bucket % 5 != 0


def _events_allowed_by_automation(
    events: list[ScheduledTrackerEvent],
    automation: dict[str, float],
) -> list[ScheduledTrackerEvent]:
    density = automation.get("density")
    return [event for event in events if _event_allowed_by_density(event, density)]


def _build_runtime_state(
    *,
    song_title: str,
    scene: TrackerScene,
    row: int,
    timestamp: float,
) -> dict:
    return {
        "timestamp": round(timestamp, 6),
        "song_title": song_title,
        "scene_name": scene.name,
        "key": scene.key,
        "tempo_bpm": scene.tempo_bpm,
        "rows_per_beat": scene.rows_per_beat,
        "total_rows": scene.pattern.rows,
        "row": row,
        "active_lanes": _active_lanes_at_row(scene, row),
        "automation": _automation_values_at_row(scene, row),
        "automation_curve": scene.metadata.get("arrangement_curve", ""),
        "scene_metadata": dict(scene.metadata),
    }


def _tmp_state_path(target: Path) -> Path:
    return target.with_name(f"{target.name}.{os.getpid()}.{time.time_ns()}.tmp")


def _write_runtime_state(path: str | Path, state: dict) -> None:
    target = Path(path)
    tmp = _tmp_state_path(target)
    tmp.write_text(json.dumps(state), encoding="utf-8")
    os.replace(str(tmp), str(target))


def write_delta_track(path: str | Path, entries: list[dict]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = _tmp_state_path(target)
    tmp.write_text(json.dumps(entries, indent=2), encoding="utf-8")
    os.replace(str(tmp), str(target))


def load_delta_track(path: str | Path) -> list[dict]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def replay_sensor_fn(delta_entries: list[dict]) -> Callable[[int], dict[str, float]]:
    by_row: dict[int, dict[str, float]] = {}
    for entry in delta_entries:
        row = entry["row"]
        if row not in by_row:
            by_row[row] = {
                "sensor_tempo_scale": entry["sensor_tempo_scale"],
                "sensor_amp_scale": entry["sensor_amp_scale"],
                "sensor_brightness": entry["sensor_brightness"],
            }
    return lambda row: dict(by_row.get(row, _SENSOR_NEUTRAL))


def schedule_scene(
    scene: TrackerScene,
    *,
    play_event: Callable[[ScheduledTrackerEvent], None],
    sleep_fn: Callable[[float], None] = time.sleep,
    stop_check: Callable[[int], bool] | None = None,
    state_path: str | Path = TRACKER_RUNTIME_STATE,
    time_fn: Callable[[], float] = time.time,
    song_title: str = "CypherClaw Tracker",
    on_row: Callable[[TrackerScene, int, dict], None] | None = None,
    sensor_fn: Callable[[int], dict[str, float]] | None = None,
    delta_track_path: str | Path | None = None,
) -> ScheduleResult:
    """Schedule one scene row by row."""

    if scene.pattern.rows <= 0:
        return ScheduleResult(completed=True, rows_processed=0, events_emitted=0)

    events = build_scene_events(scene, song_title=song_title)
    events_by_row: dict[int, list[ScheduledTrackerEvent]] = {}
    for event in events:
        events_by_row.setdefault(event.row, []).append(event)

    row_durations = metric_modulated_row_durations_seconds(scene)
    emitted = 0
    delta_entries: list[dict] = []

    for row in range(scene.pattern.rows):
        if stop_check is not None and stop_check(row):
            if delta_track_path is not None and delta_entries:
                write_delta_track(delta_track_path, delta_entries)
            return ScheduleResult(completed=False, rows_processed=row, events_emitted=emitted)

        state = _build_runtime_state(
            song_title=song_title,
            scene=scene,
            row=row,
            timestamp=time_fn(),
        )
        _write_runtime_state(state_path, state)
        if on_row is not None:
            on_row(scene, row, state)

        row_events = _events_allowed_by_automation(
            events_by_row.get(row, []),
            state.get("automation", {}),
        )

        sensor_values = sensor_fn(row) if sensor_fn is not None else _SENSOR_NEUTRAL
        for event in row_events:
            modulated = _apply_sensor_modulation(event, sensor_values)
            play_event(modulated)
            emitted += 1
            delta_entries.append({
                "row": modulated.row,
                "lane_name": modulated.lane_name,
                "sensor_tempo_scale": modulated.sensor_tempo_scale,
                "sensor_amp_scale": modulated.sensor_amp_scale,
                "sensor_brightness": modulated.sensor_brightness,
            })

        if row < scene.pattern.rows - 1:
            sleep_fn(row_durations[row])

    if delta_track_path is not None and delta_entries:
        write_delta_track(delta_track_path, delta_entries)

    return ScheduleResult(
        completed=True,
        rows_processed=scene.pattern.rows,
        events_emitted=emitted,
    )


def schedule_song(
    song: TrackerSong,
    *,
    play_event: Callable[[ScheduledTrackerEvent], None],
    sleep_fn: Callable[[float], None] = time.sleep,
    stop_check: Callable[[TrackerScene, int], bool] | None = None,
    state_path: str | Path = TRACKER_RUNTIME_STATE,
    time_fn: Callable[[], float] = time.time,
    on_scene_start: Callable[[TrackerScene, int], None] | None = None,
    on_row: Callable[[TrackerScene, int, dict], None] | None = None,
    sensor_fn: Callable[[int], dict[str, float]] | None = None,
    delta_track_path: str | Path | None = None,
) -> ScheduleResult:
    """Schedule a multi-scene tracker song."""

    rows_processed = 0
    events_emitted = 0

    for index, scene in enumerate(song.scenes):
        if on_scene_start is not None:
            on_scene_start(scene, index)

        scene_delta_path = None
        if delta_track_path is not None:
            base = Path(delta_track_path)
            scene_delta_path = base.with_name(f"{base.stem}_scene_{index}{base.suffix}")

        scene_result = schedule_scene(
            scene,
            play_event=play_event,
            sleep_fn=sleep_fn,
            stop_check=(
                None
                if stop_check is None
                else lambda row, current_scene=scene: stop_check(current_scene, row)
            ),
            state_path=state_path,
            time_fn=time_fn,
            song_title=song.title,
            on_row=on_row,
            sensor_fn=sensor_fn,
            delta_track_path=scene_delta_path,
        )
        rows_processed += scene_result.rows_processed
        events_emitted += scene_result.events_emitted
        if not scene_result.completed:
            return ScheduleResult(
                completed=False,
                rows_processed=rows_processed,
                events_emitted=events_emitted,
            )

    return ScheduleResult(
        completed=True,
        rows_processed=rows_processed,
        events_emitted=events_emitted,
    )


# ---------------------------------------------------------------------------
# Pbind-compatible serialization for Event → SuperCollider
# ---------------------------------------------------------------------------

_PBIND_KEY_MAP: dict[str, str] = {
    "event_id": "eventId",
    "phrase_id": "phraseId",
    "section_id": "sectionId",
    "voice_id": "voiceId",
    "role": "instrument",
    "pitch": "midinote",
    "nominal_beat": "nominalBeat",
    "nominal_dur_beats": "nominalDurBeats",
    "harmonic_charge": "harmonicCharge",
    "melodic_charge": "melodicCharge",
    "metric_weight": "metricWeight",
    "is_phrase_start": "phraseStart",
    "is_phrase_end": "phraseEnd",
    "is_cadential": "cadential",
    "intent_tag": "intentTag",
    "onset_sec": "start",
    "dur_sec": "dur",
    "velocity": "amp",
    "timing_deviation_ms": "timingOffset",
    "articulation": "articulation",
    "sensor_tempo_scale": "tempoScale",
    "sensor_amp_scale": "ampScale",
    "sensor_brightness": "brightness",
    "rule_stack": "ruleStack",
    "seed_path": "seedPath",
    "normalized_phrase_position": "phrasePosition",
    "normalized_section_position": "sectionPosition",
    "tempo_mult": "tempoMult",
    "amp_mult": "ampMult",
    "contour_apex": "contourApex",
    "contour_apex_index": "contourApexIndex",
    "is_contour_apex": "isContourApex",
    "metadata": "metadata",
}

_PBIND_KEY_REVERSE: dict[str, str] = {v: k for k, v in _PBIND_KEY_MAP.items()}

_PBIND_BOOL_FIELDS: frozenset[str] = frozenset(
    {"is_phrase_start", "is_phrase_end", "is_cadential", "is_contour_apex"}
)

_PBIND_JSON_FIELDS: frozenset[str] = frozenset(
    {"rule_stack", "seed_path", "metadata"}
)


def _pbind_encode(field_name: str, value: object) -> str | float | int:
    if field_name in _PBIND_BOOL_FIELDS:
        return 1 if value else 0
    if field_name in _PBIND_JSON_FIELDS:
        raw = list(value) if isinstance(value, tuple) else value
        return json.dumps(raw, separators=(",", ":"))
    if value is None:
        return ""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return value
    return str(value)


def _pbind_decode(field_name: str, value: str | float | int) -> Any:
    if field_name in _PBIND_BOOL_FIELDS:
        return bool(value)
    if field_name == "rule_stack":
        return json.loads(value) if isinstance(value, str) else []
    if field_name == "seed_path":
        return tuple(json.loads(value)) if isinstance(value, str) else ()
    if field_name == "metadata":
        return json.loads(value) if isinstance(value, str) else {}
    if field_name == "pitch":
        return None if value == "" else value
    if field_name == "contour_apex_index":
        return None if value == "" else int(value)
    return value


def event_to_pbind_dict(event: Event) -> dict[str, str | float | int]:
    """Serialize an Event into a flat Pbind-compatible dictionary.

    Keys use SC-idiomatic camelCase.  Complex fields (rule_stack, seed_path,
    metadata) are JSON-encoded strings so they survive OSC transport unchanged.
    """
    return {
        pbind_key: _pbind_encode(event_field, getattr(event, event_field))
        for event_field, pbind_key in _PBIND_KEY_MAP.items()
    }


def pbind_dict_to_event(payload: dict[str, str | float | int]) -> Event:
    """Reconstruct an Event from a Pbind dictionary produced by *event_to_pbind_dict*."""
    init_names = {f.name for f in dc_fields(Event) if f.init}
    kwargs: dict[str, Any] = {}
    for pbind_key, pbind_val in payload.items():
        event_field = _PBIND_KEY_REVERSE.get(pbind_key)
        if event_field is None or event_field not in init_names:
            continue
        kwargs[event_field] = _pbind_decode(event_field, pbind_val)
    return Event(**kwargs)
