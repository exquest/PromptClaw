#!/usr/bin/env python3
"""Summarize workspace repos for PromptClaw startup."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable


DEFAULT_STATE_PATH = Path(".promptclaw/STATE.json")
DEFAULT_REGISTRY_PATH = Path(".promptclaw/workspace_registry.json")

BranchResolver = Callable[[Path], str | None]


def _read_json_file(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return {}


def resolve_workspace_config(state_path: Path) -> dict[str, Any]:
    state = _read_json_file(state_path)
    integrations = state.get("integrations")
    if not isinstance(integrations, dict):
        return {}
    workspace = integrations.get("workspace")
    return workspace if isinstance(workspace, dict) else {}


def resolve_registry_path(explicit_registry: str | None, state_path: Path) -> Path:
    if explicit_registry:
        return Path(explicit_registry).expanduser().resolve()

    config = resolve_workspace_config(state_path)
    configured = config.get("registry_path")
    if isinstance(configured, str) and configured.strip():
        return Path(configured).expanduser().resolve()

    return DEFAULT_REGISTRY_PATH.resolve()


def load_registry(path: Path) -> dict[str, Any]:
    registry = _read_json_file(path)
    projects = registry.get("projects")
    if not isinstance(projects, list):
        registry["projects"] = []
        return registry

    normalized: list[dict[str, Any]] = []
    for item in projects:
        if not isinstance(item, dict):
            continue
        project_id = str(item.get("id") or "").strip()
        display_name = str(item.get("display_name") or project_id).strip()
        repo_path = str(item.get("path") or "").strip()
        if not project_id or not repo_path:
            continue
        aliases = item.get("aliases")
        normalized.append(
            {
                "id": project_id,
                "display_name": display_name,
                "aliases": aliases if isinstance(aliases, list) else [],
                "path": repo_path,
                "priority": int(item.get("priority") or 99),
            }
        )

    registry["projects"] = sorted(normalized, key=lambda item: (item["priority"], item["display_name"].lower()))
    return registry


def normalize_alias(value: str) -> str:
    collapsed = re.sub(r"[\s_-]+", " ", value.strip().lower())
    return collapsed


def build_alias_index(registry: dict[str, Any]) -> dict[str, str]:
    alias_index: dict[str, str] = {}
    for project in registry.get("projects", []):
        if not isinstance(project, dict):
            continue
        project_id = str(project.get("id") or "").strip()
        display_name = str(project.get("display_name") or project_id).strip()
        if not project_id:
            continue
        names = [project_id, display_name]
        aliases = project.get("aliases")
        if isinstance(aliases, list):
            names.extend(str(alias).strip() for alias in aliases if str(alias).strip())
        for name in names:
            alias_index[normalize_alias(name)] = project_id
    return alias_index


def parse_progress_summary(text: str) -> dict[str, Any]:
    summary: dict[str, Any] = {}

    progress_match = re.search(
        r"Progress:\s*\[[^\]]*\]\s*(\d+)%\s+(\d+)\s*/\s*(\d+)\s+tasks complete",
        text,
    )
    if progress_match:
        progress_percent = int(progress_match.group(1))
        completed = int(progress_match.group(2))
        total = int(progress_match.group(3))
        summary["progress_percent"] = progress_percent
        summary["completed"] = completed
        summary["total"] = total
        summary["headline"] = f"{progress_percent}% {completed}/{total} complete"

    counts_match = re.search(r"^\s*completed:\s*(.+)$", text, re.MULTILINE)
    if counts_match:
        counts: dict[str, int] = {}
        for part in counts_match.group(1).split(","):
            key, _, raw_value = part.strip().partition(":")
            if not key or not raw_value.strip().isdigit():
                continue
            counts[key.strip().lower().replace("-", "_")] = int(raw_value.strip())
        if counts:
            summary["counts"] = counts

    task_match = re.search(r"^- \*\*(.+?)\*\*:\s*([^-]+?)\s+—\s+(.+)$", text, re.MULTILINE)
    if task_match:
        summary["first_task"] = {
            "task_id": task_match.group(1).strip(),
            "status": task_match.group(2).strip(),
            "details": task_match.group(3).strip(),
        }

    current_task_match = re.search(r"^## Current Task:\s*(.+)$", text, re.MULTILINE)
    if current_task_match:
        current_task = current_task_match.group(1).strip()
        summary["current_task"] = current_task
        summary.setdefault("headline", f"Current task: {current_task}")

    classification_match = re.search(r"^## Classification:\s*(.+)$", text, re.MULTILINE)
    if classification_match:
        summary["classification"] = classification_match.group(1).strip()

    phase_match = re.search(r"^## Phase:\s*(.+)$", text, re.MULTILINE)
    if phase_match:
        summary["phase"] = phase_match.group(1).strip()

    return summary


def parse_session_notes_summary(text: str) -> dict[str, Any]:
    heading_match = re.search(r"^##\s+(.+)$", text, re.MULTILINE)
    if not heading_match:
        return {}
    return {"latest_heading": heading_match.group(1).strip()}


def resolve_git_branch(repo_path: Path) -> str | None:
    if not (repo_path / ".git").exists():
        return None

    try:
        result = subprocess.run(  # noqa: S603
            ["git", "-C", str(repo_path), "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return None

    if result.returncode != 0:
        return None
    branch = result.stdout.strip()
    return branch or None


def _resolve_project_path(project: dict[str, Any]) -> Path:
    return Path(str(project.get("path") or "")).expanduser().resolve()


def build_project_snapshot(
    project: dict[str, Any],
    *,
    branch_resolver: BranchResolver = resolve_git_branch,
) -> dict[str, Any]:
    repo_path = _resolve_project_path(project)
    exists = repo_path.exists()
    project_snapshot: dict[str, Any] = {
        "id": project["id"],
        "display_name": project["display_name"],
        "aliases": list(project.get("aliases", [])),
        "priority": project.get("priority", 99),
        "path": str(repo_path),
        "exists": exists,
        "git_branch": branch_resolver(repo_path) if exists else None,
    }

    files = {
        "sdp_toml": exists and (repo_path / "sdp.toml").is_file(),
        "project_plan": exists and (repo_path / "PROJECT_PLAN.md").is_file(),
        "progress": exists and (repo_path / "progress.md").is_file(),
        "session_notes": exists and (repo_path / "SESSION_NOTES.md").is_file(),
    }
    project_snapshot["files"] = files

    progress_summary = {}
    if files["progress"]:
        progress_summary = parse_progress_summary((repo_path / "progress.md").read_text(encoding="utf-8"))
    project_snapshot["progress"] = progress_summary

    session_summary = {}
    if files["session_notes"]:
        session_summary = parse_session_notes_summary(
            (repo_path / "SESSION_NOTES.md").read_text(encoding="utf-8")
        )
    project_snapshot["session_notes"] = session_summary

    if files["sdp_toml"] or (exists and (repo_path / ".sdp").exists()):
        status_source = "sdp"
    elif files["progress"]:
        status_source = "progress"
    else:
        status_source = "docs"
    project_snapshot["status_source"] = status_source

    return project_snapshot


def build_workspace_snapshot(
    registry_path: Path,
    *,
    branch_resolver: BranchResolver = resolve_git_branch,
    checked_at: str | None = None,
) -> dict[str, Any]:
    registry = load_registry(registry_path)
    projects = [
        build_project_snapshot(project, branch_resolver=branch_resolver)
        for project in registry.get("projects", [])
        if isinstance(project, dict)
    ]
    missing_projects = [project["id"] for project in projects if not project.get("exists")]

    timestamp = checked_at or datetime.now(UTC).isoformat().replace("+00:00", "Z")
    return {
        "checked_at": timestamp,
        "registry_path": str(registry_path),
        "project_count": len(projects),
        "alias_index": build_alias_index(registry),
        "projects": projects,
        "missing_projects": missing_projects,
    }


def _render_text(payload: dict[str, Any]) -> str:
    lines = ["Workspace snapshot"]
    for project in payload.get("projects", []):
        display_name = project.get("display_name", "unknown")
        branch = project.get("git_branch") or "no-git"
        source = project.get("status_source") or "unknown"
        headline = ""
        progress = project.get("progress")
        if isinstance(progress, dict):
            headline = str(progress.get("headline") or "").strip()
        if not headline:
            session_notes = project.get("session_notes")
            if isinstance(session_notes, dict):
                headline = str(session_notes.get("latest_heading") or "").strip()
        summary = f"{display_name} [{branch}] source={source}"
        if headline:
            summary = f"{summary} :: {headline}"
        lines.append(f"- {summary}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Summarize PromptClaw workspace repos.")
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of text.")
    parser.add_argument("--registry", help="Override the workspace registry path.")
    parser.add_argument(
        "--state-path",
        default=str(DEFAULT_STATE_PATH),
        help="Path to PromptClaw STATE.json (default: %(default)s)",
    )
    args = parser.parse_args(argv)

    state_path = Path(args.state_path)
    registry_path = resolve_registry_path(args.registry, state_path)
    payload = build_workspace_snapshot(registry_path)

    if args.json:
        json.dump(payload, sys.stdout, indent=2)
        sys.stdout.write("\n")
    else:
        sys.stdout.write(f"{_render_text(payload)}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
