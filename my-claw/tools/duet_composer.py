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
from collections.abc import Mapping
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "senseweave"))

from pythonosc import udp_client

from cypherclaw import live_midi_emitter
from cypherclaw.composer_vocabulary_bridge import scene_vocabulary_log_suffix
from cypherclaw.space_reverb import (
    VOICE_REVERB_PROFILES,
    active_house_from_scene_metadata,
    resolve_voice_space_profile,
)

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
    normalize_theramini_state,
    plan_duet_response,
    should_enter_duet,
    suggest_response_phrase,
    suggest_response_register,
    suggest_response_density,
)
from senseweave.self_critique import revise_score
from senseweave.harmonic_planner import (
    display_key_spec,
    key_root,
    normalize_key_spec,
    resolve_harmonic_plan,
)
from senseweave.instrument_patches import select_instrument_patch
from senseweave.master_bus import apply_master_bus_scene, seed_master_bus_node
from senseweave.cast_planner import select_cast_ids
from senseweave.emsd_runtime import EMSDLiveContext, build_live_emsd_context, composer_emsd_extras
from senseweave.emsd_performance import render_adjustments_for_event
from senseweave.resource_governor import ResourceBudget, take_snapshot, compute_budget
from dataclasses import replace as _dataclass_replace
from senseweave.form_grammar import plan_form
from senseweave.composition_gate import evaluate_score_tree
from senseweave.commission_context import commission_context_from_tracker_plan
from senseweave.piece_brief import build_piece_brief
from senseweave.piece_commission import commission_piece
from senseweave.piece_queue import PieceQueue
from senseweave.practice_curriculum import select_practice_block
from senseweave.prosody_engine import compose_scene_caption
from senseweave.recursive_composer import compose_score_tree
from senseweave.tracker_compiler import compile_score_tree_to_tracker
from senseweave.music_tracker import (
    build_korsakov_tracker_song,
    build_role_hints_from_cast,
    enrich_score_for_tracker,
    tracker_form_for_family,
)
from senseweave.music_tracker_runtime import ScheduledTrackerEvent, schedule_song
from senseweave.repertoire_memory import RepertoireMemory
from senseweave.tracker_cadence import (
    apply_tracker_plan_to_mood,
    constrain_score_to_cadence,
    resolve_tracker_plan,
    shape_score_for_family,
)
from senseweave.tracker_variation import (
    apply_song_variation,
    choose_rows_per_beat,
    resolve_tracker_mood,
)
from senseweave.sampler_scheduler import (
    density_for_mode,
    plan_sampler_phrase_indices,
)
from senseweave.usage_journal import (
    SampleUsageTracker,
    post_piece_hook,
    record_scheduled_sample_event,
)
from senseweave.generation.composer_hook import (
    _should_queue_now,
)
from senseweave.voice_aliases import resolve_runtime_voice_name
from senseweave.voice_shaping import shaping_for_note
from inner_life.world_model import WorldModel, read_world

import sample_capture_daemon as _sample_capture_daemon

import math as _math


def _post_song_self_quote(score_summary: dict) -> None:
    """Post-song hook: defer to ``sample_capture_daemon.self_quote``.

    The daemon owns the trigger gate (arc_payoff > 0.6, click_count == 0,
    mode != working_ambience). We never let a self-quotation failure
    interrupt the composer loop.
    """
    try:
        _sample_capture_daemon.self_quote(score_summary)
    except Exception:
        pass


_generation_queue = None
_generation_conditioner = None
_conditioner = None
_generation_last_enqueued_at: float | None = None
_GENERATION_QUEUE_DB_ENV = "CYPHERCLAW_GENERATION_QUEUE_DB"
_DEFAULT_GENERATION_QUEUE_DB = Path("/home/user/cypherclaw-data/generation_queue.db")
_MIDI_VOCABULARY_DB_ENV = "CYPHERCLAW_MIDI_VOCABULARY_DB"
_VOCABULARY_CURIOSITY_ENV = "CYPHERCLAW_VOCABULARY_CURIOSITY"
_DEFAULT_MIDI_VOCABULARY_DB = Path("/home/user/cypherclaw-data/state/midi_vocabulary.sqlite")
_LIVE_MIDI_ENABLED_ENV = "CYPHERCLAW_LIVE_MIDI_ENABLED"
_LIVE_MIDI_CONTROL_NUMBERS: dict[str, int] = {
    "density": 20,
    "master_amp": 7,
    "reverb_send": 91,
}
_live_midi_publisher: live_midi_emitter.LiveMidiPublisher | None = None
_live_midi_context: dict[str, str] = {
    "scene": "",
    "tuning": "twelve_tet",
}


def _generation_enabled() -> bool:
    if _generation_queue is not None:
        return True
    return os.environ.get("CYPHERCLAW_GENERATION_ENABLED", "").lower() in {
        "1",
        "true",
        "yes",
    }


def _midi_vocabulary_db_path() -> Path | None:
    configured = os.environ.get(_MIDI_VOCABULARY_DB_ENV)
    path = Path(configured).expanduser() if configured else _DEFAULT_MIDI_VOCABULARY_DB
    return path if path.exists() else None


def _vocabulary_curiosity(narrative_state: Mapping[str, object] | None) -> float:
    raw_value = os.environ.get(_VOCABULARY_CURIOSITY_ENV)
    if raw_value is None and narrative_state is not None:
        raw_value = narrative_state.get("curiosity")
    try:
        value = float(raw_value) if raw_value is not None else 0.15
    except (TypeError, ValueError):
        value = 0.15
    return max(0.0, min(1.0, value))


def _get_generation_queue() -> object | None:
    global _generation_queue

    if not _generation_enabled():
        return None
    if _generation_queue is None:
        from senseweave.generation.queue import GenerationQueue

        db_path = os.environ.get(_GENERATION_QUEUE_DB_ENV) or _DEFAULT_GENERATION_QUEUE_DB
        _generation_queue = GenerationQueue(db_path)
    return _generation_queue


def _get_generation_conditioner() -> object:
    global _conditioner, _generation_conditioner

    if _generation_conditioner is not None:
        return _generation_conditioner
    if _conditioner is not None:
        _generation_conditioner = _conditioner
        return _generation_conditioner

    from senseweave.generation.conditioner import GenerationConditioner

    _generation_conditioner = GenerationConditioner()
    _conditioner = _generation_conditioner
    return _generation_conditioner


def _request_hash(req: object) -> str:
    if isinstance(req, dict):
        value = req.get("request_hash")
    else:
        value = getattr(req, "request_hash", None)
    if value:
        return str(value)
    hash_method = getattr(req, "hash", None)
    if callable(hash_method):
        return str(hash_method())
    raise ValueError("generation request missing request_hash/hash()")


def _json_ready(value: object) -> object:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_ready(item) for item in value]

    tolist = getattr(value, "tolist", None)
    if callable(tolist):
        return _json_ready(tolist())

    item = getattr(value, "item", None)
    if callable(item):
        try:
            return _json_ready(item())
        except ValueError:
            pass

    return str(value)


def _active_house_from_scene_metadata(scene_metadata: Mapping[str, object]) -> str:
    """Return the live house context used for house-bound space routing."""

    return active_house_from_scene_metadata(scene_metadata)


def _request_payload(req: object) -> object:
    if isinstance(req, dict):
        payload = dict(req)
    else:
        to_dict = getattr(req, "to_dict", None)
        if callable(to_dict):
            payload = to_dict()
        elif hasattr(req, "__dict__"):
            payload = dict(vars(req))
        else:
            return _json_ready(req)

    ready = _json_ready(payload)
    if isinstance(ready, dict) and "request_hash" not in ready:
        ready["request_hash"] = _request_hash(req)
    return ready


def _score_arc_phase(score: object, learning: object) -> str:
    metadata = getattr(score, "metadata", {}) or {}
    if isinstance(metadata, dict) and metadata.get("arc_phase"):
        return str(metadata["arc_phase"])
    if isinstance(learning, dict) and learning.get("arc_phase"):
        return str(learning["arc_phase"])
    return "Emergence"


def _build_hook_request(
    *,
    mode: object,
    arc_phase: str,
    mood: dict[str, float],
    clap_centroid: object,
) -> object:
    return _get_generation_conditioner().build_request(
        mode=mode,
        arc_phase=arc_phase,
        mood=mood,
        clap_centroid=clap_centroid,
        duration_sec=5.0,
    )


def _post_song_generation_hook(
    score: object,
    learning: dict,
    mood: dict[str, float],
    mode: object,
    clap_centroid: object,
) -> int | None:
    """Post-song hook: enqueue generated audio without interrupting playback."""
    global _generation_last_enqueued_at

    try:
        queue = _get_generation_queue()
        if queue is None:
            return None

        if isinstance(learning, dict) and _generation_last_enqueued_at is not None:
            learning.setdefault(
                "last_generation_enqueued_at",
                _generation_last_enqueued_at,
            )

        if not _should_queue_now(mode, mood, learning):
            return None

        req = _build_hook_request(
            mode=mode,
            arc_phase=_score_arc_phase(score, learning),
            mood=mood,
            clap_centroid=clap_centroid,
        )
        key = _request_hash(req)
        row_id = queue.enqueue(_request_payload(req), key)
        _generation_last_enqueued_at = time.time()
        return int(row_id)
    except Exception as exc:
        print(f"  Generation hook skipped: {exc}", file=sys.stderr, flush=True)
        return None


def _generation_clap_centroid(learning: dict, mood: dict[str, float]) -> object:
    for source in (learning, learning.get("ear_metrics", {}) if isinstance(learning, dict) else {}):
        if not isinstance(source, dict):
            continue
        for key in ("clap_centroid", "target_clap_centroid", "clap_embedding"):
            value = source.get(key)
            if value is not None:
                return value

    return [
        float(mood.get("energy", 0.5) or 0.5),
        float(mood.get("valence", 0.5) or 0.5),
        float(mood.get("arousal", mood.get("energy", 0.5)) or 0.5),
        *([0.0] * 509),
    ]


def _live_midi_enabled(environ: Mapping[str, str] | None = None) -> bool:
    env = os.environ if environ is None else environ
    return env.get(_LIVE_MIDI_ENABLED_ENV, "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _get_live_midi_publisher() -> live_midi_emitter.LiveMidiPublisher | None:
    global _live_midi_publisher

    if _live_midi_publisher is not None:
        return _live_midi_publisher
    if not _live_midi_enabled():
        return None
    try:
        config = live_midi_emitter.load_config()
        _live_midi_publisher = live_midi_emitter.LiveMidiPublisher(
            config=config,
            post_batch=lambda batch: live_midi_emitter.post_midi_batch(
                batch,
                config,
            ),
        )
    except Exception as exc:
        print(f"  Live MIDI publisher unavailable: {exc}", file=sys.stderr, flush=True)
        return None
    return _live_midi_publisher


def _publish_live_midi_event(event: live_midi_emitter.LiveMidiEvent) -> None:
    publisher = _get_live_midi_publisher()
    if publisher is None:
        return
    try:
        publisher.publish(event)
        flush_due = getattr(publisher, "flush_due", None)
        if callable(flush_due):
            flush_due()
    except Exception as exc:
        print(f"  Live MIDI publish skipped: {exc}", file=sys.stderr, flush=True)


def _set_live_midi_context(scene: object, tuning: object | None = None) -> None:
    _live_midi_context["scene"] = str(scene or "")
    _live_midi_context["tuning"] = str(tuning or "twelve_tet")


def _tuning_context_from_mapping(mapping: Mapping[str, object] | None) -> str:
    if mapping is None:
        return "twelve_tet"
    for key in ("tuning_system_name", "active_tuning", "tuning"):
        value = mapping.get(key)
        if value:
            return str(value)
    return "twelve_tet"


def _tuning_context_from_scene_metadata(
    scene_metadata: Mapping[str, object] | None,
) -> str:
    return _tuning_context_from_mapping(scene_metadata)


def _live_midi_json_value(value: object) -> object:
    if value is None or isinstance(value, str | bool):
        return value
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, float) and _math.isfinite(value):
        return value
    return str(value)


def _live_midi_metadata(
    *,
    role: str,
    frequency_hz: float,
    duration_seconds: float | None,
    extra: Mapping[str, object] | None,
) -> dict[str, object]:
    metadata: dict[str, object] = {
        "duration_seconds": round(float(duration_seconds or 0.0), 4),
        "frequency_hz": round(float(frequency_hz), 3),
        "role": role,
    }
    if extra:
        for key, value in extra.items():
            metadata[str(key)] = _live_midi_json_value(value)
    return metadata


def _frequency_to_midi_note(frequency_hz: object) -> int | None:
    try:
        frequency = float(frequency_hz)
    except (TypeError, ValueError):
        return None
    if not _math.isfinite(frequency) or frequency <= 0.0:
        return None
    midi_note = int(round(69 + 12 * _math.log2(frequency / 440.0)))
    return max(0, min(127, midi_note))


def _amplitude_to_midi_velocity(amplitude: object) -> int | None:
    try:
        amp = float(amplitude)
    except (TypeError, ValueError):
        return None
    if not _math.isfinite(amp) or amp <= 0.0:
        return None
    velocity = int(round((amp / 0.24) * 127))
    return max(1, min(127, velocity))


def _voice_context_tag(voice_name: object) -> str:
    voice = resolve_runtime_voice_name(str(voice_name or ""))
    return voice[3:] if voice.startswith("sw_") else voice


def _publish_live_midi_note(
    *,
    voice_name: str,
    frequency_hz: float,
    amplitude: float,
    duration_seconds: float | None,
    role: str,
    scene: str = "",
    tuning: str = "",
    metadata: Mapping[str, object] | None = None,
) -> None:
    note = _frequency_to_midi_note(frequency_hz)
    velocity = _amplitude_to_midi_velocity(amplitude)
    if note is None or velocity is None:
        return
    scene_context = scene or _live_midi_context.get("scene", "")
    tuning_context = tuning or _live_midi_context.get("tuning", "twelve_tet")
    now = time.time()
    event_metadata = _live_midi_metadata(
        role=role,
        frequency_hz=frequency_hz,
        duration_seconds=duration_seconds,
        extra=metadata,
    )
    voice = _voice_context_tag(voice_name)
    _publish_live_midi_event(
        live_midi_emitter.build_note_on_event(
            note=note,
            velocity=velocity,
            ts=now,
            voice=voice,
            scene=scene_context,
            tuning=tuning_context,
            metadata=event_metadata,
        )
    )
    if duration_seconds is None or duration_seconds <= 0.0:
        return
    _publish_live_midi_event(
        live_midi_emitter.build_note_off_event(
            note=note,
            ts=now + float(duration_seconds),
            voice=voice,
            scene=scene_context,
            tuning=tuning_context,
            metadata=event_metadata,
        )
    )


def _control_value_to_midi(value: object) -> int:
    try:
        raw = float(value)
    except (TypeError, ValueError):
        raw = 0.0
    if not _math.isfinite(raw):
        raw = 0.0
    return max(0, min(127, int(round(max(0.0, min(1.0, raw)) * 127))))


def _publish_live_midi_controls_for_tracker_row(
    scene: object,
    row: int,
    state: Mapping[str, object],
) -> None:
    automation = state.get("automation", {})
    if not isinstance(automation, Mapping):
        return
    scene_name = str(getattr(scene, "name", "") or "")
    scene_metadata = getattr(scene, "metadata", {}) or {}
    tuning = _tuning_context_from_scene_metadata(scene_metadata)
    for control_name, controller in _LIVE_MIDI_CONTROL_NUMBERS.items():
        if control_name not in automation:
            continue
        raw_value = automation[control_name]
        _publish_live_midi_event(
            live_midi_emitter.build_control_change_event(
                controller=controller,
                value=_control_value_to_midi(raw_value),
                ts=time.time(),
                voice="master",
                scene=scene_name,
                tuning=tuning,
                metadata={
                    "control_name": control_name,
                    "control_scope": "scene_automation",
                    "raw_value": _live_midi_json_value(raw_value),
                    "row": int(row),
                },
            )
        )


THERAMINI_STATE = Path("/tmp/theramini_state.json")


# === EQ DRIFT — slow modulation prevents ear fatigue ===

# Master-bus tone motion lives inside `sw_master_smooth`, but scene transitions
# still update the exposed bus controls so EMSD mix plans affect real output.
COMPOSER_STATE = Path("/tmp/composer_state.json")
FACE_MESSAGE = Path("/tmp/face_message.json")
TRACKER_SOLO_ENABLED = os.environ.get("CYPHERCLAW_TRACKER_SOLO", "1") != "0"

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
    "pad": "sw_pad",
    "metal": "sw_metal",
    "grain": "sw_grain",
    "tabla_ge": "sw_tabla_ge",
    "tabla_tin": "sw_tabla_tin",
}

TRACKER_SYNTH_TO_VOICE = {
    "sw_pluck": "pluck",
    "sw_bowed": "bowed",
    "sw_kotekan": "kotekan",
    "sw_gong": "gong",
    "sw_bell": "bell",
    "sw_bell_warm": "bell",
    "sw_choir": "choir",
    "sw_breath": "breath",
    "sw_pad": "pad",
    "sw_metal": "metal",
    "sw_grain": "grain",
    "sw_tabla_ge": "tabla_ge",
    "sw_tabla_tin": "tabla_tin",
}

VOICE_DEFAULTS = {
    "pluck":   {"attack": 0.018, "release": 0.7, "brightness": 0.5, "position": 0.1, "damping": 0.01, "detune": 0.003, "verb": 0.15, "dly": 0.0},
    "bowed":   {"attack": 0.05,  "release": 1.2, "verb": 0.2, "dly": 0.02},     # medium depth
    "kotekan": {"attack": 0.015, "release": 0.4, "verb": 0.25, "dly": 0.03},    # sparkly, a bit back
    "gong":    {"attack": 0.15,  "release": 4.0, "verb": 0.45, "dly": 0.04},    # far away, deep
    "bell":    {"attack": 0.01,  "release": 0.8, "verb": 0.35, "dly": 0.05},    # distant shimmer
    "choir":   {"attack": 0.5,   "release": 1.5, "verb": 0.35, "dly": 0.03},    # medium-far
    "breath":  {"attack": 0.8,   "release": 2.0, "verb": 0.18, "dly": 0.01},    # close, intimate
    "pad":     {"attack": 0.9,   "release": 2.8, "verb": 0.28, "dly": 0.02},
    "metal":   {"attack": 0.01,  "release": 1.1, "verb": 0.32, "dly": 0.04},
    "grain":   {"attack": 0.12,  "release": 1.8, "verb": 0.26, "dly": 0.03},
    "tabla_ge":{"attack": 0.005, "release": 0.42, "verb": 0.12, "dly": 0.0},
    "tabla_tin":{"attack": 0.004,"release": 0.33, "verb": 0.10, "dly": 0.0},
}


# Sustained voices go through ADSR-controlled SenseweaveVoice
# Percussive voices (pluck, kotekan, gong) fire directly
_sw_voice = SenseweaveVoice(osc=c)

# Which voices are sustained (need ADSR control) vs percussive (fire-and-forget)
_SUSTAINED = set()  # nothing sustained — everything is fire-and-forget
_PERCUSSIVE = {"pluck", "kotekan", "gong", "bell", "bowed", "choir", "breath", "pad", "metal", "grain", "tabla_ge", "tabla_tin"}  # ALL fire-and-forget


def play_voice(
    voice_name: str,
    freq: float,
    amp: float,
    release: float | None = None,
    *,
    role: str = "",
    mood_mode: object = "matched",
    active_house: object | None = None,
    scene: str = "",
    tuning: str = "",
    live_midi_metadata: Mapping[str, object] | None = None,
) -> None:
    """Play a note on a named voice.

    Sustained voices (bowed, choir, breath, bell) go through SenseweaveVoice
    with ADSR control. Percussive voices (pluck, kotekan, gong) fire directly.
    """
    if voice_name in _SUSTAINED:
        # Use SenseweaveVoice — has ADSR and note_off capability
        _sw_voice.set_timbre(voice_name)
        _sw_voice.note_on(
            freq,
            amp,
            mood_mode=mood_mode,
            active_house=active_house,
        )
        _publish_live_midi_note(
            voice_name=voice_name,
            frequency_hz=freq,
            amplitude=amp,
            duration_seconds=release,
            role=role,
            scene=scene,
            tuning=tuning,
            metadata=live_midi_metadata,
        )
    else:
        # Fire and forget — natural decay
        resolved_voice = resolve_runtime_voice_name(voice_name)
        synth = (
            resolved_voice
            if resolved_voice.startswith("sw_")
            else SYNTH_MAP.get(resolved_voice, "sw_pluck")
        )
        defaults = VOICE_DEFAULTS.get(resolved_voice, {"attack": 0.01, "release": 0.5})
        shape = shaping_for_note(resolved_voice, freq)
        playback_freq = round(freq * shape.pitch_multiplier, 3)
        performance = render_adjustments_for_event(
            role=role,
            voice_name=resolved_voice,
            frequency_hz=playback_freq,
            context=_active_emsd_context,
            theramini_active=_active_theramini_playing,
        )
        playback_amp = round(
            amp * shape.amp_multiplier * performance.amp_multiplier,
            4,
        )
        playback_release = (
            (release or defaults["release"])
            * shape.release_multiplier
            * performance.release_multiplier
        )
        import random as _rnd
        args = [
            synth, next_nid(), 0, 0,
            "freq", playback_freq, "amp", playback_amp,
            "attack", defaults["attack"],
            "release", playback_release,
        ]
        # Per-voice space — verb and delay from defaults
        args.extend([
            "verb", defaults.get("verb", 0.15) + shape.verb_add + performance.verb_add,
            "dly", defaults.get("dly", 0.0) + shape.dly_add + performance.dly_add,
        ])
        profile_voice = (
            resolved_voice[3:] if resolved_voice.startswith("sw_") else resolved_voice
        )
        if profile_voice in VOICE_REVERB_PROFILES:
            space_profile = resolve_voice_space_profile(
                resolved_voice,
                mood_mode=mood_mode,
                active_house=active_house,
            )
            args.extend(["fx_bus_id", int(space_profile.fx_bus_id)])
        highpass_hz = max(shape.highpass_hz, performance.highpass_hz)
        saturation_mix = shape.saturation_mix + performance.saturation_add
        if highpass_hz > 0.0:
            args.extend(["hpf", round(highpass_hz, 1)])
        if saturation_mix > 0.0:
            args.extend(["drive", round(saturation_mix, 3)])
        # Vary pluck character per note
        if resolved_voice == "pluck":
            position_center = shape.position_center if shape.position_center is not None else 0.035
            args.extend([
                "brightness",
                defaults.get("brightness", 0.5)
                * shape.brightness_multiplier
                * performance.brightness_multiplier
                * _rnd.uniform(0.6, 1.15),
                "position", _rnd.uniform(max(0.02, position_center - 0.015), position_center + 0.015),
                "detune", _rnd.uniform(0.001, 0.006) + shape.detune_add + performance.detune_add,
            ])
        elif performance.detune_add > 0.0:
            args.extend(["detune", round(performance.detune_add, 4)])
        _publish_live_midi_note(
            voice_name=resolved_voice,
            frequency_hz=playback_freq,
            amplitude=playback_amp,
            duration_seconds=playback_release,
            role=role,
            scene=scene,
            tuning=tuning,
            metadata=live_midi_metadata,
        )
        c.send_message("/s_new", args)


def release_sustained() -> None:
    """Release all sustained voices. Call between movements."""
    _sw_voice.release_all()


# === KEY/SCALE ===

KEY_ROOTS = {
    "C": 130.8, "C#": 138.6, "D": 146.8, "D#": 155.6,
    "E": 164.8, "F": 174.6, "F#": 185.0, "G": 196.0,
    "G#": 207.7, "A": 220.0, "A#": 233.1, "B": 246.9,
    "Bb": 116.5, "Eb": 155.6, "Ab": 207.7, "Db": 138.6, "Gb": 185.0,
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
        d = _json.loads(open("/tmp/garden_state.json").read())
        if d.get("last_update", 0) > time.time() - 180:
            return d
    except Exception:
        pass
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
    cast_ids = select_cast_ids(
        all_chars,
        _cast_history,
        mood_energy=mood_energy,
        max_chars=max_chars,
    )
    cast = [{"id": cid, **all_chars[cid]["voice"], "char_name": cid} for cid in cast_ids]
    
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


def _read_narrative_state() -> dict:
    """Read volatile inner-life state for narrative arc fields."""
    import json as _json
    try:
        d = _json.loads(open("/tmp/inner_life_state.json").read())
        if d.get("cycle_started_at", 0) > 0:
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
_repertoire = RepertoireMemory()
_piece_queue = PieceQueue()
_last_intention: dict = {}
_active_emsd_context: EMSDLiveContext | None = None
_active_theramini_playing = False


# === STATE ===

def read_theramini() -> dict:
    try:
        if THERAMINI_STATE.exists():
            data = json.loads(THERAMINI_STATE.read_text())
            if time.time() - data.get("timestamp", 0) < 5.0:
                return normalize_theramini_state(data)
    except (json.JSONDecodeError, OSError):
        pass
    return normalize_theramini_state({})


def write_composer_state(
    key: str,
    mode: str,
    movement: str = "",
    song: int = 0,
    theramini_note: str | None = None,
    *,
    extras: dict[str, object] | None = None,
) -> None:
    _set_live_midi_context(movement, _tuning_context_from_mapping(extras))
    try:
        state = {"key": key, "mode": mode, "movement": movement, "song": song,
                 "theramini_note": theramini_note, "updated": time.time()}
        if extras:
            state.update(extras)
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


def _read_tracker_mood(song_num: int) -> tuple[dict[str, float], str, int]:
    """Build a compact mood vector for tracker score generation."""
    now = time.time()
    organism: dict[str, object] = {}
    try:
        organism = json.loads(Path("/tmp/organism_state.json").read_text())
    except Exception:
        pass

    room = _read_room_presence()
    outdoor = _read_outdoor()
    inner = _read_inner_life()
    resolved = resolve_tracker_mood(
        organism_state=organism,
        room_state=room,
        outdoor_state=outdoor,
        inner_state=inner,
        now=now,
    )
    mood = apply_song_variation(
        resolved.mood,
        song_num=song_num,
        hour=time.localtime(now).tm_hour,
        occupied_hint=bool(room.get("someone_here") or room.get("motion")),
        source_fresh=resolved.source_fresh,
    )
    rows_per_beat = choose_rows_per_beat(mood, song_num=song_num)
    return mood, resolved.source, rows_per_beat


def _tracker_memory_fragments(
    *,
    family: str,
    progression_profile: str,
    cadence_state: str,
    patch_name: str,
) -> list[dict[str, object]]:
    keywords = [family, progression_profile, cadence_state, patch_name, "tracker"]
    fragments: list[dict[str, object]] = []
    fragments.extend(
        _learner.recent_fragments(
            context_tags=[family, progression_profile, cadence_state],
            count=8,
            min_score=0.45,
        )
    )
    fragments.extend(
        _memory.get_recent_matching(
            keywords,
            count=10,
            min_score=0.45,
        )
    )
    fragments.extend(_memory.get_recent(count=10))

    deduped: list[dict[str, object]] = []
    seen: set[tuple[str, tuple[float, ...]]] = set()
    for fragment in fragments:
        context = str(fragment.get("context", "") or "")
        notes = tuple(
            round(float(value), 3)
            for value in fragment.get("notes", [])
            if isinstance(value, (int, float))
        )
        key = (context, notes)
        if not notes or key in seen:
            continue
        seen.add(key)
        deduped.append(fragment)
        if len(deduped) >= 24:
            break
    return deduped


def _piece_context_key(
    *,
    cadence_state: str,
    family: str,
    occupancy_state: str,
    form_class: str,
    composition_mode: str,
) -> str:
    return ":".join(
        [
            cadence_state or "unknown_cadence",
            family or "default",
            occupancy_state or "unknown_occupancy",
            form_class or "song",
            composition_mode or "hook_led",
        ]
    )


def _build_score_tree_piece(
    *,
    world: WorldModel,
    tracker_plan,
    mood: dict[str, float],
    progression_profile: str,
    song_num: int,
) -> tuple[object, object, object]:
    day_phase, weekly_phase = commission_context_from_tracker_plan(
        tracker_plan=tracker_plan,
        world=world,
    )
    commission = commission_piece(
        cadence_state=tracker_plan.cadence_state,
        day_phase=day_phase,
        weekly_phase=weekly_phase,
        attention_score=float(world.attention_score or 0.0),
        narrative_pressure=float(world.experimentation_bias or 0.0),
        occupancy_state=tracker_plan.occupancy_state,
        repertoire_entries=_repertoire.all_songs(),
        song_num=song_num,
        hour=time.localtime().tm_hour,
    )
    repertoire_hint = _repertoire.recall_hint(
        family=tracker_plan.family,
        cadence_state=tracker_plan.cadence_state,
    ) or {}
    structural_hint = _repertoire.structural_recall(
        family=tracker_plan.family,
        cadence_state=tracker_plan.cadence_state,
        form_class=commission.form_class,
        composition_mode=commission.composition_mode,
    ) or {}
    narrative_state = _read_narrative_state()
    brief = build_piece_brief(
        world=world,
        commission=commission,
        family=tracker_plan.family,
        cadence_state=tracker_plan.cadence_state,
        progression_profile=progression_profile,
        repertoire_hint=repertoire_hint or structural_hint,
        narrative=narrative_state or None,
    )
    form = plan_form(
        commission=commission,
        brief=brief,
        family=tracker_plan.family,
    )
    score_tree = compose_score_tree(
        commission=commission,
        brief=brief,
        form=form,
        family=tracker_plan.family,
        cadence_state=tracker_plan.cadence_state,
        progression_profile=progression_profile,
        song_num=song_num,
        mood=mood,
        repertoire_hint=repertoire_hint or structural_hint,
        vocabulary_db_path=_midi_vocabulary_db_path(),
        vocabulary_curiosity=_vocabulary_curiosity(narrative_state),
    )
    gate = evaluate_score_tree(score_tree)
    return commission, score_tree, gate


def tracker_solo_song(initial_key: str, song_num: int) -> str:
    """Solo mode driven by the tracker scheduler.

    The tracker becomes the single owner of note timing. Phrase generation still
    comes from the score/mood layer, but scheduling is row-based and bounded.
    """

    global _active_emsd_context, _active_theramini_playing

    mood, mood_source, _rows_per_beat = _read_tracker_mood(song_num)
    try:
        world = read_world()
    except Exception:
        world = WorldModel()
    plan = resolve_tracker_plan(
        world,
        song_num=song_num,
        hour=time.localtime().tm_hour,
    )
    mood = apply_tracker_plan_to_mood(mood, plan)
    rows_per_beat = choose_rows_per_beat(mood, song_num=song_num)
    repertoire_influence = _repertoire.influence_for_song(
        family=plan.family,
        cadence_state=plan.cadence_state,
        progression_profile=plan.progression_profile,
        song_num=song_num,
    ) or {}
    progression_profile = str(
        repertoire_influence.get("progression_profile", plan.progression_profile) or plan.progression_profile
    )
    form_variant = str(repertoire_influence.get("form_variant", "") or "")
    repertoire_density_bias = float(repertoire_influence.get("density_bias", 0.0) or 0.0)
    payoff_scene = str(repertoire_influence.get("payoff_scene", "") or "")
    payoff_bias = float(repertoire_influence.get("payoff_bias", 0.0) or 0.0)
    practice_block = select_practice_block(
        cadence_state=plan.cadence_state,
        family=plan.family,
        progression_profile=progression_profile,
        song_num=song_num,
    )
    repertoire_hint = _repertoire.recall_hint(
        family=plan.family,
        cadence_state=plan.cadence_state,
    ) or {}
    harmony = resolve_harmonic_plan(
        initial_key,
        song_num=song_num,
        mood=mood,
        family=plan.family,
        cadence_state=plan.cadence_state,
        progression_profile=progression_profile,
        garden_state=_read_garden(),
        outdoor_state=_read_outdoor(),
        midi_state=_read_midi_keyboard(),
        inner_state=_read_inner_life(),
        now=time.time(),
    )
    key_name = harmony.key
    cast = _get_cast(mood.get("energy", 0.5))
    # Resource governor may constrain cast size — applied after budget computed below
    instrument_patch = select_instrument_patch(
        cadence_state=plan.cadence_state,
        family_name=plan.family,
        occupancy_state=plan.occupancy_state,
    )
    role_hints = build_role_hints_from_cast(
        cast,
        synth_voice_map=TRACKER_SYNTH_TO_VOICE,
        cadence_state=plan.cadence_state,
        family_name=plan.family,
        occupancy_state=plan.occupancy_state,
        patch_name=instrument_patch.name,
    )
    theramini_state = read_theramini()
    cpu_capacity = max(1, os.cpu_count() or 1)
    cpu_pressure = min(1.0, max(0.0, os.getloadavg()[0] / cpu_capacity))
    health_snapshot = take_snapshot(cpu_pressure=cpu_pressure)
    resource_budget = compute_budget(health_snapshot)
    # Apply resource budget to cast — shed optional roles under pressure
    if len(cast) > resource_budget.max_voices:
        cast = cast[:resource_budget.max_voices]
    if not resource_budget.allow_color:
        cast = [ch for ch in cast if ch.get("role") != "color"] or cast[:2]
    if not resource_budget.allow_counter:
        cast = [ch for ch in cast if ch.get("role") != "counter"] or cast[:2]
    _write_active_characters(cast)
    emsd_context = build_live_emsd_context(
        cadence_state=plan.cadence_state,
        occupancy_state=plan.occupancy_state,
        family_name=plan.family,
        progression_profile=progression_profile,
        patch_name=instrument_patch.name,
        song_num=song_num,
        theramini_present=bool(theramini_state.get("is_playing") or theramini_state.get("playing")),
        repertoire_songs=_repertoire.all_songs(),
        base_density_bias=repertoire_density_bias,
        attention_score=float(world.attention_score or 0.0),
        cpu_pressure=cpu_pressure,
    )
    # Budget: cap DSP blocks under resource pressure
    if len(emsd_context.phase_plan.dsp.blocks) > resource_budget.dsp_blocks_allowed:
        _capped_dsp = _dataclass_replace(
            emsd_context.phase_plan.dsp,
            blocks=emsd_context.phase_plan.dsp.blocks[:resource_budget.dsp_blocks_allowed],
        )
        _capped_plan = _dataclass_replace(emsd_context.phase_plan, dsp=_capped_dsp)
        emsd_context = _dataclass_replace(emsd_context, phase_plan=_capped_plan)
    _active_emsd_context = emsd_context
    _active_theramini_playing = bool(theramini_state.get("is_playing") or theramini_state.get("playing"))
    commission, score_tree, gate = _build_score_tree_piece(
        world=world,
        tracker_plan=plan,
        mood=mood,
        progression_profile=progression_profile,
        song_num=song_num,
    )
    if gate.approved:
        context_key = _piece_context_key(
            cadence_state=plan.cadence_state,
            family=plan.family,
            occupancy_state=plan.occupancy_state,
            form_class=commission.form_class,
            composition_mode=commission.composition_mode,
        )
        queued_tree = _piece_queue.dequeue_matching(context_key=context_key)
        if queued_tree is not None:
            score_tree = queued_tree
            gate = evaluate_score_tree(score_tree)
        _piece_queue.set_active(score_tree)
        compiled = compile_score_tree_to_tracker(
            score_tree,
            mood=mood,
            family_name=plan.family,
            patch_name=instrument_patch.name,
            cadence_state=plan.cadence_state,
            progression_profile=progression_profile,
            role_hints=role_hints,
            scene_keys=harmony.scene_keys,
            rows_per_beat=rows_per_beat,
        )
        score = compiled.source_score
        tracker_song = compiled.tracker_song
        # Budget: skip expensive next-piece pre-composition when LLM suppressed
        if not resource_budget.suppress_llm:
            next_commission, next_tree, next_gate = _build_score_tree_piece(
                world=world,
                tracker_plan=plan,
                mood=mood,
                progression_profile=progression_profile,
                song_num=song_num + 1,
            )
            next_context_key = _piece_context_key(
                cadence_state=plan.cadence_state,
                family=plan.family,
                occupancy_state=plan.occupancy_state,
                form_class=next_commission.form_class,
                composition_mode=next_commission.composition_mode,
            )
            if next_gate.approved and not _piece_queue.has_context_key(context_key=next_context_key):
                _piece_queue.enqueue(next_tree, context_key=next_context_key)
    else:
        _fallback_course = next(
            (s.production_course for s in score_tree.sections if s.production_course),
            None,
        )
        revision = revise_score(
            mood,
            song_num=song_num,
            family=plan.family,
            cadence_state=plan.cadence_state,
            patch_name=instrument_patch.name,
            progression_profile=progression_profile,
            memory_fragments=_tracker_memory_fragments(
                family=plan.family,
                progression_profile=progression_profile,
                cadence_state=plan.cadence_state,
                patch_name=instrument_patch.name,
            ),
            repertoire_hint=repertoire_influence or None,
            course=_fallback_course or None,
        )
        score = revision.final_score
        score = shape_score_for_family(
            score,
            family=plan.family,
            cadence_state=plan.cadence_state,
            song_num=song_num,
        )
        score = constrain_score_to_cadence(score, world)
        score = enrich_score_for_tracker(score, mood=mood)
        tracker_song = build_korsakov_tracker_song(
            score,
            title=str(score.metadata.get("song_title", f"CypherClaw Tracker Song {song_num}")),
            rows_per_beat=rows_per_beat,
            mood=mood,
            role_hints=role_hints,
            form_templates=tracker_form_for_family(plan.family, song_num=song_num, variant_hint=form_variant),
            family_name=plan.family,
            scene_keys=harmony.scene_keys,
        )

    score.key = key_name
    score.metadata["patch_name"] = instrument_patch.name
    score.metadata["cadence_state"] = plan.cadence_state
    score.metadata["progression_profile"] = progression_profile
    if not gate.approved:
        score.metadata["section_functions"] = json.dumps(harmony.section_functions)
        score.metadata["section_cadences"] = json.dumps(harmony.section_cadences)
    score.metadata["harmonic_section_functions"] = json.dumps(harmony.section_functions)
    score.metadata["harmonic_section_cadences"] = json.dumps(harmony.section_cadences)
    score.metadata["reharm_strategy"] = harmony.reharm_strategy
    score.metadata["practice_block"] = practice_block.name
    score.metadata["arc_phase"] = emsd_context.arc.phase.name
    score.metadata["arc_transition_intent"] = emsd_context.arc.phase.transition_intent
    score.metadata["emsd_artistic_identity"] = emsd_context.identity.statement
    if repertoire_hint.get("title"):
        score.metadata["repertoire_hint"] = str(repertoire_hint["title"])
    if repertoire_influence.get("mode"):
        score.metadata["repertoire_influence_mode"] = str(repertoire_influence["mode"])
    if form_variant:
        score.metadata["repertoire_form_variant"] = form_variant
    score.metadata["repertoire_density_bias"] = f"{emsd_context.density_bias:.3f}"
    score.metadata["emsd_density_bias"] = f"{emsd_context.density_bias:.3f}"
    if payoff_scene:
        score.metadata["repertoire_payoff_scene"] = payoff_scene
    score.metadata["repertoire_payoff_bias"] = f"{payoff_bias:.3f}"

    # CCS-023 / T-017: per-mode sampler density gates. Plan how many sampler
    # events fire this piece and which phrase indices receive them. The
    # actual /s_new dispatch hooks attach in T-016 once the cast carries a
    # SampleRecord; for now the plan is recorded for downstream consumers
    # (metrics, journal, antipatterns) and surfaced in the operator log.
    sampler_mode_name = str(score.metadata.get("artist_mode") or "") or None
    sampler_density_meta = score.metadata.get("mode_sampler_density")
    if sampler_density_meta is not None:
        try:
            sampler_density = max(0.0, min(1.0, float(sampler_density_meta)))
        except (TypeError, ValueError):
            sampler_density = density_for_mode(sampler_mode_name)
    else:
        sampler_density = density_for_mode(sampler_mode_name)
    sampler_total_phrases = (
        sum(len(section.phrases) for section in score_tree.sections)
        if gate.approved
        else len(score.phrases)
    )
    sampler_rng = random.Random(
        hash((song_num, sampler_mode_name or "", sampler_total_phrases))
    )
    sampler_event_indices = plan_sampler_phrase_indices(
        sampler_density, sampler_total_phrases, sampler_rng
    )
    score.metadata["mode_sampler_density"] = f"{sampler_density:.3f}"
    score.metadata["sampler_event_count"] = str(len(sampler_event_indices))
    score.metadata["sampler_event_phrase_indices"] = ",".join(
        str(idx) for idx in sampler_event_indices
    )
    next_key = harmony.next_key

    print(f"\n=== SOLO TRACKER: {display_key_spec(key_name)} ===", flush=True)
    print(f"  Tracker cast: {[char['id'] for char in cast]}", flush=True)
    print(
        "  Mood:"
        f" e={mood['energy']:.2f}"
        f" v={mood['valence']:.2f}"
        f" a={mood['arousal']:.2f}"
        f" source={mood_source}"
        f" rpb={rows_per_beat}",
        flush=True,
    )
    print(
        f"  Plan: cadence={plan.cadence_state} occupancy={plan.occupancy_state} "
        f"family={plan.family} harmony_profile={progression_profile} world={plan.source}",
        flush=True,
    )
    if gate.approved:
        print(
            f"  Piece: class={commission.form_class} mode={commission.composition_mode} "
            f"target={commission.duration_target_s:.0f}s sections={len(score_tree.sections)} "
            f"ending={commission.ending_family}",
            flush=True,
        )
    print(
        f"  Harmony: source={harmony.source} palette={harmony.chord_palette} "
        f"voicing={harmony.voicing_profile} modulation={harmony.modulation_intent} "
        f"reharm={harmony.reharm_strategy}",
        flush=True,
    )
    print(f"  Orchestration: patch={instrument_patch.name}", flush=True)
    print(
        f"  EMSD: arc={emsd_context.arc.phase.name} density={emsd_context.density_bias:+.2f} "
        f"sample={emsd_context.phase_plan.sampling.source.name} "
        f"dsp={','.join(emsd_context.phase_plan.dsp.blocks)}",
        flush=True,
    )
    print(
        f"  Resource: voices={resource_budget.max_voices} color={resource_budget.allow_color} "
        f"counter={resource_budget.allow_counter} grain={resource_budget.grain_density:.2f} "
        f"density={resource_budget.density_multiplier:.2f} dsp={resource_budget.dsp_blocks_allowed} "
        f"[{resource_budget.reason}]",
        flush=True,
    )
    if repertoire_hint.get("title"):
        print(f"  Repertoire hint: {repertoire_hint['title']}", flush=True)
    if form_variant or repertoire_density_bias or payoff_scene:
        print(
            f"  Repertoire shaping: form={form_variant or 'rotation'} density_bias={repertoire_density_bias:+.2f} "
            f"payoff={payoff_scene or 'rotation'}:{payoff_bias:+.2f}",
            flush=True,
        )
    send_face_message(tracker_song.title, 12)
    _learner.start_song(
        song_num,
        key_name,
        "tracker",
        score.tempo_bpm,
        context_tags=[
            plan.family,
            progression_profile,
            plan.cadence_state,
            instrument_patch.name,
            practice_block.name.lower().replace(" ", "_"),
        ],
    )
    usage_tracker = SampleUsageTracker()
    piece_id = str(score.metadata.get("score_tree_id", "") or getattr(score_tree, "piece_id", "") or f"tracker-{song_num}")
    usage_tracker.start_piece(
        piece_id=piece_id,
        timestamp=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    )

    # Voices that count as grain/sample for budget enforcement
    _grain_sample_voices = {"grain", "sw_grain", "sample_grain", "breath"}

    def _play_tracker_event(event: ScheduledTrackerEvent) -> None:
        # Budget: probabilistically skip grain/sample events under pressure
        if (
            resource_budget.grain_density < 1.0
            and event.voice in _grain_sample_voices
            and random.random() > resource_budget.grain_density
        ):
            return
        # Budget: thin non-accent events by density multiplier
        if (
            resource_budget.density_multiplier < 1.0
            and not event.accent
            and random.random() > resource_budget.density_multiplier
        ):
            return
        play_voice(
            event.voice,
            event.frequency_hz,
            event.amplitude,
            event.duration_seconds,
            role=event.role,
            mood_mode=event.scene_metadata.get("mood_mode", "matched"),
            active_house=_active_house_from_scene_metadata(event.scene_metadata),
            scene=event.scene_name,
            tuning=_tuning_context_from_scene_metadata(event.scene_metadata),
            live_midi_metadata={
                "lane_name": event.lane_name,
                "row": event.row,
                "song_title": event.song_title,
            },
        )
        beat_duration = 60.0 / max(score.tempo_bpm, 1.0)
        _learner.record_note(
            event.frequency_hz,
            max(0.25, event.duration_seconds / beat_duration),
            event.accent,
            event.voice,
        )
        record_scheduled_sample_event(usage_tracker, event)

    def _on_scene_start(scene, _index: int) -> None:
        master_bus = apply_master_bus_scene(
            c,
            scene,
            context=emsd_context,
            theramini_active=_active_theramini_playing,
        )
        caption = compose_scene_caption(
            title=tracker_song.title,
            scene_name=scene.name,
            text_hook=str(score.metadata.get("text_hook", "")),
            cadence_state=plan.cadence_state,
            section_function=str(scene.metadata.get("section_function", "")),
            cadence_type=str(scene.metadata.get("cadence_type", "")),
            patch_name=str(scene.metadata.get("patch_name", "")),
            lane_count=len(scene.pattern.lanes),
            practice_block=practice_block.name if plan.cadence_state == "away_practice" else "",
        )
        section_curve = scene.metadata.get("arrangement_curve", "")
        scene_automation = {
            str(lane.name): float(lane.default)
            for lane in getattr(scene.pattern, "automation", ())
        }
        extras = composer_emsd_extras(emsd_context)
        extras.update(
            {
                "song_title": tracker_song.title,
                "text_hook": score.metadata.get("text_hook", ""),
                "practice_block": practice_block.name,
                "scene_caption": caption,
                "reharm_strategy": harmony.reharm_strategy,
                "target_spectral_centroid_hz": float(getattr(world, "spectral_centroid_hz", 0.0) or 0.0),
                "master_bus": master_bus,
                "section_curve": section_curve,
                "automation_values": scene_automation,
            }
        )
        write_composer_state(
            scene.key,
            "solo",
            scene.name,
            song_num,
            extras=extras,
        )
        send_face_message(caption, 6)
        vocabulary_suffix = scene_vocabulary_log_suffix(getattr(scene, "metadata", {}) or {})
        print(
            f"  [{scene.name}] rows={scene.pattern.rows} tempo={scene.tempo_bpm:.1f} "
            f"lanes={len(scene.pattern.lanes)}{vocabulary_suffix}",
            flush=True,
        )

    def _on_tracker_row(scene, row: int, state: dict) -> None:
        stride = max(1, int(getattr(scene, "rows_per_beat", 4) or 4) * 4)
        if row not in {0, scene.pattern.rows - 1} and row % stride != 0:
            return
        automation_values = state.get("automation", {})
        if not isinstance(automation_values, dict):
            automation_values = {}
        master_bus = apply_master_bus_scene(
            c,
            scene,
            context=emsd_context,
            theramini_active=_active_theramini_playing,
            automation_values=automation_values,
        )
        section_curve = state.get("automation_curve", "") or scene.metadata.get("arrangement_curve", "")
        row_extras = composer_emsd_extras(emsd_context)
        row_extras.update({
            "master_bus": master_bus,
            "section_curve": section_curve,
            "automation_values": automation_values,
        })
        write_composer_state(
            scene.key,
            "solo",
            scene.name,
            song_num,
            extras=row_extras,
        )
        _publish_live_midi_controls_for_tracker_row(scene, row, state)

    result = schedule_song(
        tracker_song,
        play_event=_play_tracker_event,
        stop_check=lambda _scene, _row: should_enter_duet(read_theramini()),
        on_scene_start=_on_scene_start,
        on_row=_on_tracker_row,
    )

    release_sustained()
    _active_emsd_context = None
    _active_theramini_playing = False
    if result.completed:
        learning = _learner.end_song(memory=_memory) or {}
        post_piece_hook(
            usage_tracker,
            arc_payoff_score=float(learning.get("arc_payoff", 0.0) or 0.0),
            mode=str(score.metadata.get("artist_mode", "") or plan.cadence_state or ""),
            clicks=int(learning.get("click_count", 0) or 0),
        )
        _post_song_self_quote({
            "arc_payoff": float(learning.get("arc_payoff", 0.0) or 0.0),
            "click_count": int(learning.get("click_count", 0) or 0),
            "mode": str(learning.get("mode", "") or plan.cadence_state or "solo"),
            "arc_phase": emsd_context.arc.phase.name,
            "mood": str(learning.get("mood", "") or mood.get("label", "") or ""),
            "song_id": str(song_num),
        })
        _post_song_generation_hook(
            score,
            learning,
            mood,
            str(score.metadata.get("artist_mode", "") or plan.cadence_state or "solo"),
            _generation_clap_centroid(learning, mood),
        )
        _repertoire.store_song(
            title=tracker_song.title,
            family=plan.family,
            progression_profile=progression_profile,
            cadence_state=plan.cadence_state,
            key=key_name,
            hook_text=str(score.metadata.get("text_hook", "")),
            hook_class=str(score.metadata.get("hook_class", "")),
            practice_block=practice_block.name if plan.cadence_state == "away_practice" else "",
            patch_name=instrument_patch.name,
            ear_metrics=learning.get("ear_metrics", {}),
            form_class=str(score.metadata.get("form_class", "")),
            composition_mode=str(score.metadata.get("composition_mode", "")),
            ending_family=str(score.metadata.get("ending_family", "")),
            score_tree=score_tree if gate.approved else None,
        )
        print(f"  Tracker done", flush=True)
        return next_key

    print("  Tracker interrupted for duet", flush=True)
    return key_name


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
        _gkey = normalize_key_spec(_garden["music_key"])
        if _gkey:
            key_name = _gkey
    elif _outdoor:
        _bright = _outdoor.get("brightness", 0.5)
        if _bright > 0.6 and key_root(key_name) not in _BRIGHT_KEYS:
            key_name = random.choice(_BRIGHT_KEYS)
        elif _bright < 0.2 and key_root(key_name) not in _DIM_KEYS:
            key_name = random.choice(_DIM_KEYS)
    # If someone is playing the MIDI keyboard, match their key
    _midi = _read_midi_keyboard()
    if _midi.get("suggested_key"):
        _midi_key = normalize_key_spec(_midi["suggested_key"])
        if _midi_key:
            key_name = _midi_key
    # Inner life music influence
    _inner = _read_inner_life()
    if _inner.get("suggested_key"):
        _inner_key = normalize_key_spec(_inner["suggested_key"])
        if _inner_key:
            key_name = _inner_key
    if _inner.get("suggest_silence"):
        time.sleep(random.uniform(5, 15))
    root = KEY_ROOTS.get(key_root(key_name), 130.8)
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
            f"I just played a song in {display_key_spec(key_name)}, {feel.value} feel at {int(bpm)} BPM. "
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
    _root_name = key_root(key_name)
    next_key = KEYS_CYCLE[(KEYS_CYCLE.index(_root_name) + 1) % len(KEYS_CYCLE)] if _root_name in KEYS_CYCLE else "G"

    density = DensityTracker()
    budget = EffectBudget()
    prev_voice_count = 0

    print(f"\n=== SOLO: {display_key_spec(key_name)} ===", flush=True)

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
    learning = _learner.end_song(memory=_memory) or {}

    _post_song_self_quote({
        "arc_payoff": float(learning.get("arc_payoff", 0.0) or 0.0),
        "click_count": int(learning.get("click_count", 0) or 0),
        "mode": "solo",
        "arc_phase": str(learning.get("arc_phase", "") or ""),
        "mood": str(learning.get("mood", "") or ""),
        "song_id": str(song_num),
    })

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
        decision = plan_duet_response(ts)
        their_key = ts.get("suggested_key", current_key)
        their_rms = ts.get("rms", 0)
        their_note = ts.get("pitch_note")
        onset_rate = float(ts.get("onset_rate", 0.0) or 0.0)

        if their_key and their_key != current_key and their_key in KEY_ROOTS:
            print(f"  Key: {current_key} → {their_key}", flush=True)
            current_key = their_key

        if not decision.duet_active:
            break

        if not decision.may_play:
            if decision.speaker == "human":
                silence_count = 0
            else:
                silence_count += 1
            movement = "Silence Requested" if decision.phase == "silence" else "Listening"
            write_composer_state(
                current_key,
                "duet",
                movement,
                song_num,
                their_note,
                extras={"conversation": decision.to_dict()},
            )
            time.sleep(BT * max(1, decision.wait_beats or 1))
            continue

        silence_count += 1
        write_composer_state(
            current_key,
            "duet",
            "Responding",
            song_num,
            their_note,
            extras={"conversation": decision.to_dict()},
        )
        root = KEY_ROOTS.get(current_key, 130.8)
        key = make_key(root)

        if decision.policy == "imitation":
            pitch = float(ts.get("pitch_hz") or root * 2)
            register = suggest_response_register(pitch)
            dens = suggest_response_density(onset_rate)
            for freq, dur in suggest_response_phrase(pitch, register, dens):
                play_voice("pluck", freq, 0.10, 0.45)
                time.sleep(dur * BT)
            time.sleep(BT)
        elif decision.policy == "counterpoint":
            register = suggest_response_register(float(ts.get("pitch_hz") or root * 2))
            for freq, dur in suggest_response_phrase(root, register, "dense"):
                play_voice("pluck", freq / 2, 0.08, 0.35)
                time.sleep(dur * BT * 0.75)
            time.sleep(BT)
        else:
            # Accompaniment: quiet harmonic support after the human's phrase has ended.
            rd = random.choice([1, 4, 5])
            amp = 0.08 if their_rms > 0.05 else 0.12
            play_voice("pluck", key[rd] / 4, amp, 0.45)
            time.sleep(BT)
            play_voice("pluck", key[rd + 4] / 2, amp * 0.4, 0.3)
            time.sleep(BT)
            play_voice("pluck", key[rd + 4] / 2, amp * 0.35, 0.25)
            time.sleep(BT)

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
    seed_master_bus_node(c)
    time.sleep(0.1)

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
            if TRACKER_SOLO_ENABLED:
                current_key = tracker_solo_song(current_key, song_num)
            else:
                current_key = solo_song(current_key, song_num)

        time.sleep(random.uniform(4, 7))


if __name__ == "__main__":
    main()
