"""Tests for `promptclaw upgrade <repo>` coherence adoption."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from promptclaw import cli
from promptclaw.bootstrap import upgrade_project


def _write_existing_config(project_root: Path) -> None:
    project_root.mkdir(parents=True, exist_ok=True)
    (project_root / "promptclaw.json").write_text(
        json.dumps(
            {
                "project": {"name": "Existing Claw", "description": "Keep this"},
                "agents": {
                    "local": {
                        "enabled": True,
                        "kind": "mock",
                        "instruction_file": "prompts/agents/local.md",
                    }
                },
                "custom": {"preserve": True},
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def _read_config(project_root: Path) -> dict[str, object]:
    return json.loads((project_root / "promptclaw.json").read_text(encoding="utf-8"))


def test_upgrade_project_adds_coherence_assets_and_is_idempotent(tmp_path: Path) -> None:
    project_root = tmp_path / "repo"
    _write_existing_config(project_root)

    report = upgrade_project(project_root)

    assert report.dry_run is False
    assert set(report.written_paths) == {
        "promptclaw.json",
        "constitution.yaml",
        "prompts/agents/codex.md",
        "prompts/agents/claude.md",
        "prompts/agents/gemini.md",
    }
    config = _read_config(project_root)
    assert config["custom"] == {"preserve": True}
    assert config["agents"] == {
        "local": {
            "enabled": True,
            "kind": "mock",
            "instruction_file": "prompts/agents/local.md",
        }
    }
    coherence = config["coherence"]
    assert isinstance(coherence, dict)
    assert coherence["enabled"] is True
    assert coherence["constitution_path"] == "constitution.yaml"
    assert (project_root / "constitution.yaml").exists()
    assert (project_root / "prompts/agents/codex.md").exists()

    second = upgrade_project(project_root)

    assert second.planned_paths == ()
    assert second.written_paths == ()


def test_upgrade_project_dry_run_previews_writes_without_mutating(tmp_path: Path) -> None:
    project_root = tmp_path / "repo"
    _write_existing_config(project_root)

    report = upgrade_project(project_root, dry_run=True)

    assert report.dry_run is True
    assert set(report.planned_paths) == {
        "promptclaw.json",
        "constitution.yaml",
        "prompts/agents/codex.md",
        "prompts/agents/claude.md",
        "prompts/agents/gemini.md",
    }
    assert report.written_paths == ()
    assert "coherence" not in _read_config(project_root)
    assert not (project_root / "constitution.yaml").exists()
    assert not (project_root / "prompts").exists()


def test_upgrade_project_force_refreshes_only_agent_protocol_section(tmp_path: Path) -> None:
    project_root = tmp_path / "repo"
    _write_existing_config(project_root)
    agent_path = project_root / "prompts/agents/codex.md"
    agent_path.parent.mkdir(parents=True)
    agent_path.write_text(
        "# Custom Codex\n\n"
        "Keep this local operating note.\n\n"
        "## Coherence - standing instructions\n\n"
        "old protocol text\n",
        encoding="utf-8",
    )

    report = upgrade_project(project_root, force=True)

    assert "prompts/agents/codex.md" in report.written_paths
    updated = agent_path.read_text(encoding="utf-8")
    assert updated.startswith("# Custom Codex\n\nKeep this local operating note.\n\n")
    assert "old protocol text" not in updated
    assert "## Coherence" in updated
    assert "```decision" in updated


def test_cli_upgrade_dry_run_outputs_planned_writes(tmp_path: Path) -> None:
    project_root = tmp_path / "repo"
    _write_existing_config(project_root)

    with patch("promptclaw.cli._bootstrap_runtime_identity"), patch("sys.stdout") as stdout:
        assert cli.main(["upgrade", str(project_root), "--dry-run"]) == 0

    output = "".join(call.args[0] for call in stdout.write.call_args_list)
    payload = json.loads(output)
    assert payload["dry_run"] is True
    assert "constitution.yaml" in payload["planned_paths"]
    assert not (project_root / "constitution.yaml").exists()
