from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .models import PromptClawConfig


@dataclass(frozen=True)
class RunPathLayout:
    run_id: str
    root: Path
    directories: tuple[Path, ...]
    files: tuple[tuple[str, Path], ...]

    def as_dict(self) -> dict[str, Any]:
        files: dict[str, str] = {}
        for name, path in self.files:
            files[name] = str(path)
        return {
            "run_id": self.run_id,
            "root": str(self.root),
            "directories": [str(path) for path in self.directories],
            "files": files,
        }


@dataclass(frozen=True)
class ProjectPaths:
    project_root: Path
    config: PromptClawConfig
    artifact_root: Path = field(init=False)
    runs_root: Path = field(init=False)
    memory_root: Path = field(init=False)
    memory_file: Path = field(init=False)
    prompts_root: Path = field(init=False)
    coherence_db: Path = field(init=False)
    constitution_file: Path = field(init=False)

    def __post_init__(self) -> None:
        artifact_root = self.project_root / self.config.artifacts.root
        values = {
            "artifact_root": artifact_root,
            "runs_root": artifact_root / "runs",
            "memory_root": artifact_root / "memory",
            "memory_file": artifact_root / "memory" / "project-memory.md",
            "prompts_root": self.project_root / "prompts",
            "coherence_db": artifact_root / "coherence.db",
            "constitution_file": self.project_root / "constitution.yaml",
        }
        for name, path in values.items():
            object.__setattr__(self, name, path)

    def _require_run_id(self, run_id: str) -> str:
        if not run_id.strip():
            raise ValueError("run_id required")
        return run_id

    def run_root(self, run_id: str) -> Path:
        if not run_id.strip():
            raise ValueError("run_id required")
        return self.runs_root / run_id

    def run_input(self, run_id: str) -> Path:
        if not run_id.strip():
            raise ValueError("run_id required")
        return self.runs_root / run_id / "input"

    def run_routing(self, run_id: str) -> Path:
        if not run_id.strip():
            raise ValueError("run_id required")
        return self.runs_root / run_id / "routing"

    def run_prompts(self, run_id: str) -> Path:
        if not run_id.strip():
            raise ValueError("run_id required")
        return self.runs_root / run_id / "prompts"

    def run_outputs(self, run_id: str) -> Path:
        if not run_id.strip():
            raise ValueError("run_id required")
        return self.runs_root / run_id / "outputs"

    def run_handoffs(self, run_id: str) -> Path:
        if not run_id.strip():
            raise ValueError("run_id required")
        return self.runs_root / run_id / "handoffs"

    def run_summary(self, run_id: str) -> Path:
        if not run_id.strip():
            raise ValueError("run_id required")
        return self.runs_root / run_id / "summary"

    def run_logs(self, run_id: str) -> Path:
        if not run_id.strip():
            raise ValueError("run_id required")
        return self.runs_root / run_id / "logs"

    def run_state(self, run_id: str) -> Path:
        if not run_id.strip():
            raise ValueError("run_id required")
        return self.runs_root / run_id / "state.json"

    def run_layout(self, run_id: str) -> RunPathLayout:
        run_id = self._require_run_id(run_id)
        root = self.runs_root / run_id
        directories = (
            root,
            root / "input",
            root / "routing",
            root / "prompts",
            root / "outputs",
            root / "handoffs",
            root / "summary",
            root / "logs",
        )
        files = (
            ("task", root / "input" / "task.md"),
            ("route_json", root / "routing" / "route.json"),
            ("route_markdown", root / "routing" / "route.md"),
            ("state", root / "state.json"),
            ("events", root / "logs" / "events.jsonl"),
        )
        return RunPathLayout(run_id=run_id, root=root, directories=directories, files=files)

    def ensure_run_layout(self, run_id: str) -> RunPathLayout:
        layout = self.run_layout(run_id)
        for directory in (*layout.directories, self.memory_root):
            directory.mkdir(parents=True, exist_ok=True)
        return layout

    def path_summary(self, run_id: str | None = None) -> dict[str, Any]:
        summary: dict[str, Any] = {
            "project_root": str(self.project_root),
            "artifact_root": str(self.artifact_root),
            "runs_root": str(self.runs_root),
            "memory_root": str(self.memory_root),
            "memory_file": str(self.memory_file),
            "prompts_root": str(self.prompts_root),
            "coherence_db": str(self.coherence_db),
            "constitution_file": str(self.constitution_file),
        }
        if run_id is not None:
            summary["run"] = self.run_layout(run_id).as_dict()
        return summary
