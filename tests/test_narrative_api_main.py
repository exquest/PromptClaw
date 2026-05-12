"""Regression checks for the ``cypherclaw.narrative_api`` entry point."""
from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


def test_main_resolves_host_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    from cypherclaw.narrative_api import __main__ as entry

    monkeypatch.setenv("NARRATIVE_BIND_HOST", "100.74.35.114")
    assert entry._resolve_host() == "100.74.35.114"

    monkeypatch.delenv("NARRATIVE_BIND_HOST", raising=False)
    assert entry._resolve_host() == "127.0.0.1"


def test_main_resolves_port_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    from cypherclaw.narrative_api import __main__ as entry

    monkeypatch.setenv("NARRATIVE_BIND_PORT", "9001")
    assert entry._resolve_port() == 9001

    monkeypatch.delenv("NARRATIVE_BIND_PORT", raising=False)
    assert entry._resolve_port() == 8765


def test_main_reads_settings_object(monkeypatch: pytest.MonkeyPatch) -> None:
    """main() must build a NarrativeSettings and pass its values to uvicorn."""
    from cypherclaw.narrative_api import __main__ as entry
    from cypherclaw.narrative_api.settings import NarrativeSettings

    monkeypatch.setenv("NARRATIVE_BIND_HOST", "192.0.2.10")
    monkeypatch.setenv("NARRATIVE_BIND_PORT", "8123")
    monkeypatch.setenv("NARRATIVE_AUTH_TOKEN", "settings-token")

    captured: dict[str, Any] = {}

    def fake_run(app: Any, **kwargs: Any) -> None:
        captured["run_kwargs"] = kwargs

    def fake_create_app(**kwargs: Any) -> str:
        captured["create_kwargs"] = kwargs
        return "fake-app"

    monkeypatch.setattr(entry, "create_app", fake_create_app)
    monkeypatch.setattr(entry.uvicorn, "run", fake_run)
    monkeypatch.setattr("cypherclaw.first_boot.bootstrap_identity", lambda **kwargs: MagicMock())

    entry.main()

    assert captured["run_kwargs"]["host"] == "192.0.2.10"
    assert captured["run_kwargs"]["port"] == 8123
    assert captured["create_kwargs"]["auth_token"] == "settings-token"
    # Sanity: settings class actually loads the same values.
    settings = NarrativeSettings(_env_file=None)
    assert settings.bind_host == "192.0.2.10"
    assert settings.bind_port == 8123


def test_main_invokes_uvicorn_with_resolved_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from cypherclaw.narrative_api import __main__ as entry

    monkeypatch.setenv("NARRATIVE_BIND_HOST", "100.74.35.114")
    monkeypatch.setenv("NARRATIVE_BIND_PORT", "8765")
    monkeypatch.setenv("NARRATIVE_AUTH_TOKEN", "token-123")

    captured: dict[str, Any] = {}

    def fake_create_app(**kwargs: Any) -> str:
        captured["create_kwargs"] = kwargs
        return "fake-app"

    def fake_run(app: Any, **kwargs: Any) -> None:
        captured["app"] = app
        captured["run_kwargs"] = kwargs

    monkeypatch.setattr(entry, "create_app", fake_create_app)
    monkeypatch.setattr(entry.uvicorn, "run", fake_run)
    monkeypatch.setattr("cypherclaw.first_boot.bootstrap_identity", lambda **kwargs: MagicMock())

    entry.main()

    assert captured["app"] == "fake-app"
    assert captured["run_kwargs"]["host"] == "100.74.35.114"
    assert captured["run_kwargs"]["port"] == 8765
    assert captured["create_kwargs"]["auth_token"] == "token-123"


def test_main_calls_bootstrap_identity() -> None:
    """Verify that main() calls bootstrap_identity() for startup hardening."""
    import ast
    from pathlib import Path

    source = Path("src/cypherclaw/narrative_api/__main__.py").read_text()
    tree = ast.parse(source)

    # Find main() function
    main_fn = None
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "main":
            main_fn = node
            break

    assert main_fn is not None, "main() function not found"

    # Extract all call names in main()
    calls = []
    for node in ast.walk(main_fn):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                calls.append(node.func.id)
            elif isinstance(node.func, ast.Attribute):
                calls.append(node.func.attr)

    assert "bootstrap_identity" in calls, (
        "main() must call bootstrap_identity() for startup hardening"
    )


def test_main_module_exposes_fastapi_app() -> None:
    from cypherclaw.narrative_api import main

    assert isinstance(main.app, FastAPI)


def test_asgi_module_startup_bootstraps_identity_persistence_between_imports(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    """ASGI app import must mint once and reuse identity on later boots."""
    import importlib
    import sys

    import cypherclaw.first_boot as first_boot

    identity_path = tmp_path / "identity.json"
    real_bootstrap = first_boot.bootstrap_identity
    booted_ids: list[str] = []

    def bootstrap_for_test(**kwargs: Any):
        identity = real_bootstrap(
            mode="federated",
            release="test-release",
            parent_id="origin-home",
            identity_path=identity_path,
        )
        booted_ids.append(identity.instance_id)
        return identity

    monkeypatch.setattr(first_boot, "bootstrap_identity", bootstrap_for_test)

    def import_fresh_main():
        sys.modules.pop("cypherclaw.narrative_api.main", None)
        package = sys.modules.get("cypherclaw.narrative_api")
        if package is not None and hasattr(package, "main"):
            delattr(package, "main")
        return importlib.import_module("cypherclaw.narrative_api.main")

    first_main = import_fresh_main()
    second_main = import_fresh_main()

    assert isinstance(first_main.app, FastAPI)
    assert isinstance(second_main.app, FastAPI)
    assert identity_path.exists()
    assert len(booted_ids) == 2
    assert booted_ids[0] == booted_ids[1]


def test_main_module_health_endpoint_responds() -> None:
    from cypherclaw.narrative_api import main

    client = TestClient(main.app)
    response = client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert "status" in body
    assert "version" in body
