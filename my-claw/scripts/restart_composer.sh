#!/bin/bash
# Pop-safe composer restart on top of the current audio server.

set -euo pipefail

export PYTHONPATH=/home/user/cypherclaw/src:/home/user/cypherclaw/tools
export JACK_NO_START_SERVER=1

mute_outputs() {
    amixer -D hw:USB sset 'Line 01 Mute' on 2>/dev/null || true
    amixer -D hw:USB sset 'Line 02 Mute' on 2>/dev/null || true
}

unmute_outputs() {
    amixer -D hw:USB sset 'Line 01 Mute' off 2>/dev/null || true
    amixer -D hw:USB sset 'Line 02 Mute' off 2>/dev/null || true
}

reset_and_seed_master_chain() {
    /home/user/cypherclaw/.venv/bin/python3 - <<'PY'
import time

from pythonosc import udp_client

from senseweave.master_bus import master_bus_s_new_args

client = udp_client.SimpleUDPClient("127.0.0.1", 57110)
client.send_message("/g_freeAll", [0])
time.sleep(0.3)
client.send_message("/s_new", master_bus_s_new_args())
PY
}

seed_master_node_only() {
    /home/user/cypherclaw/.venv/bin/python3 - <<'PY'
from pythonosc import udp_client

from senseweave.master_bus import master_bus_s_new_args

client = udp_client.SimpleUDPClient("127.0.0.1", 57110)
client.send_message("/s_new", master_bus_s_new_args())
PY
}

wait_for_composer() {
    local attempt
    for attempt in $(seq 1 12); do
        if pgrep -f /home/user/cypherclaw/tools/duet_composer.py >/dev/null 2>&1; then
            pgrep -f /home/user/cypherclaw/tools/duet_composer.py | head -n 1
            return 0
        fi
        sleep 1
    done
    return 1
}

if ! pgrep -x scsynth >/dev/null 2>&1; then
    bash /home/user/cypherclaw/scripts/start_audio.sh
    sleep 2
fi

mute_outputs

pkill -TERM -f /home/user/cypherclaw/tools/duet_composer.py 2>/dev/null || true
sleep 1
if pgrep -f /home/user/cypherclaw/tools/duet_composer.py >/dev/null 2>&1; then
    pkill -KILL -f /home/user/cypherclaw/tools/duet_composer.py 2>/dev/null || true
fi

reset_and_seed_master_chain

nohup setsid /home/user/cypherclaw/.venv/bin/python3 -u /home/user/cypherclaw/tools/duet_composer.py >/tmp/duet_composer.log 2>&1 </dev/null &
pid=$!
if ! live_pid="$(wait_for_composer)"; then
    tail -n 40 /tmp/duet_composer.log 2>/dev/null || true
    unmute_outputs
    echo "Composer failed to start" >&2
    exit 1
fi

sleep 1
seed_master_node_only

unmute_outputs
echo "Composer PID: ${live_pid:-$pid}"
echo "Unmuted — pop-free restart complete"
