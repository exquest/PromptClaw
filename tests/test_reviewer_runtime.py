"""Tests for the CypherClaw reviewer reports."""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "my-claw" / "tools"))

import reviewer


class FakeObservatory:
    def get_agent_stats(self, days: int = 1) -> dict[str, dict[str, float]]:
        if days == 1:
            return {
                "codex": {
                    "total": 4,
                    "successes": 4,
                    "total_tokens": 2000,
                    "avg_duration": 45_000,
                    "gate_passes": 4,
                },
                "gemini": {
                    "total": 3,
                    "successes": 1,
                    "total_tokens": 1500,
                    "avg_duration": 120_000,
                    "gate_passes": 1,
                },
            }
        if days == 7:
            return {
                "codex": {"total": 8, "successes": 7, "avg_duration": 55_000, "total_tokens": 5000},
                "gemini": {"total": 4, "successes": 2, "avg_duration": 90_000, "total_tokens": 2500},
            }
        return {
            "codex": {"total": 15, "successes": 13, "avg_duration": 60_000, "total_tokens": 100_000},
            "gemini": {"total": 8, "successes": 3, "avg_duration": 110_000, "total_tokens": 80_000},
        }

    def get_healing_log(self, days: int = 1) -> list[dict[str, object]]:
        if days == 1:
            return [{"failure_type": "gate_failure", "success": 1} for _ in range(6)]
        if days == 7:
            return [
                {"failure_type": "gate_failure", "success": 1},
                {"failure_type": "gate_failure", "success": 1},
                {"failure_type": "gate_failure", "success": 0},
            ]
        return [{"failure_type": "agent_error", "success": 1} for _ in range(5)]

    def get_task_results(self, since: datetime | None = None, agent: str | None = None) -> list[dict[str, object]]:
        results = [
            {"task_id": "T-1", "duration_ms": 700_000, "agent": "gemini"},
            {"task_id": "T-2", "duration_ms": 30_000, "agent": "codex"},
        ]
        if agent is None:
            return results
        return [row for row in results if row["agent"] == agent]

    def get_agent_skills(self) -> list[dict[str, object]]:
        return [
            {"agent": "codex", "category": "coding", "score": 0.92, "sample_count": 6},
            {"agent": "gemini", "category": "research", "score": 0.88, "sample_count": 4},
            {"agent": "gemini", "category": "coding", "score": 0.32, "sample_count": 5},
        ]

    def get_weekly_rollups(self, weeks_back: int = 0) -> list[dict[str, object]]:
        if weeks_back == 0:
            return [
                {
                    "tasks_completed": 10,
                    "tasks_failed": 2,
                    "total_tokens": 12_000,
                    "total_duration_ms": 480_000,
                    "gate_passes": 9,
                    "gate_total": 12,
                }
            ]
        return [
            {
                "tasks_completed": 6,
                "tasks_failed": 3,
                "total_tokens": 9_000,
                "total_duration_ms": 540_000,
                "gate_passes": 5,
                "gate_total": 9,
            }
        ]

    def aggregate(self, metric: str = "tasks", period: str = "monthly") -> dict[str, object]:
        return {
            "total": 23,
            "successes": 16,
            "failures": 7,
            "total_tokens": 650_000,
            "avg_duration": 75_000,
            "gate_passes": 15,
        }


def test_daily_brief_surfaces_attention_and_insights() -> None:
    report = reviewer.Reviewer(FakeObservatory()).daily_brief("2026-04-01")

    assert "📊 Daily Brief — April 01, 2026" in report
    assert "Tasks: 5 completed, 2 failed, 1 stuck" in report
    assert "Top agent: codex" in report
    assert "⚠️ Attention:" in report
    assert "failed gate checks" in report
    assert "💡 Insight:" in report


def test_weekly_retro_includes_goals_and_routing_breakdown() -> None:
    report = reviewer.Reviewer(FakeObservatory()).weekly_retro()

    assert "📋 Weekly Retro" in report
    assert "Performance:" in report
    assert "Agent Evolution:" in report
    assert "Routing Changes:" in report
    assert "Goals for Next Week:" in report
    assert "Reduce gate failure failures" in report or "Improve gemini coding score" in report


def test_monthly_review_includes_recommendations() -> None:
    report = reviewer.Reviewer(FakeObservatory()).monthly_review()

    assert "📖 Monthly Review" in report
    assert "Overview:" in report
    assert "Agent Performance:" in report
    assert "Recommendations for Next Month:" in report
    assert "Token usage is high" in report
    assert "Re-evaluate gemini usage" in report
