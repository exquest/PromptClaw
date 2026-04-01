"""Quota monitoring for graceful provider degradation."""

from __future__ import annotations

import importlib
import os
import re
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from sdp_runtime import run_sdp_command

AGENT_PROVIDERS = {
    "claude": "anthropic",
    "codex": "openai",
    "gemini": "google",
}

PROVIDER_AGENTS = {provider: agent for agent, provider in AGENT_PROVIDERS.items()}

HEALTHY_THRESHOLD = 0.30
WARN_THRESHOLD = 0.15
PAUSE_THRESHOLD = 0.05

QUOTA_ERROR_PATTERNS = [
    r"rate.?limit",
    r"quota.?(?:exceeded|exhausted|limit)",
    r"insufficient.?(?:credits?|funds?|balance|quota)",
    r"billing",
    r"token.?(?:limit|exceeded|exhausted)",
    r"429",
    r"resource.?exhausted",
    r"capacity",
    r"overloaded",
]

_QUOTA_ERROR_REGEXES = [re.compile(pattern, re.IGNORECASE) for pattern in QUOTA_ERROR_PATTERNS]


def is_quota_error(text: str) -> bool:
    """Return ``True`` when stderr/output looks like quota exhaustion."""
    if not text:
        return False
    return any(regex.search(text) for regex in _QUOTA_ERROR_REGEXES)


class QuotaMonitor:
    """Poll provider quota headroom and expose routing-safe availability."""

    def __init__(
        self,
        *,
        observatory=None,
        poll_interval: float = 60.0,
        alert_callback: Callable[[str], object] | None = None,
        project_root: str | Path | None = None,
        agent_providers: dict[str, str] | None = None,
    ) -> None:
        self.observatory = observatory
        self.poll_interval = poll_interval
        self.alert_callback = alert_callback
        self.project_root = Path(project_root) if project_root else Path(__file__).resolve().parent.parent
        self.agent_providers = dict(agent_providers or AGENT_PROVIDERS)
        self.providers = tuple(dict.fromkeys(self.agent_providers.values()))

        self.provider_status = {provider: "healthy" for provider in self.providers}
        self._provider_details = {
            provider: {
                "status": "healthy",
                "headroom": 1.0,
                "confidence": "unknown",
                "updated_at": None,
                "reason": "startup",
            }
            for provider in self.providers
        }

        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        """Start the background polling thread."""
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._poll_loop, daemon=True, name="quota-monitor")
        self._thread.start()

    def stop(self) -> None:
        """Stop the background polling thread."""
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=max(1.0, self.poll_interval * 2))

    def poll_once(self) -> None:
        """Collect one headroom snapshot for each provider."""
        for provider in self.providers:
            try:
                headroom, confidence = self._load_provider_headroom(provider)
                status = self._status_for_headroom(headroom)
                self._apply_status(
                    provider,
                    status=status,
                    headroom=headroom,
                    confidence=confidence,
                    reason="poll",
                )
            except Exception as exc:
                self._apply_status(
                    provider,
                    status="error",
                    headroom=0.0,
                    confidence="error",
                    reason=str(exc) or "quota check failed",
                )

    def force_status(
        self,
        provider: str,
        status: str,
        *,
        headroom: float | None = None,
        confidence: str = "runtime",
        reason: str = "runtime",
    ) -> None:
        """Force a provider into a runtime state after a live failure."""
        with self._lock:
            existing = dict(self._provider_details.get(provider, {}))
        self._apply_status(
            provider,
            status=status,
            headroom=self._coerce_headroom(existing.get("headroom", 0.0)) if headroom is None else headroom,
            confidence=confidence,
            reason=reason,
        )

    def get_available_agents(self, agents: list[str] | tuple[str, ...] | None = None) -> list[str]:
        """Return agents in healthy/warn states, with a best-effort fallback."""
        candidates = list(agents) if agents is not None else list(self.agent_providers)
        candidates = [agent for agent in candidates if agent in self.agent_providers]
        if not candidates:
            return []

        with self._lock:
            details = {provider: dict(values) for provider, values in self._provider_details.items()}

        available = [
            agent
            for agent in candidates
            if details.get(self.agent_providers[agent], {}).get("status") in {"healthy", "warn"}
        ]
        if available:
            return available

        best_agent = max(
            candidates,
            key=lambda agent: self._coerce_headroom(
                details.get(self.agent_providers[agent], {}).get("headroom", 0.0)
            ),
        )
        return [best_agent]

    def get_provider_status(self) -> dict[str, dict[str, object]]:
        """Return a thread-safe snapshot of provider status details."""
        with self._lock:
            return {provider: dict(values) for provider, values in self._provider_details.items()}

    def get_agent_headroom(self, agent: str) -> float:
        """Return the latest headroom for an agent's provider."""
        provider = self.agent_providers.get(agent)
        if provider is None:
            return 0.0
        with self._lock:
            return self._coerce_headroom(self._provider_details.get(provider, {}).get("headroom", 0.0))

    def _poll_loop(self) -> None:
        while not self._stop_event.is_set():
            self.poll_once()
            if self._wait_for_next_poll():
                break

    def _wait_for_next_poll(self) -> bool:
        return self._stop_event.wait(self.poll_interval)

    def _load_provider_headroom(self, provider: str) -> tuple[float, str]:
        """Read provider headroom from sdp-cli, with defensive fallbacks."""
        try:
            module = importlib.import_module("sdp.state.db")
        except ImportError:
            return (1.0, "unknown")

        getter = getattr(module, "get_quota_headroom")
        try:
            return self._normalize_headroom_result(getter(provider))
        except TypeError:
            return self._normalize_headroom_result(
                getter(str(self.project_root / ".sdp" / "state.db"), provider)
            )
        except Exception:
            return self._load_provider_headroom_from_cli(provider)

    def _load_provider_headroom_from_cli(self, provider: str) -> tuple[float, str]:
        stdout, stderr, returncode = run_sdp_command(
            ["sdp-cli", "capacity", "plan"],
            project_root=self.project_root,
            env=os.environ,
            timeout_s=15,
        )
        if returncode != 0:
            raise RuntimeError(stderr or f"sdp-cli capacity plan failed for {provider}")
        return (self._parse_cli_headroom(provider, stdout), "estimated")

    def _parse_cli_headroom(self, provider: str, stdout: str) -> float:
        for line in stdout.splitlines():
            lowered = line.lower()
            if provider not in lowered:
                continue
            match = re.search(r"(\d+(?:\.\d+)?)\s*%", line)
            if match:
                return max(0.0, min(1.0, float(match.group(1)) / 100.0))
        raise ValueError(f"unable to parse headroom for {provider}")

    def _normalize_headroom_result(self, result: object) -> tuple[float, str]:
        if not isinstance(result, tuple) or len(result) != 2:
            raise ValueError(f"unexpected quota headroom result: {result!r}")
        headroom, confidence = result
        return (self._coerce_headroom(headroom), str(confidence))

    @staticmethod
    def _coerce_headroom(value: object) -> float:
        if not isinstance(value, (int, float, str)):
            raise TypeError(f"unsupported headroom value: {value!r}")
        return max(0.0, min(1.0, float(value)))

    def _status_for_headroom(self, headroom: float) -> str:
        if headroom > HEALTHY_THRESHOLD:
            return "healthy"
        if headroom > WARN_THRESHOLD:
            return "warn"
        if headroom > PAUSE_THRESHOLD:
            return "degraded"
        return "paused"

    def _apply_status(
        self,
        provider: str,
        *,
        status: str,
        headroom: float,
        confidence: str,
        reason: str,
    ) -> None:
        headroom = max(0.0, min(1.0, float(headroom)))
        now = datetime.now(timezone.utc).isoformat()

        with self._lock:
            previous = dict(self._provider_details.get(provider, {}))
            self.provider_status[provider] = status
            self._provider_details[provider] = {
                "status": status,
                "headroom": headroom,
                "confidence": confidence,
                "updated_at": now,
                "reason": reason,
            }

        previous_status = str(previous.get("status", "healthy"))
        if previous_status != status:
            self._record_transition(
                provider,
                previous_status=previous_status,
                current_status=status,
                headroom=headroom,
                confidence=confidence,
                reason=reason,
            )

    def _record_transition(
        self,
        provider: str,
        *,
        previous_status: str,
        current_status: str,
        headroom: float,
        confidence: str,
        reason: str,
    ) -> None:
        agent = PROVIDER_AGENTS.get(provider, provider)
        message = (
            "⚠️ Provider Degradation\n"
            f"{provider}: {previous_status} -> {current_status} ({headroom:.0%} headroom)\n"
            f"Active agents: {', '.join(self.get_available_agents())}\n"
            f"{agent.title()} excluded from routing until headroom recovers."
        )

        if self.alert_callback is not None:
            try:
                self.alert_callback(message[:300])
            except Exception:
                pass

        if self.observatory is None:
            return

        context = {
            "provider": provider,
            "previous_status": previous_status,
            "current_status": current_status,
            "headroom": headroom,
            "confidence": confidence,
            "reason": reason,
            "active_agents": self.get_available_agents(),
        }
        try:
            self.observatory.record_healing(
                "provider_degradation",
                2 if current_status in {"degraded", "paused", "error"} else 1,
                f"{provider}: {previous_status}->{current_status}",
                True,
                context,
            )
        except Exception:
            pass
        try:
            self.observatory.record("provider_quota_transition", context)
        except Exception:
            pass
