"""Tests for the LifeImprover bridge."""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "my-claw" / "tools"))

import lifeimprover_bridge


def test_is_available_returns_true_on_http_200(monkeypatch: pytest.MonkeyPatch) -> None:
    bridge = lifeimprover_bridge.LifeImproverBridge()

    class FakeResponse:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(
        lifeimprover_bridge.urllib.request,
        "urlopen",
        lambda req, timeout=5: FakeResponse(),
    )

    assert bridge.is_available() is True


def test_get_pipeline_status_uses_api_when_available(monkeypatch: pytest.MonkeyPatch) -> None:
    bridge = lifeimprover_bridge.LifeImproverBridge()
    monkeypatch.setattr(
        bridge,
        "_api_get",
        lambda endpoint: [
            {"stage": "new"},
            {"stage": "new"},
            {"status": "qualified"},
        ],
    )

    status = bridge.get_pipeline_status()

    assert status.total == 3
    assert status.by_stage == {"new": 2, "qualified": 1}


def test_get_pipeline_status_falls_back_to_cli(monkeypatch: pytest.MonkeyPatch) -> None:
    bridge = lifeimprover_bridge.LifeImproverBridge()
    monkeypatch.setattr(bridge, "_api_get", lambda endpoint: None)
    monkeypatch.setattr(bridge, "_run_ldp", lambda *args, timeout=15: "raw cli output")

    status = bridge.get_pipeline_status()

    assert status.total == 0
    assert status.by_stage == {"raw": "raw cli output"}


def test_telegram_summary_formats_online_status(monkeypatch: pytest.MonkeyPatch) -> None:
    bridge = lifeimprover_bridge.LifeImproverBridge()
    monkeypatch.setattr(bridge, "is_available", lambda: True)
    monkeypatch.setattr(
        bridge,
        "get_daily_briefing",
        lambda: lifeimprover_bridge.BriefingResult(True, "Ship the queue"),
    )
    monkeypatch.setattr(
        bridge,
        "get_pipeline_status",
        lambda: lifeimprover_bridge.PipelineStatus(
            leads=[{"id": 1}, {"id": 2}],
            total=2,
            by_stage={"new": 1, "qualified": 1},
        ),
    )

    summary = bridge.telegram_summary()

    assert "🏠 LifeImprover Status" in summary
    assert "📋 Today:" in summary
    assert "Ship the queue" in summary
    assert "🎯 Pipeline: 2 leads (new: 1, qualified: 1)" in summary


def test_run_ldp_appends_stderr_on_failure(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    bridge = lifeimprover_bridge.LifeImproverBridge()
    bridge.project_path = tmp_path

    monkeypatch.setattr(
        lifeimprover_bridge.subprocess,
        "run",
        lambda cmd, **kwargs: SimpleNamespace(returncode=1, stdout="", stderr="bad command"),
    )

    output = bridge._run_ldp("today")

    assert output == "\n[stderr] bad command"
