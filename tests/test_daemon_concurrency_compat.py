"""Compatibility checks for daemon concurrency wiring."""

from __future__ import annotations

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _daemon_source() -> str:
    candidates = [
        PROJECT_ROOT / "my-claw" / "tools" / "cypherclaw_daemon.py",
        PROJECT_ROOT / "tools" / "cypherclaw_daemon.py",
    ]
    daemon_path = next((path for path in candidates if path.exists()), candidates[0])
    return daemon_path.read_text()


def test_semaphore_constants_in_source() -> None:
    source = _daemon_source()
    assert "_SEMAPHORE_MAX = 2" in source
    assert "_SEMAPHORE_IO_REVERT_THRESHOLD = 2" in source
    assert "threading.Semaphore(_SEMAPHORE_MAX)" in source


def test_semaphore_events_in_source() -> None:
    source = _daemon_source()
    assert '"semaphore_acquired"' in source
    assert '"semaphore_released"' in source
    assert '"semaphore_rejected"' in source


def test_watchdog_callback_wired_in_source() -> None:
    source = _daemon_source()
    assert "on_io_kill=_on_io_guard_triggered" in source
