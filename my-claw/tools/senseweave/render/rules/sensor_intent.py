"""R12 sensor-to-intent aggregation matrix."""
from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

DEFAULT_ALPHA = 0.1
DEFAULT_ON_THRESHOLD = 0.6
DEFAULT_OFF_THRESHOLD = 0.4

SENSOR_CHANNELS: tuple[str, ...] = (
    "theramini_active",
    "room_activity",
    "room_transient",
    "speech_detected",
    "outdoor_brightness",
)
INTENTION_KEYS: tuple[str, ...] = (
    "global_energy",
    "global_restraint",
    "global_brightness",
)

INTENTION_BASELINE: dict[str, float] = {
    "global_energy": 0.08,
    "global_restraint": 0.48,
    "global_brightness": 0.20,
}
SENSOR_INTENTION_WEIGHTS: dict[str, dict[str, float]] = {
    "theramini_active": {
        "global_energy": 0.28,
        "global_restraint": -0.10,
        "global_brightness": 0.18,
    },
    "room_activity": {
        "global_energy": 0.25,
        "global_restraint": -0.18,
        "global_brightness": 0.11,
    },
    "room_transient": {
        "global_energy": 0.16,
        "global_restraint": -0.12,
        "global_brightness": 0.07,
    },
    "speech_detected": {
        "global_energy": 0.13,
        "global_restraint": 0.12,
        "global_brightness": 0.14,
    },
    "outdoor_brightness": {
        "global_energy": 0.08,
        "global_restraint": 0.02,
        "global_brightness": 0.30,
    },
}

_ACTIVITY_VALUES: dict[str, float] = {
    "quiet": 0.0,
    "idle": 0.0,
    "low": 0.25,
    "moderate": 0.55,
    "active": 1.0,
    "high": 1.0,
}


def _clamp(value: float, lower: float = 0.0, upper: float = 1.0) -> float:
    return max(lower, min(upper, value))


def _as_mapping(value: object) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return value
    return {}


def _first_mapping(frame: Mapping[str, Any], *keys: str) -> Mapping[str, Any]:
    for key in keys:
        value = frame.get(key)
        if isinstance(value, Mapping):
            return value
    return {}


def _to_float(value: object) -> float | None:
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            return None
    return None


def _first_number(*values: object, default: float = 0.0) -> float:
    for value in values:
        number = _to_float(value)
        if number is not None:
            return _clamp(number)
    return default


def _activity_value(value: object) -> float:
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in _ACTIVITY_VALUES:
            return _ACTIVITY_VALUES[normalized]
    return _first_number(value)


def _extract_sensor_values(frame: Mapping[str, Any]) -> dict[str, float]:
    theramini = _first_mapping(frame, "theramini", "theramini_state")
    room = _first_mapping(frame, "room", "room_activity_state", "room_activity")
    speech = _first_mapping(frame, "speech", "room_speech")
    outdoor = _first_mapping(frame, "outdoor", "garden", "porch_eye", "camera")

    theramini_active = max(
        _first_number(frame.get("theramini_active"), frame.get("theramini_playing")),
        _first_number(theramini.get("playing"), theramini.get("is_playing")),
        _clamp(_first_number(theramini.get("rms")) * 2.0),
    )
    room_activity = max(
        _activity_value(frame.get("room_activity")),
        _activity_value(room.get("activity")),
        _activity_value(room.get("activity_level")),
        _clamp(_first_number(room.get("membrane_rms")) * 4.0),
        _clamp(_first_number(room.get("heartbeat_rms")) * 6.0),
    )
    room_transient = max(
        _first_number(frame.get("room_transient"), frame.get("recent_transient")),
        _first_number(room.get("transient"), room.get("recent_transient")),
    )
    speech_detected = max(
        _first_number(frame.get("speech_detected")),
        _first_number(speech.get("detected"), speech.get("speech_detected")),
    )
    outdoor_brightness = _first_number(
        frame.get("outdoor_brightness"),
        frame.get("brightness"),
        outdoor.get("brightness"),
    )

    return {
        "theramini_active": theramini_active,
        "room_activity": room_activity,
        "room_transient": room_transient,
        "speech_detected": speech_detected,
        "outdoor_brightness": outdoor_brightness,
    }


def _aggregate_from_active(
    active: Mapping[str, bool],
    *,
    k: float,
    baseline: Mapping[str, float],
    weights: Mapping[str, Mapping[str, float]],
) -> dict[str, float]:
    scale = _clamp(k)
    aggregate = {key: float(baseline.get(key, 0.0)) for key in INTENTION_KEYS}
    for sensor in SENSOR_CHANNELS:
        if not active.get(sensor, False):
            continue
        sensor_weights = weights.get(sensor, {})
        for intention in INTENTION_KEYS:
            aggregate[intention] += scale * float(sensor_weights.get(intention, 0.0))
    return {
        intention: round(_clamp(aggregate[intention]), 3)
        for intention in INTENTION_KEYS
    }


def _baseline_intentions(baseline: Mapping[str, float]) -> dict[str, float]:
    return {
        intention: round(_clamp(float(baseline.get(intention, 0.0))), 3)
        for intention in INTENTION_KEYS
    }


@dataclass
class SensorIntentFilter:
    """Stateful one-pole sensor smoother with per-channel hysteresis."""

    alpha: float = DEFAULT_ALPHA
    on_threshold: float = DEFAULT_ON_THRESHOLD
    off_threshold: float = DEFAULT_OFF_THRESHOLD
    baseline: Mapping[str, float] = field(default_factory=lambda: INTENTION_BASELINE)
    weights: Mapping[str, Mapping[str, float]] = field(
        default_factory=lambda: SENSOR_INTENTION_WEIGHTS,
    )
    _smoothed: dict[str, float] = field(default_factory=dict, init=False, repr=False)
    _active: dict[str, bool] = field(default_factory=dict, init=False, repr=False)
    _initialized: bool = field(default=False, init=False, repr=False)

    def __post_init__(self) -> None:
        self.alpha = _clamp(float(self.alpha))
        self.on_threshold = _clamp(float(self.on_threshold))
        self.off_threshold = _clamp(float(self.off_threshold))
        self._active = {sensor: False for sensor in SENSOR_CHANNELS}

    def update(self, frame: Mapping[str, Any], *, k: float = 1.0) -> dict[str, float]:
        raw = _extract_sensor_values(frame)
        for sensor in SENSOR_CHANNELS:
            raw_value = raw[sensor]
            if self._initialized:
                previous = self._smoothed.get(sensor, raw_value)
                smoothed = previous + (self.alpha * (raw_value - previous))
            else:
                smoothed = raw_value
            smoothed = _clamp(smoothed)
            self._smoothed[sensor] = smoothed

            if self._active[sensor]:
                self._active[sensor] = smoothed >= self.off_threshold
            else:
                self._active[sensor] = smoothed >= self.on_threshold

        self._initialized = True
        return _aggregate_from_active(
            self._active,
            k=k,
            baseline=self.baseline,
            weights=self.weights,
        )

    def neutral(self) -> dict[str, float]:
        return _baseline_intentions(self.baseline)


def aggregate_sensor_intent_stream(
    sensor_stream: Iterable[Mapping[str, Any]],
    *,
    alpha: float = DEFAULT_ALPHA,
    on_threshold: float = DEFAULT_ON_THRESHOLD,
    off_threshold: float = DEFAULT_OFF_THRESHOLD,
    k: float = 1.0,
) -> list[dict[str, dict[str, float]]]:
    """Render each raw sensor frame as aggregate intentions only."""

    sensor_filter = SensorIntentFilter(
        alpha=alpha,
        on_threshold=on_threshold,
        off_threshold=off_threshold,
    )
    return [
        {"aggregate_intentions": sensor_filter.update(frame, k=k)}
        for frame in sensor_stream
    ]


def aggregate_sensor_intentions(
    sensor_stream: Iterable[Mapping[str, Any]],
    *,
    alpha: float = DEFAULT_ALPHA,
    on_threshold: float = DEFAULT_ON_THRESHOLD,
    off_threshold: float = DEFAULT_OFF_THRESHOLD,
    k: float = 1.0,
) -> dict[str, float]:
    """Return final aggregate intentions for a raw sensor stream."""

    sensor_filter = SensorIntentFilter(
        alpha=alpha,
        on_threshold=on_threshold,
        off_threshold=off_threshold,
    )
    latest = sensor_filter.neutral()
    for frame in sensor_stream:
        latest = sensor_filter.update(frame, k=k)
    return latest


def _looks_like_sensor_frame(value: Mapping[str, Any]) -> bool:
    return any(
        key in value
        for key in (
            *SENSOR_CHANNELS,
            "theramini",
            "theramini_state",
            "room",
            "room_activity_state",
            "speech",
            "room_speech",
            "outdoor",
            "garden",
            "porch_eye",
            "camera",
        )
    )


def _coerce_sensor_stream(score: Any) -> list[Mapping[str, Any]] | None:
    if isinstance(score, Mapping):
        stream = score.get("sensor_stream")
        if isinstance(stream, Sequence) and not isinstance(stream, (str, bytes)):
            return [_as_mapping(frame) for frame in stream if isinstance(frame, Mapping)]
        if _looks_like_sensor_frame(score):
            return [score]
        return None
    if isinstance(score, Sequence) and not isinstance(score, (str, bytes)):
        return [_as_mapping(frame) for frame in score if isinstance(frame, Mapping)]
    return None


class SensorIntentRule:
    """Aggregate raw SenseWeave sensor streams into global intentions."""

    rule_id = "R12"

    def apply(
        self,
        score: Any,
        *,
        k: float,
        seeds: Mapping[str, int] | None,
        roles: frozenset[str] | None,
    ) -> Any:
        del seeds, roles
        if k == 0.0:
            return score
        stream = _coerce_sensor_stream(score)
        if stream is None:
            return score
        return {"aggregate_intentions": aggregate_sensor_intentions(stream, k=k)}


def apply_sensor_intent(
    score: Any,
    *,
    k: float = 1.0,
) -> Any:
    """Apply R12 sensor-to-intent aggregation to sensor stream payloads."""

    return SensorIntentRule().apply(score, k=k, seeds=None, roles=None)
