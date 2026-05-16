from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .models import Event
from .paths import ProjectPaths
from .utils import append_text, ensure_dir, write_json, write_text

RUN_SUMMARY_JSON_FILENAME = "run-summary.json"
RUN_SUMMARY_JSON_REQUIRED_KEYS: tuple[str, ...] = ("workflow", "status", "tool", "action")


@dataclass(frozen=True)
class ArtifactFileStatus:
    name: str
    path: Path
    exists: bool
    size_bytes: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "path": str(self.path),
            "exists": self.exists,
            "size_bytes": self.size_bytes,
        }


@dataclass(frozen=True)
class ArtifactRunReport:
    run_id: str
    root: Path
    files: tuple[ArtifactFileStatus, ...]
    event_count: int
    latest_event_type: str

    def as_dict(self) -> dict[str, Any]:
        files: dict[str, dict[str, Any]] = {}
        present_count = 0
        missing_files: list[str] = []
        for status in self.files:
            files[status.name] = status.as_dict()
            if status.exists:
                present_count += 1
            else:
                missing_files.append(status.name)
        return {
            "run_id": self.run_id,
            "root": str(self.root),
            "files": files,
            "present_count": present_count,
            "missing_count": len(missing_files),
            "missing_files": missing_files,
            "event_count": self.event_count,
            "latest_event_type": self.latest_event_type,
        }


class ArtifactManager:
    def __init__(self, paths: ProjectPaths, run_id: str) -> None:
        self.paths = paths
        self.run_id = run_id

    def create_run_layout(self) -> None:
        layout = self.paths.run_layout(self.run_id)
        for directory in layout.directories:
            ensure_dir(directory)
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
        if not filename.strip():
            raise ValueError("prompt filename required")
        path = self.paths.run_prompts(self.run_id) / filename
        write_text(path, content)
        return path

    def write_output(self, filename: str, content: str) -> Path:
        if not filename.strip():
            raise ValueError("output filename required")
        path = self.paths.run_outputs(self.run_id) / filename
        write_text(path, content)
        return path

    def write_handoff(self, filename: str, content: str) -> Path:
        if not filename.strip():
            raise ValueError("handoff filename required")
        path = self.paths.run_handoffs(self.run_id) / filename
        write_text(path, content)
        return path

    def write_summary(self, filename: str, content: str) -> Path:
        if not filename.strip():
            raise ValueError("summary filename required")
        path = self.paths.run_summary(self.run_id) / filename
        write_text(path, content)
        return path

    def write_run_summary_json(
        self,
        *,
        workflow: str,
        status: str,
        tool: list[str],
        action: list[str],
    ) -> Path:
        if not workflow.strip():
            raise ValueError("workflow required")
        if not status.strip():
            raise ValueError("status required")
        path = self.paths.run_summary(self.run_id) / RUN_SUMMARY_JSON_FILENAME
        write_json(path, {
            "workflow": workflow,
            "status": status,
            "tool": list(tool),
            "action": list(action),
        })
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

    def read_events(self) -> list[Event]:
        path = self.paths.run_logs(self.run_id) / "events.jsonl"
        if not path.exists():
            return []
        events: list[Event] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            d = json.loads(line)
            events.append(Event(
                timestamp=d.get("timestamp", ""),
                event_type=d.get("event_type", ""),
                message=d.get("message", ""),
                phase=d.get("phase", ""), agent=d.get("agent", ""), role=d.get("role", ""),
                extra=dict(d.get("extra") or {}),
            ))
        return events

    def _file_status(self, name: str, path: Path) -> ArtifactFileStatus:
        if path.exists():
            size_bytes = path.stat().st_size
            return ArtifactFileStatus(
                name=name,
                path=path,
                exists=True,
                size_bytes=size_bytes,
            )
        return ArtifactFileStatus(
            name=name,
            path=path,
            exists=False,
            size_bytes=0,
        )

    def build_run_report(self) -> ArtifactRunReport:
        layout = self.paths.run_layout(self.run_id)
        file_statuses: list[ArtifactFileStatus] = []
        for name, path in layout.files:
            file_statuses.append(self._file_status(name, path))
        events = self.read_events()
        latest_event_type = ""
        if events:
            latest_event_type = events[-1].event_type
        return ArtifactRunReport(
            run_id=self.run_id,
            root=layout.root,
            files=tuple(file_statuses),
            event_count=len(events),
            latest_event_type=latest_event_type,
        )
