#!/bin/bash
# CypherClaw full boot script — starts X, displays, audio, all daemons
# Run from /etc/rc.local or a systemd service as user

set -euo pipefail
VENV=/home/user/cypherclaw/.venv/bin/python3
LOG=/tmp/cypherclaw_boot.log
exec > $LOG 2>&1

# Idempotency guard — refuse to re-run if another instance ran in the last 60s.
# Prevents agetty/login auto-respawn from spawning duplicate daemons.
GUARD_FILE=/run/user/1000/cypherclaw_boot.lastrun
mkdir -p /run/user/1000 2>/dev/null
if [ -f "$GUARD_FILE" ]; then
    LAST=$(stat -c %Y "$GUARD_FILE" 2>/dev/null || echo 0)
    NOW=$(date +%s)
    if [ $((NOW - LAST)) -lt 60 ]; then
        echo "$(date) boot script ran less than 60s ago — sleeping to keep session alive"
        exec sleep infinity
    fi
fi
touch "$GUARD_FILE"

echo "$(date) CypherClaw boot starting..."

archive_root() {
    if [ -n "${CYPHERCLAW_ARCHIVE_ROOT:-}" ]; then
        printf '%s\n' "${CYPHERCLAW_ARCHIVE_ROOT}"
        return 0
    fi
    if [ -d /mnt/archive ] && [ -w /mnt/archive ]; then
        printf '/mnt/archive/cypherclaw\n'
        return 0
    fi
    if [ -d /home/user/cypherclaw-data ] && [ -w /home/user/cypherclaw-data ]; then
        printf '/home/user/cypherclaw-data\n'
        return 0
    fi
    printf '/home/user/cypherclaw/.promptclaw/archive-storage\n'
}

ARCHIVE_ROOT=$(archive_root)
PORCH_CAPTURE_DIR="${ARCHIVE_ROOT}/camera/porch_eye_captures"
SIDE_CAPTURE_DIR="${ARCHIVE_ROOT}/camera/side_eye_captures"
mkdir -p "${PORCH_CAPTURE_DIR}" "${SIDE_CAPTURE_DIR}"

ensure_observer_ollama_service() {
    sudo -n systemctl start cypherclaw-observer-ollama.service 2>/dev/null || true
}

ensure_sample_capture_service() {
    sudo -n systemctl start cypherclaw-sample-capture.service 2>/dev/null || true
}

ensure_singleton_daemon() {
    local pattern="$1"
    shift
    local pid
    mapfile -t daemon_pids < <(pgrep -f "${pattern}" || true)
    if ((${#daemon_pids[@]} > 1)); then
        local keep_index=$((${#daemon_pids[@]} - 1))
        local keep_pid="${daemon_pids[${keep_index}]}"
        for pid in "${daemon_pids[@]}"; do
            if [[ "${pid}" != "${keep_pid}" ]]; then
                kill -TERM "${pid}" 2>/dev/null || true
            fi
        done
        sleep 1
    fi
    if ! pgrep -f "${pattern}" >/dev/null 2>&1; then
        nohup "$@" &>/dev/null &
    fi
}

# Wait for PipeWire
sleep 5

# Start X on vt1 if not already running
if [ ! -f /tmp/.X0-lock ]; then
    sudo Xorg :0 -keeptty vt1 &
    sleep 3
fi
export DISPLAY=:0

# Start window manager
openbox &
sleep 1

# Configure monitors
xrandr --output DP-2 --mode 1280x1024 --pos 0x0 --output DP-0 --mode 3840x2160 --pos 1280x0 --primary 2>/dev/null || true
sleep 1

# Core audio/visual stack
# The AV boot wrapper owns audio, composer, face, gallery, room listener,
# sample playback, and self-listener startup so boot responsibility stays single-source.
bash /home/user/cypherclaw/scripts/cypherclaw_av_boot.sh

# Keep the rolling JACK capture daemon active once audio is up.
ensure_sample_capture_service

# Dedicated observer vision queue.
ensure_observer_ollama_service

# Cameras
ensure_singleton_daemon \
    "/home/user/cypherclaw/tools/senseweave/porch_eye.py .*cY6cUV7hxEIy8k1v" \
    $VENV /home/user/cypherclaw/tools/senseweave/porch_eye.py \
    "rtsps://192.168.1.1:7441/cY6cUV7hxEIy8k1v?enableSrtp" \
    --capture-dir "${PORCH_CAPTURE_DIR}" --interval 30
ensure_singleton_daemon \
    "side_eye_state.json" \
    $VENV -c "
import sys;sys.path.insert(0,'/home/user/cypherclaw/tools/senseweave')
import porch_eye;porch_eye.DEFAULT_STATE_FILE='/tmp/side_eye_state.json'
porch_eye.run_porch_eye('rtsps://192.168.1.1:7441/oEUVMaB2G3pwbY42?enableSrtp','${SIDE_CAPTURE_DIR}',interval=30.0)
"
ensure_singleton_daemon \
    /home/user/cypherclaw/tools/observer_vision.py \
    env OBSERVER_OLLAMA_URLS=http://127.0.0.1:11435/api/chat,http://127.0.0.1:11434/api/chat \
    $VENV /home/user/cypherclaw/tools/observer_vision.py --video-device /dev/video0
ensure_singleton_daemon \
    /home/user/cypherclaw/tools/room_presence_daemon.py \
    $VENV /home/user/cypherclaw/tools/room_presence_daemon.py --observer-frame-only
# Sensors
nohup $VENV /home/user/cypherclaw/tools/theramini_midi.py /dev/midi3 &>/dev/null &
nohup $VENV /home/user/cypherclaw/tools/theramini_listener.py &>/dev/null &
nohup $VENV /home/user/cypherclaw/tools/contact_listener.py &>/dev/null &
nohup $VENV /home/user/cypherclaw/tools/midi_keyboard_listener.py &>/dev/null &
nohup $VENV /home/user/cypherclaw/tools/input_monitor.py &>/dev/null &
nohup $VENV -c "
import sys;sys.path.insert(0,'/home/user/cypherclaw/tools/senseweave')
from sensor_fusion import run_fusion_loop;run_fusion_loop(interval=2.0)
" &>/dev/null &
nohup $VENV /home/user/cypherclaw/tools/senseweave/presence_engine.py --interval 2.0 &>/dev/null &
nohup $VENV /home/user/cypherclaw/tools/senseweave/cadence_engine.py --interval 5.0 &>/dev/null &
ensure_singleton_daemon \
    "from garden_watcher import update_garden_state,write_garden_state" \
    $VENV -c "
import sys,json,time,os
sys.path.insert(0,'/home/user/cypherclaw/tools/senseweave')
from garden_watcher import update_garden_state,write_garden_state
while True:
    try:
        b=0.5
        for cam in ['/tmp/porch_eye_state.json','/tmp/side_eye_state.json']:
            try:
                d=json.loads(open(cam).read())
                if d.get('brightness',0)>0:b=d['brightness'];break
            except:pass
        write_garden_state(update_garden_state(b))
    except:pass
    time.sleep(30)
"
# Other daemons
nohup $VENV /home/user/cypherclaw/tools/nightly_reflection.py &>/dev/null &
nohup $VENV /home/user/cypherclaw/tools/senseweave/pareidolia_art_engine.py &>/dev/null &

# Main daemon (chat system) — handled by cypherclaw-main-daemon.service.
# Do not spawn here; would create duplicates on every agetty respawn.

# Boost volume after the audio chain seeds the master bus
sleep 5
wpctl set-volume @DEFAULT_AUDIO_SINK@ 1.0 2>/dev/null

echo "$(date) CypherClaw boot complete — all systems online"

# Focus the face display window for keyboard input
sleep 3
DISPLAY=:0 xdotool mousemove 640 512 click 1 2>/dev/null

# Inner life — the mind
nohup $VENV -u -m inner_life.main &>/dev/null &

# Archive daemon — records everything
nohup env CYPHERCLAW_ARCHIVE_ROOT="${ARCHIVE_ROOT}" CYPHERCLAW_PORCH_CAPTURE_DIR="${PORCH_CAPTURE_DIR}" CYPHERCLAW_SIDE_CAPTURE_DIR="${SIDE_CAPTURE_DIR}" $VENV -u /home/user/cypherclaw/tools/archive_daemon.py &>/dev/null &

# Hide mouse cursor
DISPLAY=:0 unclutter -idle 0 -root &>/dev/null &

# Keep the session alive forever — prevents agetty from re-spawning login
# and re-running this script (which would re-spawn duplicate daemons).
echo "$(date) boot complete — entering keepalive"
exec sleep infinity
