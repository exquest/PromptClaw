"""Regression tests for ``cypherclaw.narrative_api.settings``."""
from __future__ import annotations

import pytest


def test_settings_defaults_when_env_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("NARRATIVE_BIND_HOST", raising=False)
    monkeypatch.delenv("NARRATIVE_BIND_PORT", raising=False)
    monkeypatch.delenv("NARRATIVE_AUTH_TOKEN", raising=False)

    from cypherclaw.narrative_api.settings import NarrativeSettings

    settings = NarrativeSettings(_env_file=None)

    assert settings.bind_host == "127.0.0.1"
    assert settings.bind_port == 8765
    assert settings.auth_token is None


def test_settings_loads_values_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NARRATIVE_BIND_HOST", "100.74.35.114")
    monkeypatch.setenv("NARRATIVE_BIND_PORT", "9001")
    monkeypatch.setenv("NARRATIVE_AUTH_TOKEN", "token-xyz")

    from cypherclaw.narrative_api.settings import NarrativeSettings

    settings = NarrativeSettings(_env_file=None)

    assert settings.bind_host == "100.74.35.114"
    assert settings.bind_port == 9001
    assert settings.auth_token == "token-xyz"


def test_settings_loads_from_dotenv(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("NARRATIVE_BIND_HOST", raising=False)
    monkeypatch.delenv("NARRATIVE_BIND_PORT", raising=False)
    monkeypatch.delenv("NARRATIVE_AUTH_TOKEN", raising=False)

    env_file = tmp_path / ".env"
    env_file.write_text(
        "NARRATIVE_BIND_HOST=10.0.0.5\n"
        "NARRATIVE_BIND_PORT=4242\n"
        "NARRATIVE_AUTH_TOKEN=from-dotenv\n"
    )

    from cypherclaw.narrative_api.settings import NarrativeSettings

    settings = NarrativeSettings(_env_file=str(env_file))

    assert settings.bind_host == "10.0.0.5"
    assert settings.bind_port == 4242
    assert settings.auth_token == "from-dotenv"


def test_main_module_uses_settings_for_auth_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """main.app should be built from a NarrativeSettings instance."""
    import importlib

    from cypherclaw.narrative_api import main as main_module
    from cypherclaw.narrative_api.settings import NarrativeSettings

    monkeypatch.setenv("NARRATIVE_AUTH_TOKEN", "main-token")
    reloaded = importlib.reload(main_module)

    assert isinstance(reloaded.settings, NarrativeSettings)
    assert reloaded.settings.auth_token == "main-token"
