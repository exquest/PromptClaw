"""Tests for quota-aware agent selection."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "my-claw" / "tools"))

import agent_selector
import ollama_health
import quota_monitor


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


@pytest.fixture(autouse=True)
def _healthy_ollama(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ollama_health, "check_health", lambda port: True)


class TestAgentSelectorQuota:
    def test_select_prefers_ollama_when_healthy_for_netops(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        monitor = quota_monitor.QuotaMonitor(poll_interval=0.01)
        monkeypatch.setattr(
            quota_monitor.QuotaMonitor,
            "_load_provider_headroom",
            lambda self, provider: (1.0, "local") if provider == "local" else (0.9, "observed"),
        )
        monitor.poll_once()

        selector = agent_selector.AgentSelector(
            observatory=None,
            quota_monitor=monitor,
            state_file=tmp_path / "selector-state.json",
        )
        monkeypatch.setattr(agent_selector.random, "random", lambda: 1.0)

        assert selector.select("vpn firewall routing help", available_agents=["ollama", "codex", "gemini"]) == "ollama"

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

    def test_select_falls_back_to_cloud_when_ollama_unhealthy_and_recovers(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        monitor = quota_monitor.QuotaMonitor(poll_interval=0.01)
        monkeypatch.setattr(
            quota_monitor.QuotaMonitor,
            "_load_provider_headroom",
            lambda self, provider: (1.0, "local") if provider == "local" else (0.9, "observed"),
        )
        monitor.poll_once()

        selector = agent_selector.AgentSelector(
            observatory=None,
            quota_monitor=monitor,
            state_file=tmp_path / "selector-state.json",
        )
        monkeypatch.setattr(agent_selector.random, "random", lambda: 1.0)

        health = {"ok": False}
        monkeypatch.setattr(ollama_health, "check_health", lambda port: health["ok"])

        assert selector.select("vpn firewall routing help", available_agents=["ollama", "codex", "gemini"]) == "codex"

        health["ok"] = True

        assert selector.select("vpn firewall routing help", available_agents=["ollama", "codex", "gemini"]) == "ollama"


class TestAgentSelectorEndToEnd:
    """Looped, multi-step scenarios that drive the public selector surface."""

    def test_alternation_rotation_across_long_select_sequence(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        selector = agent_selector.AgentSelector(
            observatory=None,
            quota_monitor=FakeQuotaMonitor(available=["claude", "codex", "gemini"]),
            state_file=tmp_path / "rotation-state.json",
        )
        monkeypatch.setattr(agent_selector.random, "random", lambda: 1.0)
        monkeypatch.setattr(
            selector,
            "get_fitness",
            lambda agent_name, category: {"claude": 0.80, "codex": 0.78, "gemini": 0.76}[agent_name],
        )

        picks: list[str] = []
        providers: list[str] = []
        for _ in range(8):
            chosen = selector.select(
                "implement the feature",
                available_agents=["claude", "codex", "gemini"],
            )
            picks.append(chosen)
            providers.append(agent_selector.PROVIDERS[chosen])

        assert len(picks) == 8
        for previous, current in zip(providers, providers[1:]):
            assert previous != current

    def test_state_round_trip_through_state_file(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        state_file = tmp_path / "selector-state.json"
        first = agent_selector.AgentSelector(
            observatory=None,
            quota_monitor=FakeQuotaMonitor(available=["claude", "codex", "gemini"]),
            state_file=state_file,
        )
        monkeypatch.setattr(agent_selector.random, "random", lambda: 1.0)
        monkeypatch.setattr(
            first,
            "get_fitness",
            lambda agent_name, category: 0.90 if agent_name == "claude" else 0.50,
        )

        chosen = first.select("implement the feature", available_agents=["claude", "codex", "gemini"])
        assert chosen == "claude"
        assert state_file.exists()

        second = agent_selector.AgentSelector(
            observatory=None,
            quota_monitor=FakeQuotaMonitor(available=["claude", "codex", "gemini"]),
            state_file=state_file,
        )
        summary = second.status_summary()

        assert "last lead: claude" in summary
        assert "1 tasks" in summary

    def test_category_detection_matches_keyword_table(self, tmp_path: Path) -> None:
        selector = agent_selector.AgentSelector(
            observatory=None,
            quota_monitor=None,
            state_file=tmp_path / "category-state.json",
        )

        cases = [
            ("design system structure", "architecture"),
            ("implement the feature", "coding"),
            ("verify the changes", "review"),
            ("investigate the libraries", "research"),
            ("pytest coverage gate", "testing"),
            ("deploy to production server", "devops"),
            ("vpn firewall routing help", "netops"),
            ("compose the document", "writing"),
            ("decide the route", "routing"),
            ("narrative_prose", "narrative_prose"),
        ]

        seen: dict[str, str] = {}
        for description, expected in cases:
            seen[description] = selector.detect_category(description)

        for description, expected in cases:
            assert seen[description] == expected, (description, seen[description], expected)

    def test_ollama_health_recovery_cycle_across_repeated_selects(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        monitor = quota_monitor.QuotaMonitor(poll_interval=0.01)
        monkeypatch.setattr(
            quota_monitor.QuotaMonitor,
            "_load_provider_headroom",
            lambda self, provider: (1.0, "local") if provider == "local" else (0.9, "observed"),
        )
        monitor.poll_once()

        selector = agent_selector.AgentSelector(
            observatory=None,
            quota_monitor=monitor,
            state_file=tmp_path / "ollama-cycle-state.json",
        )
        monkeypatch.setattr(agent_selector.random, "random", lambda: 1.0)
        monkeypatch.setattr(
            selector,
            "get_fitness",
            lambda agent_name, category: 0.50,
        )

        health_states = [True, False, True, False, True]
        health = {"ok": health_states[0]}
        monkeypatch.setattr(ollama_health, "check_health", lambda port: health["ok"])

        picks: list[str] = []
        for state in health_states:
            health["ok"] = state
            chosen = selector.select(
                "vpn firewall routing help",
                available_agents=["ollama", "codex", "gemini"],
            )
            picks.append(chosen)

        for state, pick in zip(health_states, picks):
            if state:
                assert pick == "ollama", (state, pick)
            else:
                assert pick != "ollama", (state, pick)

    def test_pair_selection_returns_distinct_agents_when_all_available(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        selector = agent_selector.AgentSelector(
            observatory=None,
            quota_monitor=FakeQuotaMonitor(available=["claude", "codex", "gemini"]),
            state_file=tmp_path / "pair-state.json",
        )
        monkeypatch.setattr(agent_selector.random, "random", lambda: 1.0)
        monkeypatch.setattr(
            selector,
            "get_fitness",
            lambda agent_name, category: {"claude": 0.85, "codex": 0.65, "gemini": 0.55}[agent_name],
        )

        lead, verify = selector.select_pair("implement the feature")

        assert lead != verify
        assert lead in {"claude", "codex", "gemini"}
        assert verify in {"claude", "codex", "gemini"}

    def test_status_summary_lists_every_default_agent_and_provider(
        self,
        tmp_path: Path,
    ) -> None:
        selector = agent_selector.AgentSelector(
            observatory=None,
            quota_monitor=FakeQuotaMonitor(
                available=["claude", "gemini"],
                statuses={"anthropic": "warn", "openai": "paused", "google": "healthy"},
                headrooms={"claude": 0.25, "codex": 0.02, "gemini": 0.80},
            ),
            state_file=tmp_path / "summary-state.json",
        )

        summary = selector.status_summary()

        for agent_name in agent_selector.DEFAULT_AGENTS:
            assert agent_name in summary
        for provider in ("anthropic", "openai", "google"):
            assert provider in summary
        assert "warn" in summary
        assert "paused" in summary
        assert "healthy" in summary

    def test_disabled_agents_filter_is_per_call_not_persistent(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        selector = agent_selector.AgentSelector(
            observatory=None,
            quota_monitor=FakeQuotaMonitor(available=["claude", "codex", "gemini"]),
            state_file=tmp_path / "disabled-state.json",
        )
        monkeypatch.setattr(agent_selector.random, "random", lambda: 1.0)
        monkeypatch.setattr(
            selector,
            "get_fitness",
            lambda agent_name, category: {"claude": 0.90, "codex": 0.80, "gemini": 0.70}[agent_name],
        )

        sequence = [
            ({"claude"}, {"codex", "gemini"}),
            (set(), {"claude", "codex", "gemini"}),
            ({"codex", "gemini"}, {"claude"}),
            (set(), {"claude", "codex", "gemini"}),
        ]

        picks: list[str] = []
        for disabled, eligible in sequence:
            chosen = selector.select(
                "implement the feature",
                available_agents=["claude", "codex", "gemini"],
                disabled_agents=disabled,
            )
            picks.append(chosen)
            assert chosen in eligible
            assert chosen not in disabled

        assert picks[2] == "claude"

    def test_headroom_sweep_shifts_winner_between_agents(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        scenarios = [
            ({"claude": 0.95, "codex": 0.05, "gemini": 0.0}, "claude"),
            ({"claude": 0.05, "codex": 0.95, "gemini": 0.0}, "codex"),
            ({"claude": 0.10, "codex": 0.10, "gemini": 0.95}, "gemini"),
        ]

        for headrooms, expected_winner in scenarios:
            selector = agent_selector.AgentSelector(
                observatory=None,
                quota_monitor=FakeQuotaMonitor(
                    available=["claude", "codex", "gemini"],
                    headrooms=headrooms,
                ),
                state_file=tmp_path / f"headroom-{expected_winner}.json",
            )
            monkeypatch.setattr(agent_selector.random, "random", lambda: 1.0)
            monkeypatch.setattr(selector, "get_fitness", lambda agent_name, category: 0.50)

            chosen = selector.select(
                "implement the feature",
                available_agents=["claude", "codex", "gemini"],
            )
            assert chosen == expected_winner, (headrooms, chosen)

    def test_record_outcome_without_observatory_is_safe_across_many_calls(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        selector = agent_selector.AgentSelector(
            observatory=None,
            quota_monitor=FakeQuotaMonitor(available=["claude", "codex", "gemini"]),
            state_file=tmp_path / "record-state.json",
        )
        monkeypatch.setattr(agent_selector.random, "random", lambda: 1.0)

        outcomes = [
            ("claude", "implement the feature", True),
            ("codex", "verify the changes", False),
            ("gemini", "investigate the libraries", True),
            ("claude", "compose the document", False),
            ("codex", "pytest coverage gate", True),
        ]

        for agent_name, description, success in outcomes:
            selector.record_outcome(agent_name, description, success)

        summary = selector.status_summary()
        assert "Agent Fitness" in summary

    def test_select_raises_when_every_agent_is_disabled(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        selector = agent_selector.AgentSelector(
            observatory=None,
            quota_monitor=FakeQuotaMonitor(available=["claude", "codex", "gemini"]),
            state_file=tmp_path / "no-eligible-state.json",
        )
        monkeypatch.setattr(agent_selector.random, "random", lambda: 1.0)

        with pytest.raises(ValueError):
            selector.select(
                "implement the feature",
                available_agents=["claude", "codex"],
                disabled_agents={"claude", "codex"},
            )
