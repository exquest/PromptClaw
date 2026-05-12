from __future__ import annotations

import enum
import json
import math
import struct
from collections.abc import Sequence
from dataclasses import FrozenInstanceError, dataclass, field, fields, is_dataclass
from typing import Any, ClassVar, Optional, Self, cast


class IntentTag(enum.Enum):
    BUILD = "build"
    SETTLE = "settle"
    QUESTION = "question"
    ANSWER = "answer"
    WITHHOLD = "withhold"
    PUNCTUATE = "punctuate"


_OSC_EVENT_ADDRESS = "/cypherclaw/event"
_OSC_BUNDLE_HEADER = b"#bundle\x00"
_OSC_IMMEDIATE_TIMETAG = b"\x00\x00\x00\x00\x00\x00\x00\x01"

VALID_ARC_SHAPES: frozenset[str] = frozenset(
    {"parabolic", "cosine", "bezier", "flat", "inverted"}
)
SECTION_ENVELOPE_INTERPOLATIONS: frozenset[str] = frozenset({"linear", "spline"})
SECTION_ENVELOPE_PARAMETERS: tuple[str, ...] = (
    "tempo_base",
    "density_target",
    "dynamic_plane",
    "brightness",
    "tension_trajectory",
)
Breakpoint = tuple[float, float]
BreakpointFunction = float | Sequence[Breakpoint]


@dataclass
class PerformanceIntent:
    phrase_id: str
    arc_shape: str = "parabolic"
    arc_peak_position: float = 0.6
    tempo_deviation_pct: float = 4.0
    dynamic_range_db: float = 9.0
    articulation_mean: float = 0.5
    breath_after_ms: float = 250.0
    tension_target: float = 0.5
    restraint: float = 0.0
    call_response_role: str = ""

    def __post_init__(self) -> None:
        if self.arc_shape not in VALID_ARC_SHAPES:
            raise ValueError(
                f"arc_shape must be one of {sorted(VALID_ARC_SHAPES)}, "
                f"got {self.arc_shape!r}"
            )
        if not 0.0 <= self.arc_peak_position <= 1.0:
            raise ValueError(
                f"arc_peak_position must be in [0.0, 1.0], got {self.arc_peak_position}"
            )
        if self.tempo_deviation_pct < 0.0:
            raise ValueError(
                f"tempo_deviation_pct must be >= 0, got {self.tempo_deviation_pct}"
            )
        if self.dynamic_range_db < 0.0:
            raise ValueError(
                f"dynamic_range_db must be >= 0, got {self.dynamic_range_db}"
            )
        if not 0.0 <= self.articulation_mean <= 1.0:
            raise ValueError(
                f"articulation_mean must be in [0.0, 1.0], got {self.articulation_mean}"
            )
        if self.breath_after_ms < 0.0:
            raise ValueError(
                f"breath_after_ms must be >= 0, got {self.breath_after_ms}"
            )
        if not 0.0 <= self.tension_target <= 1.0:
            raise ValueError(
                f"tension_target must be in [0.0, 1.0], got {self.tension_target}"
            )
        if not 0.0 <= self.restraint <= 1.0:
            raise ValueError(
                f"restraint must be in [0.0, 1.0], got {self.restraint}"
            )


@dataclass(frozen=True)
class SectionEnvelopeSample:
    tempo_base: float = 1.0
    density_target: float = 1.0
    dynamic_plane: float = 1.0
    brightness: float = 1.0
    tension_trajectory: float = 0.0


@dataclass
class SectionEnvelope:
    tempo_base: BreakpointFunction = 1.0
    density_target: BreakpointFunction = 1.0
    dynamic_plane: BreakpointFunction = 1.0
    brightness: BreakpointFunction = 1.0
    tension_trajectory: BreakpointFunction = 0.0
    interpolation: str = "linear"

    def __post_init__(self) -> None:
        if self.interpolation not in SECTION_ENVELOPE_INTERPOLATIONS:
            raise ValueError(
                "interpolation must be one of "
                f"{sorted(SECTION_ENVELOPE_INTERPOLATIONS)}, got {self.interpolation!r}"
            )
        for parameter in SECTION_ENVELOPE_PARAMETERS:
            normalized = _normalize_breakpoint_function(
                parameter,
                getattr(self, parameter),
            )
            object.__setattr__(self, parameter, normalized)

    def sample(self, position: float) -> SectionEnvelopeSample:
        normalized_position = _normalized_position("sample position", position)
        return SectionEnvelopeSample(
            tempo_base=self.value_at("tempo_base", normalized_position),
            density_target=self.value_at("density_target", normalized_position),
            dynamic_plane=self.value_at("dynamic_plane", normalized_position),
            brightness=self.value_at("brightness", normalized_position),
            tension_trajectory=self.value_at(
                "tension_trajectory",
                normalized_position,
            ),
        )

    def value_at(self, parameter: str, position: float) -> float:
        if parameter not in SECTION_ENVELOPE_PARAMETERS:
            raise ValueError(
                f"parameter must be one of {sorted(SECTION_ENVELOPE_PARAMETERS)}, "
                f"got {parameter!r}"
            )
        normalized_position = _normalized_position("sample position", position)
        breakpoint_function = getattr(self, parameter)
        return _sample_breakpoint_function(
            cast(float | tuple[Breakpoint, ...], breakpoint_function),
            normalized_position,
            self.interpolation,
        )


@dataclass
class Event:
    event_id: str = ""
    phrase_id: str = ""
    section_id: str = ""
    voice_id: str = ""
    role: str = ""
    pitch: int | float | None = None
    nominal_beat: float = 0.0
    nominal_dur_beats: float = 0.0
    harmonic_charge: float = 0.0
    melodic_charge: float = 0.0
    metric_weight: float = 0.0
    is_phrase_start: bool = False
    is_phrase_end: bool = False
    is_cadential: bool = False
    intent_tag: str = ""
    onset_sec: float = 0.0
    dur_sec: float = 0.0
    velocity: float = 1.0
    timing_deviation_ms: float = 0.0
    articulation: str = ""
    sensor_tempo_scale: float = 0.0
    sensor_amp_scale: float = 0.0
    sensor_brightness: float = 0.0
    rule_stack: list[str] = field(default_factory=list)
    seed_path: tuple[int, ...] = field(default_factory=tuple)

    normalized_phrase_position: float = 0.0
    normalized_section_position: float = 0.0
    section_envelope: Optional[SectionEnvelope] = None
    tempo_mult: float = 1.0
    amp_mult: float = 1.0
    phrase: object | None = None
    contour_apex: float = 0.0
    contour_apex_index: int | None = None
    is_contour_apex: bool = False
    metadata: dict[str, str] = field(default_factory=dict)

    SCORE_LEVEL_FIELDS: ClassVar[frozenset[str]] = frozenset(
        {
            "event_id",
            "phrase_id",
            "section_id",
            "voice_id",
            "role",
            "pitch",
            "nominal_beat",
            "nominal_dur_beats",
            "harmonic_charge",
            "melodic_charge",
            "metric_weight",
            "is_phrase_start",
            "is_phrase_end",
            "is_cadential",
            "intent_tag",
        }
    )

    def __post_init__(self) -> None:
        if isinstance(self.section_envelope, dict):
            object.__setattr__(
                self,
                "section_envelope",
                SectionEnvelope(**self.section_envelope),
            )
        object.__setattr__(self, "rule_stack", [str(rule) for rule in self.rule_stack])
        object.__setattr__(self, "seed_path", tuple(int(seed) for seed in self.seed_path))
        object.__setattr__(self, "_score_fields_locked", False)

    def __setattr__(self, name: str, value: object) -> None:
        if (
            name in self.SCORE_LEVEL_FIELDS
            and getattr(self, "_score_fields_locked", False)
        ):
            raise FrozenInstanceError(
                f"cannot assign to score-level field {name!r} after render stage"
            )
        super().__setattr__(name, value)

    @property
    def score_fields_locked(self) -> bool:
        return bool(getattr(self, "_score_fields_locked", False))

    def lock_score_fields(self) -> None:
        object.__setattr__(self, "_score_fields_locked", True)

    def freeze_score_fields(self) -> None:
        self.lock_score_fields()

    def mark_rendered(self) -> None:
        self.lock_score_fields()

    def to_json_dict(self) -> dict[str, Any]:
        return {
            event_field.name: _json_safe(getattr(self, event_field.name))
            for event_field in fields(self)
        }

    def to_dict(self) -> dict[str, Any]:
        return self.to_json_dict()

    @classmethod
    def from_json_dict(cls, payload: dict[str, Any]) -> Self:
        init_fields = {event_field.name for event_field in fields(cls) if event_field.init}
        return cls(**{key: value for key, value in payload.items() if key in init_fields})

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> Self:
        return cls.from_json_dict(payload)

    def to_json(self) -> str:
        return json.dumps(self.to_json_dict(), separators=(",", ":"), sort_keys=True)

    @classmethod
    def from_json(cls, payload: str) -> Self:
        decoded = json.loads(payload)
        if not isinstance(decoded, dict):
            raise ValueError("event JSON payload must decode to an object")
        return cls.from_json_dict(decoded)

    def to_osc_bundle(self) -> bytes:
        message = _encode_osc_message(_OSC_EVENT_ADDRESS, self.to_json())
        return (
            _OSC_BUNDLE_HEADER
            + _OSC_IMMEDIATE_TIMETAG
            + struct.pack(">i", len(message))
            + message
        )

    @classmethod
    def from_osc_bundle(cls, payload: bytes) -> Self:
        message = _extract_single_osc_message(payload)
        address, offset = _read_osc_string(message, 0)
        if address != _OSC_EVENT_ADDRESS:
            raise ValueError(f"unexpected OSC address {address!r}")
        type_tags, offset = _read_osc_string(message, offset)
        if type_tags != ",s":
            raise ValueError(f"unexpected OSC type tags {type_tags!r}")
        event_json, offset = _read_osc_string(message, offset)
        if offset != len(message):
            raise ValueError("unexpected trailing OSC message data")
        return cls.from_json(event_json)


def _normalize_breakpoint_function(
    parameter: str,
    value: object,
) -> float | tuple[Breakpoint, ...]:
    if _is_number(value):
        scalar = float(cast(float, value))
        _validate_section_parameter_value(parameter, scalar)
        return scalar
    if isinstance(value, str | bytes) or not isinstance(value, Sequence):
        raise ValueError(f"{parameter} must be a number or a sequence of breakpoints")
    if len(value) == 0:
        raise ValueError(f"{parameter} must include at least one breakpoint")

    points: list[Breakpoint] = []
    for breakpoint_value in value:
        if (
            isinstance(breakpoint_value, str | bytes)
            or not isinstance(breakpoint_value, Sequence)
            or len(breakpoint_value) != 2
        ):
            raise ValueError(
                f"{parameter} breakpoints must be (position, value) pairs"
            )
        position = _normalized_position(
            f"{parameter} breakpoint position",
            breakpoint_value[0],
        )
        point_value = _finite_float(f"{parameter} breakpoint value", breakpoint_value[1])
        _validate_section_parameter_value(parameter, point_value)
        points.append((position, point_value))

    points.sort(key=lambda point: point[0])
    for previous, current in zip(points, points[1:]):
        if previous[0] == current[0]:
            raise ValueError(f"{parameter} breakpoint positions must be unique")
    return tuple(points)


def _sample_breakpoint_function(
    value: float | tuple[Breakpoint, ...],
    position: float,
    interpolation: str,
) -> float:
    if isinstance(value, float):
        return value
    if len(value) == 1 or position <= value[0][0]:
        return value[0][1]
    if position >= value[-1][0]:
        return value[-1][1]

    for index, (left, right) in enumerate(zip(value, value[1:])):
        left_position, left_value = left
        right_position, right_value = right
        if left_position <= position <= right_position:
            if interpolation == "spline" and len(value) > 2:
                return _spline_interpolate(value, index, position)
            return _linear_interpolate(
                left_position,
                left_value,
                right_position,
                right_value,
                position,
            )
    return value[-1][1]


def _linear_interpolate(
    left_position: float,
    left_value: float,
    right_position: float,
    right_value: float,
    position: float,
) -> float:
    span = right_position - left_position
    if span == 0.0:
        return left_value
    ratio = (position - left_position) / span
    return left_value + (right_value - left_value) * ratio


def _spline_interpolate(
    points: tuple[Breakpoint, ...],
    index: int,
    position: float,
) -> float:
    left_position, left_value = points[index]
    right_position, right_value = points[index + 1]
    span = right_position - left_position
    if span == 0.0:
        return left_value

    ratio = (position - left_position) / span
    left_slope = _spline_slope(points, index)
    right_slope = _spline_slope(points, index + 1)
    h00 = 2.0 * ratio**3 - 3.0 * ratio**2 + 1.0
    h10 = ratio**3 - 2.0 * ratio**2 + ratio
    h01 = -2.0 * ratio**3 + 3.0 * ratio**2
    h11 = ratio**3 - ratio**2
    interpolated = (
        h00 * left_value
        + h10 * span * left_slope
        + h01 * right_value
        + h11 * span * right_slope
    )
    lower_bound = min(point[1] for point in points)
    upper_bound = max(point[1] for point in points)
    return min(upper_bound, max(lower_bound, interpolated))


def _spline_slope(points: tuple[Breakpoint, ...], index: int) -> float:
    if index == 0:
        left_position, left_value = points[0]
        right_position, right_value = points[1]
    elif index == len(points) - 1:
        left_position, left_value = points[-2]
        right_position, right_value = points[-1]
    else:
        left_position, left_value = points[index - 1]
        right_position, right_value = points[index + 1]
    return (right_value - left_value) / (right_position - left_position)


def _normalized_position(label: str, value: object) -> float:
    position = _finite_float(label, value)
    if not 0.0 <= position <= 1.0:
        raise ValueError(f"{label} must be in [0.0, 1.0], got {position}")
    return position


def _validate_section_parameter_value(parameter: str, value: float) -> None:
    if parameter == "tempo_base":
        if value <= 0.0:
            raise ValueError(f"{parameter} must be > 0.0, got {value}")
        return
    if not 0.0 <= value <= 1.0:
        raise ValueError(f"{parameter} must be in [0.0, 1.0], got {value}")


def _finite_float(label: str, value: object) -> float:
    if not _is_number(value):
        raise ValueError(f"{label} must be a finite number, got {value!r}")
    result = float(cast(float, value))
    if not math.isfinite(result):
        raise ValueError(f"{label} must be a finite number, got {value!r}")
    return result


def _is_number(value: object) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool)


def _json_safe(value: object) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, tuple | list):
        return [_json_safe(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if is_dataclass(value) and not isinstance(value, type):
        return {
            event_field.name: _json_safe(getattr(value, event_field.name))
            for event_field in fields(value)
        }
    return str(value)


def _encode_osc_message(address: str, event_json: str) -> bytes:
    return _pad_osc_string(address) + _pad_osc_string(",s") + _pad_osc_string(event_json)


def _extract_single_osc_message(payload: bytes) -> bytes:
    if not payload.startswith(_OSC_BUNDLE_HEADER):
        raise ValueError("OSC payload is not a bundle")
    if len(payload) < 20:
        raise ValueError("OSC bundle is incomplete")
    offset = len(_OSC_BUNDLE_HEADER) + 8
    size = struct.unpack_from(">i", payload, offset)[0]
    offset += 4
    if size < 0:
        raise ValueError("OSC element size cannot be negative")
    end = offset + size
    if end != len(payload):
        raise ValueError("OSC bundle must contain exactly one event message")
    return payload[offset:end]


def _pad_osc_string(value: str) -> bytes:
    encoded = value.encode("utf-8") + b"\x00"
    padding = (-len(encoded)) % 4
    return encoded + (b"\x00" * padding)


def _read_osc_string(payload: bytes, offset: int) -> tuple[str, int]:
    if offset >= len(payload):
        raise ValueError("OSC string offset is outside payload")
    try:
        end = payload.index(b"\x00", offset)
    except ValueError as exc:
        raise ValueError("OSC string is missing null terminator") from exc
    value = payload[offset:end].decode("utf-8")
    next_offset = end + 1
    next_offset += (-next_offset) % 4
    if next_offset > len(payload):
        raise ValueError("OSC string padding exceeds payload")
    return value, next_offset
