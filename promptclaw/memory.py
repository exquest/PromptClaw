from __future__ import annotations

from pathlib import Path

from .models import RunState
from .paths import ProjectPaths
from .utils import append_text, ensure_dir, read_text

class MemoryStore:
    def __init__(self, paths: ProjectPaths) -> None:
        self.paths = paths

    def read(self) -> str:
        return read_text(self.paths.memory_file)

    def append_run_summary(self, state: RunState, summary_text: str) -> None:
        ensure_dir(self.paths.memory_root)
        block = (
            f"\n## Run {state.run_id}\n"
            f"- Title: {state.title}\n"
            f"- Status: {state.status}\n"
            f"- Lead: {state.lead_agent or 'n/a'}\n"
            f"- Verifier: {state.verifier_agent or 'n/a'}\n"
            f"- Final phase: {state.current_phase}\n\n"
            f"{summary_text.strip()}\n"
        )
        append_text(self.paths.memory_file, block)
