#!/bin/bash
# Boot the persistent CypherClaw audio/visual runtime stack after login/display.

set -euo pipefail

export HOME=/home/user
export DISPLAY=:0
export XDG_RUNTIME_DIR=/run/user/1000
export PYTHONPATH=/home/user/cypherclaw/src:/home/user/cypherclaw/tools
export JACK_NO_START_SERVER=1
FACE_X_DISPLAY=:0.0
GALLERY_X_DISPLAY=:0.1

VENV=/home/user/cypherclaw/.venv/bin/python3

preferred_self_listener_backend() {
    printf 'jack\n'
}

start_openbox_if_missing() {
    if ! pgrep -x openbox >/dev/null 2>&1; then
        nohup setsid env DISPLAY="${FACE_X_DISPLAY}" openbox >/tmp/openbox.log 2>&1 </dev/null &
        sleep 1
    fi
}

wait_for_display() {
    local attempt
    for attempt in $(seq 1 30); do
        if xdpyinfo -display "${DISPLAY}" >/dev/null 2>&1; then
            return 0
        fi
        sleep 2
    done
    return 1
}

ensure_display_stack() {
    if wait_for_display; then
        start_openbox_if_missing
        return 0
    fi

    bash /home/user/cypherclaw/scripts/start_displays.sh || true
    sleep 2

    if wait_for_display; then
        start_openbox_if_missing
        return 0
    fi

    return 1
}

normalize_dual_head_modes() {
    env DISPLAY=:0 xrandr --screen 0 --output DP-2 --mode 1280x1024 --rate 60 >/dev/null 2>&1 || true
    env DISPLAY=:0 xrandr --screen 1 --output DP-0 --mode 3840x2160 --rate 60 >/dev/null 2>&1 || true
}

wait_for_existing_core_stack() {
    local attempt
    for attempt in $(seq 1 15); do
        if pgrep -x scsynth >/dev/null 2>&1 && pgrep -f /home/user/cypherclaw/tools/duet_composer.py >/dev/null 2>&1; then
            return 0
        fi
        sleep 2
    done
    return 1
}

restart_daemon() {
    local pattern="$1"
    local log_path="$2"
    shift 2
    pkill -TERM -f "${pattern}" 2>/dev/null || true
    sleep 1
    nohup setsid "$@" >"${log_path}" 2>&1 </dev/null &
}

start_daemon_if_missing() {
    local pattern="$1"
    local log_path="$2"
    shift 2
    local attempt
    for attempt in $(seq 1 8); do
        if pgrep -f "${pattern}" >/dev/null 2>&1; then
            return 0
        fi
        sleep 2
    done
    nohup setsid "$@" >"${log_path}" 2>&1 </dev/null &
}

dedupe_daemon() {
    local pattern="$1"
    local log_path="$2"
    shift 2
    local keep_index
    local keep_pid
    local pid
    mapfile -t daemon_pids < <(pgrep -f "${pattern}" || true)
    if ((${#daemon_pids[@]} > 1)); then
        keep_index=$((${#daemon_pids[@]} - 1))
        keep_pid="${daemon_pids[${keep_index}]}"
        for pid in "${daemon_pids[@]}"; do
            if [[ "${pid}" != "${keep_pid}" ]]; then
                kill -TERM "${pid}" 2>/dev/null || true
            fi
        done
        sleep 1
        mapfile -t daemon_pids < <(pgrep -f "${pattern}" || true)
        if ((${#daemon_pids[@]} > 1)); then
            keep_index=$((${#daemon_pids[@]} - 1))
            keep_pid="${daemon_pids[${keep_index}]}"
            for pid in "${daemon_pids[@]}"; do
                if [[ "${pid}" != "${keep_pid}" ]]; then
                    kill -KILL "${pid}" 2>/dev/null || true
                fi
            done
            sleep 1
        fi
    fi
    if ! pgrep -f "${pattern}" >/dev/null 2>&1; then
        nohup setsid "$@" >"${log_path}" 2>&1 </dev/null &
    fi
}

wait_for_sc_port() {
    local attempt
    for attempt in $(seq 1 12); do
        if jack_lsp 2>/dev/null | grep -Fxq "SuperCollider:out_1"; then
            return 0
        fi
        if pw-jack jack_lsp 2>/dev/null | grep -Fxq "SuperCollider:out_1"; then
            return 0
        fi
        sleep 1
    done
    return 1
}

ensure_display_stack || true
normalize_dual_head_modes

if ! wait_for_existing_core_stack; then
    bash /home/user/cypherclaw/scripts/start_audio.sh
    bash /home/user/cypherclaw/scripts/restart_composer.sh
fi
wait_for_sc_port || true

restart_daemon \
    /home/user/cypherclaw/tools/self_listener.py \
    /tmp/self_listener.log \
    env SELF_LISTENER_CAPTURE_BACKEND="$(preferred_self_listener_backend)" SELF_LISTENER_PORT=SuperCollider:out_1 \
    "${VENV}" -u /home/user/cypherclaw/tools/self_listener.py

dedupe_daemon \
    /home/user/cypherclaw/tools/room_listener.py \
    /tmp/room_listener.log \
    "${VENV}" -u /home/user/cypherclaw/tools/room_listener.py

dedupe_daemon \
    /home/user/cypherclaw/tools/sample_playback_engine.py \
    /tmp/sample_playback_engine.log \
    "${VENV}" -u /home/user/cypherclaw/tools/sample_playback_engine.py

restart_daemon \
    /home/user/cypherclaw/tools/face_display.py \
    /tmp/face_display.log \
    env DISPLAY="${FACE_X_DISPLAY}" FACE_DISPLAY=1 SDL_AUDIODRIVER=dummy \
    "${VENV}" -u /home/user/cypherclaw/tools/face_display.py

restart_daemon \
    /home/user/cypherclaw/tools/gallery_x11.py \
    /tmp/gallery_x11.log \
    env DISPLAY="${GALLERY_X_DISPLAY}" SDL_AUDIODRIVER=dummy \
    "${VENV}" -u /home/user/cypherclaw/tools/gallery_x11.py

sleep 5

dedupe_daemon \
    /home/user/cypherclaw/tools/room_listener.py \
    /tmp/room_listener.log \
    "${VENV}" -u /home/user/cypherclaw/tools/room_listener.py

dedupe_daemon \
    /home/user/cypherclaw/tools/sample_playback_engine.py \
    /tmp/sample_playback_engine.log \
    "${VENV}" -u /home/user/cypherclaw/tools/sample_playback_engine.py

restart_daemon \
    /home/user/cypherclaw/tools/face_display.py \
    /tmp/face_display.log \
    env DISPLAY="${FACE_X_DISPLAY}" FACE_DISPLAY=1 SDL_AUDIODRIVER=dummy \
    "${VENV}" -u /home/user/cypherclaw/tools/face_display.py

restart_daemon \
    /home/user/cypherclaw/tools/gallery_x11.py \
    /tmp/gallery_x11.log \
    env DISPLAY="${GALLERY_X_DISPLAY}" SDL_AUDIODRIVER=dummy \
    "${VENV}" -u /home/user/cypherclaw/tools/gallery_x11.py
