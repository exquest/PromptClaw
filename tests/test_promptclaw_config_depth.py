"""Depth-2 tests for promptclaw.config [frac-0046]."""

from __future__ import annotations

import json
from pathlib import Path

import sdp.fractal as fractal
from promptclaw.config import (
    CONFIG_FILENAME,
    ConfigStatusReport,
    config_path,
    config_status_report,
    default_project_config,
    enabled_agents,
    load_or_default,
    save_config,
    summarize_config,
    validate_config,
)
from promptclaw.models import AgentConfig


CONFIG_MODULE_PATH = Path("promptclaw/config.py")


def _config_with_mixed_agents():
    config = default_project_config("Config Claw")
    config.agents["zeta"] = AgentConfig(
        name="zeta",
        enabled=False,
        kind="mock",
        capabilities=["docs"],
    )
    config.agents["alpha"] = AgentConfig(
        name="alpha",
        enabled=True,
        kind="mock",
        capabilities=["coding"],
    )
    return config


def test_enabled_agents_returns_sorted_enabled_names() -> None:
    config = _config_with_mixed_agents()

    names = enabled_agents(config)

    assert isinstance(names, tuple)
    assert names == ("alpha", "claude", "codex", "gemini")


def test_config_status_report_summarizes_default_config() -> None:
    config = default_project_config("Status Claw")

    report = config_status_report(config)

    assert isinstance(report, ConfigStatusReport)
    assert report.project_name == "Status Claw"
    assert report.artifact_root == ".promptclaw"
    assert report.control_plane_mode == "heuristic"
    assert report.control_plane_agent == "claude"
    assert report.default_task_type == "general"
    assert report.agent_count == 3
    assert report.enabled_agent_names == ("claude", "codex", "gemini")
    assert report.disabled_agent_names == ()
    assert report.is_valid is True
    assert report.issues == ()


def test_config_status_report_reflects_validation_issues() -> None:
    config = default_project_config("Broken Claw")
    config.project.name = ""
    config.routing.max_retries = -1

    report = config_status_report(config)
    expected_issues = tuple(validate_config(config))

    assert report.is_valid is False
    assert report.issues == expected_issues
    assert "project.name must not be empty" in report.issues


def test_summarize_config_is_json_safe() -> None:
    config = _config_with_mixed_agents()
    config.agents["zeta"].enabled = False

    summary = summarize_config(config)

    json.dumps(summary)
    assert summary["project_name"] == "Config Claw"
    assert summary["control_plane_mode"] == "heuristic"
    assert summary["control_plane_agent"] == "claude"
    assert summary["enabled_agent_names"] == ["alpha", "claude", "codex", "gemini"]
    assert summary["disabled_agent_names"] == ["zeta"]
    assert summary["agent_count"] == 5
    assert summary["is_valid"] is True
    assert summary["issues"] == []


def test_load_or_default_returns_persisted_or_defaults(tmp_path: Path) -> None:
    persisted_root = tmp_path / "persisted"
    persisted_root.mkdir()
    persisted_config = default_project_config("Persisted Claw")
    save_config(persisted_root, persisted_config)
    assert config_path(persisted_root).exists()

    loaded = load_or_default(persisted_root)
    assert loaded.project.name == "Persisted Claw"

    fresh_root = tmp_path / "fresh"
    fresh_root.mkdir()
    assert not (fresh_root / CONFIG_FILENAME).exists()

    defaulted = load_or_default(fresh_root, project_name="Fresh Claw")
    assert defaulted.project.name == "Fresh Claw"
    assert "claude" in defaulted.agents
    assert not (fresh_root / CONFIG_FILENAME).exists()


def test_config_module_reaches_depth_two() -> None:
    module = fractal.classify_depth(CONFIG_MODULE_PATH)
    assert module.depth >= 2, (
        f"expected promptclaw/config.py depth >= 2, got {module.depth}: {module.reason}"
    )
