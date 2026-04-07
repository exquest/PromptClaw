"""CypherClaw Duet Composer — plays music that adapts to the Theramini.

Two modes:
  SOLO: plays autonomous songs (conversation.py style)
  DUET: adapts key, register, rhythm, and volume to complement the Theramini

Reads /tmp/theramini_state.json to know what the player is doing.
Writes /tmp/composer_state.json for the face display.
Sends OSC to scsynth :57110.
"""
from __future__ import annotations

import json
import os
import random
import signal
import sys
import threading
import time
from enum import Enum
from pathlib import Path

from pythonosc import udp_client

THERAMINI_STATE = Path("/tmp/theramini_state.json")
COMPOSER_STATE = Path("/tmp/composer_state.json")
FACE_MESSAGE = Path("/tmp/face_message.json")

BT = 0.43  # beat duration

# OSC client
c = udp_client.SimpleUDPClient("127.0.0.1", 57110)
nid_counter = 60000
nid_lock = threading.Lock()


def next_nid() -> int:
    global nid_counter
    with nid_lock:
        nid_counter = (nid_counter + 1) % 65000 + 60100
        return nid_counter


def pluck(freq: float, amp: float = 0.15, release: float = 0.4) -> None:
    c.send_message("/s_new", ["sw_pluck", next_nid(), 0, 0,
        "freq", freq, "amp", amp, "attack", 0.003, "release", release])


def gong(freq: float) -> None:
    c.send_message("/s_new", ["sw_gong", next_nid(), 0, 0,
        "freq", freq, "amp", 0.014, "attack", 0.15, "release", 3.5])


# === SCALES ===

def make_key(root: float) -> dict[int, float]:
    semi = [0, 2, 4, 5, 7, 9, 11]
    f: dict[int, float] = {}
    for o in range(5):
        for i, s in enumerate(semi):
            f[i + 1 + o * 7] = root * (2 ** ((s + 12 * o) / 12))
    return f


KEY_ROOTS = {
    "C": 130.8, "C#": 138.6, "D": 146.8, "D#": 155.6,
    "E": 164.8, "F": 174.6, "F#": 185.0, "G": 196.0,
    "G#": 207.7, "A": 220.0, "A#": 233.1, "B": 246.9,
    "Bb": 116.5,
}

KEYS_CYCLE = ["C", "G", "D", "A", "E", "F"]

PROGS = [[1,4,5,1], [1,6,4,5], [1,4,1,5], [1,3,4,5]]

MELODIES = [
    [1,3,5,8,7,5,3,1],
    [5,6,5,3,4,3,2,1],
    [1,2,3,5,8,7,5,3],
    [8,7,5,6,5,3,2,1],
    [3,5,8,7,5,3,5,1],
]

BASS_SOLOS = [
    [1,5,4,3,1],
    [1,2,3,5,1],
    [5,4,3,2,1],
]


class Mode(Enum):
    SOLO = "solo"
    DUET = "duet"


# === STATE READING ===

def read_theramini() -> dict:
    """Read current Theramini state. Returns empty dict on failure."""
    try:
        if THERAMINI_STATE.exists():
            data = json.loads(THERAMINI_STATE.read_text())
            # Only trust recent data (within 5 seconds — listener captures 1s clips)
            if time.time() - data.get("timestamp", 0) < 5.0:
                return data
    except (json.JSONDecodeError, OSError):
        pass
    return {}


def write_composer_state(key: str, mode: str, movement: str = "", song: int = 0,
                         theramini_note: str | None = None) -> None:
    try:
        state = {
            "key": key,
            "mode": mode,
            "movement": movement,
            "song": song,
            "theramini_note": theramini_note,
            "updated": time.time(),
        }
        tmp = COMPOSER_STATE.with_suffix(".tmp")
        tmp.write_text(json.dumps(state))
        os.replace(str(tmp), str(COMPOSER_STATE))
    except OSError:
        pass


def send_face_message(text: str, duration: float = 30) -> None:
    try:
        msg = {"message": text, "message_until": time.time() + duration}
        tmp = FACE_MESSAGE.with_suffix(".tmp")
        tmp.write_text(json.dumps(msg))
        os.replace(str(tmp), str(FACE_MESSAGE))
    except OSError:
        pass


# === SOLO MODE (autonomous songs) ===

def solo_song(key_name: str, song_num: int) -> str:
    """Play one autonomous song. Returns the next key name."""
    root = KEY_ROOTS.get(key_name, 130.8)
    key = make_key(root)
    prog = random.choice(PROGS)
    mel = random.choice(MELODIES)
    bass_solo = random.choice(BASS_SOLOS)
    next_key = KEYS_CYCLE[(KEYS_CYCLE.index(key_name) + 1) % len(KEYS_CYCLE)] if key_name in KEYS_CYCLE else "G"

    print(f"\n=== SOLO: {key_name} major ===", flush=True)
    write_composer_state(key_name, "solo", "Opening", song_num)
    t0 = time.time()

    # Check for Theramini throughout — if detected, return early to switch to DUET
    def check_theramini() -> bool:
        ts = read_theramini()
        return ts.get("is_playing", False) and ts.get("pitch_confidence", 0) > 0.3

    # --- Bass speaks ---
    time.sleep(0.5)
    for deg in bass_solo[:3]:
        if check_theramini():
            return key_name  # Switch to duet
        pluck(key[deg] / 4, 0.20, 0.55)
        time.sleep(BT * random.choice([1.5, 2, 2.5]))
    time.sleep(BT * 2)

    # --- Melody responds ---
    write_composer_state(key_name, "solo", "Theme", song_num)
    for deg in mel[:4]:
        if check_theramini():
            return key_name
        pluck(key[deg], 0.16, 0.45)
        time.sleep(BT * 2)
    time.sleep(BT * 2)

    # --- Waltz + melody ---
    write_composer_state(key_name, "solo", "Waltz", song_num)
    def waltz():
        for rd in prog:
            bass = key[rd] / 4
            fifth = key[rd + 4] / 2
            pluck(bass, 0.20, 0.45)
            time.sleep(BT)
            pluck(fifth, 0.09, 0.3)
            time.sleep(BT)
            pluck(fifth, 0.06, 0.25)
            time.sleep(BT)

    bt = threading.Thread(target=waltz, daemon=True)
    bt.start()
    for deg in mel:
        if check_theramini():
            bt.join()
            return key_name
        pluck(key[deg], 0.16, 0.4)
        time.sleep(BT * random.choice([1, 1, 1.5, 0.5]))
    bt.join()
    time.sleep(BT * 3)

    # --- Key change ---
    nroot = KEY_ROOTS.get(next_key, 196.0)
    nkey = make_key(nroot)
    write_composer_state(next_key, "solo", "Development", song_num)
    gong(key[1] / 4)
    time.sleep(BT * 3)

    bt = threading.Thread(target=lambda: [
        (pluck(nkey[rd] / 4, 0.18, 0.4), time.sleep(BT),
         pluck(nkey[rd + 4] / 2, 0.08, 0.3), time.sleep(BT),
         pluck(nkey[rd + 4] / 2, 0.06, 0.25), time.sleep(BT))
        for rd in prog
    ], daemon=True)
    bt.start()
    for deg in mel:
        if check_theramini():
            bt.join()
            return next_key
        pluck(nkey[deg], 0.16, 0.4)
        time.sleep(BT * random.choice([1, 1, 1.5]))
    bt.join()
    time.sleep(BT * 3)

    # --- Resolution ---
    write_composer_state(key_name, "solo", "Resolution", song_num)
    pluck(key[5], 0.12, 0.6)
    time.sleep(BT * 3)
    pluck(key[3], 0.10, 0.6)
    time.sleep(BT * 3)
    pluck(key[1], 0.08, 0.8)
    time.sleep(BT * 5)
    time.sleep(2)

    elapsed = int(time.time() - t0)
    print(f"  Solo done ({elapsed}s)", flush=True)
    return next_key


# === DUET MODE (adapting to Theramini) ===

def duet_loop(initial_key: str, song_num: int) -> str:
    """Play in duet mode, adapting to the Theramini player.

    Keeps playing as long as Theramini is active. Returns the last key.
    """
    current_key = initial_key
    silence_count = 0
    MAX_SILENCE = 15  # cycles of no Theramini before returning to solo

    print(f"\n=== DUET MODE: starting in {current_key} ===", flush=True)
    send_face_message("Duet mode — I hear you playing!", 20)

    while silence_count < MAX_SILENCE:
        ts = read_theramini()
        is_playing = ts.get("is_playing", False) and ts.get("pitch_confidence", 0) > 0.3
        their_note = ts.get("pitch_note")
        their_key = ts.get("suggested_key")
        their_rms = ts.get("rms", 0)
        consecutive_silence = ts.get("consecutive_silence_ms", 0)

        if not is_playing:
            silence_count += 1
            # During silence, play a gentle response
            if silence_count == 3:
                # She paused — respond with a short phrase
                print(f"  Responding in {current_key}...", flush=True)
                write_composer_state(current_key, "duet", "Responding", song_num, their_note)
                key = make_key(KEY_ROOTS.get(current_key, 130.8))
                mel = random.choice(MELODIES)
                for deg in mel[:4]:
                    pluck(key[deg], 0.12, 0.45)
                    time.sleep(BT * random.choice([1, 1.5, 2]))
                time.sleep(BT * 2)
            elif silence_count == 8:
                # Longer pause — play a gentle bass figure
                key = make_key(KEY_ROOTS.get(current_key, 130.8))
                for deg in [1, 5, 3, 1]:
                    pluck(key[deg] / 4, 0.10, 0.5)
                    time.sleep(BT * 2)
            else:
                time.sleep(BT * 2)
            continue

        # She's playing! Reset silence counter
        silence_count = 0

        # Adapt key if she changed
        if their_key and their_key != current_key and their_key in KEY_ROOTS:
            print(f"  Key change: {current_key} → {their_key}", flush=True)
            current_key = their_key

        write_composer_state(current_key, "duet", "Listening", song_num, their_note)

        # Decide what to play based on her activity
        key = make_key(KEY_ROOTS.get(current_key, 130.8))

        if their_rms > 0.1:
            # She's playing loudly — play quiet, sustained, complementary
            # Low register, simple, give her space
            deg = random.choice([1, 3, 5])
            pluck(key[deg] / 4, 0.06, 0.6)
            time.sleep(BT * 3)
        elif their_rms > 0.02:
            # She's playing moderately — gentle waltz underneath
            rd = random.choice([1, 4, 5])
            pluck(key[rd] / 4, 0.10, 0.4)
            time.sleep(BT)
            pluck(key[rd + 4] / 2, 0.05, 0.3)
            time.sleep(BT)
            pluck(key[rd + 4] / 2, 0.04, 0.25)
            time.sleep(BT)
        else:
            # She's playing very quietly — match her with a single quiet note
            deg = random.choice([1, 3, 5, 8])
            pluck(key[deg], 0.04, 0.5)
            time.sleep(BT * 2)

    # Theramini went silent — transition back to solo
    print(f"  Theramini silent, returning to solo in {current_key}", flush=True)
    send_face_message("", 0)  # Clear message
    return current_key


# === MAIN LOOP ===

def main() -> None:
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    signal.signal(signal.SIGINT, lambda *_: sys.exit(0))

    # Clear all synths on startup
    c.send_message("/g_freeAll", [0])
    time.sleep(0.5)

    print("CypherClaw Duet Composer", flush=True)
    print("SOLO mode until Theramini detected, then DUET", flush=True)

    key_idx = random.randint(0, len(KEYS_CYCLE) - 1)
    current_key = KEYS_CYCLE[key_idx]
    song_num = 0
    mode = Mode.SOLO

    while True:
        song_num += 1

        # Check if Theramini is playing right now
        ts = read_theramini()
        theramini_active = ts.get("is_playing", False) and ts.get("pitch_confidence", 0) > 0.3

        if theramini_active:
            # Switch to duet
            their_key = ts.get("suggested_key", current_key)
            if their_key in KEY_ROOTS:
                current_key = their_key
            mode = Mode.DUET
            print(f"\n--- Song {song_num}: DUET in {current_key} ---", flush=True)
            current_key = duet_loop(current_key, song_num)
            mode = Mode.SOLO
        else:
            # Solo mode
            mode = Mode.SOLO
            print(f"\n--- Song {song_num}: SOLO ---", flush=True)
            current_key = solo_song(current_key, song_num)

        time.sleep(random.uniform(4, 7))


if __name__ == "__main__":
    main()
