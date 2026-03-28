from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .models import PromptClawConfig

@dataclass(frozen=True)
class ProjectPaths:
    project_root: Path
    config: PromptClawConfig

    @property
    def artifact_root(self) -> Path:
        return self.project_root / self.config.artifacts.root

    @property
    def runs_root(self) -> Path:
        return self.artifact_root / "runs"

    @property
    def memory_root(self) -> Path:
        return self.artifact_root / "memory"

    @property
    def memory_file(self) -> Path:
        return self.memory_root / "project-memory.md"

    @property
    def prompts_root(self) -> Path:
        return self.project_root / "prompts"

    @property
    def coherence_db(self) -> Path:
        return self.artifact_root / "coherence.db"

    @property
    def constitution_file(self) -> Path:
        return self.project_root / "constitution.yaml"

    def run_root(self, run_id: str) -> Path:
        return self.runs_root / run_id

    def run_input(self, run_id: str) -> Path:
        return self.run_root(run_id) / "input"

    def run_routing(self, run_id: str) -> Path:
        return self.run_root(run_id) / "routing"

    def run_prompts(self, run_id: str) -> Path:
        return self.run_root(run_id) / "prompts"

    def run_outputs(self, run_id: str) -> Path:
        return self.run_root(run_id) / "outputs"

    def run_handoffs(self, run_id: str) -> Path:
        return self.run_root(run_id) / "handoffs"

    def run_summary(self, run_id: str) -> Path:
        return self.run_root(run_id) / "summary"

    def run_logs(self, run_id: str) -> Path:
        return self.run_root(run_id) / "logs"

    def run_state(self, run_id: str) -> Path:
        return self.run_root(run_id) / "state.json"
