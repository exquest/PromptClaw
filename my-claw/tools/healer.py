"""
PromptClaw Self-Healing Engine

Severity-based reactive healing for agent failures, missing deps,
process crashes, gate failures, server issues, and stale tasks.

Part of the Self-Improving System (Pillar 2).
"""

import re
import subprocess
import time
from dataclasses import dataclass
from typing import Callable, Optional


# ---------------------------------------------------------------------------
# Severity levels
# ---------------------------------------------------------------------------
SILENT = 1  # auto-fix, no notification
NOTIFY = 2  # auto-fix, notify Anthony after
ASK = 3     # ask Anthony before acting


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------
@dataclass
class Failure:
    type: str           # agent_error, missing_dep, process_crash, gate_failure, server_unhealthy, stale_task
    error_message: str
    context: dict       # agent, task_id, command, retry_count, etc.
    timestamp: float


@dataclass
class HealingResult:
    resolved: bool
    action_taken: str
    severity: int
    message: str        # human-readable summary for Telegram


# ---------------------------------------------------------------------------
# Healer
# ---------------------------------------------------------------------------
class Healer:
    """Self-healing engine with severity-based response."""

    SEVERITY_SILENT = SILENT
    SEVERITY_NOTIFY = NOTIFY
    SEVERITY_ASK = ASK

    # Agent fallback order
    AGENT_PREFERENCE = ["claude", "codex", "gemini"]

    def __init__(self, notify_fn: Callable[[str], None], ask_fn: Callable[[str], str]):
        """
        Args:
            notify_fn: sends a Telegram message (fire-and-forget)
            ask_fn:    sends a Telegram message and waits for Anthony's reply
        """
        self.notify_fn = notify_fn
        self.ask_fn = ask_fn

        # Track recent crash timestamps per process for crash-loop detection
        self._crash_history: dict[str, list[float]] = {}

        # Dispatch table: failure type -> handler
        self._handlers: dict[str, Callable[[Failure], HealingResult]] = {
            "agent_error": self._heal_agent_error,
            "missing_dep": self._heal_missing_dep,
            "process_crash": self._heal_process_crash,
            "gate_failure": self._heal_gate_failure,
            "server_unhealthy": self._heal_server_unhealthy,
            "stale_task": self._heal_stale_task,
        }

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def handle_failure(self, failure: Failure) -> HealingResult:
        """Main entry point. Classify, heal, notify/ask as needed."""
        severity = self.classify_severity(failure)

        handler = self._handlers.get(failure.type)
        if handler is None:
            return HealingResult(
                resolved=False,
                action_taken="no handler registered",
                severity=ASK,
                message=f"Unknown failure type '{failure.type}': {failure.error_message}",
            )

        # For ASK severity, get permission first
        if severity == ASK:
            answer = self.ask_fn(
                f"Healing needed ({failure.type}):\n"
                f"{failure.error_message}\n\n"
                f"Should I attempt auto-fix? (yes/no)"
            )
            if answer.strip().lower() not in ("yes", "y", "ok", "go", "do it"):
                return HealingResult(
                    resolved=False,
                    action_taken="user declined auto-fix",
                    severity=ASK,
                    message=f"Skipped healing for {failure.type} — Anthony said no.",
                )

        result = handler(failure)
        result.severity = severity

        # For NOTIFY severity, send a message after the fix
        if severity == NOTIFY:
            status = "resolved" if result.resolved else "UNRESOLVED"
            self.notify_fn(
                f"Healing [{status}] ({failure.type}):\n"
                f"{result.action_taken}\n"
                f"{result.message}"
            )

        return result

    def classify_severity(self, failure: Failure) -> int:
        """Rules-based severity classification."""
        ftype = failure.type
        ctx = failure.context
        retry_count = ctx.get("retry_count", 0)

        if ftype == "missing_dep":
            # Missing pip package -> SILENT (auto-install)
            return SILENT

        if ftype == "agent_error":
            if retry_count >= 3:
                # Agent failed 3+ times -> NOTIFY
                return NOTIFY
            # First try / early retries -> SILENT (retry)
            return SILENT

        if ftype == "gate_failure":
            if retry_count >= 3:
                # Gate failure 3+ times -> ASK
                return ASK
            # First time -> SILENT (retry with feedback)
            return SILENT

        if ftype == "server_unhealthy":
            rollback_failed = ctx.get("rollback_failed", False)
            if rollback_failed:
                return ASK
            # Auto-rollback if possible -> NOTIFY
            return NOTIFY

        if ftype == "process_crash":
            process_name = ctx.get("process", "unknown")
            now = failure.timestamp or time.time()
            history = self._crash_history.get(process_name, [])
            # Count crashes in the last 5 minutes
            window = 5 * 60
            recent = [t for t in history if now - t < window]
            if len(recent) >= 3:
                # Crash-looping (>3 in 5 min) -> ASK
                return ASK
            return SILENT

        if ftype == "stale_task":
            # Stale task (no progress 30+ min) -> NOTIFY (kill and report)
            return NOTIFY

        # Unknown failure type — be safe, ask
        return ASK

    # ------------------------------------------------------------------
    # Healing strategies
    # ------------------------------------------------------------------
    def _heal_agent_error(self, failure: Failure) -> HealingResult:
        """Retry agent, try alternate agents in preference order."""
        current_agent = failure.context.get("agent", "unknown")
        task_id = failure.context.get("task_id", "unknown")
        command = failure.context.get("command", "")

        # Build the fallback chain: same agent first, then alternates
        agents_to_try = [current_agent]
        for agent in self.AGENT_PREFERENCE:
            if agent != current_agent and agent not in agents_to_try:
                agents_to_try.append(agent)

        for agent in agents_to_try:
            success = self._try_run_agent(agent, command, task_id)
            if success:
                return HealingResult(
                    resolved=True,
                    action_taken=f"Retried with agent '{agent}'",
                    severity=SILENT,
                    message=f"Agent error on task {task_id} resolved by retrying with {agent}.",
                )

        return HealingResult(
            resolved=False,
            action_taken=f"Tried agents {agents_to_try}, all failed",
            severity=NOTIFY,
            message=f"Agent error on task {task_id} — all agents failed. Manual intervention needed.",
        )

    def _heal_missing_dep(self, failure: Failure) -> HealingResult:
        """Parse error for package name, pip install."""
        package = self._parse_package_name(failure.error_message)
        if not package:
            return HealingResult(
                resolved=False,
                action_taken="Could not parse package name from error",
                severity=NOTIFY,
                message=f"Missing dependency but couldn't identify package: {failure.error_message}",
            )

        # Try install methods in order
        install_methods = [
            (["/opt/anaconda3/bin/pip", "install", package], "conda pip"),
            (["pip3", "install", package], "system pip3"),
        ]

        for cmd, label in install_methods:
            try:
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=120,
                )
                if result.returncode == 0:
                    return HealingResult(
                        resolved=True,
                        action_taken=f"Installed '{package}' via {label}",
                        severity=SILENT,
                        message=f"Auto-installed missing package '{package}' using {label}.",
                    )
            except (FileNotFoundError, subprocess.TimeoutExpired):
                continue

        return HealingResult(
            resolved=False,
            action_taken=f"Failed to install '{package}' via all methods",
            severity=NOTIFY,
            message=f"Could not install '{package}'. Tried conda pip and system pip3.",
        )

    def _heal_process_crash(self, failure: Failure) -> HealingResult:
        """Check if process is running, restart if needed."""
        process_name = failure.context.get("process", "unknown")
        restart_cmd = failure.context.get("restart_command")
        now = failure.timestamp or time.time()

        # Record this crash
        if process_name not in self._crash_history:
            self._crash_history[process_name] = []
        self._crash_history[process_name].append(now)

        # Prune old entries (older than 10 minutes)
        cutoff = now - 600
        self._crash_history[process_name] = [
            t for t in self._crash_history[process_name] if t > cutoff
        ]

        # Check if already running
        if self._is_process_running(process_name):
            return HealingResult(
                resolved=True,
                action_taken=f"Process '{process_name}' is already running",
                severity=SILENT,
                message=f"Process '{process_name}' recovered on its own.",
            )

        # Try to restart
        if restart_cmd:
            try:
                subprocess.Popen(
                    restart_cmd if isinstance(restart_cmd, list) else restart_cmd.split(),
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                time.sleep(2)
                if self._is_process_running(process_name):
                    return HealingResult(
                        resolved=True,
                        action_taken=f"Restarted '{process_name}'",
                        severity=SILENT,
                        message=f"Process '{process_name}' restarted successfully.",
                    )
            except Exception as e:
                return HealingResult(
                    resolved=False,
                    action_taken=f"Restart command failed: {e}",
                    severity=NOTIFY,
                    message=f"Failed to restart '{process_name}': {e}",
                )

        return HealingResult(
            resolved=False,
            action_taken=f"No restart command available for '{process_name}'",
            severity=NOTIFY,
            message=f"Process '{process_name}' is down and no restart command is configured.",
        )

    def _heal_gate_failure(self, failure: Failure) -> HealingResult:
        """Feed error back to agent for retry."""
        agent = failure.context.get("agent", "claude")
        task_id = failure.context.get("task_id", "unknown")
        gate_output = failure.error_message

        # Build a retry prompt that includes the failure context
        retry_prompt = (
            f"The previous attempt failed gate checks. "
            f"Here is the gate output:\n\n{gate_output}\n\n"
            f"Please fix the issues and try again."
        )

        success = self._try_run_agent(agent, retry_prompt, task_id)
        if success:
            return HealingResult(
                resolved=True,
                action_taken=f"Retried '{agent}' with gate feedback",
                severity=SILENT,
                message=f"Gate failure on task {task_id} resolved by feeding error back to {agent}.",
            )

        # Try alternate agents with the feedback
        for alt_agent in self.AGENT_PREFERENCE:
            if alt_agent != agent:
                success = self._try_run_agent(alt_agent, retry_prompt, task_id)
                if success:
                    return HealingResult(
                        resolved=True,
                        action_taken=f"Retried with alternate agent '{alt_agent}' + gate feedback",
                        severity=SILENT,
                        message=f"Gate failure on task {task_id} resolved by {alt_agent} with error context.",
                    )

        return HealingResult(
            resolved=False,
            action_taken="All agents failed to pass gate after feedback",
            severity=ASK,
            message=f"Gate failure on task {task_id} — no agent could pass the gate. Needs human review.",
        )

    def _heal_server_unhealthy(self, failure: Failure) -> HealingResult:
        """Check health, rollback if recent deploy."""
        url = failure.context.get("url", "unknown")
        rollback_cmd = failure.context.get("rollback_command")
        project_dir = failure.context.get("project_dir")

        # First, re-check health (maybe it was transient)
        if self._check_server_health(url):
            return HealingResult(
                resolved=True,
                action_taken="Server recovered on recheck",
                severity=NOTIFY,
                message=f"Server at {url} was briefly unhealthy but recovered.",
            )

        # Try rollback if we have the info
        if rollback_cmd:
            try:
                result = subprocess.run(
                    rollback_cmd if isinstance(rollback_cmd, list) else rollback_cmd.split(),
                    capture_output=True,
                    text=True,
                    timeout=120,
                    cwd=project_dir,
                )
                if result.returncode == 0 and self._check_server_health(url):
                    return HealingResult(
                        resolved=True,
                        action_taken=f"Rolled back deployment at {url}",
                        severity=NOTIFY,
                        message=f"Server {url} was unhealthy. Rolled back successfully.",
                    )
            except Exception:
                pass

        # Rollback failed or unavailable
        return HealingResult(
            resolved=False,
            action_taken=f"Server unhealthy at {url}, rollback {'failed' if rollback_cmd else 'unavailable'}",
            severity=ASK,
            message=f"Server at {url} is DOWN. {'Rollback failed.' if rollback_cmd else 'No rollback command available.'} Manual intervention required.",
        )

    def _heal_stale_task(self, failure: Failure) -> HealingResult:
        """Kill orphaned process, restart or escalate."""
        task_id = failure.context.get("task_id", "unknown")
        pid = failure.context.get("pid")
        stale_minutes = failure.context.get("stale_minutes", 30)

        action_parts = []

        # Kill orphaned process if we have a PID
        if pid:
            try:
                import os
                import signal
                os.kill(pid, signal.SIGTERM)
                action_parts.append(f"Killed PID {pid}")
            except ProcessLookupError:
                action_parts.append(f"PID {pid} already dead")
            except PermissionError:
                action_parts.append(f"No permission to kill PID {pid}")

        # Try to restart the task
        restart_cmd = failure.context.get("restart_command")
        if restart_cmd:
            try:
                subprocess.Popen(
                    restart_cmd if isinstance(restart_cmd, list) else restart_cmd.split(),
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                action_parts.append("Restarted task")
                return HealingResult(
                    resolved=True,
                    action_taken="; ".join(action_parts),
                    severity=NOTIFY,
                    message=f"Task {task_id} was stale ({stale_minutes}min no progress). Killed and restarted.",
                )
            except Exception as e:
                action_parts.append(f"Restart failed: {e}")

        return HealingResult(
            resolved=False,
            action_taken="; ".join(action_parts) if action_parts else "No PID or restart command",
            severity=NOTIFY,
            message=f"Task {task_id} stale for {stale_minutes}min. {'; '.join(action_parts) if action_parts else 'Could not remediate.'}",
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _try_run_agent(self, agent: str, command: str, task_id: str) -> bool:
        """
        Attempt to run an agent command. Returns True on success.
        Placeholder — actual implementation will call the agent router.
        """
        # In production, this calls the daemon's agent runner.
        # For now, return False (no actual agents available in isolation).
        return False

    def _parse_package_name(self, error_message: str) -> Optional[str]:
        """Extract package name from common Python error messages."""
        # ModuleNotFoundError: No module named 'foobar'
        m = re.search(r"No module named ['\"]?(\w[\w.-]*)", error_message)
        if m:
            return m.group(1).split(".")[0]  # top-level package

        # ImportError: cannot import name 'X' from 'Y'
        m = re.search(r"cannot import name .+ from ['\"]?(\w[\w.-]*)", error_message)
        if m:
            return m.group(1).split(".")[0]

        # command not found style
        m = re.search(r"['\"]?(\w[\w-]*)['\"]?:\s*(?:command )?not found", error_message)
        if m:
            return m.group(1)

        return None

    def _is_process_running(self, process_name: str) -> bool:
        """Check if a process with the given name is running."""
        try:
            result = subprocess.run(
                ["pgrep", "-f", process_name],
                capture_output=True,
                text=True,
                timeout=10,
            )
            return result.returncode == 0
        except Exception:
            return False

    def _check_server_health(self, url: str) -> bool:
        """Simple HTTP health check using curl."""
        try:
            result = subprocess.run(
                ["curl", "-sf", "--max-time", "10", "-o", "/dev/null", "-w", "%{http_code}", url],
                capture_output=True,
                text=True,
                timeout=15,
            )
            return result.returncode == 0 and result.stdout.strip().startswith("2")
        except Exception:
            return False
