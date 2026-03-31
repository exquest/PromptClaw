"""Tests for quota-aware provider degradation."""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "my-claw" / "tools"))

import quota_monitor


class FakeObservatory:
    def __init__(self) -> None:
        self.healing_events: list[dict[str, object]] = []
        self.events: list[tuple[str, dict[str, object]]] = []

    def record_healing(
        self,
        failure_type: str,
        severity: int,
        action_taken: str,
        success: bool,
        context: dict[str, object],
    ) -> None:
        self.healing_events.append(
            {
                "failure_type": failure_type,
                "severity": severity,
                "action_taken": action_taken,
                "success": success,
                "context": context,
            }
        )

    def record(self, event_type: str, data: dict[str, object]) -> None:
        self.events.append((event_type, data))


def _values(
    *,
    anthropic: tuple[float, str] = (0.9, "observed"),
    openai: tuple[float, str] = (0.9, "observed"),
    google: tuple[float, str] = (0.9, "observed"),
) -> dict[str, tuple[float, str]]:
    return {
        "anthropic": anthropic,
        "openai": openai,
        "google": google,
    }


def _patch_headroom(
    monkeypatch: pytest.MonkeyPatch,
    values: dict[str, tuple[float, str]],
) -> None:
    monkeypatch.setattr(
        quota_monitor.QuotaMonitor,
        "_load_provider_headroom",
        lambda self, provider: values[provider],
    )


def _build_monitor(*, observatory: FakeObservatory | None = None, alerts: list[str] | None = None) -> quota_monitor.QuotaMonitor:
    return quota_monitor.QuotaMonitor(
        observatory=observatory,
        poll_interval=0.01,
        alert_callback=(alerts.append if alerts is not None else None),
    )


class TestQuotaMonitor:
    def test_healthy_when_headroom_above_30_pct(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monitor = _build_monitor()
        _patch_headroom(monkeypatch, _values(anthropic=(0.31, "observed")))

        monitor.poll_once()

        assert monitor.provider_status["anthropic"] == "healthy"

    def test_warn_when_headroom_15_to_30_pct(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monitor = _build_monitor()
        _patch_headroom(monkeypatch, _values(anthropic=(0.22, "observed")))

        monitor.poll_once()

        assert monitor.provider_status["anthropic"] == "warn"

    def test_degraded_when_headroom_5_to_15_pct(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monitor = _build_monitor()
        _patch_headroom(monkeypatch, _values(anthropic=(0.10, "observed")))

        monitor.poll_once()

        assert monitor.provider_status["anthropic"] == "degraded"

    def test_paused_when_headroom_below_5_pct(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monitor = _build_monitor()
        _patch_headroom(monkeypatch, _values(anthropic=(0.03, "observed")))

        monitor.poll_once()

        assert monitor.provider_status["anthropic"] == "paused"

    def test_get_available_agents_excludes_paused(self) -> None:
        monitor = _build_monitor()
        monitor.force_status("anthropic", "paused", headroom=0.01, confidence="runtime")
        monitor.force_status("openai", "healthy", headroom=0.70, confidence="observed")
        monitor.force_status("google", "warn", headroom=0.25, confidence="observed")

        assert "claude" not in monitor.get_available_agents()

    def test_get_available_agents_excludes_degraded(self) -> None:
        monitor = _build_monitor()
        monitor.force_status("anthropic", "healthy", headroom=0.60, confidence="observed")
        monitor.force_status("openai", "degraded", headroom=0.10, confidence="observed")
        monitor.force_status("google", "healthy", headroom=0.80, confidence="observed")

        assert "codex" not in monitor.get_available_agents()

    def test_get_available_agents_includes_warn(self) -> None:
        monitor = _build_monitor()
        monitor.force_status("anthropic", "healthy", headroom=0.90, confidence="observed")
        monitor.force_status("openai", "warn", headroom=0.20, confidence="observed")
        monitor.force_status("google", "paused", headroom=0.01, confidence="observed")

        assert "codex" in monitor.get_available_agents()

    def test_never_returns_empty_list(self) -> None:
        monitor = _build_monitor()
        monitor.force_status("anthropic", "paused", headroom=0.01, confidence="runtime")
        monitor.force_status("openai", "paused", headroom=0.04, confidence="runtime")
        monitor.force_status("google", "paused", headroom=0.02, confidence="runtime")

        assert monitor.get_available_agents() == ["codex"]

    def test_status_transition_triggers_alert(self, monkeypatch: pytest.MonkeyPatch) -> None:
        alerts: list[str] = []
        monitor = _build_monitor(alerts=alerts)
        _patch_headroom(monkeypatch, _values(anthropic=(0.80, "observed")))
        monitor.poll_once()

        _patch_headroom(monkeypatch, _values(anthropic=(0.25, "observed")))
        monitor.poll_once()

        assert alerts
        assert "healthy" in alerts[-1]
        assert "warn" in alerts[-1]

    def test_alert_not_sent_for_same_status(self, monkeypatch: pytest.MonkeyPatch) -> None:
        alerts: list[str] = []
        monitor = _build_monitor(alerts=alerts)
        _patch_headroom(monkeypatch, _values(anthropic=(0.22, "observed")))

        monitor.poll_once()
        alerts.clear()
        monitor.poll_once()

        assert alerts == []

    def test_sdp_import_failure_falls_back_gracefully(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monitor = _build_monitor()

        monkeypatch.setattr(quota_monitor.importlib, "import_module", lambda name: (_ for _ in ()).throw(ImportError("missing")))

        monitor.poll_once()
        status = monitor.get_provider_status()

        assert monitor.provider_status == {
            "anthropic": "healthy",
            "openai": "healthy",
            "google": "healthy",
        }
        assert status["anthropic"]["headroom"] == pytest.approx(1.0)
        assert status["anthropic"]["confidence"] == "unknown"

    def test_cli_error_treated_as_error_status(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monitor = _build_monitor()

        fake_module = SimpleNamespace(
            get_quota_headroom=lambda *args: (_ for _ in ()).throw(RuntimeError("db failure"))
        )
        monkeypatch.setattr(quota_monitor.importlib, "import_module", lambda name: fake_module)
        monkeypatch.setattr(quota_monitor, "run_sdp_command", lambda *args, **kwargs: ("", "boom", 1))

        monitor.poll_once()

        assert monitor.provider_status["anthropic"] == "error"

    def test_records_degradation_to_observatory(self, monkeypatch: pytest.MonkeyPatch) -> None:
        observatory = FakeObservatory()
        monitor = _build_monitor(observatory=observatory)
        _patch_headroom(monkeypatch, _values(anthropic=(0.90, "observed")))
        monitor.poll_once()

        _patch_headroom(monkeypatch, _values(anthropic=(0.12, "observed")))
        monitor.poll_once()

        assert observatory.healing_events
        assert observatory.healing_events[-1]["failure_type"] == "provider_degradation"

    def test_polling_interval_respected(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monitor = _build_monitor()
        waits: list[float] = []

        monkeypatch.setattr(monitor, "poll_once", lambda: None)

        def fake_wait() -> bool:
            waits.append(monitor.poll_interval)
            monitor._stop_event.set()
            return True

        monkeypatch.setattr(monitor, "_wait_for_next_poll", fake_wait)

        monitor._poll_loop()

        assert waits == [0.01]

    def test_stop_terminates_polling_thread(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monitor = _build_monitor()
        _patch_headroom(monkeypatch, _values())

        monitor.start()
        monitor.stop()

        assert monitor._thread is not None
        assert not monitor._thread.is_alive()

    def test_runtime_failure_detection(self) -> None:
        assert quota_monitor.is_quota_error("HTTP 429 rate limit exceeded")
        assert quota_monitor.is_quota_error("insufficient balance for this request")
        assert quota_monitor.is_quota_error("resource exhausted")
        assert not quota_monitor.is_quota_error("SyntaxError: invalid syntax")
