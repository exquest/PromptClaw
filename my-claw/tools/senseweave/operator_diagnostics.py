"""Operator-facing SenseWeave diagnostics from live authority files."""
from __future__ import annotations

import json
import math
import time
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .rollout_controls import SenseWeaveFeatureFlags, load_feature_flags
from .sample_status import sample_status_text


_PRODUCTION_COURSE_KEYS: tuple[str, ...] = (
    "phase_profile",
    "mode_scale",
    "harmonic_function",
    "meter_groove",
    "genre_strategy",
    "mix_role",
    "spatial_intent",
)

_PRODUCTION_DISPLAY_LABELS: dict[str, str] = {
    "phase_profile": "phase",
    "mode_scale": "scale",
    "harmonic_function": "harmonic",
    "meter_groove": "groove",
    "genre_strategy": "strategy",
    "mix_role": "mix",
    "spatial_intent": "spatial",
}

_DEFAULT_CRITIQUE_THRESHOLDS: dict[str, tuple[str, float]] = {
    "underdeveloped_score": ("max", 0.7),
    "static_score": ("max", 0.7),
    "development_score": ("min", 0.25),
    "hook_clarity": ("min", 0.2),
}

_AGGREGATE_INTENTION_KEYS: tuple[str, ...] = (
    "global_energy",
    "global_restraint",
    "global_brightness",
)


def generation_status(path: Path | None = None) -> dict[str, object]:
    """Read and format generation status for face/inkplate."""
    status_path = path or Path("/tmp/generation_status.json")
    try:
        raw = json.loads(status_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError, UnicodeDecodeError):
        raw = {}

    if not isinstance(raw, dict):
        raw = {}

    try:
        queue_depth = int(raw.get("queue_depth", 0))
    except (TypeError, ValueError):
        queue_depth = 0

    is_generating = bool(raw.get("is_generating", False))

    status: dict[str, object] = {
        "queue_depth": queue_depth,
        "is_generating": is_generating,
    }

    if queue_depth > 1:
        status["caption"] = f"♫ queued: {queue_depth}"
    elif queue_depth == 1 or is_generating:
        status["caption"] = "♫ generating"
    else:
        status["caption"] = "♫ ready"

    return status


@dataclass(frozen=True)
class DiagnosticPaths:
    """Paths that make up the live SenseWeave diagnostic surface."""

    score_tree: Path = Path("/tmp/current_score_tree.json")
    tracker_runtime: Path = Path("/tmp/tracker_runtime_state.json")
    composer_state: Path = Path("/tmp/composer_state.json")
    sample_activity: Path = Path("/tmp/sample_dsp_activity.json")
    sample_playback: Path = Path("/tmp/sample_playback_state.json")
    master_bus: Path = Path("/tmp/master_bus_state.json")
    self_listener: Path = Path("/tmp/self_listen.json")
    theramini: Path = Path("/tmp/theramini_state.json")


@dataclass(frozen=True)
class OperatorDiagnostics:
    """Compact status payload for Telegram and operator displays."""

    score_tree: str
    section_function: str
    arrangement_curve: str
    ear_metrics: str
    sample_source: str
    master_bus: str
    self_listener: str
    flags: SenseWeaveFeatureFlags
    production_course: str = "unavailable"
    theramini_relation: str = "unavailable"
    critique_notes: str = "unavailable"
    aggregate_intentions: dict[str, float] | str = "unavailable"
    sampler_metrics: str = "unavailable"

    def to_status_dict(self) -> dict[str, object]:
        """Return a JSON-like dictionary for daemon status snapshots."""
        return {
            "score_tree": self.score_tree,
            "section_function": self.section_function,
            "arrangement_curve": self.arrangement_curve,
            "ear_metrics": self.ear_metrics,
            "sample_source": self.sample_source,
            "master_bus": self.master_bus,
            "self_listener": self.self_listener,
            "production_course": self.production_course,
            "theramini_relation": self.theramini_relation,
            "critique_notes": self.critique_notes,
            "aggregate_intentions": self.aggregate_intentions,
            "sampler_metrics": self.sampler_metrics,
            "flags": self.flags.to_status_dict(),
        }


def _read_json(path: Path) -> dict[str, Any]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError, UnicodeDecodeError):
        return {}
    return dict(raw) if isinstance(raw, Mapping) else {}


def _float(value: object, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _label(value: object) -> str:
    return str(value or "").replace("_", " ").strip()


def _score_tree_status(score_tree: Mapping[str, Any], composer_state: Mapping[str, Any]) -> str:
    if not score_tree:
        title = str(composer_state.get("song_title", "") or "").strip()
        score_tree_id = str(composer_state.get("score_tree_id", "") or "").strip()
        if title or score_tree_id:
            return f"{title or 'untitled'} ({score_tree_id or 'unknown id'})"
        return "unknown"

    title = str(score_tree.get("title", "") or "untitled").strip()
    piece_id = str(score_tree.get("piece_id", "") or "unknown id").strip()
    commission = score_tree.get("commission", {})
    form_class = ""
    composition_mode = ""
    if isinstance(commission, Mapping):
        form_class = str(commission.get("form_class", "") or "").strip()
        composition_mode = str(commission.get("composition_mode", "") or "").strip()
    sections = score_tree.get("sections", ())
    section_count = len(sections) if isinstance(sections, list) else 0
    form_text = "/".join(part for part in (form_class, composition_mode) if part)
    detail = f"{piece_id}"
    if form_text:
        detail += f", {form_text}"
    if section_count:
        detail += f", {section_count} sections"
    return f"{title} ({detail})"


def _section_function_status(
    tracker_runtime: Mapping[str, Any],
    composer_state: Mapping[str, Any],
) -> str:
    metadata = tracker_runtime.get("scene_metadata", {})
    if isinstance(metadata, Mapping):
        section_function = str(metadata.get("section_function", "") or "").strip()
        if section_function:
            return section_function
    caption = str(composer_state.get("scene_caption", "") or "").strip()
    if caption:
        return caption
    movement = str(composer_state.get("movement", "") or "").strip()
    return movement or "unknown"


def _automation_summary(automation: object) -> str:
    if not isinstance(automation, Mapping):
        return ""
    parts: list[str] = []
    for key in ("density", "master_amp", "reverb_send"):
        if key not in automation:
            continue
        parts.append(f"{key}={_float(automation[key]):.2f}".rstrip("0").rstrip("."))
    return " ".join(parts)


def _arrangement_curve_status(
    tracker_runtime: Mapping[str, Any],
    composer_state: Mapping[str, Any],
) -> str:
    curve = str(
        tracker_runtime.get("automation_curve", "")
        or composer_state.get("section_curve", "")
        or ""
    ).strip()
    summary = _automation_summary(tracker_runtime.get("automation") or composer_state.get("automation_values"))
    if curve and summary:
        return f"{curve} {summary}"
    return curve or summary or "unknown"


def _ear_metrics_status(composer_state: Mapping[str, Any]) -> str:
    metrics = composer_state.get("ear_metrics", {})
    if not isinstance(metrics, Mapping) or not metrics:
        return "unavailable"
    fields = (
        ("hook", "hook_clarity"),
        ("cadence", "cadence_strength"),
        ("development", "development_score"),
        ("static", "static_score"),
    )
    parts = [
        f"{label}={_float(metrics[key]):.2f}".rstrip("0").rstrip(".")
        for label, key in fields
        if key in metrics
    ]
    return " ".join(parts) if parts else "unavailable"


def _sample_source_status(
    sample_activity: Mapping[str, Any],
    sample_playback: Mapping[str, Any],
    self_listener: Mapping[str, Any],
    composer_state: Mapping[str, Any],
) -> str:
    status = sample_status_text(
        dict(sample_activity),
        dict(sample_playback),
        dict(self_listener),
        combine_activity_and_playback=True,
    )
    if status:
        return status
    composer_source = _label(composer_state.get("sample_source", ""))
    return composer_source or "unavailable"


def _master_bus_status(
    master_bus: Mapping[str, Any],
    composer_state: Mapping[str, Any],
    *,
    now: float,
) -> str:
    values = composer_state.get("master_bus", {})
    has_values = isinstance(values, Mapping) and bool(values)
    timestamp = _float(master_bus.get("timestamp") or master_bus.get("updated"), 0.0)
    healthy = timestamp > 0.0 and (now - timestamp) < 10.0
    if not has_values and not master_bus:
        return "unknown"

    state = "alive" if healthy else "stale" if master_bus else "unknown"
    value_parts: list[str] = []
    if isinstance(values, Mapping):
        for key in ("amp", "drive", "warmth", "reverb", "room"):
            if key in values:
                value_parts.append(f"{key}={_float(values[key]):.2f}".rstrip("0").rstrip("."))
    suffix = " ".join(value_parts)
    return f"{state} {suffix}".strip()


def _self_listener_status(self_listener: Mapping[str, Any], *, now: float) -> str:
    if not self_listener:
        return "unavailable"
    error = str(self_listener.get("error", "") or "").strip()
    timestamp = _float(self_listener.get("timestamp"), 0.0)
    fresh = timestamp <= 0.0 or (now - timestamp) < 10.0
    state = "offline" if error else "live" if fresh else "stale"
    rms = _float(self_listener.get("rms", self_listener.get("amplitude", 0.0)))
    backend = _label(self_listener.get("capture_backend", ""))
    port = str(self_listener.get("capture_port", "") or "").strip()
    parts = [state, f"rms={rms:.2f}".rstrip("0").rstrip(".")]
    if backend:
        parts.append(f"backend={backend}")
    if port:
        parts.append(f"port={port}")
    if error:
        parts.append(f"error={error}")
    return " ".join(parts)


def _production_course_from_metadata(metadata: Mapping[str, Any]) -> dict[str, str]:
    """Extract production_* keys from scene_metadata."""
    course: dict[str, str] = {}
    for key in _PRODUCTION_COURSE_KEYS:
        value = str(metadata.get(f"production_{key}", "") or "").strip()
        if value:
            course[key] = value
    return course


def _production_course_from_score_tree(
    score_tree: Mapping[str, Any],
    tracker_runtime: Mapping[str, Any],
) -> dict[str, str]:
    """Extract production_course from score_tree current section."""
    scene_name = str(tracker_runtime.get("scene_name", "") or "").strip()
    sections = score_tree.get("sections", ())
    if not isinstance(sections, list) or not sections:
        return {}
    target = None
    if scene_name:
        for section in sections:
            if isinstance(section, Mapping) and str(section.get("scene_name", "")) == scene_name:
                target = section
                break
    if target is None:
        target = sections[0]
    pc = target.get("production_course", {}) if isinstance(target, Mapping) else {}
    if not isinstance(pc, Mapping):
        return {}
    return {
        key: str(pc[key])
        for key in _PRODUCTION_COURSE_KEYS
        if key in pc and str(pc[key]).strip()
    }


def _production_course_status(
    tracker_runtime: Mapping[str, Any],
    score_tree: Mapping[str, Any],
    composer_state: Mapping[str, Any],
) -> str:
    metadata = tracker_runtime.get("scene_metadata", {})
    if not isinstance(metadata, Mapping):
        metadata = {}
    course = _production_course_from_metadata(metadata)
    if not course:
        course = _production_course_from_score_tree(score_tree, tracker_runtime)
    if not course and composer_state:
        arc_phase = str(composer_state.get("arc_phase", "") or "").strip()
        if arc_phase:
            course["phase_profile"] = arc_phase
    if not course:
        return "unavailable"
    parts = [
        f"{_PRODUCTION_DISPLAY_LABELS[key]}={_label(course[key])}"
        for key in _PRODUCTION_COURSE_KEYS
        if key in course
    ]
    return " ".join(parts) if parts else "unavailable"


def _theramini_relation_status(
    tracker_runtime: Mapping[str, Any],
    score_tree: Mapping[str, Any],
    theramini: Mapping[str, Any],
) -> str:
    metadata = tracker_runtime.get("scene_metadata", {})
    if not isinstance(metadata, Mapping):
        metadata = {}
    relation = str(metadata.get("production_counterpoint_relation", "") or "").strip()
    if not relation:
        sections = score_tree.get("sections", ())
        scene_name = str(tracker_runtime.get("scene_name", "") or "").strip()
        if isinstance(sections, list):
            for section in sections:
                if not isinstance(section, Mapping):
                    continue
                if scene_name and str(section.get("scene_name", "")) != scene_name:
                    continue
                pc = section.get("production_course", {})
                if isinstance(pc, Mapping):
                    relation = str(pc.get("counterpoint_relation", "") or "").strip()
                break
    if not relation and not theramini:
        return "unavailable"
    relation_display = _label(relation) if relation else ""
    is_playing = bool(theramini.get("is_playing") or theramini.get("playing"))
    note_name = str(theramini.get("note_name", "") or "").strip()
    if is_playing:
        playing_text = f"playing {note_name}" if note_name else "playing"
        if relation_display:
            return f"{relation_display} ({playing_text})"
        return playing_text
    if relation_display:
        return relation_display
    return "unavailable"


def _critique_notes_status(composer_state: Mapping[str, Any]) -> str:
    metrics = composer_state.get("ear_metrics", {})
    if not isinstance(metrics, Mapping) or not metrics:
        return "unavailable"
    failures: list[str] = []
    for metric_name, (direction, threshold) in _DEFAULT_CRITIQUE_THRESHOLDS.items():
        if metric_name not in metrics:
            continue
        value = _float(metrics[metric_name])
        if direction == "min" and value < threshold:
            failures.append(f"{metric_name}<{threshold}")
        elif direction == "max" and value > threshold:
            failures.append(f"{metric_name}>{threshold}")
    if failures:
        return "flagged: " + " ".join(failures)
    has_any = any(m in metrics for m in _DEFAULT_CRITIQUE_THRESHOLDS)
    return "passing" if has_any else "unavailable"


def _bounded_intention_value(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return round(min(1.0, max(0.0, number)), 3)


def _aggregate_intentions_status(
    *states: Mapping[str, Any],
) -> dict[str, float] | str:
    for state in states:
        candidate = state.get("aggregate_intentions")
        if not isinstance(candidate, Mapping):
            continue
        intentions: dict[str, float] = {}
        for key in _AGGREGATE_INTENTION_KEYS:
            value = _bounded_intention_value(candidate.get(key))
            if value is None:
                break
            intentions[key] = value
        else:
            return intentions
    return "unavailable"


def _sampler_metrics_status(composer_state: Mapping[str, Any]) -> str:
    """Format sampler-CI metrics (event count, library:self ratio) for operators."""
    has_count = "sampler_event_count_per_piece" in composer_state
    has_ratio = "sampler_library_vs_self_ratio" in composer_state
    if not has_count and not has_ratio:
        return "unavailable"

    parts: list[str] = []
    if has_count:
        count = _float(composer_state["sampler_event_count_per_piece"], math.nan)
        parts.append("events/piece=?" if math.isnan(count) else f"events/piece={int(count)}")
    if has_ratio:
        ratio = _float(composer_state["sampler_library_vs_self_ratio"], math.nan)
        if math.isnan(ratio):
            parts.append("library:self=?")
        elif math.isinf(ratio):
            parts.append("library:self=inf out-of-band")
        else:
            band = "ok" if 1.5 <= ratio <= 3.0 else "out-of-band"
            parts.append(f"library:self={ratio:.2f} {band}")
    return " ".join(parts)


def collect_operator_diagnostics(
    *,
    paths: DiagnosticPaths | None = None,
    now: float | None = None,
    flags: SenseWeaveFeatureFlags | None = None,
) -> OperatorDiagnostics:
    """Collect operator diagnostics from SenseWeave authority files."""
    active_paths = paths or DiagnosticPaths()
    current_time = time.time() if now is None else now
    score_tree = _read_json(active_paths.score_tree)
    tracker_runtime = _read_json(active_paths.tracker_runtime)
    composer_state = _read_json(active_paths.composer_state)
    sample_activity = _read_json(active_paths.sample_activity)
    sample_playback = _read_json(active_paths.sample_playback)
    master_bus = _read_json(active_paths.master_bus)
    self_listener = _read_json(active_paths.self_listener)
    theramini = _read_json(active_paths.theramini)

    return OperatorDiagnostics(
        score_tree=_score_tree_status(score_tree, composer_state),
        section_function=_section_function_status(tracker_runtime, composer_state),
        arrangement_curve=_arrangement_curve_status(tracker_runtime, composer_state),
        ear_metrics=_ear_metrics_status(composer_state),
        sample_source=_sample_source_status(sample_activity, sample_playback, self_listener, composer_state),
        master_bus=_master_bus_status(master_bus, composer_state, now=current_time),
        self_listener=_self_listener_status(self_listener, now=current_time),
        flags=flags or load_feature_flags(),
        production_course=_production_course_status(tracker_runtime, score_tree, composer_state),
        theramini_relation=_theramini_relation_status(tracker_runtime, score_tree, theramini),
        critique_notes=_critique_notes_status(composer_state),
        aggregate_intentions=_aggregate_intentions_status(tracker_runtime, composer_state),
        sampler_metrics=_sampler_metrics_status(composer_state),
    )
