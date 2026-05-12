from __future__ import annotations

import math
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools"))

from senseweave.music_tracker import (
    SceneConstraint,
    TrackerLane,
    TrackerPattern,
    TrackerScene,
    TrackerStep,
)
from senseweave.render.rules.agogic import (
    DEFAULT_VELOCITY_GAIN_DB,
    AgogicAccentRule,
    detect_contour_apex,
    detect_harmonic_charge_peak,
)


def _scene(steps: list[TrackerStep], *, role: str = "melody") -> TrackerScene:
    lane = TrackerLane(name=role, role=role, voice="pluck", steps=steps)
    return TrackerScene(
        name="fixture",
        key="C",
        tempo_bpm=120.0,
        rows_per_beat=4,
        pattern=TrackerPattern(rows=64, lanes=[lane]),
        constraints=SceneConstraint(max_polyphony=1, allowed_roles=(role,)),
        metadata={"groove_meter": "4/4"},
    )


def _step(
    index: int,
    degree: int,
    *,
    charge: float | None = None,
    velocity: float = 0.4,
) -> TrackerStep:
    metadata = {}
    if charge is not None:
        metadata["harmonic_charge"] = str(charge)
    return TrackerStep(
        row=index * 20,
        length_rows=20,
        scale_degree=degree,
        velocity=velocity,
        metadata=metadata,
    )


def _changed_indices(before: list[TrackerStep], after: list[TrackerStep]) -> list[int]:
    return [
        index
        for index, (old, new) in enumerate(zip(before, after, strict=True))
        if old.length_rows != new.length_rows or old.velocity != new.velocity
    ]


def _db_gain(old_velocity: float, new_velocity: float) -> float:
    return 20.0 * math.log10(new_velocity / old_velocity)


def test_detect_contour_apex_finds_up_down_peak() -> None:
    steps = [_step(index, degree) for index, degree in enumerate([1, 3, 6, 4, 2])]

    assert detect_contour_apex(steps) == 2

    rendered = AgogicAccentRule().apply(_scene(steps), k=1.0, seeds=None, roles=None)
    shaped_steps = rendered.pattern.lanes[0].steps

    assert _changed_indices(steps, shaped_steps) == [2]
    assert 1.05 <= shaped_steps[2].length_rows / steps[2].length_rows <= 1.15
    assert 3.0 <= _db_gain(steps[2].velocity, shaped_steps[2].velocity) <= 6.0


def test_detect_harmonic_charge_peak_can_drive_agogic_accent() -> None:
    steps = [
        _step(0, 1, charge=0.1),
        _step(1, 2, charge=0.4),
        _step(2, 3, charge=0.9),
        _step(3, 4, charge=0.2),
    ]

    assert detect_contour_apex(steps) is None
    assert detect_harmonic_charge_peak(steps) == 2

    rendered = AgogicAccentRule().apply(_scene(steps), k=1.0, seeds=None, roles=None)
    shaped_steps = rendered.pattern.lanes[0].steps

    assert _changed_indices(steps, shaped_steps) == [2]
    assert shaped_steps[2].length_rows == 22
    assert math.isclose(
        _db_gain(steps[2].velocity, shaped_steps[2].velocity),
        DEFAULT_VELOCITY_GAIN_DB,
        abs_tol=0.02,
    )


def test_agogic_accent_shapes_only_one_apex_per_phrase() -> None:
    steps = [_step(index, degree) for index, degree in enumerate([1, 5, 2, 6, 3])]

    rendered = AgogicAccentRule().apply(_scene(steps), k=1.0, seeds=None, roles=None)
    shaped_steps = rendered.pattern.lanes[0].steps

    assert _changed_indices(steps, shaped_steps) == [3]
