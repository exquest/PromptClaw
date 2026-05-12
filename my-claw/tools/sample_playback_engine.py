#!/usr/bin/env python3
"""Live sample-playback engine for CypherClaw."""
from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Any

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "senseweave"))

from archive_paths import resolve_sample_events_dir
from senseweave.sample_event_renderer import render_sample_event


ACTIVITY_PATH = Path("/tmp/sample_dsp_activity.json")
STATE_PATH = Path("/tmp/sample_playback_state.json")
OUTPUT_DIR = Path(os.environ.get("CYPHERCLAW_SAMPLE_EVENT_DIR", str(resolve_sample_events_dir(__file__))))
POLL_SECONDS = float(os.environ.get("SAMPLE_PLAYBACK_POLL_SECONDS", "1.0"))

COOLDOWNS = {
    "grain_cloud": 5.0,
    "slice_accents": 4.0,
    "window_echo": 5.0,
    "freeze_bed": 18.0,
    "lowpass_wash": 12.0,
    "texture_bed": 10.0,
}


@dataclass
class EngineState:
    last_trigger_at: float = 0.0
    last_signature: str = ""
    last_transport_key: str = ""
    current_output_path: str = ""


@dataclass(frozen=True)
class LaunchDecision:
    should_launch: bool
    reason: str
    cooldown_s: float


def read_json(path: Path) -> dict:
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def write_state(state: dict) -> None:
    tmp = STATE_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(state))
    os.replace(str(tmp), str(STATE_PATH))


def choose_launch(
    *,
    activity: dict,
    now: float,
    state: EngineState,
    player_running: bool,
) -> LaunchDecision:
    mode = str(activity.get("activity_mode", "texture_bed"))
    cooldown = COOLDOWNS.get(mode, 8.0)
    if player_running:
        return LaunchDecision(False, "player_running", cooldown)
    if not bool(activity.get("capture_ready")):
        return LaunchDecision(False, "capture_not_ready", cooldown)
    if not str(activity.get("capture_path", "")):
        return LaunchDecision(False, "missing_capture_path", cooldown)
    transport_trigger_now = bool(activity.get("transport_trigger_now"))
    transport_trigger_key = str(activity.get("transport_trigger_key", "") or "")
    if transport_trigger_now and transport_trigger_key:
        if transport_trigger_key == state.last_transport_key:
            return LaunchDecision(False, "transport_held", cooldown)
        if now - state.last_trigger_at >= cooldown:
            return LaunchDecision(True, "transport_lock", cooldown)
        return LaunchDecision(False, "transport_cooldown", cooldown)
    if bool(activity.get("trigger_now")):
        if now - state.last_trigger_at >= cooldown:
            return LaunchDecision(True, "trigger_now", cooldown)
        return LaunchDecision(False, "cooldown", cooldown)
    if mode in {"freeze_bed", "lowpass_wash", "texture_bed"} and float(activity.get("wet_mix", 0.0) or 0.0) >= 0.18:
        if now - state.last_trigger_at >= cooldown:
            return LaunchDecision(True, "bed_refresh", cooldown)
    return LaunchDecision(False, "inactive", cooldown)


def playback_signature(activity: dict) -> str:
    return "|".join(
        [
            str(activity.get("sample_source", "")),
            str(activity.get("capture_path", "")),
            str(activity.get("activity_mode", "")),
            str(activity.get("wet_mix", "")),
            str(activity.get("capture_age_s", "")),
        ]
    )


def launch_pw_play(path: Path) -> subprocess.Popen[bytes]:
    return subprocess.Popen(
        ["pw-play", str(path)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def maybe_launch_event(
    *,
    activity: dict[str, Any],
    now: float,
    state: EngineState,
    player: subprocess.Popen[bytes] | None,
) -> dict[str, Any]:
    player_running = player is not None and player.poll() is None
    decision = choose_launch(activity=activity, now=now, state=state, player_running=player_running)
    signature = playback_signature(activity)
    if not decision.should_launch:
        return {
            "launched": False,
            "player": player,
            "decision": decision,
            "signature": signature,
        }

    capture_path = Path(str(activity.get("capture_path", "")))
    if not capture_path.exists():
        return {
            "launched": False,
            "player": player,
            "decision": LaunchDecision(False, "missing_capture_file", decision.cooldown_s),
            "signature": signature,
        }

    try:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        output_path = OUTPUT_DIR / f"sample-event-{int(now)}.wav"
        meta = render_sample_event(
            source_path=capture_path,
            output_path=output_path,
            activity=activity,
            seed=int(now),
        )
        player = launch_pw_play(output_path)
    except Exception as exc:
        write_state(
            {
                "timestamp": now,
                "playing": player_running,
                "mode": activity.get("activity_mode", ""),
                "reason": "render_failed",
                "error": str(exc),
                "traceback": traceback.format_exc(limit=2),
                "capture_path": str(capture_path),
                "sample_source": activity.get("sample_source", ""),
                "requested_sample_source": activity.get("requested_sample_source", ""),
            }
        )
        return {
            "launched": False,
            "player": player,
            "decision": LaunchDecision(False, "render_failed", decision.cooldown_s),
            "signature": signature,
        }

    state.last_trigger_at = now
    state.last_signature = signature
    state.last_transport_key = str(activity.get("transport_trigger_key", "") or "")
    state.current_output_path = str(output_path)
    write_state(
        {
            "timestamp": now,
            "playing": True,
            "mode": meta["mode"],
            "reason": decision.reason,
            "output_path": str(output_path),
            "capture_path": str(capture_path),
            "sample_source": activity.get("sample_source", ""),
            "requested_sample_source": activity.get("requested_sample_source", ""),
            "transport_trigger_key": state.last_transport_key,
            "duration_s": meta["duration_s"],
        }
    )
    return {
        "launched": True,
        "player": player,
        "decision": decision,
        "signature": signature,
    }


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    state = EngineState()
    player: subprocess.Popen[bytes] | None = None

    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    signal.signal(signal.SIGINT, lambda *_: sys.exit(0))

    while True:
        now = time.time()
        activity = read_json(ACTIVITY_PATH)
        player_running = player is not None and player.poll() is None
        if not activity:
            write_state({"timestamp": now, "playing": player_running, "reason": "no_activity"})
            time.sleep(POLL_SECONDS)
            continue

        launch = maybe_launch_event(activity=activity, now=now, state=state, player=player)
        player = launch["player"]
        decision = launch["decision"]
        launched = bool(launch["launched"])
        if not launched:
            write_state(
                {
                    "timestamp": now,
                    "playing": player_running,
                    "mode": activity.get("activity_mode", ""),
                    "reason": decision.reason,
                    "capture_path": activity.get("capture_path", ""),
                    "sample_source": activity.get("sample_source", ""),
                    "requested_sample_source": activity.get("requested_sample_source", ""),
                    "transport_trigger_key": str(activity.get("transport_trigger_key", "") or ""),
                    "output_path": state.current_output_path,
                }
            )
        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    main()
