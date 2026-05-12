"""Tests for the performance-worm logger."""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools"))

from senseweave.render.worm import (
    MECHANICAL_AREA_THRESHOLD,
    SATURATION_AREA_THRESHOLD,
    WormResult,
    compute_worm,
    convex_hull_area,
    emit_worm,
)


def test_convex_hull_area_triangle() -> None:
    points = [(0.0, 0.0), (4.0, 0.0), (0.0, 3.0)]
    assert convex_hull_area(points) == 6.0


def test_convex_hull_area_square() -> None:
    points = [(0.0, 0.0), (2.0, 0.0), (2.0, 2.0), (0.0, 2.0)]
    assert convex_hull_area(points) == 4.0


def test_convex_hull_area_collinear_returns_zero() -> None:
    points = [(0.0, 0.0), (1.0, 1.0), (2.0, 2.0)]
    assert convex_hull_area(points) == 0.0


def test_convex_hull_area_fewer_than_three_unique_returns_zero() -> None:
    assert convex_hull_area([(1.0, 1.0), (1.0, 1.0)]) == 0.0
    assert convex_hull_area([(1.0, 1.0)]) == 0.0
    assert convex_hull_area([]) == 0.0


def test_mechanical_worm_is_rejected() -> None:
    result = compute_worm(
        "test-mechanical",
        tempo=[120.0, 120.1, 120.0, 119.9],
        loudness=[64.0, 64.1, 64.0, 63.9],
    )
    assert result.rejected
    assert result.rejection_reason is not None
    assert "point-worm" in result.rejection_reason
    assert result.hull_area < MECHANICAL_AREA_THRESHOLD


def test_space_filling_worm_is_rejected() -> None:
    result = compute_worm(
        "test-spacefill",
        tempo=[60.0, 200.0, 60.0, 200.0, 130.0],
        loudness=[0.0, 127.0, 127.0, 0.0, 64.0],
        saturation_threshold=SATURATION_AREA_THRESHOLD,
    )
    assert result.rejected
    assert result.rejection_reason is not None
    assert "space-filling" in result.rejection_reason
    assert result.hull_area > SATURATION_AREA_THRESHOLD


def test_expressive_worm_is_accepted() -> None:
    result = compute_worm(
        "test-expressive",
        tempo=[118.0, 122.0, 125.0, 120.0, 116.0, 119.0],
        loudness=[60.0, 68.0, 72.0, 65.0, 58.0, 63.0],
    )
    assert not result.rejected
    assert result.rejection_reason is None
    assert MECHANICAL_AREA_THRESHOLD <= result.hull_area <= SATURATION_AREA_THRESHOLD


def test_compute_worm_truncates_to_shorter_series() -> None:
    result = compute_worm("trunc", tempo=[100.0, 110.0], loudness=[50.0])
    assert len(result.points) == 1


def test_emit_worm_writes_json(tmp_path: object) -> None:
    result = compute_worm(
        "emit-test",
        tempo=[100.0, 110.0, 105.0, 115.0],
        loudness=[50.0, 70.0, 60.0, 80.0],
    )
    out = emit_worm(result, artifacts_dir=tmp_path)
    json_path = out / "worm.json"
    assert json_path.exists()

    data = json.loads(json_path.read_text(encoding="utf-8"))
    assert data["piece_id"] == "emit-test"
    assert isinstance(data["hull_area"], float)
    assert isinstance(data["points"], list)
    assert len(data["points"]) == 4


def test_emit_worm_creates_piece_subdirectory(tmp_path: object) -> None:
    result = WormResult(
        piece_id="subdir-test",
        points=((1.0, 2.0), (3.0, 4.0), (5.0, 6.0)),
        hull_area=2.0,
        rejected=False,
    )
    out = emit_worm(result, artifacts_dir=tmp_path)
    assert out.name == "subdir-test"
    assert out.parent.name == "worms"
