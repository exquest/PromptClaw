"""Sample/DSP activity planning for live EMSD runtime."""
from __future__ import annotations

from typing import Any

from .sample_lab import SAMPLE_SOURCES, canonical_sample_source_name, sample_bank

ROOM_COMPOSITION_PHASES = {"Divination", "Emergence", "Convergence", "Crystallization"}


def _clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def _mode_for_transforms(sample_source: str, transforms: list[str], dsp_blocks: list[str]) -> str:
    transform_set = set(transforms)
    block_set = set(dsp_blocks)
    if "granular_cloud" in transform_set:
        return "grain_cloud"
    if sample_source == "theramini_in" and "slice_rearrange" in transform_set and "pitch_window" in transform_set:
        return "window_echo"
    if "slice_rearrange" in transform_set:
        return "slice_accents"
    if "spectral_freeze" in transform_set or "freeze_tail" in block_set:
        return "freeze_bed"
    if "lowpass_resample" in transform_set:
        return "lowpass_wash"
    return "texture_bed"


def _row_bucket(self_state: dict[str, Any]) -> str:
    """Return 'early', 'mid', or 'late' based on tracker row position."""
    raw_row = self_state.get("tracker_row")
    tracker_row = int(raw_row) if raw_row is not None else -1
    total_rows = int(self_state.get("tracker_total_rows", 0) or 0)
    if tracker_row < 0 or total_rows <= 0:
        return "mid"
    position = tracker_row / max(1, total_rows - 1) if total_rows > 1 else 0.5
    if position < 0.33:
        return "early"
    if position > 0.66:
        return "late"
    return "mid"


def _scene_profile(
    *,
    composer_state: dict[str, Any],
    self_state: dict[str, Any],
    sample_source: str,
    base_mode: str,
) -> tuple[str, str]:
    arc_phase = str(composer_state.get("arc_phase", "") or "")
    scene_name = str(self_state.get("tracker_scene_name", "") or "")
    bucket = _row_bucket(self_state)
    if scene_name == "Development" and sample_source in {"room_mic", "contact_mic"}:
        if bucket == "late":
            return "development_grains", "grain_cloud"
        return "development_grains", "grain_cloud"
    if scene_name in {"Recap", "Release"} and sample_source in {"room_mic", "theramini_in", "self_bus"}:
        if bucket == "late":
            return "afterglow_residue", "freeze_bed"
        return "recap_echo", "window_echo"
    if scene_name in {"Resolution", "Afterglow"}:
        return "afterglow_residue", "freeze_bed"
    if scene_name in {"Theme", "Emergence"} and sample_source in {"room_mic", "contact_mic"}:
        if bucket == "late":
            return "emergence_motion", "grain_cloud"
        return "theme_accents", "slice_accents"
    if arc_phase == "Divination":
        return "divination_bed", "freeze_bed"
    if arc_phase == "Emergence" and sample_source in {"room_mic", "contact_mic"}:
        return "emergence_motion", "grain_cloud"
    if arc_phase == "Conversation" and sample_source in {"theramini_in", "room_mic"}:
        return "conversation_echo", "window_echo"
    if arc_phase in {"Convergence", "Crystallization"}:
        return "afterglow_residue", "freeze_bed"
    return "generic", base_mode


def _render_targets(
    *,
    scene_profile: str,
    activity_mode: str,
    sample_density: float,
    buffer_seconds: float,
    cadence_name: str,
    lowpass_hz: float,
    stretch_ratio: float,
) -> dict[str, float]:
    render_duration_s = 2.2
    peak_target = _clamp(0.12 + sample_density * 0.18, 0.10, 0.22)
    density_scale = 1.0
    reverse_probability = 0.0
    adjusted_lowpass = lowpass_hz
    adjusted_stretch = stretch_ratio

    if activity_mode == "freeze_bed":
        render_duration_s = 3.6 + buffer_seconds * 0.04
        peak_target = _clamp(0.11 + sample_density * 0.12, 0.10, 0.18)
    elif activity_mode == "grain_cloud":
        render_duration_s = 2.3 + sample_density * 1.3
        peak_target = _clamp(0.14 + sample_density * 0.16, 0.12, 0.22)
    elif activity_mode in {"slice_accents", "window_echo"}:
        render_duration_s = 2.0 + sample_density * 0.9
        peak_target = _clamp(0.15 + sample_density * 0.12, 0.12, 0.22)

    if scene_profile == "development_grains":
        render_duration_s = max(render_duration_s, 2.8)
        peak_target = max(peak_target, 0.19)
        density_scale = 1.3
        reverse_probability = 0.18
        adjusted_lowpass = max(adjusted_lowpass, 2800.0)
    elif scene_profile == "emergence_motion":
        render_duration_s = max(render_duration_s, 2.6)
        peak_target = max(peak_target, 0.17)
        density_scale = 1.15
        adjusted_lowpass = max(adjusted_lowpass, 2600.0)
    elif scene_profile == "theme_accents":
        render_duration_s = max(render_duration_s, 2.1)
        peak_target = max(peak_target, 0.16)
    elif scene_profile in {"afterglow_residue", "divination_bed"}:
        render_duration_s = max(render_duration_s, 4.6 if scene_profile == "afterglow_residue" else 4.2)
        peak_target = min(peak_target, 0.14 if scene_profile == "afterglow_residue" else 0.13)
        adjusted_stretch = max(adjusted_stretch, 1.5 if cadence_name != "sleep" else 1.8)
        adjusted_lowpass = max(adjusted_lowpass, 1600.0 if cadence_name in {"sleep", "wind_down"} else 2200.0)
    elif scene_profile in {"recap_echo", "conversation_echo"}:
        render_duration_s = max(render_duration_s, 2.8 if scene_profile == "recap_echo" else 3.0)
        peak_target = min(max(peak_target, 0.16), 0.2)
        adjusted_lowpass = max(adjusted_lowpass, 2400.0)

    return {
        "render_duration_s": round(render_duration_s, 2),
        "peak_target": round(peak_target, 3),
        "density_scale": round(density_scale, 3),
        "reverse_probability": round(reverse_probability, 2),
        "lowpass_hz": round(adjusted_lowpass, 1),
        "stretch_ratio": round(adjusted_stretch, 2),
    }


def _capture_is_ready(meta: dict[str, Any], refresh_seconds: int) -> bool:
    exists = bool(meta.get("exists", False))
    age_seconds = meta.get("age_seconds")
    if age_seconds is None and not exists:
        return False
    return exists and float(age_seconds or 0.0) <= (refresh_seconds * 1.5)


def _bank_capture_is_ready(meta: dict[str, Any], source_name: str) -> bool:
    try:
        bank = sample_bank(source_name)
    except KeyError:
        return False
    exists = bool(meta.get("exists", False))
    age_seconds = meta.get("age_seconds")
    if age_seconds is None and not exists:
        return False
    return exists and float(age_seconds or 0.0) <= bank.freshness_seconds


def _transport_trigger(
    *,
    scene_name: str,
    activity_mode: str,
    tracker_row: int,
    rows_per_beat: int,
) -> tuple[bool, str, int]:
    if tracker_row < 0 or rows_per_beat <= 0:
        return False, "", 0
    bar_rows = max(1, rows_per_beat * 4)
    if activity_mode == "slice_accents":
        quantum_rows = max(1, rows_per_beat)
    elif activity_mode == "grain_cloud":
        quantum_rows = max(1, rows_per_beat * 2)
    elif activity_mode == "window_echo":
        quantum_rows = bar_rows
    elif activity_mode == "freeze_bed":
        quantum_rows = bar_rows * 2
    elif activity_mode == "lowpass_wash":
        quantum_rows = bar_rows
    else:
        quantum_rows = bar_rows
    trigger_now = tracker_row == 0 or (tracker_row % quantum_rows) == 0
    trigger_key = f"{scene_name or 'scene'}:{activity_mode}:{tracker_row // quantum_rows}"
    return trigger_now, trigger_key, quantum_rows


def _resolve_capture_source(
    *,
    requested_source: str,
    requested_path: str,
    capture_meta: dict[str, Any],
    capture_registry: dict[str, dict[str, Any]],
) -> tuple[str, str, dict[str, Any]]:
    requested_bank_name = canonical_sample_source_name(requested_source)
    requested_def = SAMPLE_SOURCES.get(requested_bank_name)
    if requested_def is not None and _bank_capture_is_ready(capture_meta, requested_bank_name):
        return requested_bank_name, requested_path, capture_meta

    fallback_sources = sample_bank(requested_bank_name).fallback_sources if requested_def is not None else ()
    for fallback_source in fallback_sources:
        fallback_meta = dict(capture_registry.get(fallback_source, {}))
        fallback_def = SAMPLE_SOURCES.get(fallback_source)
        if fallback_def is None:
            continue
        fallback_meta.setdefault("path", fallback_def.capture_path)
        if _bank_capture_is_ready(fallback_meta, fallback_source):
            return fallback_source, str(fallback_meta["path"]), fallback_meta

    return requested_bank_name, requested_path, capture_meta


def _room_capture_meta(
    *,
    requested_source: str,
    capture_registry: dict[str, dict[str, Any]],
    capture_meta: dict[str, Any],
) -> dict[str, Any]:
    if requested_source == "room_mic":
        return dict(capture_meta)
    room_meta = dict(capture_registry.get("room_mic", {}))
    room_def = SAMPLE_SOURCES.get("room_mic")
    if room_def is not None:
        room_meta.setdefault("path", room_def.capture_path)
    return room_meta


def _prefer_room_mic(
    *,
    requested_source: str,
    composer_state: dict[str, Any],
    cadence_state: dict[str, Any],
    capture_registry: dict[str, dict[str, Any]],
    capture_meta: dict[str, Any],
) -> bool:
    if requested_source != "self_bus":
        return False
    if str(cadence_state.get("cadence_state", "")) == "away_practice":
        return False
    arc_phase = str(composer_state.get("arc_phase", "") or "")
    if arc_phase and arc_phase not in ROOM_COMPOSITION_PHASES:
        return False
    sample_density = float(composer_state.get("sample_density", 0.0) or 0.0)
    if sample_density > 0.38:
        return False
    room_meta = _room_capture_meta(
        requested_source=requested_source,
        capture_registry=capture_registry,
        capture_meta=capture_meta,
    )
    room_def = SAMPLE_SOURCES.get("room_mic")
    return room_def is not None and _capture_is_ready(room_meta, room_def.refresh_seconds)


def build_sample_dsp_activity(
    *,
    timestamp: float,
    composer_state: dict[str, Any],
    cadence_state: dict[str, Any],
    self_state: dict[str, Any],
    sensor_states: dict[str, dict[str, Any]] | None = None,
    capture_meta: dict[str, Any] | None = None,
    capture_registry: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build one concrete sample/DSP activity plan from live state."""

    sensor_states = sensor_states or {}
    capture_meta = capture_meta or {}
    capture_registry = capture_registry or {}
    raw_sample_source = str(composer_state.get("sample_source", ""))
    sample_source = canonical_sample_source_name(raw_sample_source)
    capture_path = str(composer_state.get("sample_capture_path", ""))
    refresh_seconds = int(composer_state.get("sample_refresh_seconds", 60) or 60)
    transforms = [str(value) for value in composer_state.get("sample_transforms", [])]
    dsp_blocks = [str(value) for value in composer_state.get("dsp_blocks", [])]
    sample_density = float(composer_state.get("sample_density", 0.0) or 0.0)
    buffer_seconds = float(composer_state.get("sample_buffer_seconds", 0.0) or 0.0)
    trigger_threshold = float(composer_state.get("sample_trigger_threshold", 0.0) or 0.0)

    requested_source = raw_sample_source or sample_source
    resolved_request = requested_source
    if _prefer_room_mic(
        requested_source=requested_source,
        composer_state=composer_state,
        cadence_state=cadence_state,
        capture_registry=capture_registry,
        capture_meta=capture_meta,
    ):
        resolved_request = "room_mic"
        room_meta = _room_capture_meta(
            requested_source=sample_source,
            capture_registry=capture_registry,
            capture_meta=capture_meta,
        )
        capture_meta = room_meta
        capture_path = str(room_meta.get("path", SAMPLE_SOURCES["room_mic"].capture_path))
    sample_source, capture_path, active_capture_meta = _resolve_capture_source(
        requested_source=resolved_request,
        requested_path=capture_path,
        capture_meta=capture_meta,
        capture_registry=capture_registry,
    )
    requested_bank_name = canonical_sample_source_name(resolved_request)
    source_refresh = SAMPLE_SOURCES.get(sample_source)
    if source_refresh is not None:
        refresh_seconds = source_refresh.refresh_seconds
    age_seconds = active_capture_meta.get("age_seconds")
    capture_ready = _capture_is_ready(active_capture_meta, refresh_seconds)

    room_activity = sensor_states.get("room_activity", {})
    room_speech = sensor_states.get("room_speech", {})
    theramini = sensor_states.get("theramini", {})

    source_trigger = False
    if sample_source == "room_mic":
        source_trigger = bool(room_activity.get("recent_transient") or room_speech.get("speech_detected"))
    elif sample_source == "contact_mic":
        source_trigger = bool(
            room_activity.get("recent_transient")
            or room_activity.get("activity_level") in {"active", "moderate"}
        )
    elif sample_source == "theramini_in":
        source_trigger = bool(theramini.get("is_playing"))
    elif sample_source == "self_bus":
        source_trigger = bool(self_state.get("is_playing") and not self_state.get("has_clicks"))
    elif sample_source == "garden_mic":
        source_trigger = cadence_state.get("cadence_state") not in {"sleep", "wind_down"}

    self_rms = float(self_state.get("rms", 0.0) or 0.0)
    loud_enough = True
    if sample_source == "self_bus":
        loud_enough = self_rms >= max(0.01, trigger_threshold * 0.15)
    trigger_now = bool(capture_ready and source_trigger and loud_enough)
    tracker_scene_name = str(self_state.get("tracker_scene_name", "") or "")
    tracker_row = int(self_state.get("tracker_row", -1) or -1)
    tracker_rows_per_beat = int(self_state.get("tracker_rows_per_beat", 0) or 0)

    cadence_name = str(cadence_state.get("cadence_state", "") or "")
    activity_mode = _mode_for_transforms(sample_source, transforms, dsp_blocks)
    scene_profile, activity_mode = _scene_profile(
        composer_state=composer_state,
        self_state=self_state,
        sample_source=sample_source,
        base_mode=activity_mode,
    )
    transport_trigger_now, transport_trigger_key, transport_quantum_rows = _transport_trigger(
        scene_name=tracker_scene_name,
        activity_mode=activity_mode,
        tracker_row=tracker_row,
        rows_per_beat=tracker_rows_per_beat,
    )
    wet_mix = _clamp(0.16 + sample_density * 0.42 + len(dsp_blocks) * 0.03, 0.0, 0.85)
    if not capture_ready:
        wet_mix *= 0.35
    elif trigger_now:
        wet_mix = _clamp(wet_mix + 0.08, 0.0, 0.9)

    grain_density_hz = 0.0
    if activity_mode in {"grain_cloud", "slice_accents", "window_echo"}:
        grain_density_hz = round(_clamp(sample_density * 18.0, 0.0, 12.0), 2)
    stretch_ratio = 1.0
    if "stretch" in transforms or "spectral_freeze" in transforms:
        stretch_ratio = round(_clamp(1.0 + buffer_seconds / 24.0, 1.0, 2.25), 2)
    lowpass_hz = 0.0
    if "lowpass_resample" in transforms or cadence_name in {"sleep", "wind_down"}:
        lowpass_hz = 1800.0 if cadence_name == "sleep" else 2600.0
    pitch_window_semitones = 3 if "pitch_window" in transforms else 0
    reverse_probability = round(0.24 if "reverse_accents" in transforms else 0.0, 2)
    render_targets = _render_targets(
        scene_profile=scene_profile,
        activity_mode=activity_mode,
        sample_density=sample_density,
        buffer_seconds=buffer_seconds,
        cadence_name=cadence_name,
        lowpass_hz=lowpass_hz,
        stretch_ratio=stretch_ratio,
    )
    grain_density_hz = round(
        _clamp(grain_density_hz * float(render_targets["density_scale"]), 0.0, 12.0),
        2,
    )
    reverse_probability = max(reverse_probability, float(render_targets["reverse_probability"]))

    return {
        "timestamp": round(float(timestamp), 3),
        "requested_sample_source": requested_source,
        "sample_bank": requested_bank_name,
        "sample_source": sample_source,
        "capture_path": capture_path,
        "capture_ready": capture_ready,
        "capture_age_s": None if age_seconds is None else round(float(age_seconds), 2),
        "scene_profile": scene_profile,
        "activity_mode": activity_mode,
        "trigger_now": trigger_now,
        "transport_trigger_now": bool(capture_ready and transport_trigger_now),
        "transport_trigger_key": transport_trigger_key,
        "transport_quantum_rows": transport_quantum_rows,
        "tracker_scene_name": tracker_scene_name,
        "tracker_row": tracker_row,
        "wet_mix": round(wet_mix, 3),
        "grain_density_hz": grain_density_hz,
        "stretch_ratio": float(render_targets["stretch_ratio"]),
        "lowpass_hz": float(render_targets["lowpass_hz"]),
        "pitch_window_semitones": pitch_window_semitones,
        "reverse_probability": reverse_probability,
        "render_duration_s": float(render_targets["render_duration_s"]),
        "peak_target": float(render_targets["peak_target"]),
        "dsp_blocks": dsp_blocks,
        "sample_transforms": transforms,
        "sample_density": round(sample_density, 3),
        "buffer_seconds": round(buffer_seconds, 2),
        "source_freshness_s": sample_bank(sample_source).freshness_seconds if sample_source in SAMPLE_SOURCES else 0,
        "fallback_sources": list(sample_bank(requested_bank_name).fallback_sources)
        if requested_bank_name in SAMPLE_SOURCES
        else [],
    }
