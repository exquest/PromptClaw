from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from .models import RunState
from .paths import ProjectPaths
from .utils import append_text, ensure_dir, read_text

_RUN_HEADER_RE = re.compile(r"^## Run (?P<run_id>.+?)\s*$")
_BULLET_RE = re.compile(r"^- (?P<key>[^:]+):\s*(?P<value>.*)$")
_BULLET_FIELDS: dict[str, str] = {
    "Title": "title",
    "Status": "status",
    "Lead": "lead_agent",
    "Verifier": "verifier_agent",
    "Final phase": "final_phase",
}


@dataclass(frozen=True)
class MemoryEntry:
    run_id: str
    title: str
    status: str
    lead_agent: str
    verifier_agent: str
    final_phase: str
    body: str


def format_run_block(state: RunState, summary_text: str) -> str:
    lead = state.lead_agent or "n/a"
    verifier = state.verifier_agent or "n/a"
    body = summary_text.strip()
    return (
        f"\n## Run {state.run_id}\n"
        f"- Title: {state.title}\n- Status: {state.status}\n"
        f"- Lead: {lead}\n- Verifier: {verifier}\n"
        f"- Final phase: {state.current_phase}\n\n{body}\n"
    )


def parse_memory_log(text: str) -> tuple[MemoryEntry, ...]:
    entries: list[MemoryEntry] = []
    current: str | None = None
    fields: dict[str, str] = {}
    body_lines: list[str] = []
    body_started = False
    for raw in text.splitlines():
        header = _RUN_HEADER_RE.match(raw)
        if header:
            if current is not None:
                entries.append(_finalize_entry(current, fields, body_lines))
            current = header.group("run_id").strip()
            fields, body_lines, body_started = {}, [], False
            continue
        if current is None:
            continue
        if not body_started:
            bullet = _BULLET_RE.match(raw)
            if bullet is not None:
                attr = _BULLET_FIELDS.get(bullet.group("key").strip())
                if attr is not None:
                    fields[attr] = bullet.group("value").strip()
                    continue
            if raw.strip() == "":
                continue
            body_started = True
        body_lines.append(raw)
    if current is not None:
        entries.append(_finalize_entry(current, fields, body_lines))
    return tuple(entries)


def _finalize_entry(
    run_id: str, fields: dict[str, str], body_lines: list[str]
) -> MemoryEntry:
    title = fields.get("title", "")
    status = fields.get("status", "")
    lead = fields.get("lead_agent", "")
    verifier = fields.get("verifier_agent", "")
    final_phase = fields.get("final_phase", "")
    body = "\n".join(body_lines).strip()
    return MemoryEntry(run_id, title, status, lead, verifier, final_phase, body)


def summarize_memory_log(text: str) -> dict[str, Any]:
    entries = parse_memory_log(text)
    statuses: dict[str, int] = {}
    leads: dict[str, int] = {}
    for entry in entries:
        if entry.status:
            statuses[entry.status] = statuses.get(entry.status, 0) + 1
        if entry.lead_agent and entry.lead_agent != "n/a":
            leads[entry.lead_agent] = leads.get(entry.lead_agent, 0) + 1
    return {
        "entry_count": len(entries),
        "latest_run_id": entries[-1].run_id if entries else "",
        "statuses": dict(sorted(statuses.items())),
        "lead_agents": dict(sorted(leads.items())),
    }


class MemoryStore:
    def __init__(self, paths: ProjectPaths) -> None:
        self.paths = paths

    def read(self) -> str:
        return read_text(self.paths.memory_file)

    def append_run_summary(self, state: RunState, summary_text: str) -> None:
        ensure_dir(self.paths.memory_root)
        block = format_run_block(state, summary_text)
        append_text(self.paths.memory_file, block)

    def entries(self) -> tuple[MemoryEntry, ...]:
        text = self.read()
        if not text:
            return ()
        return parse_memory_log(text)

    def latest_entry(self) -> MemoryEntry | None:
        results = self.entries()
        if not results:
            return None
        return results[-1]

    def summary(self) -> dict[str, Any]:
        return summarize_memory_log(self.read())
