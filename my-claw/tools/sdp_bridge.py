"""Bridge between CypherClaw daemon and sdp-cli pipeline engine.

Provides a simplified interface for creating tasks, running the sdp-cli
pipeline, and querying task status — all callable from the daemon.
"""

from __future__ import annotations

import hashlib
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

# Try to import sdp-cli — graceful fallback if not installed
try:
    from sdp.config.settings import load_settings, SDPSettings
    from sdp.pipeline.task_queue import TaskQueue, ImportedTaskSpec
    from sdp.orchestrator import run_single_task, RunOutcome
    from sdp._cli_impl import _build_agents
    from sdp.pipeline.failover import choose_verify_agent
    SDP_AVAILABLE = True
except ImportError:
    SDP_AVAILABLE = False

from sdp_runtime import select_agent_pair


@dataclass
class TaskResult:
    """Result of a completed pipeline task."""
    task_id: str
    success: bool
    outcome: str  # "success", "gate_failure", "verify_fail", "timeout", etc.
    lead_agent: str
    verify_agent: str
    duration_seconds: float
    errors: list[str] = field(default_factory=list)
    summary: str = ""


class SDPBridge:
    """Simplified interface to sdp-cli's pipeline for CypherClaw."""

    def __init__(
        self,
        project_root: str | Path,
        on_progress: Callable | None = None,
        quota_monitor=None,
    ):
        self.project_root = Path(project_root)
        self.on_progress = on_progress  # callback(task_id, phase, message)
        self.quota_monitor = quota_monitor
        self._settings: SDPSettings | None = None
        self._agents: dict[str, Any] | None = None
        self._queue: TaskQueue | None = None

        if SDP_AVAILABLE:
            try:
                os.chdir(str(self.project_root))
                self._settings = load_settings()
                self._agents = _build_agents(self._settings)
                db_path = str(self._settings.state_db_path)
                self._queue = TaskQueue(db_path=db_path)
            except Exception:
                # sdp-cli might not be configured for this project
                self._settings = None

    @property
    def available(self) -> bool:
        return SDP_AVAILABLE and self._settings is not None

    def _require_settings(self) -> SDPSettings:
        if self._settings is None:
            raise RuntimeError("sdp-cli settings are unavailable")
        return self._settings

    def _require_agents(self) -> dict[str, Any]:
        if self._agents is None:
            raise RuntimeError("sdp-cli agents are unavailable")
        return self._agents

    def _require_queue(self) -> TaskQueue:
        if self._queue is None:
            raise RuntimeError("sdp-cli queue is unavailable")
        return self._queue

    def create_task(self, description: str, tier: str = "T1",
                    criteria: str = "") -> str | None:
        """Create a single task. Returns task_id or None if unavailable."""
        if not self.available:
            return None
        queue = self._require_queue()

        task_id = f"T-{hashlib.md5(f'{description}{time.time()}'.encode()).hexdigest()[:6]}"
        spec = ImportedTaskSpec(
            task_id=task_id,
            description=description,
            tier=tier,
            complexity_score=self._estimate_complexity(description),
            criteria=criteria,
            dependencies=[],
        )
        queue.import_task_specs([spec], if_exists="replace")
        return task_id

    def create_tasks(self, specs: list[dict]) -> list[str]:
        """Create multiple tasks. Each spec: {description, tier, criteria, depends_on}.
        Returns list of task_ids."""
        if not self.available:
            return []
        queue = self._require_queue()

        task_ids = []
        import_specs = []
        for i, s in enumerate(specs):
            desc = s["description"]
            tid = f"T-{hashlib.md5(f'{desc}{time.time()}{i}'.encode()).hexdigest()[:6]}"
            task_ids.append(tid)
            import_specs.append(ImportedTaskSpec(
                task_id=tid,
                description=s["description"],
                tier=s.get("tier", "T1"),
                complexity_score=self._estimate_complexity(s["description"]),
                criteria=s.get("criteria", ""),
                dependencies=s.get("depends_on", []),
            ))
        queue.import_task_specs(import_specs, if_exists="replace")
        return task_ids

    def run_next(self) -> TaskResult | None:
        """Execute the next pending task through the full pipeline."""
        if not self.available:
            return None
        queue = self._require_queue()
        agents = self._require_agents()
        settings = self._require_settings()

        task = queue.get_next_pending()
        if not task:
            return None

        if self.on_progress:
            self.on_progress(task.task_id, "starting", f"Running: {task.description[:60]}")

        available_agents = tuple(agents.keys())
        quota_monitor = getattr(self, "quota_monitor", None)
        if quota_monitor is not None:
            try:
                filtered_agents = tuple(quota_monitor.get_available_agents(available_agents))
                if filtered_agents:
                    available_agents = filtered_agents
            except Exception:
                pass

        lead_name, verify_name = select_agent_pair(
            getattr(task, "lead_agent", None),
            available_agents,
            choose_verify_agent=choose_verify_agent if SDP_AVAILABLE else None,
        )
        lead = agents.get(lead_name)
        if lead is None:
            lead_name, lead = next(iter(agents.items()))
        verifier = agents.get(verify_name, lead)
        if verifier is lead and verify_name not in agents:
            verify_name = lead_name

        try:
            result = run_single_task(
                task=task,
                lead=lead,
                verifier=verifier,
                lead_name=lead_name,
                verify_name=verify_name,
                settings=settings,
            )

            return TaskResult(
                task_id=task.task_id,
                success=result.outcome == RunOutcome.SUCCESS,
                outcome=result.outcome.name if hasattr(result.outcome, 'name') else str(result.outcome),
                lead_agent=lead_name,
                verify_agent=verify_name,
                duration_seconds=result.duration_seconds,
                errors=result.errors,
                summary=result.verdict or "",
            )
        except Exception as e:
            return TaskResult(
                task_id=task.task_id,
                success=False,
                outcome="error",
                lead_agent=lead_name,
                verify_agent=verify_name,
                duration_seconds=0,
                errors=[str(e)],
            )

    def run_all(self) -> list[TaskResult]:
        """Execute all pending tasks sequentially."""
        results = []
        while True:
            result = self.run_next()
            if result is None:
                break
            results.append(result)
            if self.on_progress:
                status = "✅" if result.success else "❌"
                self.on_progress(
                    result.task_id, "complete",
                    f"{status} {result.task_id}: {result.outcome}"
                )
        return results

    def get_queue_status(self) -> dict:
        """Get current task queue status."""
        if not self.available:
            return {"available": False}
        queue = self._require_queue()

        tasks = queue.list_all()
        return {
            "available": True,
            "total": len(tasks),
            "pending": sum(1 for t in tasks if t.status == "pending"),
            "running": sum(1 for t in tasks if t.status == "running"),
            "complete": sum(1 for t in tasks if t.status == "complete"),
            "blocked": sum(1 for t in tasks if t.status == "blocked"),
            "tasks": [{"id": t.task_id, "status": t.status, "description": t.description[:60]} for t in tasks[-10:]],
        }

    def _estimate_complexity(self, description: str) -> int:
        """Simple complexity heuristic based on description length and keywords."""
        score = min(len(description) // 20, 30)  # longer = more complex
        complex_words = ["architecture", "refactor", "migration", "integration", "pipeline", "security"]
        for word in complex_words:
            if word in description.lower():
                score += 10
        return min(score, 100)
