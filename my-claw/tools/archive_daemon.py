"""Archive Daemon — records everything CypherClaw creates and experiences.

Runs continuously. Archives:
- Music: 30s recordings every 5 minutes
- Conversations: full Telegram + face bus to daily log
- Camera: hourly snapshots from all cameras
- State: periodic snapshots of all sensor state
"""
import json, os, shutil, subprocess, time
from datetime import datetime
from pathlib import Path

from archive_paths import resolve_archive_recordings_root, resolve_camera_capture_dir


ARCHIVE_ROOT = Path(os.environ.get("CYPHERCLAW_ARCHIVE_RECORDINGS_DIR", str(resolve_archive_recordings_root(__file__))))
MUSIC_DIR = ARCHIVE_ROOT / "music"
CONVERSATIONS_DIR = ARCHIVE_ROOT / "conversations"
CAMERA_DIR = ARCHIVE_ROOT / "camera"
STATE_DIR = ARCHIVE_ROOT / "state_snapshots"
PORCH_CAPTURE_DIR = Path(os.environ.get("CYPHERCLAW_PORCH_CAPTURE_DIR", str(resolve_camera_capture_dir(__file__, "porch_eye"))))
SIDE_CAPTURE_DIR = Path(os.environ.get("CYPHERCLAW_SIDE_CAPTURE_DIR", str(resolve_camera_capture_dir(__file__, "side_eye"))))

for d in [MUSIC_DIR, CONVERSATIONS_DIR, CAMERA_DIR, STATE_DIR]:
    d.mkdir(parents=True, exist_ok=True)


def archive_music():
    """Record 30 seconds of own output and save with timestamp."""
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = MUSIC_DIR / f"performance_{ts}.wav"
    try:
        subprocess.run(
            ["pw-jack", "jack_rec", "-f", str(path), "-d", "30", "-b", "16",
             "SuperCollider:out_1", "SuperCollider:out_2"],
            timeout=35, capture_output=True,
        )
        if path.exists() and path.stat().st_size > 10000:
            try:
                comp = json.loads(open("/tmp/composer_state.json").read())
                inner = json.loads(open("/tmp/inner_life_state.json").read())
                meta = {
                    "timestamp": ts, "key": comp.get("key"),
                    "movement": comp.get("movement"), "song": comp.get("song"),
                    "mood": inner.get("mood"), "arc_phase": inner.get("arc_phase"),
                    "mode": inner.get("mode"),
                }
                path.with_suffix(".json").write_text(json.dumps(meta, indent=2))
            except Exception:
                pass
            print(f"Music: {path.name}", flush=True)
    except Exception:
        pass


def archive_conversations():
    """Append face bus to daily conversation log."""
    today = datetime.now().strftime("%Y-%m-%d")
    log_path = CONVERSATIONS_DIR / f"conversations_{today}.jsonl"

    bus_path = "/tmp/cypherclaw_messages.jsonl"
    bus_offset_path = "/tmp/archive_bus_offset"

    try:
        if not os.path.exists(bus_path):
            return
        with open(bus_path) as f:
            lines = f.readlines()

        # Track what we already archived
        offset = 0
        try:
            offset = int(open(bus_offset_path).read().strip())
        except Exception:
            pass

        new_lines = lines[offset:]
        if new_lines:
            with open(log_path, "a") as out:
                for line in new_lines:
                    out.write(line)
            with open(bus_offset_path, "w") as f:
                f.write(str(len(lines)))
            print(f"Conversations: {len(new_lines)} new messages", flush=True)
    except Exception:
        pass

    # Also archive daemon conversation buffer
    try:
        daemon = json.loads(open("/home/user/cypherclaw/tools/.daemon_state.json").read())
        conv = daemon.get("conversation", [])
        if conv:
            daemon_log = CONVERSATIONS_DIR / f"daemon_{today}.jsonl"
            existing = set()
            try:
                existing = set(open(daemon_log).readlines())
            except Exception:
                pass
            with open(daemon_log, "a") as out:
                for msg in conv:
                    line = json.dumps({"source": "daemon", **msg}) + "\n"
                    if line not in existing:
                        out.write(line)
    except Exception:
        pass


def archive_cameras():
    """Save a snapshot from each camera."""
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    day_dir = CAMERA_DIR / datetime.now().strftime("%Y-%m-%d")
    day_dir.mkdir(exist_ok=True)

    for name, src in [("observer", "/tmp/observer_frame.jpg"),
                      ("room", "/tmp/room_frame.jpg")]:
        try:
            if os.path.exists(src) and os.path.getsize(src) > 1000:
                shutil.copy2(src, day_dir / f"{name}_{ts}.jpg")
        except Exception:
            pass

    for name, src_dir in [("porch", str(PORCH_CAPTURE_DIR)),
                          ("side", str(SIDE_CAPTURE_DIR))]:
        try:
            frames = sorted(Path(src_dir).glob("frame_*.jpg"))
            if frames:
                shutil.copy2(frames[-1], day_dir / f"{name}_{ts}.jpg")
        except Exception:
            pass

    print(f"Cameras: {ts}", flush=True)


def archive_state_snapshot():
    """Save a snapshot of all state files."""
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    snapshot = {}
    for name, path in [
        ("composer", "/tmp/composer_state.json"),
        ("organism", "/tmp/organism_state.json"),
        ("inner_life", "/tmp/inner_life_state.json"),
        ("characters", "/tmp/active_characters.json"),
        ("garden", "/tmp/garden_state.json"),
        ("observer", "/tmp/observer_state.json"),
    ]:
        try:
            snapshot[name] = json.loads(open(path).read())
        except Exception:
            snapshot[name] = None

    path = STATE_DIR / f"snapshot_{ts}.json"
    path.write_text(json.dumps(snapshot, indent=2))
    print(f"State: {path.name}", flush=True)


def run():
    print("Archive daemon started", flush=True)
    last_music = 0
    last_conv = 0
    last_camera = 0
    last_state = 0

    while True:
        now = time.time()
        try:
            if now - last_music >= 300:
                archive_music()
                last_music = now

            if now - last_conv >= 600:
                archive_conversations()
                last_conv = now

            if now - last_camera >= 3600:
                archive_cameras()
                last_camera = now

            if now - last_state >= 1800:
                archive_state_snapshot()
                last_state = now

        except Exception:
            pass
        time.sleep(30)


if __name__ == "__main__":
    run()
