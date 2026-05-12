from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Final, cast

from cypherclaw.render.events import Event
from cypherclaw.render.role_gate import role_is_eligible


STYLE_GATE_RANGES: Final[dict[str, tuple[float, float]]] = {
    "legato": (0.95, 1.02),
    "normal": (0.70, 0.85),
    "staccato": (0.30, 0.50),
    "staccatissimo": (0.15, 0.25),
}


@dataclass
class ArticulationRule:
    default_style: str = "normal"
    repeated_pitch_multiplier: float = 0.92
    upward_leap_multiplier: float = 1.05
    upward_leap_threshold: float = 3.0

    rule_id = "R7"

    def applies_to(self, role: str, metadata: Mapping[str, object] | None = None) -> bool:
        return role_is_eligible(role, metadata)

    def apply(self, event: Event) -> None:
        if not self.applies_to(event.role, event.metadata):
            return
        nominal = self._nominal_duration(event)
        gate_time = self.gate_time_for_style(
            _event_or_note_attr(
                event,
                ("articulation_style", "articulation", "style"),
            ),
        )

        pitch = self._pitch(event)
        previous_pitch = self._previous_pitch(event)
        if pitch is not None and previous_pitch is not None:
            interval = pitch - previous_pitch
            if interval == 0:
                gate_time *= self.repeated_pitch_multiplier
            elif interval >= self.upward_leap_threshold:
                gate_time *= self.upward_leap_multiplier

        setattr(event, "gate_time", gate_time)
        setattr(event, "dur_sec", gate_time * nominal)

    def gate_time_for_style(self, style: object | None) -> float:
        style_key = self._normalize_style(style)
        low, high = STYLE_GATE_RANGES[style_key]
        return (low + high) / 2.0

    def _normalize_style(self, style: object | None) -> str:
        style_text = self.default_style if style is None else str(style)
        style_key = style_text.strip().lower().replace("-", "_")
        if style_key in STYLE_GATE_RANGES:
            return style_key
        return "normal"

    def _nominal_duration(self, event: Event) -> float:
        nominal = _event_or_note_attr(
            event,
            ("nominal_dur_sec", "nominal_sec", "duration_sec"),
        )
        if nominal is None:
            nominal = getattr(event, "dur_sec", None)
        if nominal is None:
            raise ValueError("ArticulationRule requires a nominal duration")
        return float(cast(Any, nominal))

    def _pitch(self, event: Event) -> float | None:
        return _coerce_optional_float(
            _event_or_note_attr(
                event,
                ("pitch", "midi_pitch", "pitch_midi", "scale_degree"),
            ),
        )

    def _previous_pitch(self, event: Event) -> float | None:
        previous_pitch = _event_or_note_attr(
            event,
            ("previous_pitch", "prev_pitch", "last_pitch"),
        )
        if previous_pitch is not None:
            return _coerce_optional_float(previous_pitch)

        previous_note = _event_or_note_attr(event, ("previous_note", "prev_note"))
        if previous_note is None:
            return None
        return _coerce_optional_float(
            _first_attr(
                previous_note,
                ("pitch", "midi_pitch", "pitch_midi", "scale_degree"),
            ),
        )


def _event_or_note_attr(event: Event, names: tuple[str, ...]) -> object | None:
    for source in (event, getattr(event, "note", None)):
        if source is None:
            continue
        value = _first_attr(source, names)
        if value is not None:
            return value
    return None


def _first_attr(source: object, names: tuple[str, ...]) -> object | None:
    for name in names:
        value = getattr(source, name, None)
        if value is not None:
            return value
    return None


def _coerce_optional_float(value: object | None) -> float | None:
    if value is None:
        return None
    return float(cast(Any, value))
