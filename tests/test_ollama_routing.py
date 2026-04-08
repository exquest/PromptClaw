"""Tests for dual-socket Ollama model-per-role routing (R750-002)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "my-claw" / "tools"))

import agent_selector


class TestOllamaRouteDefaults:
    """Verify the built-in route table covers required roles and ports."""

    REQUIRED_ROLES = {"coding", "review", "netops", "orchestrator", "default"}

    def test_all_required_roles_present(self) -> None:
        assert self.REQUIRED_ROLES.issubset(agent_selector.OLLAMA_ROUTE_DEFAULTS)

    def test_each_entry_has_model_and_port(self) -> None:
        for role, cfg in agent_selector.OLLAMA_ROUTE_DEFAULTS.items():
            assert "model" in cfg, f"{role} missing 'model'"
            assert "port" in cfg, f"{role} missing 'port'"

    def test_socket0_port(self) -> None:
        for role in ("coding", "orchestrator", "default"):
            assert agent_selector.OLLAMA_ROUTE_DEFAULTS[role]["port"] == 11434

    def test_socket1_port(self) -> None:
        for role in ("review", "netops"):
            assert agent_selector.OLLAMA_ROUTE_DEFAULTS[role]["port"] == 11435

    def test_ports_are_only_valid_sockets(self) -> None:
        valid = {11434, 11435}
        for role, cfg in agent_selector.OLLAMA_ROUTE_DEFAULTS.items():
            assert cfg["port"] in valid, f"{role} has unexpected port {cfg['port']}"


class TestGetOllamaRoute:
    """Verify get_ollama_route returns correct model+port per category."""

    def test_coding_route(self) -> None:
        route = agent_selector.get_ollama_route("coding")
        assert route["model"] == "qwen3-coder:30b"
        assert route["port"] == 11434

    def test_review_route(self) -> None:
        route = agent_selector.get_ollama_route("review")
        assert route["model"] == "qwen3.5:122b"
        assert route["port"] == 11435

    def test_netops_route(self) -> None:
        route = agent_selector.get_ollama_route("netops")
        assert route["model"] == "qwen3:30b-a3b"
        assert route["port"] == 11435

    def test_orchestrator_route(self) -> None:
        route = agent_selector.get_ollama_route("orchestrator")
        assert route["model"] == "qwen3:30b-a3b"
        assert route["port"] == 11434

    def test_default_route(self) -> None:
        route = agent_selector.get_ollama_route("default")
        assert route["model"] == "qwen3:30b-a3b"
        assert route["port"] == 11434

    def test_unknown_category_falls_back_to_default(self) -> None:
        route = agent_selector.get_ollama_route("something_unknown")
        default = agent_selector.get_ollama_route("default")
        assert route == default

    def test_returns_copy_not_reference(self) -> None:
        route = agent_selector.get_ollama_route("coding")
        route["model"] = "tampered"
        fresh = agent_selector.get_ollama_route("coding")
        assert fresh["model"] != "tampered"


class TestOllamaRouteEnvOverride:
    """Verify OLLAMA_ROUTE_JSON env var overrides defaults."""

    def test_override_single_role(self, monkeypatch: pytest.MonkeyPatch) -> None:
        override = {"coding": {"model": "deepseek-coder:33b", "port": 11435}}
        monkeypatch.setenv("OLLAMA_ROUTE_JSON", json.dumps(override))

        route = agent_selector.get_ollama_route("coding")
        assert route["model"] == "deepseek-coder:33b"
        assert route["port"] == 11435

    def test_override_preserves_unmentioned_roles(self, monkeypatch: pytest.MonkeyPatch) -> None:
        override = {"coding": {"model": "custom:7b", "port": 11434}}
        monkeypatch.setenv("OLLAMA_ROUTE_JSON", json.dumps(override))

        review = agent_selector.get_ollama_route("review")
        assert review == {"model": "qwen3.5:122b", "port": 11435}

    def test_override_adds_new_role(self, monkeypatch: pytest.MonkeyPatch) -> None:
        override = {"writing": {"model": "mistral:7b", "port": 11434}}
        monkeypatch.setenv("OLLAMA_ROUTE_JSON", json.dumps(override))

        route = agent_selector.get_ollama_route("writing")
        assert route["model"] == "mistral:7b"
        assert route["port"] == 11434

    def test_malformed_json_ignored(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("OLLAMA_ROUTE_JSON", "not valid json{{{")

        route = agent_selector.get_ollama_route("coding")
        assert route == dict(agent_selector.OLLAMA_ROUTE_DEFAULTS["coding"])

    def test_incomplete_entry_ignored(self, monkeypatch: pytest.MonkeyPatch) -> None:
        override = {"coding": {"model": "only-model"}}  # missing port
        monkeypatch.setenv("OLLAMA_ROUTE_JSON", json.dumps(override))

        route = agent_selector.get_ollama_route("coding")
        assert route == dict(agent_selector.OLLAMA_ROUTE_DEFAULTS["coding"])

    def test_empty_env_uses_defaults(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("OLLAMA_ROUTE_JSON", "")

        route = agent_selector.get_ollama_route("coding")
        assert route == dict(agent_selector.OLLAMA_ROUTE_DEFAULTS["coding"])

    def test_non_dict_env_ignored(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("OLLAMA_ROUTE_JSON", json.dumps([1, 2, 3]))

        route = agent_selector.get_ollama_route("coding")
        assert route == dict(agent_selector.OLLAMA_ROUTE_DEFAULTS["coding"])
