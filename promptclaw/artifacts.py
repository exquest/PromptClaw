from __future__ import annotations

import json
from pathlib import Path

from .models import Event
from .paths import ProjectPaths
from .utils import append_text, ensure_dir, write_json, write_text

class ArtifactManager:
    def __init__(self, paths: ProjectPaths, run_id: str) -> None:
        self.paths = paths
        self.run_id = run_id

    def create_run_layout(self) -> None:
        ensure_dir(self.paths.run_root(self.run_id))
        ensure_dir(self.paths.run_input(self.run_id))
        ensure_dir(self.paths.run_routing(self.run_id))
        ensure_dir(self.paths.run_prompts(self.run_id))
        ensure_dir(self.paths.run_outputs(self.run_id))
        ensure_dir(self.paths.run_handoffs(self.run_id))
        ensure_dir(self.paths.run_summary(self.run_id))
        ensure_dir(self.paths.run_logs(self.run_id))
        ensure_dir(self.paths.memory_root)

    def write_task(self, task_text: str) -> Path:
        path = self.paths.run_input(self.run_id) / "task.md"
        write_text(path, task_text)
        return path

    def write_route_json(self, data: dict) -> Path:
        path = self.paths.run_routing(self.run_id) / "route.json"
        write_json(path, data)
        return path

    def write_route_markdown(self, markdown: str) -> Path:
        path = self.paths.run_routing(self.run_id) / "route.md"
        write_text(path, markdown)
        return path

    def write_prompt(self, filename: str, content: str) -> Path:
        path = self.paths.run_prompts(self.run_id) / filename
        write_text(path, content)
        return path

    def write_output(self, filename: str, content: str) -> Path:
        path = self.paths.run_outputs(self.run_id) / filename
        write_text(path, content)
        return path

    def write_handoff(self, filename: str, content: str) -> Path:
        path = self.paths.run_handoffs(self.run_id) / filename
        write_text(path, content)
        return path

    def write_summary(self, filename: str, content: str) -> Path:
        path = self.paths.run_summary(self.run_id) / filename
        write_text(path, content)
        return path

    def append_event(self, event: Event) -> Path:
        path = self.paths.run_logs(self.run_id) / "events.jsonl"
        append_text(path, json.dumps({
            "timestamp": event.timestamp,
            "event_type": event.event_type,
            "message": event.message,
            "phase": event.phase,
            "agent": event.agent,
            "role": event.role,
            "extra": event.extra,
        }, ensure_ascii=False) + "\n")
        return path
