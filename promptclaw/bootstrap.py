from __future__ import annotations

from pathlib import Path

from .orchestrator import PromptClawOrchestrator
from .templates import project_scaffold
from .utils import ensure_dir, read_text, write_text


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
