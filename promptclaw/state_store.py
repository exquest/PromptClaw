from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from .models import Event, RunState
from .paths import ProjectPaths
from .utils import read_json, write_json

class StateStore:
    def __init__(self, paths: ProjectPaths) -> None:
        self.paths = paths

    def save(self, state: RunState) -> None:
        write_json(self.paths.run_state(state.run_id), asdict(state))

    def load(self, run_id: str) -> RunState:
        raw = read_json(self.paths.run_state(run_id))
        if raw is None:
            raise FileNotFoundError(f"Missing state for run {run_id}")
        events = [Event(**item) for item in raw.get("events", [])]
        return RunState(
            run_id=raw["run_id"],
            title=raw["title"],
            status=raw["status"],
            current_phase=raw["current_phase"],
            created_at=raw["created_at"],
            updated_at=raw["updated_at"],
            task_text=raw["task_text"],
            lead_agent=raw.get("lead_agent", ""),
            verifier_agent=raw.get("verifier_agent", ""),
            route_decision=raw.get("route_decision", {}),
            clarification_question=raw.get("clarification_question"),
            final_summary_path=raw.get("final_summary_path", ""),
            retries_used=raw.get("retries_used", 0),
            events=events,
        )

    def list_runs(self) -> list[RunState]:
        runs: list[RunState] = []
        if not self.paths.runs_root.exists():
            return runs
        for state_file in sorted(self.paths.runs_root.glob("*/state.json")):
            raw = read_json(state_file)
            if not raw:
                continue
            events = [Event(**item) for item in raw.get("events", [])]
            runs.append(
                RunState(
                    run_id=raw["run_id"],
                    title=raw["title"],
                    status=raw["status"],
                    current_phase=raw["current_phase"],
                    created_at=raw["created_at"],
                    updated_at=raw["updated_at"],
                    task_text=raw["task_text"],
                    lead_agent=raw.get("lead_agent", ""),
                    verifier_agent=raw.get("verifier_agent", ""),
                    route_decision=raw.get("route_decision", {}),
                    clarification_question=raw.get("clarification_question"),
                    final_summary_path=raw.get("final_summary_path", ""),
                    retries_used=raw.get("retries_used", 0),
                    events=events,
                )
            )
        return sorted(runs, key=lambda item: item.created_at)
