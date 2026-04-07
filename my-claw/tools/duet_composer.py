"""CypherClaw Duet Composer v2 — Korsakov Ch.1-6 integrated.

SOLO mode: structured songs with Korsakov orchestration.
DUET mode: adapts to Theramini player.

Integrates:
- accompaniment.py (Ch.4): density-reactive patterns, pedal points, breathing
- voice_manager_v2.py (Ch.5): voice balance, octave separation, crescendo
- orchestral_form.py (Ch.6): tutti roles, sfp pairs, effect budget, silence
- generative_scores.py: score generation from mood
- theramini_duet.py: duet musical intelligence
"""
from __future__ import annotations

import json
import os
import random
import signal
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "senseweave"))

from pythonosc import udp_client

# Korsakov modules
from senseweave.synthesis.accompaniment import (
    DensityTracker,
    get_pattern,
    pedal_note,
    select_accompaniment_type,
    should_pedal,
)
from senseweave.synthesis.voice_manager_v2 import (
    VOICES,
    balance_amplitudes,
    select_voices_for_movement,
    suggest_fusion_pair,
    voice_count_for_movement,
)
from senseweave.synthesis.orchestral_form import (
    ArticulationPair,
    EffectBudget,
    MOVEMENT_INDEX,
    plan_diverging_crescendo,
    select_sfp_pair,
    should_insert_silence,
    silence_duration_beats,
    suggest_reentry_voice,
    suggest_tint,
    tint_texture,
)
from senseweave.theramini_duet import (
    calculate_wait_beats,
    should_enter_duet,
    should_exit_duet,
    suggest_response_key,
    suggest_response_phrase,
    suggest_response_register,
    suggest_response_density,
)

THERAMINI_STATE = Path("/tmp/theramini_state.json")
COMPOSER_STATE = Path("/tmp/composer_state.json")
FACE_MESSAGE = Path("/tmp/face_message.json")

BT = 0.43

# OSC
c = udp_client.SimpleUDPClient("127.0.0.1", 57110)
nid_counter = 60000
nid_lock = threading.Lock()


def next_nid() -> int:
    global nid_counter
    with nid_lock:
        nid_counter = (nid_counter + 1) % 65000 + 60100
        return nid_counter


# === SYNTH VOICES ===
# Map voice names to synth names and play functions

SYNTH_MAP = {
    "pluck": "sw_pluck",
    "bowed": "sw_bowed",
    "kotekan": "sw_kotekan",
    "gong": "sw_gong",
    "bell": "sw_bell_warm",
    "choir": "sw_choir",
    "breath": "sw_breath",
}

VOICE_DEFAULTS = {
    "pluck":   {"attack": 0.003, "release": 0.45},
    "bowed":   {"attack": 0.05,  "release": 1.2},
    "kotekan": {"attack": 0.005, "release": 0.35},
    "gong":    {"attack": 0.15,  "release": 3.5},
    "bell":    {"attack": 0.01,  "release": 0.7},
    "choir":   {"attack": 0.5,   "release": 1.5},
    "breath":  {"attack": 0.8,   "release": 2.0},
}


def play_voice(voice_name: str, freq: float, amp: float, release: float | None = None) -> None:
    """Play a note on a named voice."""
    synth = SYNTH_MAP.get(voice_name, "sw_pluck")
    defaults = VOICE_DEFAULTS.get(voice_name, {"attack": 0.01, "release": 0.5})
    c.send_message("/s_new", [synth, next_nid(), 0, 0,
        "freq", freq, "amp", amp,
        "attack", defaults["attack"],
        "release", release or defaults["release"]])


# === KEY/SCALE ===

KEY_ROOTS = {
    "C": 130.8, "C#": 138.6, "D": 146.8, "D#": 155.6,
    "E": 164.8, "F": 174.6, "F#": 185.0, "G": 196.0,
    "G#": 207.7, "A": 220.0, "A#": 233.1, "B": 246.9, "Bb": 116.5,
}
KEYS_CYCLE = ["C", "G", "D", "A", "E", "F"]


def make_key(root: float) -> dict[int, float]:
    semi = [0, 2, 4, 5, 7, 9, 11]
    f: dict[int, float] = {}
    for o in range(5):
        for i, s in enumerate(semi):
            f[i + 1 + o * 7] = root * (2 ** ((s + 12 * o) / 12))
    return f


PROGS = [[1, 4, 5, 1], [1, 6, 4, 5], [1, 4, 1, 5], [1, 3, 4, 5]]

MELODIES = [
    [1, 3, 5, 8, 7, 5, 3, 1],
    [5, 6, 5, 3, 4, 3, 2, 1],
    [1, 2, 3, 5, 8, 7, 5, 3],
    [8, 7, 5, 6, 5, 3, 2, 1],
    [3, 5, 8, 7, 5, 3, 5, 1],
]

BASS_SOLOS = [[1, 5, 4, 3, 1], [1, 2, 3, 5, 1], [5, 4, 3, 2, 1]]


# === STATE ===

def read_theramini() -> dict:
    try:
        if THERAMINI_STATE.exists():
            data = json.loads(THERAMINI_STATE.read_text())
            if time.time() - data.get("timestamp", 0) < 5.0:
                return data
    except (json.JSONDecodeError, OSError):
        pass
    return {}


def write_composer_state(key: str, mode: str, movement: str = "", song: int = 0,
                         theramini_note: str | None = None) -> None:
    try:
        state = {"key": key, "mode": mode, "movement": movement, "song": song,
                 "theramini_note": theramini_note, "updated": time.time()}
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


# === SOLO MODE WITH KORSAKOV ORCHESTRATION ===

def solo_song(key_name: str, song_num: int) -> str:
    root = KEY_ROOTS.get(key_name, 130.8)
    key = make_key(root)
    prog = random.choice(PROGS)
    mel = random.choice(MELODIES)
    bass_solo = random.choice(BASS_SOLOS)
    next_key = KEYS_CYCLE[(KEYS_CYCLE.index(key_name) + 1) % len(KEYS_CYCLE)] if key_name in KEYS_CYCLE else "G"

    density = DensityTracker()
    budget = EffectBudget()
    prev_voice_count = 0

    print(f"\n=== SOLO: {key_name} major ===", flush=True)

    def check_theramini() -> bool:
        return should_enter_duet(read_theramini())

    # --- EMERGENCE (Mvt 0): 1-2 voices, solo pluck ---
    mvt = "Emergence"
    mvt_idx = 0
    write_composer_state(key_name, "solo", mvt, song_num)
    voices = select_voices_for_movement(mvt)
    print(f"  I. {mvt} — {len(voices)} voices", flush=True)

    time.sleep(0.5)
    # Bass speaks alone
    for deg in bass_solo[:3]:
        if check_theramini():
            return key_name
        play_voice("pluck", key[deg] / 4, 0.18, 0.55)
        time.sleep(BT * random.choice([1.5, 2, 2.5]))
    time.sleep(BT * 2)

    # Melody responds
    for deg in mel[:4]:
        if check_theramini():
            return key_name
        play_voice("pluck", key[deg], 0.16, 0.45)
        density.note_played()
        time.sleep(BT * 2)
    time.sleep(BT * 2)

    # --- THEME (Mvt 1): 2-3 voices, waltz + melody ---
    mvt = "Theme"
    mvt_idx = 1
    write_composer_state(key_name, "solo", mvt, song_num)
    print(f"  II. {mvt}", flush=True)

    # Tint available from Theme onwards
    tint_voice = suggest_tint(mvt)

    for rep in range(2):
        loud = 0.7 + rep * 0.1
        # Ch.4: select accompaniment type based on density
        acc_type = select_accompaniment_type(density.density(), density.is_resting())
        acc_root = key[prog[0]] if prog else key[1]
        acc_fifth = key[prog[0] + 4] if prog else key[5]

        def bass_thread():
            for chord in prog:
                r = key[chord] / 4
                f = key[chord + 4] / 2
                pattern = get_pattern(acc_type, r * 2, f * 2, BT, loud * 0.7)
                for freq, amp, rel, wait in pattern:
                    play_voice("pluck", freq, amp, rel)
                    time.sleep(wait)

        bt = threading.Thread(target=bass_thread, daemon=True)
        bt.start()

        for deg in mel:
            if check_theramini():
                bt.join()
                return key_name
            play_voice("pluck", key[deg], 0.16 * loud, 0.4)
            density.note_played()
            time.sleep(BT * random.choice([1, 1, 1.5, 0.5]))
        bt.join()

        # Ch.6: timbral tint at phrase boundary
        if budget.can_use("tinting", mvt_idx):
            tv, ta = tint_texture([v.name for v in voices], tint_voice)
            if ta > 0:
                play_voice(tv, key[1], ta * 0.3, 2.0)
                budget.spend("tinting")

        time.sleep(BT * 3)

    # Ch.4: pedal point at phrase boundary
    if should_pedal(0):
        pf, pa, pr = pedal_note(root, BT)
        play_voice("gong", pf, pa, pr)

    time.sleep(BT * 2)

    # --- DEVELOPMENT (Mvt 2): 3-5 voices, key change, crescendo ---
    mvt = "Development"
    mvt_idx = 2
    nroot = KEY_ROOTS.get(next_key, 196.0)
    nkey = make_key(nroot)
    write_composer_state(next_key, "solo", mvt, song_num)
    print(f"  III. {mvt} → {next_key}", flush=True)

    # Gong transition
    play_voice("gong", key[1] / 4, 0.014, 3.5)
    time.sleep(BT * 3)

    # Ch.5: diverging crescendo — build from center outward
    cresc_plan = plan_diverging_crescendo(4)

    # Counterpoint: melody + bass with Ch.4 density-reactive accompaniment
    loud = 0.85
    acc_type = select_accompaniment_type(density.density(), density.is_resting())

    def dev_bass():
        for chord in prog:
            r = nkey[chord] / 4
            f = nkey[chord + 4] / 2
            pattern = get_pattern(acc_type, r * 2, f * 2, BT, loud * 0.6)
            for freq, amp, rel, wait in pattern:
                play_voice("pluck", freq, amp, rel)
                time.sleep(wait)

    bt = threading.Thread(target=dev_bass, daemon=True)
    bt.start()

    for deg in mel:
        if check_theramini():
            bt.join()
            return next_key
        play_voice("pluck", nkey[deg], 0.18 * loud, 0.4)
        density.note_played()
        time.sleep(BT * random.choice([1, 1, 1.5]))
    bt.join()
    time.sleep(BT * 2)

    # Ch.6: sfp pair at climax
    if budget.can_use("sfp", mvt_idx):
        pair = select_sfp_pair("excited")
        play_voice(pair.attack_voice, nkey[1] / 2, pair.attack_amp, pair.attack_release)
        play_voice(pair.sustain_voice, nkey[1], pair.sustain_amp, pair.sustain_release)
        budget.spend("sfp")

    # Ch.5: fusion pair for climax peak
    if budget.can_use("fusion", mvt_idx):
        fp = suggest_fusion_pair("excited")
        for deg in mel[:4]:
            play_voice(fp[0], nkey[deg], 0.10, 0.4)
            play_voice(fp[1], nkey[deg] * 2, 0.04, 0.3)
            density.note_played()
            time.sleep(BT)
        budget.spend("fusion")

    prev_voice_count = 5
    time.sleep(BT * 2)

    # Ch.6: post-tutti silence
    if should_insert_silence(prev_voice_count, 2):
        sil_beats = silence_duration_beats(prev_voice_count)
        print(f"    [silence: {sil_beats} beats]", flush=True)
        time.sleep(BT * sil_beats)
        # Re-enter with lightest voice
        reentry = suggest_reentry_voice()
        play_voice(reentry, nkey[1], 0.03, 2.0)
        time.sleep(BT * 2)

    # --- RECAP (Mvt 3): 2-3 voices, original key, re-orchestrated ---
    mvt = "Recap"
    mvt_idx = 3
    write_composer_state(key_name, "solo", mvt, song_num)
    print(f"  IV. {mvt} — {key_name}", flush=True)

    # Ch.1: re-orchestrate the return — bowed takes melody this time
    play_voice("gong", key[1] / 4, 0.012, 3.0)
    time.sleep(BT * 3)

    # Ch.4: simpler accompaniment (melody is legato bowed)
    def recap_bass():
        for chord in prog:
            play_voice("pluck", key[chord] / 4, 0.12, 0.4)
            time.sleep(BT * 3)

    bt = threading.Thread(target=recap_bass, daemon=True)
    bt.start()

    for deg in mel:
        play_voice("bowed", key[deg] / 2, 0.08, BT * 1.5)
        time.sleep(BT * 1.3)
    bt.join()
    time.sleep(BT * 3)

    prev_voice_count = 2

    # --- RESOLUTION (Mvt 4): 1-2 voices, solo, silence ---
    mvt = "Resolution"
    mvt_idx = 4
    write_composer_state(key_name, "solo", mvt, song_num)
    print(f"  V. {mvt}", flush=True)

    # Ch.6: new timbre reserved for resolution
    if budget.can_use("new_timbre", mvt_idx):
        play_voice("choir", key[5], 0.03, 3.0)
        time.sleep(2)
        budget.spend("new_timbre")

    # Three slow descending notes
    play_voice("pluck", key[5], 0.10, 0.6)
    time.sleep(BT * 4)
    play_voice("pluck", key[3], 0.08, 0.6)
    time.sleep(BT * 4)
    play_voice("pluck", key[1], 0.06, 0.8)
    time.sleep(BT * 5)

    # Silence
    time.sleep(3)
    budget.reset()
    elapsed = int(time.time() - time.time())
    print(f"  Done", flush=True)
    return next_key


# === DUET MODE ===

def duet_loop(initial_key: str, song_num: int) -> str:
    current_key = initial_key
    silence_count = 0
    MAX_SILENCE = 15

    print(f"\n=== DUET MODE: {current_key} ===", flush=True)
    send_face_message("Duet mode — I hear you!", 20)

    while silence_count < MAX_SILENCE:
        ts = read_theramini()

        if not should_enter_duet(ts) and not ts.get("is_playing"):
            silence_count += 1
            if silence_count == 3:
                # Respond after pause — use theramini_duet intelligence
                write_composer_state(current_key, "duet", "Responding", song_num)
                root = KEY_ROOTS.get(current_key, 130.8)
                register = suggest_response_register(root * 2)
                dens = suggest_response_density(0.5)
                phrase = suggest_response_phrase(root, register, dens)
                for freq, dur in phrase:
                    play_voice("pluck", freq, 0.12, 0.45)
                    time.sleep(dur * BT)
                time.sleep(BT * 2)
            elif silence_count == 8:
                # Longer pause — bass figure
                root = KEY_ROOTS.get(current_key, 130.8)
                for deg in [1, 5, 3, 1]:
                    key = make_key(root)
                    play_voice("pluck", key[deg] / 4, 0.10, 0.5)
                    time.sleep(BT * 2)
            else:
                time.sleep(BT * 2)
            continue

        silence_count = 0
        their_key = ts.get("suggested_key", current_key)
        their_rms = ts.get("rms", 0)
        their_note = ts.get("pitch_note")

        if their_key and their_key != current_key and their_key in KEY_ROOTS:
            print(f"  Key: {current_key} → {their_key}", flush=True)
            current_key = their_key

        write_composer_state(current_key, "duet", "Listening", song_num, their_note)
        root = KEY_ROOTS.get(current_key, 130.8)
        key = make_key(root)

        # Adapt: loud playing → quiet sustained; quiet → gentle waltz
        if their_rms > 0.1:
            play_voice("pluck", key[random.choice([1, 3, 5])] / 4, 0.06, 0.6)
            time.sleep(BT * 3)
        elif their_rms > 0.02:
            rd = random.choice([1, 4, 5])
            play_voice("pluck", key[rd] / 4, 0.10, 0.4)
            time.sleep(BT)
            play_voice("pluck", key[rd + 4] / 2, 0.05, 0.3)
            time.sleep(BT)
            play_voice("pluck", key[rd + 4] / 2, 0.04, 0.25)
            time.sleep(BT)
        else:
            play_voice("pluck", key[random.choice([1, 3, 5, 8])], 0.04, 0.5)
            time.sleep(BT * 2)

    print(f"  Theramini silent → SOLO in {current_key}", flush=True)
    send_face_message("", 0)
    return current_key


# === MAIN ===

def main() -> None:
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    signal.signal(signal.SIGINT, lambda *_: sys.exit(0))

    c.send_message("/g_freeAll", [0])
    time.sleep(0.5)

    print("CypherClaw Duet Composer v2 — Korsakov Ch.1-6", flush=True)

    key_idx = random.randint(0, len(KEYS_CYCLE) - 1)
    current_key = KEYS_CYCLE[key_idx]
    song_num = 0

    while True:
        song_num += 1
        ts = read_theramini()

        if should_enter_duet(ts):
            their_key = ts.get("suggested_key", current_key)
            if their_key in KEY_ROOTS:
                current_key = their_key
            print(f"\n--- Song {song_num}: DUET ---", flush=True)
            current_key = duet_loop(current_key, song_num)
        else:
            print(f"\n--- Song {song_num}: SOLO ---", flush=True)
            current_key = solo_song(current_key, song_num)

        time.sleep(random.uniform(4, 7))


if __name__ == "__main__":
    main()
