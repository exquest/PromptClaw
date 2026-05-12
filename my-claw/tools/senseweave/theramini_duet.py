"""Theramini Duet -- musical intelligence for CypherClaw's duet responses.

Given what the Theramini is playing (pitch, onset rate, silence),
decide what CypherClaw should play back: key, register, density, and phrase.

Reads pitch analysis from audio_analysis.py (sibling module).
Stdlib only -- no numpy.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
import os
import random
import sys
import time
from typing import Any, Literal, Mapping

# Allow importing audio_analysis from the parent tools directory
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from audio_analysis import pitch_to_nearest_key, pitch_to_note_name

# --------------------------------------------------------------------------- #
# Constants
# --------------------------------------------------------------------------- #

# A4 reference
_A4_HZ = 440.0

# Major-scale intervals in semitones from root
_MAJOR_SCALE_SEMITONES = [0, 2, 4, 5, 7, 9, 11]

# Register boundaries (Hz)
_LOW_CEILING = 250.0   # below this = low register
_HIGH_FLOOR = 700.0    # above this = high register

# Duet entry thresholds
_MIN_CONFIDENCE = 0.3
_MAX_STALE_SECONDS = 10.0

# Density thresholds (onsets per second)
_FAST_ONSET_THRESHOLD = 2.0
_SLOW_ONSET_THRESHOLD = 0.5

# Duration multipliers per density class (in beats)
_DURATION_RANGES: dict[str, tuple[float, float]] = {
    "sparse": (1.5, 3.0),
    "moderate": (0.75, 1.5),
    "dense": (0.25, 0.75),
}

# Octave shifts per register
_REGISTER_OCTAVE_SHIFT: dict[str, int] = {
    "low": -1,
    "mid": 0,
    "high": 1,
}

# Conversation protocol shared by listeners and duet output.
ConversationPhase = Literal["listening", "speaking", "solo", "silence"]
ConversationSpeaker = Literal["human", "cypherclaw", "none"]
DuetPolicy = Literal[
    "turn_taking",
    "imitation",
    "counterpoint",
    "accompaniment",
    "call_response",
    "commentary",
    "completion",
    "silence_request",
    "solo",
]
PartnerBehavior = Literal[
    "listening_first",
    "complementary_register",
    "rhythmic_sympathy",
    "harmonic_response_intervals",
    "accompaniment_textures",
    "call_response",
    "imitation",
    "commentary",
    "completion",
    "silence",
]

_PARTNER_BEHAVIORS: tuple[PartnerBehavior, ...] = (
    "listening_first",
    "complementary_register",
    "rhythmic_sympathy",
    "harmonic_response_intervals",
    "accompaniment_textures",
    "call_response",
    "imitation",
    "commentary",
    "completion",
    "silence",
)
_RESPONSE_POLICIES = {
    "imitation",
    "counterpoint",
    "accompaniment",
    "call_response",
    "commentary",
    "completion",
}
_RESPONSE_DELAY_MS = 1200
_SOLO_INACTIVITY_MS = 5000
_SILENCE_CC_THRESHOLD = 3

_CC_NAMES: dict[int, str] = {
    1: "mod_wheel",
    2: "breath",
    7: "volume",
    11: "expression",
    64: "sustain",
}


@dataclass(frozen=True)
class ConversationDecision:
    """Current Theramini conversation state and CypherClaw's allowed action."""

    phase: ConversationPhase
    policy: DuetPolicy
    speaker: ConversationSpeaker
    may_play: bool
    duet_active: bool
    wait_beats: int = 0
    reason: str = ""
    partner_behaviors: tuple[PartnerBehavior, ...] = _PARTNER_BEHAVIORS
    response_register: str = ""
    rhythmic_sympathy: str = ""
    harmonic_intervals: tuple[int, ...] = ()
    accompaniment_texture: str = ""
    lead_role: str = ""
    support_role: str = ""
    max_overlap_beats: int = 0

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-serializable representation for state files."""
        return {
            "phase": self.phase,
            "policy": self.policy,
            "speaker": self.speaker,
            "may_play": self.may_play,
            "duet_active": self.duet_active,
            "wait_beats": self.wait_beats,
            "reason": self.reason,
            "partner_behaviors": list(self.partner_behaviors),
            "response_register": self.response_register,
            "rhythmic_sympathy": self.rhythmic_sympathy,
            "harmonic_intervals": list(self.harmonic_intervals),
            "accompaniment_texture": self.accompaniment_texture,
            "lead_role": self.lead_role,
            "support_role": self.support_role,
            "max_overlap_beats": self.max_overlap_beats,
        }


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _note_name_to_freq(note_name: str, octave: int) -> float:
    """Convert a note name (e.g. 'A') and octave to frequency in Hz.

    Uses A4 = 440 Hz as reference.
    """
    _names = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
    try:
        semitone = _names.index(note_name)
    except ValueError:
        return _A4_HZ  # fallback

    # MIDI number: C4 = 60, A4 = 69
    midi = (octave + 1) * 12 + semitone
    return _A4_HZ * (2.0 ** ((midi - 69) / 12.0))


def _root_freq_for_key(key_name: str) -> float:
    """Return the frequency of the key root in octave 4."""
    return _note_name_to_freq(key_name, 4)


def _scale_freqs(key_name: str, scale_notes: list[str], octave: int) -> list[float]:
    """Return frequencies for all scale degrees in a given octave."""
    freqs = []
    root_idx_map = {
        "C": 0, "C#": 1, "D": 2, "D#": 3, "E": 4, "F": 5,
        "F#": 6, "G": 7, "G#": 8, "A": 9, "A#": 10, "B": 11,
    }
    for note in scale_notes:
        freqs.append(_note_name_to_freq(note, octave))
    # Fix: notes that wrap around (e.g. B in D major) should be in the right octave.
    # If a note's frequency is less than the root, bump it up an octave.
    root_freq = _note_name_to_freq(key_name, octave)
    fixed = []
    for i, f in enumerate(freqs):
        if f < root_freq - 1.0:  # small tolerance
            fixed.append(f * 2.0)
        else:
            fixed.append(f)
    return sorted(fixed)


def _coerce_float(value: object, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _coerce_int(value: object, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _normalize_policy_name(value: object) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip().lower().replace("-", "_").replace("/", "_").replace(" ", "_")


def _normalize_midi_cc(state: Mapping[str, Any]) -> dict[str, object]:
    """Normalize CC payloads from MIDI readers into named controls."""
    raw: dict[str, int] = {}
    named: dict[str, object] = {}

    for source_name in ("midi_cc", "cc", "cc_values"):
        source = state.get(source_name)
        if not isinstance(source, Mapping):
            continue

        raw_source = source.get("raw")
        if isinstance(raw_source, Mapping):
            for key, value in raw_source.items():
                cc_num = _coerce_int(key, -1)
                if cc_num >= 0:
                    raw[str(cc_num)] = max(0, min(127, _coerce_int(value)))

        for key, value in source.items():
            if key == "raw":
                continue
            cc_num = _coerce_int(key, -1)
            if cc_num >= 0:
                raw[str(cc_num)] = max(0, min(127, _coerce_int(value)))
                continue
            name = str(key)
            if name == "sustain":
                named[name] = bool(value)
            else:
                named[name] = max(0, min(127, _coerce_int(value)))

    for cc_num, name in _CC_NAMES.items():
        if str(cc_num) in raw:
            value = raw[str(cc_num)]
            named[name] = value >= 64 if name == "sustain" else value

    for name in ("mod_wheel", "breath", "volume", "expression", "sustain"):
        if name in state and name not in named:
            named[name] = bool(state[name]) if name == "sustain" else max(0, min(127, _coerce_int(state[name])))

    return {
        "raw": raw,
        "mod_wheel": named.get("mod_wheel", 0),
        "breath": named.get("breath", 127),
        "volume": named.get("volume", 100),
        "expression": named.get("expression", 100),
        "sustain": bool(named.get("sustain", False)),
    }


def _silence_requested(state: Mapping[str, Any], midi_cc: Mapping[str, object]) -> bool:
    if bool(state.get("silence_request") or state.get("request_silence")):
        return True
    requested = _normalize_policy_name(
        state.get("requested_policy")
        or state.get("duet_policy")
        or state.get("response_policy")
        or state.get("policy")
    )
    if requested in {"silence", "silence_request"}:
        return True

    for name in ("breath", "volume", "expression"):
        if _coerce_int(midi_cc.get(name), 127) <= _SILENCE_CC_THRESHOLD:
            return True
    return False


def _human_gesture_active(state: Mapping[str, Any], now: float) -> bool:
    if not bool(state.get("is_playing", state.get("playing", False))):
        return False
    if bool(state.get("idle_tone", False)):
        return False
    if _coerce_float(state.get("pitch_confidence"), 0.0) < _MIN_CONFIDENCE:
        return False

    timestamp = _coerce_float(state.get("timestamp"), 0.0)
    if timestamp <= 0 or now - timestamp > _MAX_STALE_SECONDS:
        return False

    return state.get("pitch_hz") is not None or state.get("last_note") is not None


def _requested_response_policy(state: Mapping[str, Any]) -> DuetPolicy:
    requested = _normalize_policy_name(
        state.get("requested_policy")
        or state.get("duet_policy")
        or state.get("response_policy")
        or state.get("policy")
    )
    if requested in {"silence", "silence_request"}:
        return "silence_request"
    if requested in _RESPONSE_POLICIES:
        return requested  # type: ignore[return-value]

    onset_rate = _coerce_float(
        state.get("onset_rate", state.get("activity_rate", 0.0)),
        0.0,
    )
    if onset_rate > _FAST_ONSET_THRESHOLD:
        return "counterpoint"
    if onset_rate < _SLOW_ONSET_THRESHOLD:
        return "imitation"
    return "accompaniment"


def _rhythmic_sympathy_for_onset_rate(onset_rate: float) -> str:
    if onset_rate > _FAST_ONSET_THRESHOLD:
        return "spacious_afterbeats"
    if onset_rate < _SLOW_ONSET_THRESHOLD:
        return "long_tone_breath"
    return "shared_pulse"


def _harmonic_intervals_for_policy(policy: DuetPolicy) -> tuple[int, ...]:
    intervals: dict[DuetPolicy, tuple[int, ...]] = {
        "turn_taking": (),
        "imitation": (0, 12),
        "counterpoint": (-5, 3, 7),
        "accompaniment": (-12, -5, 0),
        "call_response": (2, 7, 12),
        "commentary": (3, 5, 10),
        "completion": (5, 7, 12),
        "silence_request": (),
        "solo": (),
    }
    return intervals[policy]


def _accompaniment_texture_for_policy(policy: DuetPolicy) -> str:
    textures: dict[DuetPolicy, str] = {
        "turn_taking": "listening",
        "imitation": "echoed_contour",
        "counterpoint": "light_counterline",
        "accompaniment": "soft_pedal_texture",
        "call_response": "answering_phrase",
        "commentary": "short_interjection",
        "completion": "cadence_tail",
        "silence_request": "silence",
        "solo": "solo",
    }
    return textures[policy]


def _lead_support_roles(
    *,
    phase: ConversationPhase,
    speaker: ConversationSpeaker,
    may_play: bool,
) -> tuple[str, str]:
    if phase == "solo":
        return "cypherclaw", "none"
    if phase == "silence":
        return "none", "none"
    if speaker == "human":
        return "theramini", "cypherclaw"
    if may_play or speaker == "cypherclaw":
        return "cypherclaw", "theramini"
    return "theramini", "cypherclaw"


def _make_conversation_decision(
    *,
    phase: ConversationPhase,
    policy: DuetPolicy,
    speaker: ConversationSpeaker,
    may_play: bool,
    duet_active: bool,
    state: Mapping[str, Any] | None = None,
    wait_beats: int = 0,
    reason: str = "",
) -> ConversationDecision:
    context = state or {}
    pitch = _coerce_float(context.get("pitch_hz"), _A4_HZ)
    if pitch <= 0.0:
        pitch = _A4_HZ
    onset_rate = _coerce_float(
        context.get("onset_rate", context.get("activity_rate", 0.0)),
        0.0,
    )
    lead_role, support_role = _lead_support_roles(
        phase=phase,
        speaker=speaker,
        may_play=may_play,
    )
    return ConversationDecision(
        phase=phase,
        policy=policy,
        speaker=speaker,
        may_play=may_play,
        duet_active=duet_active,
        wait_beats=wait_beats,
        reason=reason,
        response_register=suggest_response_register(pitch),
        rhythmic_sympathy=_rhythmic_sympathy_for_onset_rate(onset_rate),
        harmonic_intervals=_harmonic_intervals_for_policy(policy),
        accompaniment_texture=_accompaniment_texture_for_policy(policy),
        lead_role=lead_role,
        support_role=support_role,
        max_overlap_beats=0 if not may_play or speaker == "human" else 1,
    )


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #


def normalize_theramini_state(
    theramini_state: Mapping[str, Any] | None,
    *,
    now: float | None = None,
    speaking: bool = False,
) -> dict[str, object]:
    """Return a shared state contract for listener, MIDI/CC, and duet logic."""
    state: dict[str, object] = dict(theramini_state or {})
    now_value = time.time() if now is None else now

    if "timestamp" not in state:
        state["timestamp"] = 0.0

    midi_cc = _normalize_midi_cc(state)
    silence_request = _silence_requested(state, midi_cc)
    human_active = _human_gesture_active(state, now_value)
    is_speaking = bool(state.get("speaking", speaking))
    is_listening = human_active and not silence_request and not is_speaking
    silence_ms = _coerce_int(state.get("consecutive_silence_ms"), 0)

    if is_speaking:
        phase: ConversationPhase = "speaking"
        speaker: ConversationSpeaker = "cypherclaw"
        policy: DuetPolicy = _requested_response_policy(state)
        may_play = True
        duet_active = True
        reason = "cypherclaw_turn"
    elif is_listening:
        phase = "listening"
        speaker = "human"
        policy = "turn_taking"
        may_play = False
        duet_active = True
        reason = "human_gesture_active"
    elif silence_ms >= _SOLO_INACTIVITY_MS:
        phase = "solo"
        speaker = "none"
        policy = "solo"
        may_play = False
        duet_active = False
        reason = "inactive"
    elif silence_request:
        phase = "silence"
        speaker = "none"
        policy = "silence_request"
        may_play = False
        duet_active = True
        reason = "silence_requested"
    else:
        phase = "listening"
        speaker = "none"
        policy = "turn_taking"
        may_play = False
        duet_active = True
        reason = "waiting_for_turn"

    decision = _make_conversation_decision(
        phase=phase,
        policy=policy,
        speaker=speaker,
        may_play=may_play,
        duet_active=duet_active,
        state=state,
        wait_beats=calculate_wait_beats(silence_ms, 0.5),
        reason=reason,
    )

    state["midi_cc"] = midi_cc
    state["human_gesture_active"] = human_active
    state["listening"] = is_listening
    state["speaking"] = is_speaking
    state["silence_request"] = silence_request
    state["conversation"] = decision.to_dict()
    return state


def plan_duet_response(
    theramini_state: Mapping[str, Any] | None,
    *,
    now: float | None = None,
    response_delay_ms: int = _RESPONSE_DELAY_MS,
    inactivity_ms: int = _SOLO_INACTIVITY_MS,
) -> ConversationDecision:
    """Choose the next duet action without crowding the human player's turn."""
    state = normalize_theramini_state(theramini_state, now=now)
    silence_ms = _coerce_int(state.get("consecutive_silence_ms"), 0)

    if bool(state.get("human_gesture_active")):
        if bool(state.get("silence_request")):
            return _make_conversation_decision(
                phase="silence",
                policy="silence_request",
                speaker="none",
                may_play=False,
                duet_active=True,
                state=state,
                wait_beats=0,
                reason="silence_requested",
            )
        return _make_conversation_decision(
            phase="listening",
            policy="turn_taking",
            speaker="human",
            may_play=False,
            duet_active=True,
            state=state,
            wait_beats=0,
            reason="human_gesture_active",
        )

    if should_exit_duet(state, silence_threshold_ms=inactivity_ms):
        return _make_conversation_decision(
            phase="solo",
            policy="solo",
            speaker="none",
            may_play=False,
            duet_active=False,
            state=state,
            wait_beats=0,
            reason="inactive",
        )

    if bool(state.get("silence_request")):
        return _make_conversation_decision(
            phase="silence",
            policy="silence_request",
            speaker="none",
            may_play=False,
            duet_active=True,
            state=state,
            wait_beats=calculate_wait_beats(silence_ms, 0.5),
            reason="silence_requested",
        )

    if silence_ms < response_delay_ms:
        return _make_conversation_decision(
            phase="listening",
            policy="turn_taking",
            speaker="none",
            may_play=False,
            duet_active=True,
            state=state,
            wait_beats=calculate_wait_beats(silence_ms, 0.5),
            reason="waiting_for_turn",
        )

    return _make_conversation_decision(
        phase="speaking",
        policy=_requested_response_policy(state),
        speaker="cypherclaw",
        may_play=True,
        duet_active=True,
        state=state,
        wait_beats=0,
        reason="response_window",
    )


def supported_partner_behaviors() -> tuple[PartnerBehavior, ...]:
    """Return the ensemble-space behaviors this duet policy can express."""
    return _PARTNER_BEHAVIORS


def suggest_response_key(their_pitch_hz: float) -> tuple[str, float]:
    """Given detected pitch, return (key_name, root_freq) for the response.

    Uses pitch_to_nearest_key from audio_analysis.py to find the key,
    then returns the root frequency in octave 4.
    """
    key_name, _scale = pitch_to_nearest_key(their_pitch_hz)
    root_freq = _root_freq_for_key(key_name)
    return key_name, root_freq


def suggest_response_register(their_pitch_hz: float) -> str:
    """Suggest a complementary register.

    If they're playing high, suggest 'low'.
    If they're playing mid, answer on the nearest opposite side band.
    If they're playing low, suggest 'high'.
    """
    if their_pitch_hz >= _HIGH_FLOOR:
        return "low"
    if their_pitch_hz <= _LOW_CEILING:
        return "high"
    return "low" if their_pitch_hz >= _A4_HZ else "high"


def suggest_response_density(their_onset_rate: float) -> str:
    """Suggest inverse density based on their onset rate (onsets/sec).

    Fast playing (>2/s) -> 'sparse' (long held notes).
    Slow playing (<0.5/s) -> 'moderate' (gentle response).
    Medium playing -> 'dense' (fill in the gaps).
    """
    if their_onset_rate > _FAST_ONSET_THRESHOLD:
        return "sparse"
    elif their_onset_rate < _SLOW_ONSET_THRESHOLD:
        return "moderate"
    else:
        return "dense"


def suggest_response_phrase(
    key_root: float,
    register: str,
    density: str,
) -> list[tuple[float, float]]:
    """Generate a response phrase as [(freq_hz, duration_beats)].

    Builds from the scale of the nearest key to key_root.
    Phrase length is 3-6 notes. Register shifts the octave.
    Density controls note durations.
    """
    key_name, scale_notes = pitch_to_nearest_key(key_root)

    # Base octave is 4; shift by register
    octave = 4 + _REGISTER_OCTAVE_SHIFT.get(register, 0)
    freqs = _scale_freqs(key_name, scale_notes, octave)
    if register == "low":
        separated = [freq for freq in freqs if freq <= key_root * 0.75]
        if separated:
            freqs = separated
    elif register == "high":
        separated = [freq for freq in freqs if freq >= key_root * 1.5]
        if separated:
            freqs = separated

    if not freqs:
        # Fallback: just use the root
        freqs = [key_root]

    # Duration range from density
    dur_lo, dur_hi = _DURATION_RANGES.get(density, (0.5, 1.0))

    # Phrase length: 3-6 notes
    phrase_len = random.randint(3, 6)

    phrase: list[tuple[float, float]] = []
    prev_idx = random.randint(0, len(freqs) - 1)

    for _ in range(phrase_len):
        # Prefer stepwise motion: move by 0, 1, or 2 scale degrees
        step = random.choice([-2, -1, -1, 0, 1, 1, 2])
        idx = max(0, min(len(freqs) - 1, prev_idx + step))
        freq = freqs[idx]
        duration = round(random.uniform(dur_lo, dur_hi), 2)
        phrase.append((round(freq, 2), duration))
        prev_idx = idx

    return phrase


def calculate_wait_beats(consecutive_silence_ms: int, beat_duration: float) -> int:
    """How many beats to wait after they stop before responding.

    Returns 0 if they're still playing (silence_ms == 0).
    Returns 2-4 beats after they stop, scaling with silence duration.
    """
    if consecutive_silence_ms <= 0:
        return 0

    # Scale from 2 beats at 500ms silence to 4 beats at 3000ms+
    silence_sec = consecutive_silence_ms / 1000.0
    # Linear interpolation: 0.5s -> 2 beats, 3.0s -> 4 beats
    t = min(1.0, max(0.0, (silence_sec - 0.5) / 2.5))
    beats = 2.0 + t * 2.0
    return min(4, max(2, round(beats)))


def should_enter_duet(theramini_state: dict) -> bool:
    """Return True if a human is actually playing the Theramini.

    Checks:
    - is_playing is True
    - pitch_confidence above threshold
    - timestamp is fresh (not stale)
    - not an idle tone
    """
    try:
        state = normalize_theramini_state(theramini_state)
        return bool(state.get("human_gesture_active")) and not bool(state.get("silence_request"))
    except (TypeError, KeyError, ValueError):
        return False


def should_exit_duet(
    theramini_state: dict,
    silence_threshold_ms: int = 5000,
) -> bool:
    """Return True if they've stopped playing long enough to exit duet mode.

    Exits when:
    - consecutive_silence_ms exceeds threshold
    - timestamp is stale (listener may have died)
    """
    try:
        state = normalize_theramini_state(theramini_state)
        # Stale timestamp = exit (fail safe)
        timestamp = _coerce_float(state.get("timestamp"), 0.0)
        if timestamp <= 0 or time.time() - timestamp > _MAX_STALE_SECONDS:
            return True

        silence_ms = _coerce_int(state.get("consecutive_silence_ms"), 0)
        if silence_ms >= silence_threshold_ms:
            return True

        return False
    except (TypeError, KeyError, ValueError):
        return True
