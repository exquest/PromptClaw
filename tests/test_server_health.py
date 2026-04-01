"""Tests for the CypherClaw server health helper."""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "my-claw" / "tools"))

import server_health


def test_telegram_report_formats_healthy_status() -> None:
    report = server_health.telegram_report(
        {
            "healthy": True,
            "checks": {
                "disk_usage": "20%",
                "memory": "40% used",
                "load": "0.3 / 0.2 / 0.1 (8 cores)",
                "temperature": "55C",
                "uptime": "up 2 hours",
                "daemon": "active",
            },
            "warnings": [],
        },
        [],
    )

    assert "All systems nominal" in report
    assert "Disk: 20%" in report
    assert "Daemon: active" in report


def test_check_health_marks_disk_pressure_unhealthy(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(server_health.platform, "system", lambda: "Linux")
    monkeypatch.setattr(server_health.os, "getloadavg", lambda: (1.0, 0.5, 0.25))
    monkeypatch.setattr(server_health.os, "cpu_count", lambda: 8)

    def fake_run(cmd: list[str], **_: object) -> SimpleNamespace:
        if cmd[:2] == ["df", "-h"]:
            return SimpleNamespace(stdout="Filesystem Size Used Avail Use% Mounted on\n/dev/root 100G 95G 5G 95% /\n")
        if cmd[:2] == ["free", "-m"]:
            return SimpleNamespace(stdout="Mem: 1000 500 0 0 0 500\n")
        if cmd[:2] == ["ps", "aux"]:
            return SimpleNamespace(stdout="")
        if cmd[:2] == ["systemctl", "is-active"]:
            return SimpleNamespace(stdout="active\n")
        if cmd[:1] == ["uptime"]:
            return SimpleNamespace(stdout="up 1 day\n")
        return SimpleNamespace(stdout="")

    monkeypatch.setattr(server_health.subprocess, "run", fake_run)

    health = server_health.check_health()

    assert health["healthy"] is False
    assert "CRITICAL: Disk 95% full" in health["warnings"]
    assert health["checks"]["disk_usage"] == "95%"


def test_check_health_reports_linux_nominal_state(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(server_health.platform, "system", lambda: "Linux")
    monkeypatch.setattr(server_health.os, "getloadavg", lambda: (0.5, 0.4, 0.3))
    monkeypatch.setattr(server_health.os, "cpu_count", lambda: 8)

    def fake_run(cmd: list[str], **_: object) -> SimpleNamespace:
        if cmd[:2] == ["df", "-h"]:
            return SimpleNamespace(stdout="Filesystem Size Used Avail Use% Mounted on\n/dev/root 100G 20G 80G 20% /\n")
        if cmd[:2] == ["free", "-m"]:
            return SimpleNamespace(stdout="Mem: 1000 200 0 0 0 800\n")
        if cmd[:2] == ["ps", "aux"]:
            return SimpleNamespace(stdout="USER PID %CPU %MEM VSZ RSS TTY STAT START TIME COMMAND\n")
        if cmd[:2] == ["systemctl", "is-active"]:
            return SimpleNamespace(stdout="active\n")
        if cmd[:2] == ["bash", "-c"]:
            return SimpleNamespace(stdout="45000\n")
        if cmd[:1] == ["uptime"]:
            return SimpleNamespace(stdout="up 2 days\n")
        if cmd[:3] == ["pgrep", "-c", "-f"]:
            return SimpleNamespace(stdout="1\n", returncode=0)
        return SimpleNamespace(stdout="")

    monkeypatch.setattr(server_health.subprocess, "run", fake_run)

    health = server_health.check_health()

    assert health["healthy"] is True
    assert health["warnings"] == []
    assert health["checks"]["memory"] == "20% used (800MB free)"
    assert health["checks"]["daemon"] == "active"
