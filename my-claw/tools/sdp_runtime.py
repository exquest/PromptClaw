"""Helpers for invoking sdp-cli and selecting bridge agent pairs."""

from __future__ import annotations

import subprocess
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path

DEFAULT_SDP_COMMAND_TIMEOUT_SECONDS = 60
SHORT_SDP_STATUS_TIMEOUT_SECONDS = 15
_USE_POLICY_TIMEOUT = object()
DEFAULT_SDP_STATE_DB = Path(__file__).resolve().parent.parent / ".sdp" / "state.db"


def sdp_timeout_for(command: Sequence[str], *, default_timeout: int = DEFAULT_SDP_COMMAND_TIMEOUT_SECONDS) -> int | None:
    """Return the external subprocess timeout for an sdp-cli command."""
    normalized = tuple(command)
    if normalized[:2] == ("sdp-cli", "run"):
        return None
    if normalized[:2] == ("sdp-cli", "status"):
        return SHORT_SDP_STATUS_TIMEOUT_SECONDS
    if normalized[:3] == ("sdp-cli", "tasks", "list"):
        return SHORT_SDP_STATUS_TIMEOUT_SECONDS
    return default_timeout


def run_sdp_command(
    command: Sequence[str],
    *,
    project_root: str | Path,
    env: Mapping[str, str],
    timeout_s: int | None | object = _USE_POLICY_TIMEOUT,
) -> tuple[str, str, int]:
    """Run an sdp-cli command with the project timeout policy."""
    resolved_timeout = sdp_timeout_for(command) if timeout_s is _USE_POLICY_TIMEOUT else timeout_s
    result = subprocess.run(
        list(command),
        capture_output=True,
        text=True,
        timeout=resolved_timeout,
        cwd=str(project_root),
        env=dict(env),
    )
    return result.stdout.strip(), result.stderr.strip(), result.returncode


def get_provider_headroom(provider: str) -> tuple[float, str]:
    """Return ``(headroom_0_to_1, confidence)`` for a provider.

    Falls back to a neutral healthy state when the sdp-cli Python API is
    unavailable in the current environment.
    """
    try:
        from sdp.state.db import get_quota_headroom

        try:
            headroom, confidence = get_quota_headroom(provider)
        except TypeError:
            headroom, confidence = get_quota_headroom(str(DEFAULT_SDP_STATE_DB), provider)
        return (max(0.0, min(1.0, float(headroom))), str(confidence))
    except Exception:
        return (1.0, "unknown")


def select_agent_pair(
    task_lead_agent: str | None,
    available_agents: Sequence[str],
    *,
    choose_verify_agent: Callable[..., str] | None = None,
) -> tuple[str, str]:
    """Resolve lead/verifier using task defaults and sdp-cli verification policy."""
    normalized_agents = tuple(agent.strip() for agent in available_agents if isinstance(agent, str) and agent.strip())
    if not normalized_agents:
        return "claude", "claude"

    preferred_lead = (task_lead_agent or "").strip()
    lead_name = preferred_lead if preferred_lead in normalized_agents else normalized_agents[0]

    verify_name = ""
    if choose_verify_agent is not None:
        try:
            verify_name = choose_verify_agent(lead_name, available_agents=normalized_agents).strip()
        except TypeError:
            verify_name = choose_verify_agent(lead_name, normalized_agents).strip()

    if verify_name not in normalized_agents or verify_name == "":
        verify_name = next((agent for agent in normalized_agents if agent != lead_name), lead_name)

    return lead_name, verify_name
