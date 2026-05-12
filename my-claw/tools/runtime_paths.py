"""Layout-aware runtime path resolution for CypherClaw."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class RuntimePaths:
    project_root: Path
    tools_dir: Path
    workspace_dir: Path
    tasks_dir: Path


def _candidate_roots(start: Path) -> list[Path]:
    current = start.resolve()
    if current.is_file():
        current = current.parent
    return [current, *current.parents]


def _looks_like_runtime_root(candidate: Path) -> bool:
    return (candidate / "tools").is_dir() and (candidate / "sdp").exists()


def resolve_runtime_root(anchor: str | Path) -> Path:
    """Resolve the CypherClaw runtime root for either tools/ or src/ layouts."""
    start = Path(anchor)
    for candidate in _candidate_roots(start):
        if _looks_like_runtime_root(candidate):
            return candidate
    current = start.resolve()
    if current.is_file():
        current = current.parent
    if current.name == "tools":
        return current.parent
    if current.name == "cypherclaw" and current.parent.name == "src":
        return current.parent.parent
    return current


def resolve_runtime_paths(anchor: str | Path) -> RuntimePaths:
    """Resolve shared runtime directories independent of code layout."""
    project_root = resolve_runtime_root(anchor)
    tools_dir = project_root / "tools"
    workspace_dir = tools_dir / "workspace"
    return RuntimePaths(
        project_root=project_root,
        tools_dir=tools_dir,
        workspace_dir=workspace_dir,
        tasks_dir=workspace_dir / "tasks",
    )
