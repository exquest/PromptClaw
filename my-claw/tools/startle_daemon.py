"""Startle daemon for sudden-sound detection and face reactions.

The daemon polls fused room-activity readings produced by
``my-claw/tools/input_monitor.py``, maintains a rolling baseline of recent
amplitudes, and runs the existing ``senseweave.startle`` rules to decide
whether the installation should react with a startle face and/or mute its
output. The result is written atomically to ``/tmp/startle_state.json`` so
``inner_life.world_model`` and other consumers can pick up the latest
``startled`` / ``startle_count`` flags.

The module is import-safe: importing it does not start a loop, so the helpers
below can be exercised directly from tests.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

TOOLS_DIR = Path(__file__).resolve().parent
SENSEWEAVE_DIR = TOOLS_DIR / "senseweave"
if str(SENSEWEAVE_DIR) not in sys.path:
    sys.path.insert(0, str(SENSEWEAVE_DIR))

from startle import (  # noqa: E402  (path tweak above is required)
    StartleState,
    should_mute_output,
    startle_to_face_reaction,
    update_startle,
)


ROOM_STATE_PATH = Path("/tmp/room_activity.json")
STARTLE_STATE_PATH = Path("/tmp/startle_state.json")
DEFAULT_INTERVAL_SECONDS = 0.5
BASELINE_WINDOW = 20
BASELINE_FLOOR = 0.001


@dataclass
class DaemonState:
    """Combined startle state plus rolling-baseline tracker."""

    startle: StartleState = field(default_factory=StartleState)
    baseline_history: list[float] = field(default_factory=list)


def read_room_activity(
    room_path: str | Path = ROOM_STATE_PATH,
) -> dict[str, Any]:
    """Read one fused room-activity JSON object."""

    try:
        data = json.loads(Path(room_path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def amp_from_room(room: Mapping[str, Any]) -> float:
    """Return the louder of the window/cypherclaw mic amplitudes."""

    window = _float_value(room.get("window_mic_amp", 0.0), default=0.0)
    claw = _float_value(room.get("cypherclaw_mic_amp", 0.0), default=0.0)
    return max(window, claw)


def update_baseline(
    history: Sequence[float],
    amp: float,
    *,
    window: int = BASELINE_WINDOW,
) -> list[float]:
    """Append ``amp`` to the rolling baseline history, dropping old samples."""

    bounded = max(1, int(window))
    new_history = list(history)
    new_history.append(float(amp))
    if len(new_history) > bounded:
        new_history = new_history[-bounded:]
    return new_history


def baseline_value(
    history: Sequence[float],
    *,
    floor: float = BASELINE_FLOOR,
) -> float:
    """Return the rolling-median baseline RMS, never below ``floor``."""

    if not history:
        return floor
    median = statistics.median(history)
    return max(float(median), floor)


def render_output(
    startle: StartleState,
    *,
    amp: float,
    baseline: float,
    now: float | None = None,
) -> dict[str, Any]:
    """Render the JSON payload consumers read from the startle state file."""

    timestamp = time.time() if now is None else now
    return {
        "startled": startle.startled,
        "startle_count": startle.startle_count,
        "cooldown_active": startle.cooldown_active,
        "face_reaction": startle_to_face_reaction(startle),
        "should_mute": should_mute_output(startle),
        "amp": float(amp),
        "baseline": float(baseline),
        "timestamp": float(timestamp),
    }


def write_output(
    payload: Mapping[str, Any],
    state_path: str | Path = STARTLE_STATE_PATH,
) -> None:
    """Atomically write the startle JSON file via a ``.tmp`` rename."""

    target = Path(state_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + ".tmp")
    tmp.write_text(json.dumps(dict(payload)), encoding="utf-8")
    tmp.replace(target)


def process_once(
    *,
    state: DaemonState,
    room_path: str | Path = ROOM_STATE_PATH,
    state_path: str | Path = STARTLE_STATE_PATH,
) -> tuple[DaemonState, dict[str, Any]]:
    """Run one daemon cycle and return the new state plus written payload."""

    room = read_room_activity(room_path)
    amp = amp_from_room(room)
    history = update_baseline(state.baseline_history, amp)
    baseline = baseline_value(history)
    new_startle = update_startle(state.startle, amp, baseline)
    payload = render_output(new_startle, amp=amp, baseline=baseline)
    write_output(payload, state_path)
    return DaemonState(startle=new_startle, baseline_history=history), payload


def run_daemon(
    *,
    interval: float = DEFAULT_INTERVAL_SECONDS,
    max_iterations: int = 0,
    room_path: str | Path = ROOM_STATE_PATH,
    state_path: str | Path = STARTLE_STATE_PATH,
) -> None:
    """Run the startle daemon loop."""

    state = DaemonState()
    iteration = 0
    while True:
        try:
            state, _payload = process_once(
                state=state, room_path=room_path, state_path=state_path
            )
        except Exception as exc:  # pragma: no cover - defensive daemon guard
            print(f"[startle_daemon] cycle failed: {exc}", file=sys.stderr)

        iteration += 1
        if max_iterations > 0 and iteration >= max_iterations:
            break
        if interval > 0:
            time.sleep(interval)


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point."""

    parser = argparse.ArgumentParser(description="CypherClaw startle daemon")
    parser.add_argument("--interval", type=float, default=DEFAULT_INTERVAL_SECONDS)
    parser.add_argument("--room-path", default=str(ROOM_STATE_PATH))
    parser.add_argument("--state-path", default=str(STARTLE_STATE_PATH))
    parser.add_argument("--max-iterations", type=int, default=0)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args(argv)

    max_iterations = 1 if args.once else args.max_iterations
    try:
        run_daemon(
            interval=args.interval,
            max_iterations=max_iterations,
            room_path=args.room_path,
            state_path=args.state_path,
        )
    except KeyboardInterrupt:
        return 130
    return 0


def _float_value(value: Any, *, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


if __name__ == "__main__":
    raise SystemExit(main())
