"""Regression tests for Linux-safe daemon status checks."""

from __future__ import annotations

import inspect
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _tools_path() -> str:
    candidates = [
        PROJECT_ROOT / "my-claw" / "tools",
        PROJECT_ROOT / "tools",
    ]
    resolved = next((path for path in candidates if path.exists()), candidates[0])
    return str(resolved.relative_to(PROJECT_ROOT))


def test_check_status_no_crash() -> None:
    tools_path = _tools_path()
    code = (
        "import sys; "
        f"sys.path.insert(0, {tools_path!r}); "
        "from cypherclaw_daemon import check_status; "
        "check_status()"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        cwd=str(PROJECT_ROOT),
    )
    assert result.returncode == 0, result.stderr


def test_check_status_uses_platform_detection() -> None:
    sys.path.insert(0, str((PROJECT_ROOT / _tools_path()).resolve()))
    from cypherclaw_daemon import check_status

    source = inspect.getsource(check_status)
    assert "platform" in source
