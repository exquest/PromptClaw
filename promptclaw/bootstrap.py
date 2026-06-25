from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .coherence.models import CoherenceConfig
from .config import CONFIG_FILENAME
from .orchestrator import PromptClawOrchestrator
from .templates import (
    coherence_protocol_section,
    default_constitution_text,
    project_scaffold,
)
from .utils import ensure_dir, read_json, read_text, write_text


@dataclass(frozen=True)
class UpgradeReport:
    project_root: str
    dry_run: bool
    force: bool
    planned_paths: tuple[str, ...]
    written_paths: tuple[str, ...]
    unchanged_paths: tuple[str, ...]


def init_project(project_root: Path, name: str) -> list[Path]:
    ensure_dir(project_root)
    created: list[Path] = []
    for relative_path, content in project_scaffold(name).items():
        path = project_root / relative_path
        write_text(path, content)
        created.append(path)
    return created


def bootstrap_task_from_prompts(project_root: Path) -> str:
    vision = read_text(project_root / "prompts/00-project-vision.md").strip()
    roles = read_text(project_root / "prompts/01-agent-roles.md").strip()
    routing = read_text(project_root / "prompts/02-routing-rules.md").strip()
    startup_profile = read_text(project_root / "docs/STARTUP_PROFILE.md").strip()
    return (
        "# Bootstrap a custom PromptClaw\n\n"
        "Use the following materials to improve this PromptClaw project.\n\n"
        "## Project vision\n"
        f"{vision}\n\n"
        "## Agent roles\n"
        f"{roles}\n\n"
        "## Routing rules\n"
        f"{routing}\n\n"
        + (
            "## Startup profile\n"
            f"{startup_profile}\n\n"
            if startup_profile
            else ""
        )
        + "## Required outcome\n"
        "Produce a concrete blueprint for this custom PromptClaw, including orchestration behavior, "
        "prompt structure, memory strategy, handoff policy, and recommended artifacts.\n"
    )


def bootstrap_project(project_root: Path) -> str:
    orchestrator = PromptClawOrchestrator(project_root)
    task_text = bootstrap_task_from_prompts(project_root)
    state = orchestrator.run(task_text=task_text, title="Bootstrap PromptClaw")
    return state.run_id


def upgrade_project(project_root: Path, *, dry_run: bool = False, force: bool = False) -> UpgradeReport:
    """Add coherence assets to an existing PromptClaw project without clobbering it."""
    ensure_dir(project_root)
    planned_writes: list[tuple[str, str]] = []
    unchanged_paths: list[str] = []

    config_file = project_root / CONFIG_FILENAME
    raw_config = read_json(config_file)
    if not isinstance(raw_config, dict):
        raise FileNotFoundError(f"Missing config: {config_file}")

    upgraded_config = _merge_coherence_config(raw_config)
    if upgraded_config != raw_config:
        planned_writes.append((CONFIG_FILENAME, _json_config_text(upgraded_config)))
    else:
        unchanged_paths.append(CONFIG_FILENAME)

    constitution_path = project_root / "constitution.yaml"
    if constitution_path.exists():
        unchanged_paths.append("constitution.yaml")
    else:
        planned_writes.append(("constitution.yaml", default_constitution_text()))

    for relative_path, content in _agent_prompt_templates(raw_config).items():
        path = project_root / relative_path
        if not path.exists():
            planned_writes.append((relative_path, content))
            continue
        if force:
            existing = path.read_text(encoding="utf-8")
            refreshed = _refresh_agent_protocol_section(existing)
            if refreshed != existing:
                planned_writes.append((relative_path, refreshed))
                continue
        unchanged_paths.append(relative_path)

    planned_paths = tuple(relative_path for relative_path, _content in planned_writes)
    written_paths: list[str] = []
    if not dry_run:
        for relative_path, content in planned_writes:
            write_text(project_root / relative_path, content)
            written_paths.append(relative_path)

    return UpgradeReport(
        project_root=str(project_root),
        dry_run=dry_run,
        force=force,
        planned_paths=planned_paths,
        written_paths=tuple(written_paths),
        unchanged_paths=tuple(unchanged_paths),
    )


def _json_config_text(config: dict[str, Any]) -> str:
    return json.dumps(config, indent=2, ensure_ascii=False) + "\n"


def _merge_coherence_config(raw_config: dict[str, Any]) -> dict[str, Any]:
    default_coherence = asdict(CoherenceConfig())
    existing = raw_config.get("coherence")
    if existing is None:
        coherence = default_coherence
    elif isinstance(existing, dict):
        coherence = {**default_coherence, **existing}
    else:
        raise ValueError("promptclaw.json coherence must be an object")

    upgraded = dict(raw_config)
    upgraded["coherence"] = coherence
    return upgraded


def _agent_prompt_templates(raw_config: dict[str, Any]) -> dict[str, str]:
    project = raw_config.get("project", {})
    project_name = "PromptClaw"
    if isinstance(project, dict) and isinstance(project.get("name"), str):
        project_name = project["name"]
    return {
        path: content
        for path, content in project_scaffold(project_name).items()
        if path.startswith("prompts/agents/")
    }


def _refresh_agent_protocol_section(existing: str) -> str:
    section = coherence_protocol_section().rstrip() + "\n"
    headings = (
        "## Coherence — standing instructions",
        "## Coherence - standing instructions",
    )
    found_indexes = [existing.find(heading) for heading in headings if existing.find(heading) >= 0]
    if found_indexes:
        start = min(found_indexes)
        prefix = existing[:start].rstrip()
        if prefix:
            return prefix + "\n\n" + section
        return section
    if existing.strip():
        return existing.rstrip() + "\n\n" + section
    return section
