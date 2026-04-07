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

# Senseweave ADSR voice for sustained sounds
from senseweave.synthesis.senseweave_voice import SenseweaveVoice, PAD, BREATH, SWELL, STAB

# Melodic mind — real-time note generation
from senseweave.synthesis.melodic_mind import (
    MelodicMind,
    MelodicMemory,
    LLMAdvisor,
    RhythmFeel,
    personality_for_hour,
)

# Continuous learner — learn-by-performing feedback loop
from senseweave.synthesis.continuous_learner import ContinuousLearner

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

import math as _math

THERAMINI_STATE = Path("/tmp/theramini_state.json")


# === EQ DRIFT — slow modulation prevents ear fatigue ===

# EQ modulation is handled INSIDE sw_master_smooth SynthDef via internal LFOs.
# No external /n_set needed — zero pops.
# EQ modulation is handled INSIDE sw_master_smooth SynthDef via internal LFOs.
# No external /n_set needed — zero pops.
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
    "pluck":   {"attack": 0.005, "release": 0.7},   # longer release = warmer, less sparse
    "bowed":   {"attack": 0.05,  "release": 1.2},
    "kotekan": {"attack": 0.005, "release": 0.4},
    "gong":    {"attack": 0.15,  "release": 4.0},    # longer gong ring
    "bell":    {"attack": 0.01,  "release": 0.8},    # slightly longer bell
    "choir":   {"attack": 0.5,   "release": 1.5},
    "breath":  {"attack": 0.8,   "release": 2.0},
}


# Sustained voices go through ADSR-controlled SenseweaveVoice
# Percussive voices (pluck, kotekan, gong) fire directly
_sw_voice = SenseweaveVoice(osc=c)

# Which voices are sustained (need ADSR control) vs percussive (fire-and-forget)
_SUSTAINED = {"bowed", "choir", "breath"}
_PERCUSSIVE = {"pluck", "kotekan", "gong", "bell"}  # bell is short enough for fire-and-forget


def play_voice(voice_name: str, freq: float, amp: float, release: float | None = None) -> None:
    """Play a note on a named voice.

    Sustained voices (bowed, choir, breath, bell) go through SenseweaveVoice
    with ADSR control. Percussive voices (pluck, kotekan, gong) fire directly.
    """
    if voice_name in _SUSTAINED:
        # Use SenseweaveVoice — has ADSR and note_off capability
        _sw_voice.set_timbre(voice_name)
        _sw_voice.note_on(freq, amp)
    else:
        # Fire and forget — natural decay
        synth = SYNTH_MAP.get(voice_name, "sw_pluck")
        defaults = VOICE_DEFAULTS.get(voice_name, {"attack": 0.01, "release": 0.5})
        c.send_message("/s_new", [synth, next_nid(), 0, 0,
            "freq", freq, "amp", amp,
            "attack", defaults["attack"],
            "release", release or defaults["release"]])


def release_sustained() -> None:
    """Release all sustained voices. Call between movements."""
    _sw_voice.release_all()


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

# Melodic mind instances (created per song with appropriate settings)
_memory = MelodicMemory()
_llm = LLMAdvisor(model="qwen3.5:4b")
_learner = ContinuousLearner(llm_advisor=_llm)
_last_intention: dict = {}


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
    global _last_intention

    # Check if the learner suggests exploring a new key or feel
    exploration = _learner.suggest_exploration()
    if exploration:
        if "try_key" in exploration and exploration["try_key"] in KEY_ROOTS:
            key_name = exploration["try_key"]
        # feel override applied below after personality lookup

    root = KEY_ROOTS.get(key_name, 130.8)
    key = make_key(root)
    prog = random.choice(PROGS)

    # Time-of-day personality shapes the entire song
    hour = time.localtime().tm_hour
    personality = personality_for_hour(hour)
    feel = personality["feel"]
    bpm = random.uniform(*personality["tempo_range"])
    chromatic_prob = personality["chromatic_probability"]

    # Apply exploration feel override if suggested
    if exploration and "try_feel" in exploration:
        try:
            feel = RhythmFeel(exploration["try_feel"])
        except ValueError:
            pass

    # Get learned adjustments before creating the mind
    adj = _learner.get_adjustments_for_mind()

    # Create a melodic mind for this song
    mind = MelodicMind(key_root=root, rhythm_feel=feel, bpm=bpm)
    mind.set_chromatic_probability(chromatic_prob + adj.get("chromatic_adjustment", 0.0))
    bt = 60.0 / bpm  # beat duration from BPM, not hardcoded

    # Start learner recording for this song
    _learner.start_song(song_num, key_name, feel.value, bpm)

    # Ask LLM for musical intention (async-ish — if slow, use cached)
    try:
        _last_intention = _llm.get_intention(hour, "calm", key_name)
    except Exception:
        pass
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
    # Bass speaks — mind generates the opening
    bass_phrase = mind.generate_phrase(3, [[1, 3, 5]])
    for freq, dur, accent in bass_phrase:
        if check_theramini():
            return key_name
        play_voice("pluck", freq / 2, 0.22 if accent else 0.16, 0.6)
        time.sleep(dur * bt * 2)
    time.sleep(bt * 2)

    # Melody responds — mind generates a response
    melody_phrase = mind.generate_phrase(4, [[prog[0], prog[0]+2, prog[0]+4]] if prog else [[1, 3, 5]])
    for freq, dur, accent in melody_phrase:
        if check_theramini():
            return key_name
        play_voice("pluck", freq, 0.20 if accent else 0.14, 0.5)
        density.note_played()
        time.sleep(dur * bt)
    time.sleep(bt * 2)

    release_sustained()  # Clean slate between movements

    # --- THEME (Mvt 1): 2-3 voices, waltz + melody ---
    mvt = "Theme"
    mvt_idx = 1
    write_composer_state(key_name, "solo", mvt, song_num)
    print(f"  II. {mvt}", flush=True)

    # Tint available from Theme onwards
    tint_voice = suggest_tint(mvt)

    for rep in range(2):
        loud = 0.7 + rep * 0.1
        acc_type = select_accompaniment_type(density.density(), density.is_resting())

        # ADSR pad underneath the theme (bowed, quiet)
        _sw_voice.set_preset("pad")
        _sw_voice.pad_chord(key[1] / 2, key[5] / 2, 0.03 * loud)

        def bass_thread():
            for chord in prog:
                r = key[chord] / 4
                f = key[chord + 4] / 2
                pattern = get_pattern(acc_type, r * 2, f * 2, bt, loud * 0.7)
                for freq, amp, rel, wait in pattern:
                    play_voice("pluck", freq, amp, rel)
                    time.sleep(wait)

        bass_t = threading.Thread(target=bass_thread, daemon=True)
        bass_t.start()

        # Mind generates melody in real-time
        chord_seq = [[c, c + 2, c + 4] for c in prog] if prog else None
        theme_phrase = mind.generate_phrase(8, chord_seq)
        for i, (freq, dur, accent) in enumerate(theme_phrase):
            if check_theramini():
                bass_t.join()
                return key_name
            if freq == 0:  # rest
                time.sleep(dur * bt)
                continue
            play_voice("pluck", freq, (0.22 if accent else 0.16) * loud, 0.5)
            _learner.record_note(freq, dur, accent, "pluck")
            density.note_played()
            # Kotekan sparkle (second rep, every 3rd note)
            if rep == 1 and i % 3 == 0 and freq > 0:
                play_voice("kotekan", freq * 2, 0.04 * loud, 0.3)
            # Real-time learning reflection
            reflections = _learner.maybe_reflect()
            if reflections and "chromatic_bump" in reflections:
                mind.set_chromatic_probability(mind._chromatic_probability + reflections["chromatic_bump"])
            time.sleep(dur * bt)
        bass_t.join()

        # Release pad at end of phrase
        release_sustained()

        # Timbral tint at phrase boundary
        if budget.can_use("tinting", mvt_idx):
            tv, ta = tint_texture([v.name for v in voices], tint_voice)
            if ta > 0:
                play_voice(tv, key[1], ta * 0.3, 2.0)
                budget.spend("tinting")

        time.sleep(bt * 3)

    # Ch.4: pedal point at phrase boundary
    if should_pedal(0):
        pf, pa, pr = pedal_note(root, BT)
        play_voice("gong", pf, pa, pr)

    time.sleep(bt * 2)

    release_sustained()

    # --- DEVELOPMENT (Mvt 2): 3-5 voices, key change, crescendo ---
    mvt = "Development"
    mvt_idx = 2
    nroot = KEY_ROOTS.get(next_key, 196.0)
    nkey = make_key(nroot)
    write_composer_state(next_key, "solo", mvt, song_num)
    print(f"  III. {mvt} → {next_key}", flush=True)

    # Gong transition
    play_voice("gong", key[1] / 4, 0.014, 3.5)
    time.sleep(bt * 3)

    # Ch.5: diverging crescendo — build from center outward
    cresc_plan = plan_diverging_crescendo(4)

    # Development: bell melody, bowed counterpoint, breath swell, pluck bass
    loud = 0.85
    acc_type = select_accompaniment_type(density.density(), density.is_resting())

    # Breath swell at the start of development (ADSR controlled)
    _sw_voice.set_preset("swell")
    _sw_voice.swell(nkey[1], 0.04 * loud)

    # Bowed pad underneath (ADSR controlled)
    _sw_voice.set_preset("pad")
    _sw_voice.pad_chord(nkey[1] / 2, nkey[5] / 2, 0.03 * loud)

    def dev_bass():
        for chord in prog:
            r = nkey[chord] / 4
            f = nkey[chord + 4] / 2
            pattern = get_pattern(acc_type, r * 2, f * 2, bt, loud * 0.6)
            for freq, amp, rel, wait in pattern:
                play_voice("pluck", freq, amp, rel)
                time.sleep(wait)

    # Bowed countermelody (lower register, delayed entry)
    # Counter uses mind-generated phrase reversed
    def counter_thread():
        time.sleep(bt * 2)
        counter_mind = MelodicMind(key_root=nroot, rhythm_feel=feel, bpm=bpm)
        counter_phrase = counter_mind.generate_phrase(5)
        for freq, dur, accent in counter_phrase:
            if freq == 0: continue
            play_voice("bowed", freq / 2, 0.06 * loud, bt * 1.5)
            time.sleep(dur * bt * 1.3)

    bass_t = threading.Thread(target=dev_bass, daemon=True)
    ct = threading.Thread(target=counter_thread, daemon=True)
    bass_t.start()
    ct.start()

    # Bell melody — mind generates in the new key
    dev_mind = MelodicMind(key_root=nroot, rhythm_feel=feel, bpm=bpm)
    dev_mind.set_chromatic_probability(chromatic_prob * 1.3)  # more chromatic in development
    dev_phrase = dev_mind.generate_phrase(8, [[c, c+2, c+4] for c in prog] if prog else None)
    for freq, dur, accent in dev_phrase:
        if check_theramini():
            bass_t.join()
            ct.join()
            release_sustained()
            return next_key
        if freq == 0:
            time.sleep(dur * bt)
            continue
        play_voice("bell", freq, (0.08 if accent else 0.05) * loud, 0.6)
        _learner.record_note(freq, dur, accent, "bell")
        density.note_played()
        if freq > root * 3:  # high notes get sparkle
            play_voice("kotekan", freq * 2, 0.035 * loud, 0.25)
        # Real-time learning reflection
        reflections = _learner.maybe_reflect()
        if reflections and "chromatic_bump" in reflections:
            dev_mind.set_chromatic_probability(dev_mind._chromatic_probability + reflections["chromatic_bump"])
        time.sleep(dur * bt)
    bass_t.join()
    ct.join()
    release_sustained()
    time.sleep(bt * 2)

    # Ch.6: sfp pair at climax
    if budget.can_use("sfp", mvt_idx):
        pair = select_sfp_pair("excited")
        play_voice(pair.attack_voice, nkey[1] / 2, pair.attack_amp, pair.attack_release)
        play_voice(pair.sustain_voice, nkey[1], pair.sustain_amp, pair.sustain_release)
        budget.spend("sfp")

    # Ch.5: fusion pair for climax peak
    if budget.can_use("fusion", mvt_idx):
        fp = suggest_fusion_pair("excited")
        fusion_phrase = dev_mind.generate_phrase(4)
        for freq, dur, accent in fusion_phrase:
            if freq == 0: continue
            play_voice(fp[0], freq, 0.14, 0.45)
            play_voice(fp[1], freq * 2, 0.04, 0.3)
            density.note_played()
            time.sleep(dur * bt)
        budget.spend("fusion")

    prev_voice_count = 5
    time.sleep(bt * 2)

    # Ch.6: post-tutti silence
    if should_insert_silence(prev_voice_count, 2):
        sil_beats = silence_duration_beats(prev_voice_count)
        print(f"    [silence: {sil_beats} beats]", flush=True)
        time.sleep(bt * sil_beats)
        # Re-enter with lightest voice
        reentry = suggest_reentry_voice()
        play_voice(reentry, nkey[1], 0.03, 2.0)
        time.sleep(bt * 2)

    release_sustained()

    # --- RECAP (Mvt 3): 2-3 voices, original key, re-orchestrated ---
    mvt = "Recap"
    mvt_idx = 3
    write_composer_state(key_name, "solo", mvt, song_num)
    print(f"  IV. {mvt} — {key_name}", flush=True)

    # Re-orchestrate: bowed melody, breath pad, gentle kotekan ornaments
    play_voice("gong", key[1] / 4, 0.012, 3.0)
    time.sleep(bt * 3)

    # Breath pad underneath (ADSR)
    _sw_voice.set_preset("breath")
    _sw_voice.breath_tone(key[1] / 2, 0.03)

    def recap_bass():
        for chord in prog:
            play_voice("pluck", key[chord] / 4, 0.14, 0.45)
            time.sleep(bt * 3)

    bass_t = threading.Thread(target=recap_bass, daemon=True)
    bass_t.start()

    # Mind generates recap melody — same key, different notes
    recap_phrase = mind.generate_phrase(8, [[c, c+2, c+4] for c in prog] if prog else None)
    for i, (freq, dur, accent) in enumerate(recap_phrase):
        if freq == 0:
            time.sleep(dur * bt)
            continue
        play_voice("bowed", freq / 2, 0.07, bt * 1.5)
        if i % 4 == 3 and freq > 0:
            play_voice("kotekan", freq * 2, 0.03, 0.35)
        time.sleep(dur * bt * 1.3)
    bass_t.join()
    release_sustained()
    time.sleep(bt * 3)

    prev_voice_count = 3

    release_sustained()

    # --- RESOLUTION (Mvt 4): 1-2 voices, solo, silence ---
    mvt = "Resolution"
    mvt_idx = 4
    write_composer_state(key_name, "solo", mvt, song_num)
    print(f"  V. {mvt}", flush=True)

    # Choir swell — the timbre saved for this moment (ADSR)
    if budget.can_use("new_timbre", mvt_idx):
        _sw_voice.set_preset("swell")
        _sw_voice.swell(key[1], 0.04)
        _sw_voice.swell(key[5], 0.03)
        budget.spend("new_timbre")
        time.sleep(2)
        release_sustained()

    # Three slow descending notes — bell for warmth
    play_voice("bell", key[5], 0.06, 0.8)
    time.sleep(bt * 4)
    play_voice("bell", key[3], 0.05, 0.8)
    time.sleep(bt * 5)
    # Final note on pluck — return to the first voice
    play_voice("pluck", key[1], 0.08, 1.0)
    time.sleep(bt * 5)

    # Silence — release everything
    release_sustained()
    time.sleep(3)
    budget.reset()

    # End-of-song learning: evaluate, store best fragments, evolve
    _learner.end_song(memory=_memory)

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
                time.sleep(bt * 2)
            elif silence_count == 8:
                # Longer pause — bass figure
                root = KEY_ROOTS.get(current_key, 130.8)
                for deg in [1, 5, 3, 1]:
                    key = make_key(root)
                    play_voice("pluck", key[deg] / 4, 0.10, 0.5)
                    time.sleep(bt * 2)
            else:
                time.sleep(bt * 2)
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
            time.sleep(bt * 3)
        elif their_rms > 0.02:
            rd = random.choice([1, 4, 5])
            play_voice("pluck", key[rd] / 4, 0.14, 0.45)
            time.sleep(bt)
            play_voice("pluck", key[rd + 4] / 2, 0.05, 0.3)
            time.sleep(bt)
            play_voice("pluck", key[rd + 4] / 2, 0.04, 0.25)
            time.sleep(bt)
        else:
            play_voice("pluck", key[random.choice([1, 3, 5, 8])], 0.04, 0.5)
            time.sleep(bt * 2)

    print(f"  Theramini silent → SOLO in {current_key}", flush=True)
    send_face_message("", 0)
    return current_key


# === MAIN ===

def _graceful_shutdown(*_):
    """Fade to silence before exit — no pops. No /n_free, no /g_freeAll."""
    try:
        # Fade master to zero
        c.send_message("/n_set", [99999, "amp", 0.0])
        # Fade all sustained voices
        release_sustained()
        # Wait for fade
        time.sleep(0.3)
        # Don't call g_freeAll — let restart_composer.sh handle it while muted
    except Exception:
        pass
    sys.exit(0)


def main() -> None:
    signal.signal(signal.SIGTERM, _graceful_shutdown)
    signal.signal(signal.SIGINT, _graceful_shutdown)

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
