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
from senseweave.render.rules.silence_budget import (
    DEFAULT_TARGET_DENSITY,
    DEFAULT_THRESHOLD,
    SilenceBudgetRule,
    _duration_rows,
    _note_density,
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


def _step(row: int, length: int, *, phrase_id: str = "p1", velocity: float = 0.8) -> TrackerStep:
    return TrackerStep(
        row=row,
        length_rows=length,
        scale_degree=1,
        velocity=velocity,
        metadata={"phrase_id": phrase_id},
    )


def _breath(row: int, length: int) -> TrackerStep:
    return TrackerStep(
        row=row,
        length_rows=length,
        scale_degree=0,
        velocity=0.0,
        metadata={"breath_r6": "true", "breath_ms": "250.0"},
    )


# --- accumulator math ---

def test_note_density_all_sounding() -> None:
    steps = [_step(0, 4), _step(4, 4)]
    assert _note_density(steps) == 1.0


def test_note_density_half_silent() -> None:
    steps = [_step(0, 4), _step(4, 4, velocity=0.0)]
    assert _note_density(steps) == 0.5


def test_note_density_empty() -> None:
    assert _note_density([]) == 0.0


def test_duration_rows() -> None:
    steps = [_step(0, 4), _step(4, 8)]
    assert _duration_rows(steps) == 12.0


def test_accumulator_below_threshold_no_change() -> None:
    steps = [
        _step(0, 4, phrase_id="p1"),
        _step(4, 4, phrase_id="p2"),
    ]
    scene = _scene(steps)
    rule = SilenceBudgetRule(target_density=0.7, threshold=100.0)
    rendered = rule.apply(scene, k=1.0, seeds=None, roles=None)
    out = rendered.pattern.lanes[0].steps
    assert all(s.velocity == 0.8 for s in out)


def test_accumulator_math_two_phrases() -> None:
    p1 = [_step(0, 8, phrase_id="p1", velocity=0.8)]
    p2 = [_step(8, 8, phrase_id="p2", velocity=0.8)]
    density_p1 = _note_density(p1)
    dt_p1 = _duration_rows(p1)
    expected_budget = (DEFAULT_TARGET_DENSITY - density_p1) * dt_p1 * 1.0
    assert density_p1 == 1.0
    assert dt_p1 == 8.0
    assert expected_budget < 0.0
    assert abs(expected_budget) < DEFAULT_THRESHOLD
    scene = _scene(p1 + p2)
    rendered = SilenceBudgetRule().apply(scene, k=1.0, seeds=None, roles=None)
    out = rendered.pattern.lanes[0].steps
    assert all(s.velocity == 0.8 for s in out)


# --- threshold trigger: tacet-drop ---

def test_threshold_triggers_tacet() -> None:
    steps = [
        _step(0, 4, phrase_id="p1", velocity=0.0),
        _step(4, 4, phrase_id="p1", velocity=0.0),
        _step(8, 4, phrase_id="p1", velocity=0.0),
        _step(12, 4, phrase_id="p2", velocity=0.8),
        _step(16, 4, phrase_id="p2", velocity=0.8),
    ]
    rule = SilenceBudgetRule(target_density=0.7, threshold=1.0)
    scene = _scene(steps)
    rendered = rule.apply(scene, k=1.0, seeds=None, roles=None)
    out = rendered.pattern.lanes[0].steps
    p2_steps = [s for s in out if s.metadata.get("phrase_id") == "p2"]
    assert all(s.velocity == 0.0 for s in p2_steps)
    assert all(s.metadata.get("silence_budget_tacet") == "true" for s in p2_steps)


def test_tacet_preserves_step_count() -> None:
    steps = [
        _step(0, 8, phrase_id="p1", velocity=0.0),
        _step(8, 4, phrase_id="p2", velocity=0.8),
        _step(12, 4, phrase_id="p2", velocity=0.8),
    ]
    rule = SilenceBudgetRule(target_density=0.7, threshold=1.0)
    scene = _scene(steps)
    rendered = rule.apply(scene, k=1.0, seeds=None, roles=None)
    assert len(rendered.pattern.lanes[0].steps) == len(steps)


# --- threshold trigger: breath extension ---

def test_threshold_extends_breath() -> None:
    steps = [
        _step(0, 4, phrase_id="p1", velocity=0.0),
        _step(4, 4, phrase_id="p1", velocity=0.0),
        _breath(8, 2),
        _step(10, 4, phrase_id="p2", velocity=0.8),
        _step(14, 4, phrase_id="p2", velocity=0.8),
    ]
    rule = SilenceBudgetRule(target_density=0.7, threshold=1.0)
    scene = _scene(steps)
    rendered = rule.apply(scene, k=1.0, seeds=None, roles=None)
    out = rendered.pattern.lanes[0].steps
    breath = out[2]
    assert breath.length_rows == 4
    assert breath.metadata.get("silence_budget_breath_ext") == "true"
    p2_steps = [s for s in out if s.metadata.get("phrase_id") == "p2"]
    assert all(s.velocity == 0.8 for s in p2_steps)


def test_breath_chosen_over_tacet() -> None:
    steps = [
        _step(0, 8, phrase_id="p1", velocity=0.0),
        _breath(8, 2),
        _step(10, 4, phrase_id="p2", velocity=0.8),
    ]
    rule = SilenceBudgetRule(target_density=0.7, threshold=1.0)
    scene = _scene(steps)
    rendered = rule.apply(scene, k=1.0, seeds=None, roles=None)
    out = rendered.pattern.lanes[0].steps
    assert out[1].metadata.get("silence_budget_breath_ext") == "true"
    assert out[2].velocity == 0.8


# --- budget reset ---

def test_budget_resets_after_trigger() -> None:
    steps = [
        _step(0, 4, phrase_id="p1", velocity=0.0),
        _step(4, 4, phrase_id="p1", velocity=0.0),
        _step(8, 4, phrase_id="p2", velocity=0.8),
        _step(12, 4, phrase_id="p3", velocity=0.8),
    ]
    rule = SilenceBudgetRule(target_density=0.7, threshold=1.0)
    scene = _scene(steps)
    rendered = rule.apply(scene, k=1.0, seeds=None, roles=None)
    out = rendered.pattern.lanes[0].steps
    p2 = [s for s in out if s.metadata.get("phrase_id") == "p2"]
    p3 = [s for s in out if s.metadata.get("phrase_id") == "p3"]
    assert all(s.velocity == 0.0 for s in p2)
    assert all(s.velocity == 0.8 for s in p3)


# --- edge cases ---

def test_k_zero_unchanged() -> None:
    steps = [_step(0, 4, phrase_id="p1"), _step(4, 4, phrase_id="p2")]
    scene = _scene(steps)
    rendered = SilenceBudgetRule().apply(scene, k=0.0, seeds=None, roles=None)
    assert rendered is scene


def test_single_phrase_unchanged() -> None:
    steps = [_step(0, 4), _step(4, 4)]
    scene = _scene(steps)
    rendered = SilenceBudgetRule(threshold=0.01).apply(scene, k=1.0, seeds=None, roles=None)
    out = rendered.pattern.lanes[0].steps
    assert all(s.velocity == 0.8 for s in out)


def test_ostinato_unchanged() -> None:
    steps = [
        _step(0, 4, phrase_id="p1", velocity=0.0),
        _step(4, 4, phrase_id="p2", velocity=0.8),
    ]
    scene = _scene(steps, role="ostinato")
    rendered = SilenceBudgetRule(threshold=0.1).apply(scene, k=1.0, seeds=None, roles=None)
    out = rendered.pattern.lanes[0].steps
    assert out[1].velocity == 0.8


def test_percussion_unchanged() -> None:
    steps = [
        _step(0, 4, phrase_id="p1", velocity=0.0),
        _step(4, 4, phrase_id="p2", velocity=0.8),
    ]
    scene = _scene(steps, role="perc")
    rendered = SilenceBudgetRule(threshold=0.1).apply(scene, k=1.0, seeds=None, roles=None)
    out = rendered.pattern.lanes[0].steps
    assert out[1].velocity == 0.8


def test_k_scales_accumulation() -> None:
    steps = [
        _step(0, 4, phrase_id="p1", velocity=0.0),
        _step(4, 4, phrase_id="p2", velocity=0.8),
    ]
    rule = SilenceBudgetRule(target_density=0.7, threshold=2.0)
    scene = _scene(steps)
    rendered_low = rule.apply(scene, k=0.3, seeds=None, roles=None)
    rendered_high = rule.apply(scene, k=1.0, seeds=None, roles=None)
    out_low = rendered_low.pattern.lanes[0].steps
    out_high = rendered_high.pattern.lanes[0].steps
    low_tacet = any(s.metadata.get("silence_budget_tacet") for s in out_low)
    high_tacet = any(s.metadata.get("silence_budget_tacet") for s in out_high)
    assert high_tacet and not low_tacet


def test_song_level_apply() -> None:
    from senseweave.music_tracker import TrackerSong

    steps = [
        _step(0, 8, phrase_id="p1", velocity=0.0),
        _step(8, 4, phrase_id="p2", velocity=0.8),
    ]
    scene = _scene(steps)
    song = TrackerSong(title="test", scenes=[scene])
    rule = SilenceBudgetRule(target_density=0.7, threshold=1.0)
    rendered = rule.apply(song, k=1.0, seeds=None, roles=None)
    out = rendered.scenes[0].pattern.lanes[0].steps
    assert out[1].metadata.get("silence_budget_tacet") == "true"
