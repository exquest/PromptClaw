"""Human-readable sample-layer status text."""
from __future__ import annotations

from collections.abc import Mapping


def _label(name: str) -> str:
    return name.replace("_", " ").strip()


def _source_text(requested: str, actual: str) -> str:
    if requested and actual and requested != actual:
        return f"{requested} via {actual}"
    return actual or requested or "sample"


def _legacy_activity_phrase(activity: Mapping[str, object]) -> str:
    requested = _label(str(activity.get("requested_sample_source", "")))
    actual = _label(str(activity.get("sample_source", "")))
    mode = _label(str(activity.get("activity_mode", ""))).strip()
    if not bool(activity.get("capture_ready")):
        return f"{requested or actual or 'sample'} not ready"
    source_text = _source_text(requested, actual)
    if bool(activity.get("trigger_now")):
        return f"sampling {source_text} · {mode}".strip()
    return f"holding {source_text} · {mode}".strip()


def _legacy_playback_phrase(playback_state: Mapping[str, object]) -> str:
    requested = _label(str(playback_state.get("requested_sample_source", "")))
    actual = _label(str(playback_state.get("sample_source", "")))
    mode = _label(str(playback_state.get("mode", ""))).strip()
    return f"playing {_source_text(requested, actual)} · {mode}".strip()


def _activity_phrase(activity: Mapping[str, object], *, include_mode: bool) -> str:
    requested = _label(str(activity.get("requested_sample_source", "")))
    actual = _label(str(activity.get("sample_source", "")))
    mode = _label(str(activity.get("activity_mode", ""))).strip()
    source_text = _source_text(requested, actual)
    if not bool(activity.get("capture_ready")):
        return f"{requested or actual or 'sample'} not ready"
    if bool(activity.get("trigger_now")):
        if include_mode and mode:
            return f"currently sampling {source_text} · {mode}"
        return f"currently sampling {source_text}"
    if include_mode and mode:
        return f"holding {source_text} · {mode}"
    return f"holding {source_text}"


def _playback_phrase(playback_state: Mapping[str, object]) -> str:
    if not bool(playback_state.get("playing")):
        return ""
    actual = _label(str(playback_state.get("sample_source", "")))
    requested = _label(str(playback_state.get("requested_sample_source", "")))
    mode = _label(str(playback_state.get("mode", ""))).strip()
    source_text = actual or requested or "sample"
    if mode and source_text:
        return f"playing sample {mode} from source {source_text}"
    if mode:
        return f"playing sample {mode}"
    return f"playing sample from source {source_text}"


def sample_status_text(
    activity: Mapping[str, object] | None,
    playback_state: Mapping[str, object] | None = None,
    monitor_state: Mapping[str, object] | None = None,
    *,
    combine_activity_and_playback: bool = False,
) -> str:
    if not combine_activity_and_playback:
        if not activity:
            return ""
        playback_state = playback_state or {}
        monitor_state = monitor_state or {}
        if bool(playback_state.get("playing")):
            playback_text = _legacy_playback_phrase(playback_state)
            if str(monitor_state.get("error", "") or "") == "no_capture":
                return f"monitor offline · {playback_text.removeprefix('playing ')}".strip()
            return playback_text
        return _legacy_activity_phrase(activity)

    playback_state = playback_state or {}
    monitor_state = monitor_state or {}
    playback_phrase = _playback_phrase(playback_state)
    activity_phrase = (
        _activity_phrase(activity, include_mode=not bool(playback_phrase))
        if activity
        else ""
    )

    parts = [part for part in (activity_phrase, playback_phrase) if part]
    if str(monitor_state.get("error", "") or "") == "no_capture":
        return " · ".join(["monitor offline", *parts]) if parts else "monitor offline"
    return " · ".join(parts)


def face_display_sample_status_text(
    activity: Mapping[str, object] | None,
    playback_state: Mapping[str, object] | None = None,
    monitor_state: Mapping[str, object] | None = None,
) -> str:
    """Combined sampler status line for the face display renderer.

    Mirrors the operator-diagnostics sampler line by enabling
    ``combine_activity_and_playback`` so the small face monitor and the
    operator surface stay in lockstep.
    """
    return sample_status_text(
        activity,
        playback_state,
        monitor_state,
        combine_activity_and_playback=True,
    )
