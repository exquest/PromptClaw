"""Regression tests for the startle daemon."""

from __future__ import annotations

import importlib
import json
import subprocess
import sys
import textwrap
from pathlib import Path
from types import ModuleType

import pytest


TOOLS_PATH = Path(__file__).parent.parent / "my-claw" / "tools"


def test_module_import_is_side_effect_free() -> None:
    script = textwrap.dedent(
        f"""
        import sys
        sys.path.insert(0, {str(TOOLS_PATH)!r})
        import startle_daemon as daemon
        expected = (
            "read_room_activity",
            "amp_from_room",
            "update_baseline",
            "baseline_value",
            "render_output",
            "write_output",
            "process_once",
            "run_daemon",
        )
        print(",".join(name for name in expected if hasattr(daemon, name)))
        """
    )

    try:
        result = subprocess.run(
            [sys.executable, "-c", script],
            capture_output=True,
            text=True,
            timeout=2.0,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        pytest.fail(f"startle_daemon import did not return: {exc}")

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip().split(",") == [
        "read_room_activity",
        "amp_from_room",
        "update_baseline",
        "baseline_value",
        "render_output",
        "write_output",
        "process_once",
        "run_daemon",
    ]


def _daemon_module() -> ModuleType:
    if str(TOOLS_PATH) not in sys.path:
        sys.path.insert(0, str(TOOLS_PATH))
    return importlib.import_module("startle_daemon")


def test_amp_and_baseline_helpers_produce_meaningful_values() -> None:
    daemon = _daemon_module()

    amp = daemon.amp_from_room(
        {"window_mic_amp": 0.07, "cypherclaw_mic_amp": 0.42, "recent_transient": True}
    )
    assert amp == pytest.approx(0.42)

    history: list[float] = []
    for sample in [0.02, 0.03, 0.025, 0.035]:
        history = daemon.update_baseline(history, sample, window=4)
    assert history == [0.02, 0.03, 0.025, 0.035]

    history = daemon.update_baseline(history, 0.5, window=4)
    assert history == [0.03, 0.025, 0.035, 0.5]

    baseline = daemon.baseline_value([0.02, 0.03, 0.025, 0.035])
    assert baseline == pytest.approx(0.0275)

    floor = daemon.baseline_value([])
    assert floor > 0.0


def test_process_once_writes_startled_state_for_loud_room(tmp_path: Path) -> None:
    daemon = _daemon_module()
    room_path = tmp_path / "room_activity.json"
    state_path = tmp_path / "startle_state.json"

    quiet_history = [0.02] * 10
    state = daemon.DaemonState(baseline_history=list(quiet_history))

    room_path.write_text(
        json.dumps(
            {
                "window_mic_amp": 0.05,
                "cypherclaw_mic_amp": 0.6,
                "recent_transient": True,
                "activity_level": "loud",
            }
        ),
        encoding="utf-8",
    )

    new_state, payload = daemon.process_once(
        state=state, room_path=room_path, state_path=state_path
    )

    assert new_state.startle.startled is True
    assert new_state.startle.startle_count == 1
    assert new_state.startle.cooldown_active is True
    assert payload["startled"] is True
    assert payload["startle_count"] == 1
    assert payload["cooldown_active"] is True
    assert payload["face_reaction"]["expression"] == "surprised"
    assert payload["face_reaction"]["eye_widen"] is True
    assert payload["face_reaction"]["duration_ms"] == 500
    assert payload["amp"] == pytest.approx(0.6)
    assert payload["baseline"] > 0.0
    assert "timestamp" in payload

    on_disk = json.loads(state_path.read_text(encoding="utf-8"))
    assert on_disk["startled"] is True
    assert on_disk["startle_count"] == 1
    assert on_disk["face_reaction"]["expression"] == "surprised"


def test_run_daemon_writes_quiet_state_for_silent_room(tmp_path: Path) -> None:
    daemon = _daemon_module()
    room_path = tmp_path / "room_activity.json"
    state_path = tmp_path / "startle_state.json"

    room_path.write_text(
        json.dumps(
            {
                "window_mic_amp": 0.001,
                "cypherclaw_mic_amp": 0.001,
                "recent_transient": False,
                "activity_level": "quiet",
            }
        ),
        encoding="utf-8",
    )

    daemon.run_daemon(
        interval=0.0,
        max_iterations=3,
        room_path=room_path,
        state_path=state_path,
    )

    on_disk = json.loads(state_path.read_text(encoding="utf-8"))
    assert on_disk["startled"] is False
    assert on_disk["startle_count"] == 0
    assert on_disk["face_reaction"]["expression"] == "calm"
    assert on_disk["face_reaction"]["eye_widen"] is False
