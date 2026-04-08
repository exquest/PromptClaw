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
import random as _rnd
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
    "pluck":   {"attack": 0.018, "release": 0.7, "brightness": 0.5, "position": 0.1, "damping": 0.01, "detune": 0.003, "verb": 0.15, "dly": 0.0},
    "bowed":   {"attack": 0.05,  "release": 1.2, "verb": 0.2, "dly": 0.02},     # medium depth
    "kotekan": {"attack": 0.015, "release": 0.4, "verb": 0.25, "dly": 0.03},    # sparkly, a bit back
    "gong":    {"attack": 0.15,  "release": 4.0, "verb": 0.45, "dly": 0.04},    # far away, deep
    "bell":    {"attack": 0.01,  "release": 0.8, "verb": 0.35, "dly": 0.05},    # distant shimmer
    "choir":   {"attack": 0.5,   "release": 1.5, "verb": 0.35, "dly": 0.03},    # medium-far
    "breath":  {"attack": 0.8,   "release": 2.0, "verb": 0.18, "dly": 0.01},    # close, intimate
}


# Sustained voices go through ADSR-controlled SenseweaveVoice
# Percussive voices (pluck, kotekan, gong) fire directly
_sw_voice = SenseweaveVoice(osc=c)

# Which voices are sustained (need ADSR control) vs percussive (fire-and-forget)
_SUSTAINED = set()  # nothing sustained — everything is fire-and-forget
_PERCUSSIVE = {"pluck", "kotekan", "gong", "bell", "bowed", "choir", "breath"}  # ALL fire-and-forget


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
        import random as _rnd
        args = [
            synth, next_nid(), 0, 0,
            "freq", freq, "amp", amp,
            "attack", defaults["attack"],
            "release", release or defaults["release"],
        ]
        # Per-voice space — verb and delay from defaults
        args.extend([
            "verb", defaults.get("verb", 0.15),
            "dly", defaults.get("dly", 0.0),
        ])
        # Vary pluck character per note
        if voice_name == "pluck":
            args.extend([
                "brightness", defaults.get("brightness", 0.5) * _rnd.uniform(0.6, 1.4),
                "position", _rnd.uniform(0.02, 0.05),
                "detune", _rnd.uniform(0.001, 0.006),
            ])
        c.send_message("/s_new", args)


def release_sustained() -> None:
    """Release all sustained voices. Call between movements."""
    _sw_voice.release_all()


# === KEY/SCALE ===

KEY_ROOTS = {
    "C": 130.8, "C#": 138.6, "D": 146.8, "D#": 155.6,
    "E": 164.8, "F": 174.6, "F#": 185.0, "G": 196.0,
    "G#": 207.7, "A": 220.0, "A#": 233.1, "B": 246.9, "Bb": 116.5,
}

# ---------------------------------------------------------------------------
# Camera awareness — outdoor light influences key, motion triggers events
# ---------------------------------------------------------------------------

def _read_outdoor() -> dict:
    """Read outdoor conditions from camera state files."""
    import json as _json
    for p in ["/tmp/porch_eye_state.json", "/tmp/side_eye_state.json"]:
        try:
            d = _json.loads(open(p).read())
            if not d.get("error") and d.get("last_capture_time", 0) > time.time() - 120:
                return d
        except Exception:
            continue
    return {}

# Map outdoor brightness to preferred keys
# Bright = major/sharp keys, dark = flat/minor-feeling keys
_BRIGHT_KEYS = ["G", "D", "A", "E"]  # bright, open
_DIM_KEYS = ["F", "C", "Bb"]          # warmer, darker


def _read_room_presence() -> dict:
    """Read room presence from /dev/video0 camera analysis."""
    import json as _json
    try:
        return _json.loads(open("/tmp/room_presence.json").read())
    except Exception:
        return {}

def _read_midi_keyboard() -> dict:
    """Read MIDI keyboard state."""
    import json as _json
    try:
        d = _json.loads(open("/tmp/midi_keyboard_state.json").read())
        if d.get("last_activity", 0) > time.time() - 5:
            return d
    except Exception:
        pass
    return {}

def _read_garden() -> dict:
    """Read garden watcher outdoor state."""
    import json as _json
    try:
        return _json.loads(open("/tmp/garden_state.json").read())
    except Exception:
        return {}


# ---------------------------------------------------------------------------
# Character System — each organism character has a visual form + musical voice
# ---------------------------------------------------------------------------
import sys as _sys
_sys.path.insert(0, "/home/user/cypherclaw/tools/senseweave")
from character_registry import CharacterRegistry

_char_registry = CharacterRegistry()

# Track which characters played recently so everyone gets a turn
_cast_history: list[str] = []

def _get_cast(mood_energy: float = 0.5, max_chars: int = 6) -> list[dict]:
    """Choose which characters are on stage. ALL 21 rotate over time.
    
    Energy determines cast SIZE (2-8). Characters who haven't played
    recently get priority. Every role is always represented.
    """
    global _cast_history
    all_chars = _char_registry.get_all()
    
    # Cast size scales with energy
    cast_size = max(3, min(8, int(2 + mood_energy * 6)))
    cast_size = min(cast_size, max_chars)
    
    # Score each character: lower = more deserving of stage time
    scores = {}
    for cid, char in all_chars.items():
        voice = char.get("voice", {})
        if not voice.get("synth"):
            continue
        # How recently did they play? (position in history, 0 = most recent)
        try:
            recency = _cast_history.index(cid)
        except ValueError:
            recency = 999  # never played — highest priority
        scores[cid] = recency
    
    # Sort by score (highest = least recently played)
    ranked = sorted(scores.keys(), key=lambda c: scores[c], reverse=True)
    
    # Pick cast: ensure at least one of each core role
    cast = []
    used_roles = set()
    core_roles = ["melody", "rhythm", "harmony"]
    
    # First: fill core roles from the most-deserving characters
    for cid in ranked:
        char = all_chars[cid]
        role = char["voice"].get("role", "")
        if role in core_roles and role not in used_roles:
            cast.append({"id": cid, **char["voice"], "char_name": cid})
            used_roles.add(role)
    
    # Then: fill remaining slots from most-deserving
    for cid in ranked:
        if len(cast) >= cast_size:
            break
        if any(c["id"] == cid for c in cast):
            continue
        char = all_chars[cid]
        cast.append({"id": cid, **char["voice"], "char_name": cid})
    
    # Update history
    _cast_history = [c["id"] for c in cast] + _cast_history
    _cast_history = _cast_history[:60]  # keep last ~3 songs worth
    
    return cast

def _play_character(char: dict, freq: float, amp: float, release: float = 0.5) -> None:
    """Play a note as a specific character using their synth and params."""
    synth = char.get("synth", "sw_pluck")
    register = char.get("register", [36, 96])
    params = char.get("params", {})
    
    # Clamp frequency to character's register (MIDI note range)
    import math
    midi = int(69 + 12 * math.log2(max(freq, 20) / 440))
    midi = max(register[0], min(register[1], midi))
    freq = 440.0 * (2 ** ((midi - 69) / 12.0))
    
    import random as _rnd
    args = [synth, next_nid(), 0, 0,
            "freq", freq, "amp", amp,
            "attack", params.get("attack", 0.01),
            "release", release,
            "verb", params.get("verb", 0.2),
            "dly", params.get("dly", 0.02)]
    
    # Add character-specific params
    for k, v in params.items():
        if k not in ("attack", "release", "verb", "dly"):
            args.extend([k, v])
    
    c.send_message("/s_new", args)

def _chars_by_role(cast: list[dict], role: str) -> list[dict]:
    """Filter cast to characters with a given role."""
    return [c for c in cast if c.get("role") == role]

def _write_active_characters(cast: list[dict]) -> None:
    """Write active characters to state so art engine can draw them."""
    import json as _json2
    try:
        data = {"active_characters": [c["id"] for c in cast], "timestamp": time.time()}
        tmp = "/tmp/active_characters.json.tmp"
        with open(tmp, "w") as f:
            _json2.dump(data, f)
        os.replace(tmp, "/tmp/active_characters.json")
    except Exception:
        pass



def _read_inner_life() -> dict:
    """Read inner life music suggestions."""
    import json as _json
    try:
        d = _json.loads(open("/tmp/inner_life_music.json").read())
        if d.get("timestamp", 0) > time.time() - 120:
            return d
    except Exception:
        pass
    return {}

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

    # Let outdoor conditions nudge key choice
    _outdoor = _read_outdoor()
    _garden = _read_garden()
    if _garden and _garden.get("music_key"):
        # Garden watcher has a key suggestion based on light + season
        _gkey = _garden["music_key"].replace("m", "")  # strip minor indicator
        if _gkey in KEY_ROOTS:
            key_name = _gkey
    elif _outdoor:
        _bright = _outdoor.get("brightness", 0.5)
        if _bright > 0.6 and key_name not in _BRIGHT_KEYS:
            key_name = random.choice(_BRIGHT_KEYS)
        elif _bright < 0.2 and key_name not in _DIM_KEYS:
            key_name = random.choice(_DIM_KEYS)
    # If someone is playing the MIDI keyboard, match their key
    _midi = _read_midi_keyboard()
    if _midi.get("playing") and _midi.get("notes"):
        from audio_analysis import pitch_to_nearest_key
        _midi_key = pitch_to_nearest_key(_midi["freqs"][0])
        if _midi_key and _midi_key[0] in KEY_ROOTS:
            key_name = _midi_key[0]
    # Inner life music influence
    _inner = _read_inner_life()
    if _inner.get("suggested_key") and _inner["suggested_key"] in KEY_ROOTS:
        key_name = _inner["suggested_key"]
    if _inner.get("suggest_silence"):
        time.sleep(random.uniform(5, 15))
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
    # Choose which characters are on stage for this song
    _energy = 0.5
    try:
        import json as _j
        _org = _j.loads(open("/tmp/organism_state.json").read())
        _energy = _org.get("organism_mood", {}).get("energy", 0.5)
    except Exception:
        pass
    _cast = _get_cast(_energy)
    _write_active_characters(_cast)
    _melody_chars = _chars_by_role(_cast, "melody")
    _rhythm_chars = _chars_by_role(_cast, "rhythm")
    _harmony_chars = _chars_by_role(_cast, "harmony")
    _color_chars = _chars_by_role(_cast, "color")
    _accent_chars = _chars_by_role(_cast, "accent")
    _foundation_chars = _chars_by_role(_cast, "foundation")
    _texture_chars = _chars_by_role(_cast, "texture")
    _punctuation_chars = _chars_by_role(_cast, "punctuation")
    _all_roles = {"melody": _melody_chars, "rhythm": _rhythm_chars,
                  "harmony": _harmony_chars, "color": _color_chars}
    print(f"  Cast: {[c['id'] for c in _cast]}", flush=True)
    
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
    # === BETWEEN-SONG CRITIQUE: ChatMusician + self-listening ===
    try:
        import json as _critique_json, urllib.request as _curl
        # 1. Read what I heard of myself
        _self = {}
        try:
            _self = _critique_json.loads(open("/tmp/self_listen.json").read())
        except Exception:
            pass
        _was_playing = _self.get("is_playing", False)
        _my_amp = _self.get("amplitude", 0)

        # 2. Ask ChatMusician to critique (ABC notation style)
        _critique_prompt = (
            f"I just played a song in {key_name} major, {feel.value} feel at {int(bpm)} BPM. "
            f"Cast: {[c['id'] for c in _cast]}. "
            f"My amplitude was {_my_amp:.3f}. "
            f"What should I try differently in the next song? "
            f"Suggest a key, tempo change, or musical idea in under 30 words."
        )
        # Mute during GPU model swap to prevent audio glitch
        try:
            import subprocess as _sp
            _sp.run(["amixer", "-D", "hw:USB", "sset", "Line 01 Mute", "on"], capture_output=True, timeout=2)
            _sp.run(["amixer", "-D", "hw:USB", "sset", "Line 02 Mute", "on"], capture_output=True, timeout=2)
        except Exception:
            pass

        _payload = _critique_json.dumps({
            "model": "chatmusician",
            "prompt": _critique_prompt,
            "stream": False,
            "options": {"num_predict": 60, "temperature": 0.9},
        }).encode()
        _req = _curl.Request("http://localhost:11434/api/generate",
                             data=_payload, headers={"Content-Type": "application/json"})
        _resp = _curl.urlopen(_req, timeout=30)
        _critique = _critique_json.loads(_resp.read()).get("response", "").strip()
        if _critique:
            print(f"  ChatMusician: {_critique[:80]}", flush=True)
            _last_intention = _critique
            # Write critique to face bus so it shows on screen
            try:
                msg = _critique_json.dumps({"text": f"Self-critique: {_critique[:150]}", "role": "system", "time": time.time()})
                with open("/tmp/cypherclaw_messages.jsonl", "a") as _bf:
                    _bf.write(msg + "\n")
            except Exception:
                pass
    except Exception:
        pass

    # Unmute after GPU model swap
    try:
        import subprocess as _sp2
        _sp2.run(["amixer", "-D", "hw:USB", "sset", "Line 01 Mute", "off"], capture_output=True, timeout=2)
        _sp2.run(["amixer", "-D", "hw:USB", "sset", "Line 02 Mute", "off"], capture_output=True, timeout=2)
    except Exception:
        pass

    # 3. Original LLM intention
    try:
        _chat_resp = _llm.get_intention(hour, "calm", key_name)
        if _chat_resp:
            _last_intention = _chat_resp
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

    # Generate antecedent/consequent phrase pair for Theme
    chord_seq = [[c, c + 2, c + 4] for c in prog] if prog else None
    theme_antecedent, theme_consequent = mind.generate_phrase_pair(8, chord_seq)

    for rep in range(2):
        loud = 0.7 + rep * 0.1
        acc_type = select_accompaniment_type(density.density(), density.is_resting())

        # ADSR pad underneath the theme (bowed, quiet)
        _sw_voice.set_preset("pad")
        _sw_voice.pad_chord(key[1] / 2, key[5] / 2, 0.03 * loud)
        # Foundation character holds the bass
        if _foundation_chars:
            _fc = _foundation_chars[0]
            _play_character(_fc, key[1] / 4, 0.025 * loud, 3.0)
        # Harmony character adds warmth
        if _harmony_chars and random.random() < 0.5:
            _hc = random.choice(_harmony_chars)
            _play_character(_hc, key[5] / 2, 0.02 * loud, 2.0)

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

        # Phrase pair: first rep = antecedent (unresolved), second = consequent (resolves)
        theme_phrase = theme_antecedent if rep == 0 else theme_consequent
        for i, (freq, dur, accent) in enumerate(theme_phrase):
            if check_theramini():
                bass_t.join()
                return key_name
            if freq == 0:  # rest
                time.sleep(dur * bt)
                continue
            # Note length varies with musical duration — longer notes ring longer
            _pluck_rel = min(2.0, max(0.3, dur * 0.6 + _rnd.uniform(-0.1, 0.2)))
            play_voice("pluck", freq, (0.22 if accent else 0.16) * loud, _pluck_rel)
            _learner.record_note(freq, dur, accent, "pluck")
            # Character voices — let a cast member double the melody
            if _melody_chars and random.random() < 0.4:
                _mc = random.choice(_melody_chars)
                _play_character(_mc, freq, 0.08 * loud, _pluck_rel * 0.8)
            # Rhythm characters on accents
            if accent and _rhythm_chars and random.random() < 0.5:
                _rc = random.choice(_rhythm_chars)
                _play_character(_rc, freq / 2, 0.06 * loud, 0.3)
            # Color characters as occasional sparkle
            if _color_chars and random.random() < 0.15:
                _cc = random.choice(_color_chars)
                _play_character(_cc, freq * 2, 0.03 * loud, 0.5)
            # React to room activity
            _room = _read_room_presence()
            if _room.get("motion") and random.random() < 0.3 and _accent_chars:
                _ac = random.choice(_accent_chars)
                _play_character(_ac, freq * 2, 0.03 * loud, 0.2)
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

    # Mind generates recap melody — consequent only (resolution, everything resolves)
    recap_chord_seq = [[c, c+2, c+4] for c in prog] if prog else None
    _, recap_phrase = mind.generate_phrase_pair(8, recap_chord_seq)
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
