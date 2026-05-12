"""Tests for the CypherClaw Telegram runtime helper."""

from __future__ import annotations

import json
import sys
from pathlib import Path
import urllib.request

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "my-claw" / "tools"))

import telegram


def test_get_telegram_config_requires_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)

    with pytest.raises(RuntimeError, match="TELEGRAM_BOT_TOKEN"):
        telegram.get_telegram_config()


def test_send_message_uses_env_config(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token-123")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "42")
    captured: dict[str, object] = {}

    def fake_api(method: str, data: dict | None = None, files: dict | None = None) -> dict:
        captured["method"] = method
        captured["data"] = data
        captured["files"] = files
        return {"ok": True}

    monkeypatch.setattr(telegram, "_api", fake_api)

    result = telegram.send_message("hello", parse_mode="Markdown")

    assert result == {"ok": True}
    assert captured["method"] == "sendMessage"
    assert captured["data"] == {"chat_id": "42", "text": "hello", "parse_mode": "Markdown"}


def test_check_messages_filters_to_configured_chat_and_updates_state(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token-123")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "42")
    monkeypatch.setattr(telegram, "STATE_FILE", str(tmp_path / "telegram-state.json"))

    def fake_get_updates(offset: int | None = None) -> list[dict]:
        assert offset is None
        return [
            {
                "update_id": 10,
                "message": {
                    "chat": {"id": 42},
                    "date": 100,
                    "text": "hello",
                    "from": {"first_name": "Anthony"},
                },
            },
            {
                "update_id": 11,
                "message": {
                    "chat": {"id": 99},
                    "date": 101,
                    "text": "ignore me",
                    "from": {"first_name": "Other"},
                },
            },
        ]

    monkeypatch.setattr(telegram, "get_updates", fake_get_updates)

    messages = telegram.check_messages()

    assert messages == [{"date": 100, "text": "hello", "from": "Anthony"}]
    state = json.loads((tmp_path / "telegram-state.json").read_text())
    assert state["last_update_id"] == 11


def test_send_message_is_suppressed_during_pytest_subprocesses(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token-123")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "42")
    monkeypatch.setenv("PYTEST_CURRENT_TEST", "tests/test_safe_reboot.py::test_resume")

    def fail_urlopen(*args: object, **kwargs: object) -> object:
        raise AssertionError("urlopen should not run when Telegram sends are suppressed")

    monkeypatch.setattr(urllib.request, "urlopen", fail_urlopen)

    result = telegram.send_message("hello from pytest")

    assert result["ok"] is True
    assert result["suppressed"] is True
    assert result["reason"] == "suppressed during pytest execution"


def test_send_message_can_override_pytest_suppression(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token-123")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "42")
    monkeypatch.setenv("PYTEST_CURRENT_TEST", "tests/test_safe_reboot.py::test_resume")
    monkeypatch.setenv("PROMPTCLAW_ALLOW_LIVE_TELEGRAM", "1")

    class _FakeResponse:
        def __enter__(self) -> "_FakeResponse":
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

        def read(self) -> bytes:
            return b'{"ok": true, "result": {"message_id": 1}}'

    captured: dict[str, object] = {}

    def fake_urlopen(req: urllib.request.Request, timeout: int = 30) -> _FakeResponse:
        captured["url"] = req.full_url
        captured["timeout"] = timeout
        captured["payload"] = json.loads(req.data.decode())
        return _FakeResponse()

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    result = telegram.send_message("live override")

    assert result == {"ok": True, "result": {"message_id": 1}}
    assert captured["url"] == "https://api.telegram.org/bottoken-123/sendMessage"
    assert captured["timeout"] == 30
    assert captured["payload"] == {"chat_id": "42", "text": "live override"}


def test_send_message_is_suppressed_from_task_run_workdir(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token-123")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "42")
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.setattr(
        telegram,
        "__file__",
        "/run/cypherclaw-tmp/workdir/cypherclaw-work/tools/telegram.py",
    )

    def fail_urlopen(*args: object, **kwargs: object) -> object:
        raise AssertionError("urlopen should not run for tmpfs task-run workdirs")

    monkeypatch.setattr(urllib.request, "urlopen", fail_urlopen)

    result = telegram.send_message("hello from workdir")

    assert result["ok"] is True
    assert result["suppressed"] is True
    assert "task-run workdir" in result["reason"]
