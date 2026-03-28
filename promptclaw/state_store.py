from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

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


class EventSourcedStateStore:
    """State store that derives RunState by replaying coherence events."""

    def __init__(self, paths: ProjectPaths, coherence_engine: Any) -> None:
        self.paths = paths
        self.coherence = coherence_engine

    def save(self, state: RunState) -> None:
        """No-op — state is derived from events, not written.

        Still writes JSON as a cache/backup for backward compatibility.
        """
        write_json(self.paths.run_state(state.run_id), asdict(state))

    def load(self, run_id: str) -> RunState:
        """Replay events to reconstruct state."""
        events = self.coherence.replay(run_id)
        if not events:
            # Fall back to JSON state file
            return StateStore(self.paths).load(run_id)
        return self._derive_state(events, run_id)

    def _derive_state(self, events: list[Any], run_id: str) -> RunState:
        """Fold coherence events into a RunState."""
        status = "running"
        title = ""
        created_at = ""
        updated_at = ""
        current_phase = ""
        task_text = ""
        lead_agent = ""
        verifier_agent = ""
        route_decision: dict[str, Any] = {}
        clarification_question: str | None = None
        final_summary_path = ""
        retries_used = 0
        run_events: list[Event] = []
        errors: list[dict[str, Any]] = []
        recovery_actions: list[str] = []
        coherence_violations: list[dict[str, Any]] = []
        enforcement_mode = "monitor"

        for ev in events:
            ts = ev.timestamp
            if not created_at:
                created_at = ts
            updated_at = ts

            # Build the RunState Event list from coherence events
            run_events.append(Event(
                timestamp=ev.timestamp,
                event_type=ev.event_type,
                message=ev.payload.get("message", ""),
                phase=ev.phase,
                agent=ev.agent,
                role=ev.role,
            ))

            etype = ev.event_type
            payload = ev.payload or {}

            if etype == "run_started":
                title = payload.get("message", "").replace("Run created for '", "").rstrip("'")
                status = "running"
                current_phase = "routing"

            elif etype == "route_decided":
                current_phase = "routing"
                if "decision" in payload:
                    route_decision = payload["decision"]
                    lead_agent = route_decision.get("lead_agent", lead_agent)
                    verifier_agent = route_decision.get("verifier_agent", verifier_agent) or ""

            elif etype == "coherence.post_routing":
                # Post-routing hook carries the decision in its extra payload
                if "decision" in payload:
                    route_decision = payload["decision"]
                    lead_agent = route_decision.get("lead_agent", lead_agent)
                    verifier_agent = route_decision.get("verifier_agent", verifier_agent) or ""

            elif etype == "awaiting_user":
                status = "awaiting_user"
                current_phase = "clarification"

            elif etype == "lead_complete":
                current_phase = "lead"

            elif etype == "verify_complete":
                current_phase = "verify"

            elif etype == "retry_complete":
                current_phase = "retry"
                retries_used += 1

            elif etype == "run_complete":
                status = "complete"
                current_phase = "complete"

            elif etype in ("routing_error", "lead_error", "verify_error"):
                errors.append({
                    "phase": ev.phase,
                    "error_type": etype,
                    "message": payload.get("message", ""),
                })

        return RunState(
            run_id=run_id,
            title=title,
            status=status,
            current_phase=current_phase,
            created_at=created_at,
            updated_at=updated_at,
            task_text=task_text,
            lead_agent=lead_agent,
            verifier_agent=verifier_agent,
            route_decision=route_decision,
            clarification_question=clarification_question,
            final_summary_path=final_summary_path,
            retries_used=retries_used,
            events=run_events,
            errors=errors,
            recovery_actions=recovery_actions,
            coherence_violations=coherence_violations,
            enforcement_mode=enforcement_mode,
        )

    def list_runs(self) -> list[RunState]:
        """List all runs from the event store."""
        all_events = self.coherence.event_store.replay_all()
        # Group events by run_id
        runs_map: dict[str, list[Any]] = {}
        for ev in all_events:
            runs_map.setdefault(ev.run_id, []).append(ev)

        states: list[RunState] = []
        for rid, evts in runs_map.items():
            states.append(self._derive_state(evts, rid))

        return sorted(states, key=lambda s: s.created_at)
