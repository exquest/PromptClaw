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
from senseweave.render.rules.punctuation import (
    DEFAULT_TERMINAL_MULTIPLIER,
    MAX_TERMINAL_MULTIPLIER,
    PunctuationRule,
)


def _scene(steps: list[TrackerStep], *, role: str = "melody", tempo: float = 120.0) -> TrackerScene:
    lane = TrackerLane(name=role, role=role, voice="pluck", steps=steps)
    return TrackerScene(
        name="fixture",
        key="C",
        tempo_bpm=tempo,
        rows_per_beat=4,
        pattern=TrackerPattern(rows=64, lanes=[lane]),
        constraints=SceneConstraint(max_polyphony=1, allowed_roles=(role,)),
        metadata={"groove_meter": "4/4"},
    )


def _step(row: int, length: int, *, phrase_id: str = "p1") -> TrackerStep:
    return TrackerStep(
        row=row,
        length_rows=length,
        scale_degree=1,
        velocity=0.5,
        metadata={"phrase_id": phrase_id},
    )


def test_terminal_note_extended() -> None:
    steps = [_step(0, 4), _step(4, 4), _step(8, 4)]
    scene = _scene(steps)
    rendered = PunctuationRule().apply(scene, k=1.0, seeds={"R6": 99}, roles=None)
    out = rendered.pattern.lanes[0].steps
    terminal = out[2]
    assert terminal.length_rows > steps[2].length_rows
    expected = int(round(4 * DEFAULT_TERMINAL_MULTIPLIER))
    assert terminal.length_rows == expected


def test_breath_inserted_after_terminal() -> None:
    steps = [_step(0, 4), _step(4, 4), _step(8, 4)]
    scene = _scene(steps)
    rendered = PunctuationRule().apply(scene, k=1.0, seeds={"R6": 99}, roles=None)
    out = rendered.pattern.lanes[0].steps
    assert len(out) == 4
    breath = out[3]
    assert breath.velocity == 0.0
    assert breath.metadata.get("breath_r6") == "true"
    assert "breath_ms" in breath.metadata


def test_breath_row_follows_extended_note() -> None:
    steps = [_step(0, 8)]
    scene = _scene(steps)
    rendered = PunctuationRule().apply(scene, k=1.0, seeds={"R6": 99}, roles=None)
    out = rendered.pattern.lanes[0].steps
    extended = out[0]
    breath = out[1]
    assert breath.row == extended.row + extended.length_rows


def test_multi_phrase_breaths() -> None:
    steps = [
        _step(0, 4, phrase_id="p1"),
        _step(4, 4, phrase_id="p1"),
        _step(8, 4, phrase_id="p2"),
        _step(12, 4, phrase_id="p2"),
    ]
    scene = _scene(steps)
    rendered = PunctuationRule().apply(scene, k=1.0, seeds={"R6": 99}, roles=None)
    out = rendered.pattern.lanes[0].steps
    breaths = [s for s in out if s.metadata.get("breath_r6") == "true"]
    assert len(breaths) == 2


def test_non_terminal_notes_unchanged() -> None:
    steps = [_step(0, 4), _step(4, 4), _step(8, 4)]
    scene = _scene(steps)
    rendered = PunctuationRule().apply(scene, k=1.0, seeds={"R6": 99}, roles=None)
    out = rendered.pattern.lanes[0].steps
    assert out[0].length_rows == 4
    assert out[1].length_rows == 4


def test_k_zero_returns_unchanged() -> None:
    steps = [_step(0, 4), _step(4, 4)]
    scene = _scene(steps)
    rendered = PunctuationRule().apply(scene, k=0.0, seeds=None, roles=None)
    assert rendered is scene


def test_ostinato_unchanged() -> None:
    steps = [_step(0, 4), _step(4, 4)]
    scene = _scene(steps, role="ostinato")
    rendered = PunctuationRule().apply(scene, k=1.0, seeds=None, roles=None)
    out = rendered.pattern.lanes[0].steps
    assert len(out) == 2
    assert out[0].length_rows == 4


def test_percussion_unchanged() -> None:
    steps = [_step(0, 4), _step(4, 4)]
    scene = _scene(steps, role="perc")
    rendered = PunctuationRule().apply(scene, k=1.0, seeds=None, roles=None)
    out = rendered.pattern.lanes[0].steps
    assert len(out) == 2


def test_grid_locked_terminal_preserved() -> None:
    steps = [
        _step(0, 4),
        TrackerStep(
            row=4, length_rows=4, scale_degree=1, velocity=0.5,
            metadata={"phrase_id": "p1", "grid_locked": "true"},
        ),
    ]
    scene = _scene(steps)
    rendered = PunctuationRule().apply(scene, k=1.0, seeds={"R6": 99}, roles=None)
    out = rendered.pattern.lanes[0].steps
    assert len(out) == 2
    assert out[1].length_rows == 4


def test_breath_budget_metadata() -> None:
    steps = [_step(0, 4), _step(4, 4)]
    scene = _scene(steps)
    rendered = PunctuationRule().apply(scene, k=1.0, seeds={"R6": 99}, roles=None)
    out = rendered.pattern.lanes[0].steps
    breaths = [s for s in out if s.metadata.get("breath_r6") == "true"]
    assert len(breaths) == 1
    ms = float(breaths[0].metadata["breath_ms"])
    assert ms > 0


def test_deterministic_with_seed() -> None:
    steps = [_step(0, 8), _step(8, 8)]
    scene = _scene(steps)
    a = PunctuationRule().apply(scene, k=1.0, seeds={"R6": 42}, roles=None)
    b = PunctuationRule().apply(scene, k=1.0, seeds={"R6": 42}, roles=None)
    out_a = a.pattern.lanes[0].steps
    out_b = b.pattern.lanes[0].steps
    assert [s.length_rows for s in out_a] == [s.length_rows for s in out_b]
    breaths_a = [s for s in out_a if s.metadata.get("breath_r6") == "true"]
    breaths_b = [s for s in out_b if s.metadata.get("breath_r6") == "true"]
    assert breaths_a[0].metadata["breath_ms"] == breaths_b[0].metadata["breath_ms"]


def test_multiplier_capped_at_max() -> None:
    rule = PunctuationRule(terminal_multiplier=2.0)
    steps = [_step(0, 10)]
    scene = _scene(steps)
    rendered = rule.apply(scene, k=1.0, seeds={"R6": 99}, roles=None)
    out = rendered.pattern.lanes[0].steps
    ratio = out[0].length_rows / steps[0].length_rows
    assert ratio <= MAX_TERMINAL_MULTIPLIER + 0.01
