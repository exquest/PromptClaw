#!/bin/bash
# Start CypherClaw audio with the best available JACK graph.

set -euo pipefail

sleep 5

systemctl --user start pipewire wireplumber 2>/dev/null || true
sleep 3

export JACK_NO_START_SERVER=1
export PIPEWIRE_LATENCY=4096/48000

SYNTHDEF_DIR=/home/user/cypherclaw/tools/senseweave/synthesis/synthdefs
SC_USER_DIR="${HOME}/.local/share/SuperCollider"
SC_LOG=/tmp/scsynth2.log

mkdir -p "$SC_USER_DIR"
ln -sfn "$SYNTHDEF_DIR" "$SC_USER_DIR/synthdefs"

log_audio_boot() {
    echo "$(date) $*" >> /tmp/audio_boot.log
}

has_scarlett_playback() {
    aplay -l 2>/dev/null | grep -Fq "Scarlett 4i4 USB"
}

start_real_jack_if_possible() {
    if ! command -v jack_control >/dev/null 2>&1; then
        return 1
    fi
    jack_control exit >/dev/null 2>&1 || true
    pkill -TERM -x jackdbus 2>/dev/null || true
    pkill -TERM -x jackd 2>/dev/null || true
    sleep 2
    rm -f /dev/shm/jack-1000-* /dev/shm/jack_sem.1000_default_* 2>/dev/null || true
    nohup jackdbus auto >/tmp/jackdbus.log 2>&1 &
    sleep 2
    jack_control ds alsa >/dev/null 2>&1 || true
    if has_scarlett_playback; then
        jack_control dps device hw:USB >/dev/null 2>&1 || true
    fi
    jack_control dps rate 48000 >/dev/null 2>&1 || true
    jack_control dps period 1024 >/dev/null 2>&1 || true
    jack_control dps nperiods 2 >/dev/null 2>&1 || true
    jack_control start >/dev/null 2>&1 || true
    sleep 3
    real_jack_ready
}

real_jack_ready() {
    jack_lsp >/dev/null 2>&1 && jack_lsp | grep -Fxq "system:playback_1"
}

JACK_BACKEND="pw-jack"
if command -v jack_lsp >/dev/null 2>&1 && real_jack_ready; then
    JACK_BACKEND="jack"
elif start_real_jack_if_possible; then
    JACK_BACKEND="jack"
fi

jack_tool() {
    if [ "$JACK_BACKEND" = "jack" ]; then
        "$@"
    else
        pw-jack "$@"
    fi
}

port_exists() {
    jack_tool jack_lsp | grep -Fxq "$1"
}

wait_for_port() {
    local port="$1"
    local attempt
    for attempt in $(seq 1 20); do
        if port_exists "$port"; then
            return 0
        fi
        sleep 1
    done
    return 1
}

start_scsynth() {
    local backend="$1"
    if [ "$backend" = "jack" ]; then
        nohup chrt -f 40 scsynth -u 57110 -a 1024 -m 65536 -d 1024 -D 1 -R 0 -o 4 -i 6 -S 48000 >"$SC_LOG" 2>&1 &
    else
        nohup pw-jack chrt -f 40 scsynth -u 57110 -a 1024 -m 65536 -d 1024 -D 1 -R 0 -o 6 -i 8 -S 48000 >"$SC_LOG" 2>&1 &
    fi
}

first_port() {
    local port
    for port in "$@"; do
        if port_exists "$port"; then
            printf '%s\n' "$port"
            return 0
        fi
    done
    return 1
}

pkill -TERM -x scsynth 2>/dev/null || true
sleep 1
rm -f "$SC_LOG"

start_scsynth "$JACK_BACKEND"
if ! wait_for_port "SuperCollider:out_1"; then
    if [ "$JACK_BACKEND" = "jack" ]; then
        log_audio_boot "Real JACK unavailable after scsynth start; retrying via pw-jack"
        pkill -TERM -x scsynth 2>/dev/null || true
        sleep 1
        JACK_BACKEND="pw-jack"
        start_scsynth "$JACK_BACKEND"
        wait_for_port "SuperCollider:out_1"
    else
        tail -n 60 "$SC_LOG" >&2 || true
        exit 1
    fi
fi

LEFT_PORT="$(
    first_port \
        "system:playback_1" \
        "Scarlett 4i4 USB Analog Surround 4.0:playback_FL" \
        "Perform-VE Analog Surround 7.1:playback_FL" \
        "Built-in Audio Analog Stereo:playback_FL" \
        "HDA NVidia Digital Stereo (HDMI):playback_FL" \
        || true
)"
RIGHT_PORT="$(
    first_port \
        "system:playback_2" \
        "Scarlett 4i4 USB Analog Surround 4.0:playback_FR" \
        "Perform-VE Analog Surround 7.1:playback_FR" \
        "Built-in Audio Analog Stereo:playback_FR" \
        "HDA NVidia Digital Stereo (HDMI):playback_FR" \
        || true
)"

if [ -n "$LEFT_PORT" ]; then
    jack_tool jack_connect "SuperCollider:out_1" "$LEFT_PORT" || true
fi
if [ -n "$RIGHT_PORT" ]; then
    jack_tool jack_connect "SuperCollider:out_2" "$RIGHT_PORT" || true
fi

PYTHONPATH=/home/user/cypherclaw/src:/home/user/cypherclaw/tools \
    /home/user/cypherclaw/.venv/bin/python3 - <<'PY'
import time

from pythonosc import udp_client

from senseweave.master_bus import master_bus_s_new_args

client = udp_client.SimpleUDPClient("127.0.0.1", 57110)
client.send_message("/g_freeAll", [0])
time.sleep(0.3)
client.send_message("/s_new", master_bus_s_new_args())
PY

for mix in A B C D E F; do
    for inp in 01 02 03 04; do
        amixer -D hw:USB sset "Mix $mix Input $inp" 0 2>/dev/null || true
    done
done
amixer -D hw:USB sset 'Analogue Output 01' 'PCM 1' 2>/dev/null || true
amixer -D hw:USB sset 'Analogue Output 02' 'PCM 2' 2>/dev/null || true
amixer -D hw:USB sset 'Standalone' off 2>/dev/null || true

log_audio_boot "Audio chain started via ${JACK_BACKEND} left=${LEFT_PORT:-missing} right=${RIGHT_PORT:-missing}"
