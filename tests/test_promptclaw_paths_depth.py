"""Depth-2 tests for promptclaw.paths [frac-0041]."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from promptclaw.artifacts import ArtifactManager
from promptclaw.config import default_project_config
from promptclaw.models import Event
from promptclaw.paths import ProjectPaths, RunPathLayout


PATHS_MODULE_PATH = Path("promptclaw/paths.py")


def _make_paths(tmp_path: Path) -> ProjectPaths:
    config = default_project_config("Paths Claw")
    return ProjectPaths(project_root=tmp_path, config=config)


def test_run_layout_matches_existing_path_helpers(tmp_path: Path) -> None:
    paths = _make_paths(tmp_path)
    run_id = "run-0041"

    layout = paths.run_layout(run_id)
    files = dict(layout.files)

    assert isinstance(layout, RunPathLayout)
    assert paths.artifact_root == tmp_path / ".promptclaw"
    assert paths.runs_root == tmp_path / ".promptclaw" / "runs"
    assert paths.memory_file == tmp_path / ".promptclaw" / "memory" / "project-memory.md"
    assert paths.coherence_db == tmp_path / ".promptclaw" / "coherence.db"
    assert layout.run_id == run_id
    assert layout.root == paths.run_root(run_id)
    assert layout.directories == (
        paths.run_root(run_id),
        paths.run_input(run_id),
        paths.run_routing(run_id),
        paths.run_prompts(run_id),
        paths.run_outputs(run_id),
        paths.run_handoffs(run_id),
        paths.run_summary(run_id),
        paths.run_logs(run_id),
    )
    assert files == {
        "task": paths.run_input(run_id) / "task.md",
        "route_json": paths.run_routing(run_id) / "route.json",
        "route_markdown": paths.run_routing(run_id) / "route.md",
        "state": paths.run_state(run_id),
        "events": paths.run_logs(run_id) / "events.jsonl",
    }


def test_path_summary_is_json_safe_and_meaningful(tmp_path: Path) -> None:
    paths = _make_paths(tmp_path)

    summary = paths.path_summary(run_id="run-0041")

    json.dumps(summary)
    assert summary["project_root"] == str(tmp_path)
    assert summary["artifact_root"] == str(paths.artifact_root)
    assert summary["prompts_root"] == str(paths.prompts_root)
    assert summary["memory_file"] == str(paths.memory_file)
    assert summary["run"]["run_id"] == "run-0041"
    assert summary["run"]["root"] == str(paths.run_root("run-0041"))
    assert summary["run"]["directories"] == [str(path) for path in paths.run_layout("run-0041").directories]
    assert summary["run"]["files"]["events"] == str(paths.run_logs("run-0041") / "events.jsonl")


def test_ensure_run_layout_creates_directories_for_artifact_manager(tmp_path: Path) -> None:
    paths = _make_paths(tmp_path)
    run_id = "run-0041"

    layout = paths.ensure_run_layout(run_id)

    for directory in layout.directories:
        assert directory.is_dir()
    assert paths.memory_root.is_dir()

    manager = ArtifactManager(paths, run_id=run_id)
    manager.create_run_layout()
    task_path = manager.write_task("Implement paths.")
    manager.append_event(
        Event(
            timestamp="2026-05-02T00:00:00+00:00",
            event_type="run_started",
            message="Run created",
        )
    )

    assert task_path == dict(layout.files)["task"]
    assert dict(layout.files)["events"].exists()


def test_empty_run_id_is_rejected_before_layout_creation(tmp_path: Path) -> None:
    paths = _make_paths(tmp_path)

    for run_id in ("", "   "):
        with pytest.raises(ValueError):
            paths.run_layout(run_id)
        with pytest.raises(ValueError):
            paths.ensure_run_layout(run_id)
        with pytest.raises(ValueError):
            paths.run_state(run_id)


def test_paths_module_reaches_depth_two() -> None:
    from sdp.fractal import classify_depth

    result = classify_depth(PATHS_MODULE_PATH)

    assert result.depth >= 2, result.reason
