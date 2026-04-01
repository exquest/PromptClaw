"""Tests for the CypherClaw healthcheck shell script."""

from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path


def _write_executable(path: Path, content: str) -> None:
    path.write_text(content)
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def _build_fake_bin(tmp_path: Path) -> Path:
    bindir = tmp_path / "bin"
    bindir.mkdir()

    _write_executable(
        bindir / "pgrep",
        """#!/bin/sh
if [ "$1" = "-c" ]; then
  echo "${FAKE_PGREP_COUNT:-1}"
  exit 0
fi
echo "${FAKE_DAEMON_PID:-1234}"
exit 0
""",
    )
    _write_executable(
        bindir / "ps",
        """#!/bin/sh
printf '%s\n' "${FAKE_PS_OUTPUT:-}"
""",
    )
    _write_executable(
        bindir / "stat",
        """#!/bin/sh
echo "${FAKE_LOG_TS:-1000}"
""",
    )
    _write_executable(
        bindir / "date",
        """#!/bin/sh
echo "${FAKE_NOW_TS:-1100}"
""",
    )
    _write_executable(
        bindir / "cat",
        """#!/bin/sh
if [ -n "$1" ]; then
  /bin/cat "$1"
else
  /bin/cat
fi
""",
    )
    return bindir


def test_healthcheck_reports_healthy_with_active_agents(tmp_path: Path) -> None:
    bindir = _build_fake_bin(tmp_path)
    proc_root = tmp_path / "proc"
    (proc_root / "1234").mkdir(parents=True)
    (proc_root / "1234" / "status").write_text("State:\tS (sleeping)\n")
    log_file = tmp_path / "daemon.log"
    log_file.write_text("ok\n")
    script = Path("my-claw/tools/healthcheck.sh").resolve()

    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{bindir}:{env['PATH']}",
            "HEALTHCHECK_LOG": str(log_file),
            "HEALTHCHECK_PROC_ROOT": str(proc_root),
            "FAKE_PGREP_COUNT": "1",
            "FAKE_DAEMON_PID": "1234",
            "FAKE_PS_OUTPUT": "",
            "FAKE_NOW_TS": "2000",
            "FAKE_LOG_TS": "1500",
            "FAKE_AGENT_COUNT": "2",
        }
    )
    # active agent pgrep call uses same fake pgrep binary, so emulate via count override
    env["FAKE_PGREP_COUNT"] = "1"

    result = subprocess.run(["bash", str(script)], capture_output=True, text=True, env=env)

    assert result.returncode == 0
    assert "HEALTHY" in result.stdout


def test_healthcheck_reports_stale_log_when_no_agents(tmp_path: Path) -> None:
    bindir = _build_fake_bin(tmp_path)
    # Override pgrep to distinguish daemon count from agents count.
    _write_executable(
        bindir / "pgrep",
        """#!/bin/sh
if [ "$1" = "-c" ] && [ "$3" = "$HEALTHCHECK_DAEMON_PATTERN" ]; then
  echo "${FAKE_DAEMON_COUNT:-1}"
  exit 0
fi
if [ "$1" = "-c" ] && [ "$3" = "${HEALTHCHECK_AGENT_PATTERN:-claude|codex|gemini}" ]; then
  echo "${FAKE_AGENT_COUNT:-0}"
  exit 0
fi
if [ "$1" = "-f" ] && [ "$2" = "${HEALTHCHECK_AGENT_PATTERN:-claude|codex|gemini}" ]; then
  exit 1
fi
echo "${FAKE_DAEMON_PID:-1234}"
exit 0
""",
    )
    proc_root = tmp_path / "proc"
    (proc_root / "1234").mkdir(parents=True)
    (proc_root / "1234" / "status").write_text("State:\tS (sleeping)\n")
    log_file = tmp_path / "daemon.log"
    log_file.write_text("old\n")
    script = Path("my-claw/tools/healthcheck.sh").resolve()

    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{bindir}:{env['PATH']}",
            "HEALTHCHECK_LOG": str(log_file),
            "HEALTHCHECK_PROC_ROOT": str(proc_root),
            "HEALTHCHECK_DAEMON_PATTERN": "python3.*cypherclaw_daemon.py",
            "HEALTHCHECK_AGENT_PATTERN": "claude|codex|gemini",
            "FAKE_DAEMON_COUNT": "1",
            "FAKE_AGENT_COUNT": "0",
            "FAKE_DAEMON_PID": "1234",
            "FAKE_PS_OUTPUT": "",
            "FAKE_NOW_TS": "2000",
            "FAKE_LOG_TS": "1000",
        }
    )

    result = subprocess.run(["bash", str(script)], capture_output=True, text=True, env=env)

    assert result.returncode == 1
    assert "log not updated" in result.stdout
