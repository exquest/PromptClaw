"""Tests for CypherClaw's SDP runtime helpers."""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "my-claw" / "tools"))

import sdp_bridge
import sdp_runtime


def test_run_sdp_command_leaves_pipeline_runs_unbounded(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    recorded: dict[str, object] = {}

    def fake_run(cmd: list[str], **kwargs: object) -> SimpleNamespace:
        recorded["cmd"] = cmd
        recorded.update(kwargs)
        return SimpleNamespace(stdout=" done \n", stderr=" warn \n", returncode=7)

    monkeypatch.setattr(sdp_runtime.subprocess, "run", fake_run)

    stdout, stderr, code = sdp_runtime.run_sdp_command(
        ["sdp-cli", "run"],
        project_root=tmp_path,
        env={"TMPDIR": "/tmp"},
    )

    assert recorded["cmd"] == ["sdp-cli", "run"]
    assert recorded["timeout"] is None
    assert stdout == "done"
    assert stderr == "warn"
    assert code == 7


def test_run_sdp_command_accepts_explicit_timeout_override(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    recorded: dict[str, object] = {}

    def fake_run(cmd: list[str], **kwargs: object) -> SimpleNamespace:
        recorded["cmd"] = cmd
        recorded.update(kwargs)
        return SimpleNamespace(stdout="", stderr="", returncode=0)

    monkeypatch.setattr(sdp_runtime.subprocess, "run", fake_run)

    sdp_runtime.run_sdp_command(
        ["sdp-cli", "status"],
        project_root=tmp_path,
        env={},
        timeout_s=3,
    )

    assert recorded["cmd"] == ["sdp-cli", "status"]
    assert recorded["timeout"] == 3


def test_select_agent_pair_uses_task_lead_and_verifier_selector() -> None:
    recorded: dict[str, object] = {}

    def fake_choose_verify_agent(lead_name: str, *, available_agents: tuple[str, ...]) -> str:
        recorded["lead_name"] = lead_name
        recorded["available_agents"] = available_agents
        return "claude"

    lead_name, verify_name = sdp_runtime.select_agent_pair(
        "codex",
        ["claude", "codex", "gemini"],
        choose_verify_agent=fake_choose_verify_agent,
    )

    assert (lead_name, verify_name) == ("codex", "claude")
    assert recorded == {
        "lead_name": "codex",
        "available_agents": ("claude", "codex", "gemini"),
    }


def test_select_agent_pair_falls_back_to_another_available_agent() -> None:
    lead_name, verify_name = sdp_runtime.select_agent_pair(
        None,
        ["claude", "codex"],
        choose_verify_agent=None,
    )

    assert (lead_name, verify_name) == ("claude", "codex")


def test_bridge_run_next_uses_runtime_agent_pair_selection(monkeypatch: pytest.MonkeyPatch) -> None:
    bridge = sdp_bridge.SDPBridge.__new__(sdp_bridge.SDPBridge)
    bridge.project_root = Path("/tmp/project")
    bridge.on_progress = None
    bridge._settings = object()
    bridge._agents = {
        "claude": object(),
        "codex": object(),
    }
    bridge._queue = SimpleNamespace(
        get_next_pending=lambda: SimpleNamespace(
            task_id="T-123",
            description="Route with task default",
            lead_agent="codex",
        )
    )

    captured: dict[str, object] = {}

    monkeypatch.setattr(sdp_bridge, "SDP_AVAILABLE", True)
    monkeypatch.setattr(sdp_bridge, "RunOutcome", SimpleNamespace(SUCCESS="SUCCESS"))

    def fake_select_agent_pair(
        task_lead_agent: str | None,
        available_agents: tuple[str, ...],
        *,
        choose_verify_agent=None,
    ) -> tuple[str, str]:
        captured["task_lead_agent"] = task_lead_agent
        captured["available_agents"] = available_agents
        captured["choose_verify_agent"] = choose_verify_agent
        return "codex", "claude"

    def fake_run_single_task(
        *,
        task,
        lead,
        verifier,
        lead_name: str,
        verify_name: str,
        settings,
    ) -> SimpleNamespace:
        captured["lead"] = lead
        captured["verifier"] = verifier
        captured["lead_name"] = lead_name
        captured["verify_name"] = verify_name
        captured["settings"] = settings
        return SimpleNamespace(
            outcome="SUCCESS",
            duration_seconds=1.25,
            errors=[],
            verdict="ok",
        )

    monkeypatch.setattr(sdp_bridge, "select_agent_pair", fake_select_agent_pair)
    monkeypatch.setattr(sdp_bridge, "run_single_task", fake_run_single_task)
    monkeypatch.setattr(sdp_bridge, "choose_verify_agent", object())

    result = bridge.run_next()

    assert result is not None
    assert result.lead_agent == "codex"
    assert result.verify_agent == "claude"
    assert captured["task_lead_agent"] == "codex"
    assert captured["available_agents"] == ("claude", "codex")
    assert captured["lead_name"] == "codex"
    assert captured["verify_name"] == "claude"
