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
from senseweave.render.rules.metric_accent import (
    METRIC_ACCENT_4_4,
    MetricAccentRule,
    metric_accent_table,
)


def _scene_for_role(role: str) -> TrackerScene:
    steps = [
        TrackerStep(row=row, length_rows=1, scale_degree=1, velocity=0.5)
        for row in range(16)
    ]
    lane = TrackerLane(name=role, role=role, voice="pluck", steps=steps)
    return TrackerScene(
        name="fixture",
        key="C",
        tempo_bpm=120.0,
        rows_per_beat=4,
        pattern=TrackerPattern(rows=16, lanes=[lane]),
        constraints=SceneConstraint(max_polyphony=1, allowed_roles=(role,)),
        metadata={"groove_meter": "4/4"},
    )


def test_metric_accent_matches_4_4_table_on_melody() -> None:
    scene = _scene_for_role("melody")

    rendered = MetricAccentRule().apply(scene, k=1.0, seeds=None, roles=None)

    melody = rendered.pattern.lanes[0]
    assert [step.velocity for step in melody.steps] == [
        round(0.5 * multiplier, 3) for multiplier in METRIC_ACCENT_4_4
    ]


def test_metric_accent_leaves_ostinato_unchanged() -> None:
    scene = _scene_for_role("ostinato")

    rendered = MetricAccentRule().apply(scene, k=1.0, seeds=None, roles=None)

    ostinato = rendered.pattern.lanes[0]
    assert [step.velocity for step in ostinato.steps] == [0.5] * 16


def test_metric_accent_leaves_grid_locked_melody_unchanged() -> None:
    scene = _scene_for_role("melody")
    scene.pattern.lanes[0].metadata["grid_locked"] = "true"

    rendered = MetricAccentRule().apply(scene, k=1.0, seeds=None, roles=None)

    melody = rendered.pattern.lanes[0]
    assert [step.velocity for step in melody.steps] == [0.5] * 16


def test_metric_accent_tables_follow_supported_meters() -> None:
    assert metric_accent_table("4/4") == METRIC_ACCENT_4_4
    assert len(metric_accent_table("3/4")) == 12
    assert len(metric_accent_table("6/8")) == 12
    assert len(metric_accent_table("5/4")) == 20
    assert len(metric_accent_table("7/8")) == 14
