"""Depth-2 narrative arc helpers — locked test surface for frac-0004."""

from __future__ import annotations

import importlib
import os
import sys
import time

import pytest


sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools"))


@pytest.fixture()
def arc():
    """Reload the narrative_arc module fresh for each test."""
    name = "inner_life.narrative_arc"
    if name in sys.modules:
        del sys.modules[name]
    module = importlib.import_module(name)
    yield module
    if name in sys.modules:
        del sys.modules[name]


@pytest.fixture()
def state():
    from inner_life.inner_state import InnerState

    return InnerState(cycle_started_at=time.time())


def test_phase_at_resolves_table_boundaries(arc) -> None:
    assert arc.phase_at(0.0) == "build"
    assert arc.phase_at(0.24) == "build"
    assert arc.phase_at(0.25) == "rise"
    assert arc.phase_at(0.5) == "climax"
    assert arc.phase_at(0.7) == "resolve"
    assert arc.phase_at(0.9) == "rest"
    assert arc.phase_at(1.0) == "rest"


def test_phase_at_clamps_out_of_range(arc) -> None:
    assert arc.phase_at(-0.5) == "build"
    assert arc.phase_at(1.5) == "rest"


def test_phase_progress_reports_within_phase_fraction(arc, state) -> None:
    state.arc_position = 0.375  # halfway through the rise phase (0.25..0.50)

    progress = arc.phase_progress(state)

    assert progress["position"] == pytest.approx(0.375)
    assert progress["phase"] == "rise"
    assert progress["phase_progress"] == pytest.approx(0.5, abs=1e-6)
    assert progress["cycle_progress"] == pytest.approx(0.375)


def test_phase_profile_combines_energy_and_action_weight(arc) -> None:
    profile = arc.phase_profile("climax")

    assert profile["phase"] == "climax"
    assert profile["energy"] == pytest.approx(arc.energy_for_phase("climax"))
    assert profile["action_weight"] == pytest.approx(arc.action_weight_for_phase("climax"))
    assert profile["label"] == "peaking"


def test_phase_profile_unknown_phase_uses_neutral_defaults(arc) -> None:
    profile = arc.phase_profile("nonsense")

    assert profile["phase"] == "nonsense"
    assert profile["energy"] == pytest.approx(0.5)
    assert profile["action_weight"] == pytest.approx(0.5)
    assert profile["label"] == "unknown"


def test_complete_cycle_aggregates_events_and_opinions(arc, state) -> None:
    state.cycle_id = 7
    state.cycle_started_at = time.time() - 60.0
    state.arc_position = 0.95
    state.arc_phase = "rest"
    state.mood = 0.42
    state.mode = "engaged"
    state.today_events = [
        {"time": 1.0, "type": "art_request", "detail": ""},
        {"time": 2.0, "type": "art_request", "detail": ""},
        {"time": 3.0, "type": "journal", "detail": ""},
        {"time": 4.0, "detail": "missing type"},
    ]
    state.opinions_formed = [
        {"time": 1.0, "about": "music", "opinion": "warm"},
        {"time": 2.0, "about": "weather", "opinion": "grey"},
    ]

    summary = arc.complete_cycle(state)

    assert summary["cycle_id"] == 7
    assert summary["events_count"] == 4
    assert summary["event_type_counts"] == {
        "art_request": 2,
        "journal": 1,
        "unknown": 1,
    }
    assert summary["opinions_count"] == 2
    assert summary["final_phase"] == "rest"
    assert summary["final_position"] == pytest.approx(0.95)
    assert summary["mood_at_end"] == pytest.approx(0.42)
    assert summary["mode_at_end"] == "engaged"
    assert summary["duration_s"] >= 60.0


def test_complete_cycle_handles_empty_history(arc, state) -> None:
    state.today_events = []
    state.opinions_formed = []

    summary = arc.complete_cycle(state)

    assert summary["events_count"] == 0
    assert summary["event_type_counts"] == {}
    assert summary["opinions_count"] == 0


def test_arc_summary_composes_progress_and_profile(arc, state) -> None:
    state.arc_position = 0.6
    state.arc_phase = "climax"

    summary = arc.arc_summary(state)

    assert summary["phase"] == "climax"
    assert summary["position"] == pytest.approx(0.6)
    assert summary["phase_progress"] == pytest.approx(0.5, abs=1e-6)
    assert summary["energy"] == pytest.approx(arc.energy_for_phase("climax"))
    assert summary["action_weight"] == pytest.approx(arc.action_weight_for_phase("climax"))
    assert summary["label"] == "peaking"


def test_module_reaches_depth_two(arc) -> None:
    sdp_src = "/Users/anthony/Programming/sdp-cli/src"
    if sdp_src not in sys.path:
        sys.path.insert(0, sdp_src)
    from sdp.fractal import classify_depth

    result = classify_depth("my-claw/tools/inner_life/narrative_arc.py")
    assert result.depth >= 2, f"expected depth >= 2, got {result.depth}: {result.reason}"
