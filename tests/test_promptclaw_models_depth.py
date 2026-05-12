"""Depth-2 tests for promptclaw.models [frac-0039]."""

from __future__ import annotations

import json
from pathlib import Path

from promptclaw.bootstrap import init_project
from promptclaw.config import default_project_config
from promptclaw.models import (
    AgentConfig,
    ConfigModelReport,
    Event,
    RouteDecision,
    RunState,
    config_model_report,
    summarize_agent,
    summarize_config_model,
    summarize_route_decision,
    summarize_run_state,
)
from promptclaw.orchestrator import PromptClawOrchestrator


MODELS_MODULE_PATH = Path("promptclaw/models.py")


def _config_with_extra_agents():
    config = default_project_config("Model Claw")
    config.agents["sleepy"] = AgentConfig(
        name="sleepy",
        enabled=False,
        kind="mock",
        capabilities=["docs"],
    )
    config.agents["runner"] = AgentConfig(
        name="runner",
        kind="command",
        command=["python", "-m", "runner"],
        capabilities=["testing", "implementation"],
    )
    return config


def test_config_model_report_counts_agent_surface() -> None:
    config = _config_with_extra_agents()

    report = config_model_report(config)

    assert isinstance(report, ConfigModelReport)
    assert report.project_name == "Model Claw"
    assert report.artifact_root == ".promptclaw"
    assert report.control_plane_mode == "heuristic"
    assert report.verification_enabled is True
    assert report.max_retries == 1
    assert report.agent_count == 5
    assert report.enabled_agent_count == 4
    assert report.disabled_agent_count == 1
    assert report.command_agent_count == 1


def test_summarize_config_model_is_json_safe_and_sorted() -> None:
    config = _config_with_extra_agents()

    summary = summarize_config_model(config)

    json.dumps(summary)
    assert summary["project_name"] == "Model Claw"
    assert summary["agent_count"] == 5
    assert [row["name"] for row in summary["agents"]] == [
        "claude",
        "codex",
        "gemini",
        "runner",
        "sleepy",
    ]

    runner = next(row for row in summary["agents"] if row["name"] == "runner")
    assert runner["enabled"] is True
    assert runner["kind"] == "command"
    assert runner["command_configured"] is True
    assert runner["capability_count"] == 2

    sleepy = next(row for row in summary["agents"] if row["name"] == "sleepy")
    assert sleepy["enabled"] is False
    assert sleepy["command_configured"] is False


def test_summarize_agent_flags_shell_command_configuration() -> None:
    agent = AgentConfig(
        name="sheller",
        kind="command",
        shell_command="echo {prompt_file}",
        capabilities=["docs", "verification"],
        instruction_file="prompts/agents/sheller.md",
    )

    summary = summarize_agent(agent)

    assert summary == {
        "name": "sheller",
        "enabled": True,
        "kind": "command",
        "command_configured": True,
        "capability_count": 2,
        "capabilities": ["docs", "verification"],
        "instruction_file": "prompts/agents/sheller.md",
    }


def test_route_and_run_state_summaries_are_json_safe() -> None:
    decision = RouteDecision(
        ambiguous=False,
        clarification_question=None,
        lead_agent="codex",
        verifier_agent="claude",
        reason="selected for coding",
        subtask_brief="implement and test",
        task_type="code",
        confidence=0.72,
    )
    state = RunState(
        run_id="run-1",
        title="Model Run",
        status="complete",
        current_phase="complete",
        created_at="2026-05-02T00:00:00+00:00",
        updated_at="2026-05-02T00:01:00+00:00",
        task_text="Implement a model helper",
        lead_agent="codex",
        verifier_agent="claude",
        route_decision=summarize_route_decision(decision),
        final_summary_path=".promptclaw/runs/run-1/summary/final-summary.md",
        events=[
            Event(
                timestamp="2026-05-02T00:00:00+00:00",
                event_type="run_started",
                message="Run created",
            )
        ],
        errors=[{"phase": "lead", "message": "recovered"}],
        recovery_actions=["lead: fallback"],
        coherence_violations=[{"phase": "lead", "rule": "C1"}],
    )

    route_summary = summarize_route_decision(decision)
    run_summary = summarize_run_state(state)

    json.dumps(route_summary)
    json.dumps(run_summary)
    assert route_summary["task_type"] == "code"
    assert route_summary["has_verifier"] is True
    assert run_summary["status"] == "complete"
    assert run_summary["route_task_type"] == "code"
    assert run_summary["event_count"] == 1
    assert run_summary["error_count"] == 1
    assert run_summary["recovery_action_count"] == 1
    assert run_summary["coherence_violation_count"] == 1
    assert run_summary["has_final_summary"] is True


def test_run_state_summary_matches_orchestrator_end_to_end(tmp_path: Path) -> None:
    init_project(tmp_path, "Model Integration Claw")
    orchestrator = PromptClawOrchestrator(tmp_path)

    state = orchestrator.run(
        "Implement a Python feature and write tests.",
        title="Model Summary Run",
    )
    summary = summarize_run_state(state)

    json.dumps(summary)
    assert summary["status"] == "complete"
    assert summary["phase"] == "complete"
    assert summary["lead_agent"] == "codex"
    assert summary["verifier_agent"] == "claude"
    assert summary["route_task_type"] == "code"
    assert summary["event_count"] >= 3
    assert summary["has_final_summary"] is True


def test_models_module_reaches_depth_two() -> None:
    from sdp.fractal import classify_depth

    result = classify_depth(MODELS_MODULE_PATH)

    assert result.depth >= 2, result.reason
