from __future__ import annotations

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
from senseweave.render.rules.duration_contrast import (
    DurationContrastRule,
    MAX_MULTIPLIER,
    MIN_MULTIPLIER,
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


def _step(index: int, length: int, *, velocity: float = 0.5) -> TrackerStep:
    return TrackerStep(
        row=index * 16,
        length_rows=length,
        scale_degree=1,
        velocity=velocity,
    )


def test_short_notes_shortened_long_notes_lengthened() -> None:
    steps = [
        _step(0, 4),
        _step(1, 8),
        _step(2, 16),
        _step(3, 32),
    ]
    scene = _scene(steps)
    rendered = DurationContrastRule().apply(scene, k=1.0, seeds=None, roles=None)
    out = rendered.pattern.lanes[0].steps

    assert out[0].length_rows <= steps[0].length_rows
    assert out[3].length_rows >= steps[3].length_rows


def test_cap_enforcement() -> None:
    steps = [
        _step(0, 1),
        _step(1, 100),
    ]
    scene = _scene(steps)
    rendered = DurationContrastRule().apply(scene, k=1.0, seeds=None, roles=None)
    out = rendered.pattern.lanes[0].steps

    ratio_short = out[0].length_rows / steps[0].length_rows
    ratio_long = out[1].length_rows / steps[1].length_rows

    assert ratio_short >= MIN_MULTIPLIER - 0.01
    assert ratio_long <= MAX_MULTIPLIER + 0.01


def test_ostinato_unchanged() -> None:
    steps = [_step(0, 4), _step(1, 16), _step(2, 32)]
    scene = _scene(steps, role="ostinato")
    rendered = DurationContrastRule().apply(scene, k=1.0, seeds=None, roles=None)
    out = rendered.pattern.lanes[0].steps

    assert [s.length_rows for s in out] == [s.length_rows for s in steps]


def test_percussion_unchanged() -> None:
    steps = [_step(0, 4), _step(1, 16), _step(2, 32)]
    scene = _scene(steps, role="perc")
    rendered = DurationContrastRule().apply(scene, k=1.0, seeds=None, roles=None)
    out = rendered.pattern.lanes[0].steps

    assert [s.length_rows for s in out] == [s.length_rows for s in steps]


def test_k_zero_returns_unchanged() -> None:
    steps = [_step(0, 4), _step(1, 16), _step(2, 32)]
    scene = _scene(steps)
    rendered = DurationContrastRule().apply(scene, k=0.0, seeds=None, roles=None)

    assert rendered is scene


def test_grid_locked_step_preserved() -> None:
    steps = [
        TrackerStep(row=0, length_rows=4, scale_degree=1, velocity=0.5,
                    metadata={"grid_locked": "true"}),
        _step(1, 16),
        _step(2, 32),
    ]
    scene = _scene(steps)
    rendered = DurationContrastRule().apply(scene, k=1.0, seeds=None, roles=None)
    out = rendered.pattern.lanes[0].steps

    assert out[0].length_rows == 4


def test_equal_durations_unchanged() -> None:
    steps = [_step(i, 16) for i in range(4)]
    scene = _scene(steps)
    rendered = DurationContrastRule().apply(scene, k=1.0, seeds=None, roles=None)
    out = rendered.pattern.lanes[0].steps

    assert [s.length_rows for s in out] == [16, 16, 16, 16]
