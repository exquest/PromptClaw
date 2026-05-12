import math

import pytest

from cypherclaw.render.events import Event
from cypherclaw.render.rules.articulation import (
    STYLE_GATE_RANGES,
    ArticulationRule,
)


@pytest.mark.parametrize("style", ("legato", "normal", "staccato", "staccatissimo"))
def test_articulation_gate_time_range_by_style(style: str) -> None:
    rule = ArticulationRule()
    event = Event(role="melody")
    event.articulation_style = style  # type: ignore[attr-defined]
    event.nominal_dur_sec = 2.0  # type: ignore[attr-defined]
    event.pitch = 60  # type: ignore[attr-defined]

    rule.apply(event)

    low, high = STYLE_GATE_RANGES[style]
    assert low <= event.gate_time <= high
    assert math.isclose(event.dur_sec, event.gate_time * 2.0)


def test_articulation_repeated_pitch_shortens_gate() -> None:
    rule = ArticulationRule()
    event = Event(role="melody")
    event.articulation_style = "normal"  # type: ignore[attr-defined]
    event.nominal_dur_sec = 1.0  # type: ignore[attr-defined]
    event.previous_pitch = 60  # type: ignore[attr-defined]
    event.pitch = 60  # type: ignore[attr-defined]

    rule.apply(event)

    base_gate = sum(STYLE_GATE_RANGES["normal"]) / 2.0
    assert math.isclose(event.gate_time, base_gate * 0.92)
    assert math.isclose(event.dur_sec, base_gate * 0.92)


def test_articulation_after_upward_leap_lengthens_gate() -> None:
    rule = ArticulationRule()
    event = Event(role="melody")
    event.articulation_style = "normal"  # type: ignore[attr-defined]
    event.nominal_dur_sec = 1.0  # type: ignore[attr-defined]
    event.previous_pitch = 60  # type: ignore[attr-defined]
    event.pitch = 67  # type: ignore[attr-defined]

    rule.apply(event)

    base_gate = sum(STYLE_GATE_RANGES["normal"]) / 2.0
    assert math.isclose(event.gate_time, base_gate * 1.05)
    assert math.isclose(event.dur_sec, base_gate * 1.05)
