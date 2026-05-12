"""Artifact run report tests for frac-0043."""

from __future__ import annotations

import json
from pathlib import Path

from promptclaw.artifacts import ArtifactManager, ArtifactRunReport
from promptclaw.config import default_project_config
from promptclaw.models import Event
from promptclaw.paths import ProjectPaths


ARTIFACTS_MODULE_PATH = Path("promptclaw/artifacts.py")


def _make_manager(tmp_path: Path) -> ArtifactManager:
    config = default_project_config("Artifact Report Claw")
    paths = ProjectPaths(project_root=tmp_path, config=config)
    manager = ArtifactManager(paths, run_id="run-0043")
    manager.create_run_layout()
    return manager


def test_build_run_report_summarizes_written_artifacts_and_events(tmp_path: Path) -> None:
    manager = _make_manager(tmp_path)
    manager.write_task("Deepen artifact reporting.")
    manager.write_route_json({"lead_agent": "codex"})
    manager.write_route_markdown("# Route\n")
    manager.append_event(
        Event(
            timestamp="2026-05-02T15:00:00+00:00",
            event_type="run_started",
            message="Run created",
            phase="routing",
            agent="codex",
            role="lead",
        )
    )
    manager.append_event(
        Event(
            timestamp="2026-05-02T15:01:00+00:00",
            event_type="route_decided",
            message="Route decided",
            phase="routing",
            agent="codex",
            role="lead",
        )
    )

    report = manager.build_run_report()
    files_by_name = {item.name: item for item in report.files}

    assert isinstance(report, ArtifactRunReport)
    assert report.run_id == "run-0043"
    assert report.root == manager.paths.run_root("run-0043")
    assert report.event_count == 2
    assert report.latest_event_type == "route_decided"
    assert files_by_name["task"].exists is True
    assert files_by_name["task"].size_bytes == len("Deepen artifact reporting.".encode("utf-8"))
    assert files_by_name["route_json"].exists is True
    assert files_by_name["route_markdown"].exists is True
    assert files_by_name["events"].exists is True
    assert files_by_name["state"].exists is False
    assert files_by_name["state"].size_bytes == 0


def test_run_report_as_dict_is_json_safe_and_counts_files(tmp_path: Path) -> None:
    manager = _make_manager(tmp_path)
    manager.write_task("Summarize artifacts.")
    manager.append_event(
        Event(
            timestamp="2026-05-02T15:02:00+00:00",
            event_type="run_started",
            message="Run created",
        )
    )

    data = manager.build_run_report().as_dict()

    json.dumps(data)
    assert data["run_id"] == "run-0043"
    assert data["root"] == str(manager.paths.run_root("run-0043"))
    assert data["event_count"] == 1
    assert data["latest_event_type"] == "run_started"
    assert data["present_count"] == 2
    assert data["missing_count"] == 3
    assert data["missing_files"] == ["route_json", "route_markdown", "state"]
    assert data["files"]["task"]["path"] == str(manager.paths.run_input("run-0043") / "task.md")
    assert data["files"]["events"]["exists"] is True


def test_artifacts_module_stays_depth_two_for_frac_0043() -> None:
    from sdp.fractal import classify_depth

    result = classify_depth(ARTIFACTS_MODULE_PATH)

    assert result.depth >= 2, result.reason
