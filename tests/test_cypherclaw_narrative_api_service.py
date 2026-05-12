"""Regression checks for the CypherClaw Narrative API systemd unit."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _read(path: str) -> str:
    return (ROOT / path).read_text()


def test_narrative_api_service_targets_default_boot_as_user() -> None:
    path = "my-claw/systemd/cypherclaw-narrative-api.service"
    unit = _read(path)

    # Unit metadata
    assert "Description=CypherClaw Narrative API" in unit
    assert "After=network-online.target" in unit
    assert "Wants=network-online.target" in unit

    # Service execution
    assert "Type=simple" in unit
    assert "EnvironmentFile=-%h/cypherclaw/.env" in unit
    assert "Environment=PYTHONUNBUFFERED=1" in unit
    assert "WorkingDirectory=%h/cypherclaw" in unit
    assert "ExecStart=%h/cypherclaw/.venv/bin/python3 -m cypherclaw.narrative_api" in unit

    # Reliability policy
    assert "Restart=on-failure" in unit
    assert "RestartSec=5" in unit
    assert "StartLimitIntervalSec=300" in unit
    assert "StartLimitBurst=10" in unit

    # Logging
    assert "StandardOutput=journal" in unit
    assert "StandardError=journal" in unit
    assert "SyslogIdentifier=cypherclaw-narrative-api" in unit

    # Installation
    assert "[Install]" in unit
    assert "WantedBy=default.target" in unit
