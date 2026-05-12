"""Tests for the CypherClaw observatory event store."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "my-claw" / "tools"))

import observatory as observatory_module


def test_record_task_result_updates_skills_and_public_skill_api(tmp_path: Path) -> None:
    db_path = tmp_path / "observatory.db"
    obs = observatory_module.Observatory(str(db_path))

    obs.record_task_result(
        agent="codex",
        task_id="T-001",
        success=True,
        duration_ms=1250,
        tokens=512,
        gate_pass=True,
        category="coding",
    )

    skills = obs.get_agent_skills("codex")

    assert skills == [
        {
            "agent": "codex",
            "category": "coding",
            "score": 1.0,
            "sample_count": 1,
            "updated_at": skills[0]["updated_at"],
        }
    ]

    obs.update_agent_skill("codex", "coding", success=False)

    updated = obs.get_agent_skills("codex")
    assert len(updated) == 1
    assert updated[0]["sample_count"] == 2
    assert updated[0]["score"] == pytest.approx(0.7)

    obs.close()


def test_rollups_healing_log_and_routing_accuracy_are_queryable(tmp_path: Path) -> None:
    db_path = tmp_path / "observatory.db"
    obs = observatory_module.Observatory(str(db_path))

    obs.record({"type": "noop"} if False else "user_message", {"text": "hello"})  # keep generic event table warm
    obs.record_task_result(
        agent="claude",
        task_id="T-001",
        success=True,
        duration_ms=1_000,
        tokens=100,
        gate_pass=True,
        category="review",
    )
    obs.record_task_result(
        agent="codex",
        task_id="T-002",
        success=False,
        duration_ms=2_000,
        tokens=200,
        gate_pass=False,
        category="coding",
    )
    obs.record_healing(
        failure_type="gate_failure",
        severity=2,
        action_taken="retry with codex",
        success=True,
        context={"task_id": "T-002"},
    )
    obs.rollup_daily()

    daily_rollup = obs.get_daily_rollup()
    healing_log = obs.get_healing_log(days=1)
    task_results = obs.get_task_results(agent="claude")
    routing_accuracy = obs.get_routing_accuracy(days=1)

    assert len(daily_rollup) == 2
    assert {row["agent"] for row in daily_rollup} == {"claude", "codex"}
    assert len(healing_log) == 1
    assert healing_log[0]["failure_type"] == "gate_failure"
    assert healing_log[0]["success"] == 1
    assert len(task_results) == 1
    assert task_results[0]["task_id"] == "T-001"
    assert routing_accuracy == pytest.approx(0.5)

    obs.close()
