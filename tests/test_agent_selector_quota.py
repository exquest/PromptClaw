"""Tests for quota-aware agent selection."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "my-claw" / "tools"))

import agent_selector


class FakeQuotaMonitor:
    def __init__(
        self,
        *,
        available: list[str],
        statuses: dict[str, str] | None = None,
        headrooms: dict[str, float] | None = None,
    ) -> None:
        self.available = list(available)
        self.statuses = statuses or {
            "anthropic": "healthy",
            "openai": "healthy",
            "google": "healthy",
        }
        self.headrooms = headrooms or {
            "claude": 0.5,
            "codex": 0.5,
            "gemini": 0.5,
        }

    def get_available_agents(self, agents: list[str] | tuple[str, ...] | None = None) -> list[str]:
        candidates = list(agents) if agents is not None else ["claude", "codex", "gemini"]
        filtered = [agent for agent in candidates if agent in self.available]
        if filtered:
            return filtered
        return [max(candidates, key=lambda agent: self.headrooms.get(agent, 0.0))]

    def get_provider_status(self) -> dict[str, dict[str, object]]:
        result: dict[str, dict[str, object]] = {}
        for agent_name, provider in agent_selector.PROVIDERS.items():
            result[provider] = {
                "status": self.statuses.get(provider, "healthy"),
                "headroom": self.headrooms.get(agent_name, 0.0),
                "confidence": "observed",
            }
        return result

    def get_agent_headroom(self, agent_name: str) -> float:
        return self.headrooms.get(agent_name, 0.0)


class TestAgentSelectorQuota:
    def test_select_excludes_paused_provider(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        selector = agent_selector.AgentSelector(
            observatory=None,
            quota_monitor=FakeQuotaMonitor(available=["gemini"]),
            state_file=tmp_path / "selector-state.json",
        )
        monkeypatch.setattr(agent_selector.random, "random", lambda: 1.0)

        assert selector.select("implement the feature") == "gemini"

    def test_select_with_all_paused_returns_best_headroom(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        selector = agent_selector.AgentSelector(
            observatory=None,
            quota_monitor=FakeQuotaMonitor(
                available=[],
                statuses={"anthropic": "paused", "openai": "paused", "google": "paused"},
                headrooms={"claude": 0.01, "codex": 0.02, "gemini": 0.09},
            ),
            state_file=tmp_path / "selector-state.json",
        )
        monkeypatch.setattr(agent_selector.random, "random", lambda: 1.0)

        assert selector.select("implement the feature") == "gemini"

    def test_select_pair_with_one_available_returns_same_for_both(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        selector = agent_selector.AgentSelector(
            observatory=None,
            quota_monitor=FakeQuotaMonitor(available=["codex"]),
            state_file=tmp_path / "selector-state.json",
        )
        monkeypatch.setattr(agent_selector.random, "random", lambda: 1.0)

        assert selector.select_pair("implement the feature") == ("codex", "codex")

    def test_headroom_bonus_applied(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        selector = agent_selector.AgentSelector(
            observatory=None,
            quota_monitor=FakeQuotaMonitor(
                available=["claude", "codex"],
                headrooms={"claude": 0.10, "codex": 0.90, "gemini": 0.0},
            ),
            state_file=tmp_path / "selector-state.json",
        )
        monkeypatch.setattr(agent_selector.random, "random", lambda: 1.0)
        monkeypatch.setattr(selector, "get_fitness", lambda agent_name, category: 0.50)

        assert selector.select("some ambiguous work", available_agents=["claude", "codex"]) == "codex"

    def test_disabled_agents_parameter_respected(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        selector = agent_selector.AgentSelector(
            observatory=None,
            quota_monitor=FakeQuotaMonitor(available=["claude", "codex", "gemini"]),
            state_file=tmp_path / "selector-state.json",
        )
        monkeypatch.setattr(agent_selector.random, "random", lambda: 1.0)

        assert selector.select("implement the feature", disabled_agents={"codex"}) != "codex"

    def test_status_summary_includes_quota(self, tmp_path: Path) -> None:
        selector = agent_selector.AgentSelector(
            observatory=None,
            quota_monitor=FakeQuotaMonitor(
                available=["claude", "gemini"],
                statuses={"anthropic": "warn", "openai": "paused", "google": "healthy"},
                headrooms={"claude": 0.25, "codex": 0.02, "gemini": 0.80},
            ),
            state_file=tmp_path / "selector-state.json",
        )

        summary = selector.status_summary()

        assert "quota" in summary.lower()
        assert "warn" in summary.lower()
        assert "paused" in summary.lower()
