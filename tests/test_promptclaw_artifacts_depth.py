"""Depth-2 tests for promptclaw.artifacts [frac-0040]."""

from __future__ import annotations

from pathlib import Path

import pytest

from promptclaw.artifacts import ArtifactManager
from promptclaw.config import default_project_config
from promptclaw.models import Event
from promptclaw.paths import ProjectPaths


ARTIFACTS_MODULE_PATH = Path("promptclaw/artifacts.py")


def _make_manager(tmp_path: Path) -> ArtifactManager:
    config = default_project_config("Artifact Claw")
    paths = ProjectPaths(project_root=tmp_path, config=config)
    manager = ArtifactManager(paths, run_id="run-0040")
    manager.create_run_layout()
    return manager


def test_read_events_round_trips_appended_events(tmp_path: Path) -> None:
    manager = _make_manager(tmp_path)
    first = Event(
        timestamp="2026-05-02T00:00:00+00:00",
        event_type="run_started",
        message="Run created",
        phase="bootstrap",
        agent="codex",
        role="lead",
        extra={"task": "frac-0040"},
    )
    second = Event(
        timestamp="2026-05-02T00:00:30+00:00",
        event_type="route_decided",
        message="Picked codex",
        phase="routing",
        agent="codex",
        role="lead",
    )

    manager.append_event(first)
    manager.append_event(second)

    events = manager.read_events()

    assert len(events) == 2
    assert events[0] == first
    assert events[1] == second


def test_read_events_returns_empty_when_log_missing(tmp_path: Path) -> None:
    manager = _make_manager(tmp_path)

    assert manager.read_events() == []


def test_write_helpers_reject_empty_filename(tmp_path: Path) -> None:
    manager = _make_manager(tmp_path)

    with pytest.raises(ValueError):
        manager.write_prompt("", "content")
    with pytest.raises(ValueError):
        manager.write_output("   ", "content")
    with pytest.raises(ValueError):
        manager.write_handoff("", "content")
    with pytest.raises(ValueError):
        manager.write_summary("", "content")


def test_write_helpers_accept_normal_filenames(tmp_path: Path) -> None:
    manager = _make_manager(tmp_path)

    prompt_path = manager.write_prompt("lead-codex.md", "prompt body")
    output_path = manager.write_output("lead-codex.md", "output body")
    handoff_path = manager.write_handoff("handoff.md", "handoff body")
    summary_path = manager.write_summary("final-summary.md", "summary body")

    assert prompt_path.read_text(encoding="utf-8") == "prompt body"
    assert output_path.read_text(encoding="utf-8") == "output body"
    assert handoff_path.read_text(encoding="utf-8") == "handoff body"
    assert summary_path.read_text(encoding="utf-8") == "summary body"


def test_artifacts_module_reaches_depth_two() -> None:
    from sdp.fractal import classify_depth

    result = classify_depth(ARTIFACTS_MODULE_PATH)

    assert result.depth >= 2, result.reason
