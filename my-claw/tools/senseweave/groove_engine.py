"""Groove engine -- rhythm craft beyond duration cells.

Maps groove identities (drift, procession, dance, etc.) to concrete timing
parameters: swing ratios, push/pull offsets, microtiming depth, polyrhythm
groupings, polymeter overlays, and body/room-pulse entrainment.  The engine
produces :class:`GrooveProfile` objects that the tracker can carry as step
metadata without breaking deterministic scheduling -- all offsets are
pre-computed, never random at playback.

Stdlib only.
"""
from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass, replace
from typing import Sequence


# ---------------------------------------------------------------------------
# Core data model
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class GrooveProfile:
    """Immutable groove descriptor for one section or phrase."""

    groove_type: str
    """Primary feel: straight, swing, shuffle, push, pull, lilt."""

    swing_ratio: float = 1.0
    """IOI ratio for swing pairs (1.0 = straight, 1.5 = triplet, 2.0 = dotted)."""

    push_pull_ms: float = 0.0
    """Global timing bias in milliseconds (negative = push/early, positive = pull/late)."""

    microtiming_depth: float = 0.0
    """0.0-1.0 amount of humanisation jitter applied per-note."""

    polyrhythm: tuple[int, int] | None = None
    """Superimposed pulse grouping, e.g. (3, 4) for 3-against-4."""

    polymeter: tuple[int, int] | None = None
    """Simultaneous meter pair, e.g. (3, 4) for 3/4 over 4/4."""

    entrainment_bpm: float | None = None
    """Body or room pulse BPM used for tempo entrainment."""

    breath_points: tuple[int, ...] = ()
    """Beat indices within a phrase where a micro-rest or lengthening occurs."""

    section_identity: str = ""
    """Human label for the groove personality of this section."""

    meter: str = "4/4"
    """Nominal meter carried as metadata; ``free`` denotes rubato/free time."""

    subdivision: str = "straight"
    """Subdivision feel: straight, swing, shuffle, dotted, triplet, rubato, polyrhythmic."""

    groove_timing: str = "grid"
    """Timing policy label such as grid, push, pull, rubato, or metric_modulation."""

    phrase_breath: str = "regular"
    """Phrase-level breath policy label carried alongside explicit breath points."""

    metric_modulation: str = ""
    """Optional ratio label for metric modulation, e.g. ``3:2``."""

    tempo_dependent_swing: bool = False
    """When True, swing ratio is computed from tempo per Friberg/Sundström."""

    syncopation_intensity: float = 0.0
    """0.0-1.0 probability that on-beat events get displaced to off-beats.
    0.0 = pure on-beat placement; 1.0 = nearly every long note splits into
    short+long off-beat pairs. Sample-applied per phrase by music_tracker."""

    lane_phase_offsets: tuple[int, ...] = ()
    """Per-lane starting-row offset hints (in tracker rows) keyed by lane order
    (bass, melody, counter, color, texture). Empty = all lanes start at row 0
    (current behavior). Non-empty offsets create polyrhythmic-cross feel by
    de-aligning lane entries within the bar."""


# ---------------------------------------------------------------------------
# Groove type vocabulary
# ---------------------------------------------------------------------------

GROOVE_TYPES: tuple[str, ...] = (
    "straight",
    "swing",
    "shuffle",
    "push",
    "pull",
    "lilt",
    "syncopated",
    "polyrhythmic_cross",
)

SUPPORTED_METERS: tuple[str, ...] = ("4/4", "3/4", "6/8", "5/4", "7/8", "free")

SUPPORTED_SUBDIVISIONS: tuple[str, ...] = (
    "straight",
    "swing",
    "shuffle",
    "dotted",
    "triplet",
    "rubato",
    "polyrhythmic",
)

# ---------------------------------------------------------------------------
# Groove identity -> GrooveProfile mapping tables
# ---------------------------------------------------------------------------

# Primary groove_identity values from piece_commission._groove_identity():
#   drift, ritual_ostinato, broken, procession, dance, pulse
# Plus groove_state values from composition_gate._GROOVE_ENERGY:
#   drone, static, sustain, pad, pulse, lift, drive
# Plus hook_engine._GROOVE_BY_FAMILY:
#   lyric, rolling, suspended, procession, study

_GROOVE_PROFILES: dict[str, GrooveProfile] = {
    # --- commission identities ---
    "drift": GrooveProfile(
        groove_type="pull",
        swing_ratio=1.0,
        push_pull_ms=8.0,
        microtiming_depth=0.35,
        breath_points=(3, 7),
        section_identity="drift",
        meter="free",
        subdivision="rubato",
        groove_timing="rubato",
        phrase_breath="open",
    ),
    "ritual_ostinato": GrooveProfile(
        groove_type="straight",
        swing_ratio=1.0,
        push_pull_ms=0.0,
        microtiming_depth=0.1,
        breath_points=(7,),
        section_identity="ritual_ostinato",
        meter="4/4",
        subdivision="straight",
    ),
    "broken": GrooveProfile(
        groove_type="shuffle",
        swing_ratio=1.6,
        push_pull_ms=-4.0,
        microtiming_depth=0.55,
        polyrhythm=(3, 4),
        breath_points=(2, 5),
        section_identity="broken",
        meter="7/8",
        subdivision="shuffle",
        groove_timing="push",
        phrase_breath="fractured",
        syncopation_intensity=0.6,
        lane_phase_offsets=(0, 2, 1, 3, 1),
    ),
    "procession": GrooveProfile(
        groove_type="push",
        swing_ratio=1.0,
        push_pull_ms=-10.0,
        microtiming_depth=0.2,
        breath_points=(3, 7),
        section_identity="procession",
        meter="3/4",
        subdivision="straight",
        groove_timing="push",
    ),
    "dance": GrooveProfile(
        groove_type="swing",
        swing_ratio=1.5,
        push_pull_ms=-5.0,
        microtiming_depth=0.4,
        breath_points=(3, 7),
        section_identity="dance",
        meter="4/4",
        subdivision="swing",
        groove_timing="swing",
        syncopation_intensity=0.4,
        lane_phase_offsets=(0, 1, 2, 0, 1),
    ),
    "pulse": GrooveProfile(
        groove_type="push",
        swing_ratio=1.0,
        push_pull_ms=-6.0,
        microtiming_depth=0.25,
        breath_points=(7,),
        section_identity="pulse",
        meter="4/4",
        subdivision="straight",
        groove_timing="push",
        syncopation_intensity=0.25,
        lane_phase_offsets=(0, 1, 0, 2, 0),
    ),
    # --- groove_state values ---
    "drone": GrooveProfile(
        groove_type="straight",
        swing_ratio=1.0,
        push_pull_ms=5.0,
        microtiming_depth=0.05,
        section_identity="drone",
    ),
    "static": GrooveProfile(
        groove_type="straight",
        swing_ratio=1.0,
        push_pull_ms=0.0,
        microtiming_depth=0.0,
        section_identity="static",
    ),
    "sustain": GrooveProfile(
        groove_type="pull",
        swing_ratio=1.0,
        push_pull_ms=6.0,
        microtiming_depth=0.08,
        section_identity="sustain",
    ),
    "pad": GrooveProfile(
        groove_type="pull",
        swing_ratio=1.0,
        push_pull_ms=4.0,
        microtiming_depth=0.06,
        section_identity="pad",
    ),
    "lift": GrooveProfile(
        groove_type="push",
        swing_ratio=1.15,
        push_pull_ms=-8.0,
        microtiming_depth=0.3,
        breath_points=(3, 7),
        section_identity="lift",
        syncopation_intensity=0.3,
        lane_phase_offsets=(0, 1, 0, 2, 1),
    ),
    "drive": GrooveProfile(
        groove_type="push",
        swing_ratio=1.2,
        push_pull_ms=-12.0,
        microtiming_depth=0.45,
        breath_points=(3, 5, 7),
        section_identity="drive",
        syncopation_intensity=0.5,
        lane_phase_offsets=(0, 2, 1, 3, 1),
    ),
    # --- hook groove families ---
    "lyric": GrooveProfile(
        groove_type="pull",
        swing_ratio=1.0,
        push_pull_ms=5.0,
        microtiming_depth=0.2,
        breath_points=(3, 7),
        section_identity="lyric",
    ),
    "rolling": GrooveProfile(
        groove_type="lilt",
        swing_ratio=1.25,
        push_pull_ms=0.0,
        microtiming_depth=0.3,
        breath_points=(2, 5),
        section_identity="rolling",
        meter="6/8",
        subdivision="triplet",
        groove_timing="lilt",
    ),
    "suspended": GrooveProfile(
        groove_type="pull",
        swing_ratio=1.0,
        push_pull_ms=10.0,
        microtiming_depth=0.15,
        section_identity="suspended",
    ),
    "study": GrooveProfile(
        groove_type="straight",
        swing_ratio=1.0,
        push_pull_ms=-3.0,
        microtiming_depth=0.5,
        polyrhythm=(5, 4),
        breath_points=(4,),
        section_identity="study",
        meter="5/4",
        subdivision="dotted",
        groove_timing="metric_modulation",
        phrase_breath="asymmetric",
        metric_modulation="5:4",
    ),
    # --- syncopated additions (2026-04-24) ---
    "syncopated": GrooveProfile(
        groove_type="syncopated",
        swing_ratio=1.0,
        push_pull_ms=-6.0,
        microtiming_depth=0.4,
        breath_points=(1, 5),
        section_identity="syncopated",
        meter="4/4",
        subdivision="straight",
        groove_timing="push",
        phrase_breath="off-beat",
        syncopation_intensity=0.65,
        lane_phase_offsets=(0, 1, 2, 3, 1),
    ),
    "polyrhythmic_cross": GrooveProfile(
        groove_type="polyrhythmic_cross",
        swing_ratio=1.0,
        push_pull_ms=0.0,
        microtiming_depth=0.35,
        polyrhythm=(3, 4),
        breath_points=(2, 6),
        section_identity="polyrhythmic_cross",
        meter="4/4",
        subdivision="polyrhythmic",
        groove_timing="grid",
        phrase_breath="staggered",
        syncopation_intensity=0.45,
        lane_phase_offsets=(0, 2, 1, 3, 0),
    ),
}

_DEFAULT_PROFILE = GrooveProfile(
    groove_type="straight",
    swing_ratio=1.0,
    push_pull_ms=0.0,
    microtiming_depth=0.15,
    section_identity="default",
    meter="4/4",
    subdivision="straight",
    groove_timing="grid",
    phrase_breath="regular",
)


# ---------------------------------------------------------------------------
# Public API: profile lookup
# ---------------------------------------------------------------------------


def groove_for_section(
    *,
    groove_state: str = "",
    groove_identity: str = "",
    groove_family: str = "",
    entrainment_bpm: float | None = None,
) -> GrooveProfile:
    """Resolve a :class:`GrooveProfile` from available groove descriptors.

    Priority: *groove_identity* (commission) > *groove_state* (section) >
    *groove_family* (hook engine).  If none match, return a neutral default.
    """

    for key in (groove_identity, groove_state, groove_family):
        profile = _GROOVE_PROFILES.get(key)
        if profile is not None:
            if entrainment_bpm is not None and entrainment_bpm > 0:
                return replace(profile, entrainment_bpm=entrainment_bpm)
            return profile

    return replace(
        _DEFAULT_PROFILE,
        entrainment_bpm=entrainment_bpm if entrainment_bpm and entrainment_bpm > 0 else None,
    )


# ---------------------------------------------------------------------------
# IOI (inter-onset interval) computation
# ---------------------------------------------------------------------------


def swing_ioi_pair(base_ioi: float, swing_ratio: float) -> tuple[float, float]:
    """Split one beat into a swing pair preserving total duration.

    Returns ``(long, short)`` where ``long / short == swing_ratio`` and
    ``long + short == 2 * base_ioi``.

    >>> swing_ioi_pair(0.5, 1.5)  # triplet swing on eighth notes
    (0.6, 0.4)
    """

    ratio = max(1.0, float(swing_ratio))
    total = 2.0 * float(base_ioi)
    long = total * ratio / (ratio + 1.0)
    short = total - long
    return (round(long, 6), round(short, 6))


def swing_offset_for_step(step_index: int, swing_ratio: float) -> float:
    """Return the signed timing offset for one step of a swing pair.

    Even steps get positive offset (long), odd steps get negative (short).
    Offset is relative to a normalised beat of 1.0.
    """

    long, short = swing_ioi_pair(1.0, swing_ratio)
    return round(long - 1.0, 6) if step_index % 2 == 0 else round(short - 1.0, 6)


def apply_groove_to_ioi(
    ioi_beats: float,
    *,
    step_index: int,
    profile: GrooveProfile,
    tempo_bpm: float = 120.0,
    role: str = "",
) -> float:
    """Return the groove-adjusted IOI for one note.

    Applies swing ratio on even/odd pairs and push/pull offset.
    When *profile.tempo_dependent_swing* is True, the ratio follows
    the Friberg/Sundström tempo curve with optional role override.
    Result is in beats (not seconds).
    """

    adjusted = float(ioi_beats)

    # --- swing / shuffle ---
    if adjusted > 0:
        if profile.tempo_dependent_swing:
            ratio = tempo_swing_ratio(
                tempo_bpm, role=role, max_ratio=_FRIBERG_MAX_RATIO,
            )
        else:
            ratio = profile.swing_ratio

        if ratio > 1.0:
            long, short = swing_ioi_pair(adjusted, ratio)
            adjusted = long if step_index % 2 == 0 else short

    # --- push / pull (ms -> beats) ---
    if profile.push_pull_ms != 0.0 and tempo_bpm > 0:
        beat_offset = (profile.push_pull_ms / 1000.0) * (tempo_bpm / 60.0)
        adjusted = max(0.0625, adjusted + beat_offset)

    return round(adjusted, 6)


# ---------------------------------------------------------------------------
# Tempo-dependent swing (Friberg & Sundström 2002)
# ---------------------------------------------------------------------------

_FRIBERG_SHORT_NOTE_MS: float = 100.0
_FRIBERG_MAX_RATIO: float = 3.5
_BENADON_BUR_RANGE: tuple[float, float] = (1.2, 1.7)

_ROLE_SWING_STYLE: dict[str, str] = {
    "ride": "ride",
    "cymbal": "ride",
    "hi-hat": "ride",
    "melody": "benadon",
    "solo": "benadon",
    "lead": "benadon",
}


def friberg_swing_ratio(
    tempo_bpm: float,
    *,
    short_note_ms: float = _FRIBERG_SHORT_NOTE_MS,
    max_ratio: float = _FRIBERG_MAX_RATIO,
) -> float:
    """Swing ratio from tempo per Friberg & Sundström (2002).

    Keeps short-note duration near *short_note_ms*, yielding high ratios at
    slow tempi (~3.5:1) declining toward 1:1 at fast tempi.
    """
    if tempo_bpm <= 0:
        return max_ratio
    beat_ms = 60_000.0 / tempo_bpm
    if beat_ms <= short_note_ms:
        return 1.0
    ratio = (beat_ms - short_note_ms) / short_note_ms
    return round(max(1.0, min(max_ratio, ratio)), 6)


def friberg_short_note_ms(tempo_bpm: float, swing_ratio: float) -> float:
    """Actual short-note duration in ms for a given ratio and tempo."""
    if tempo_bpm <= 0 or swing_ratio < 1.0:
        return 0.0
    beat_ms = 60_000.0 / tempo_bpm
    return round(beat_ms / (swing_ratio + 1.0), 3)


def tempo_swing_ratio(
    tempo_bpm: float,
    *,
    role: str = "",
    short_note_ms: float = _FRIBERG_SHORT_NOTE_MS,
    max_ratio: float = _FRIBERG_MAX_RATIO,
) -> float:
    """Tempo-dependent swing ratio with optional role-specific override.

    Cymbal/ride roles get a wider ratio; soloists are clamped to
    Benadon BUR range (1.2--1.7).
    """
    base = friberg_swing_ratio(
        tempo_bpm, short_note_ms=short_note_ms, max_ratio=max_ratio,
    )
    style = _ROLE_SWING_STYLE.get(role, "")
    if style == "ride":
        return round(min(max_ratio, base * 1.15), 6)
    if style == "benadon":
        return round(
            max(_BENADON_BUR_RANGE[0], min(_BENADON_BUR_RANGE[1], base)), 6,
        )
    return base


# ---------------------------------------------------------------------------
# Microtiming
# ---------------------------------------------------------------------------


def microtiming_offset_ms(
    *,
    step_index: int,
    profile: GrooveProfile,
    seed: int = 0,
) -> float:
    """Deterministic per-note timing jitter in milliseconds.

    Uses a hash of (*step_index*, *seed*) so the result is repeatable but
    perceptually irregular.  Range scales with ``profile.microtiming_depth``:
    depth 1.0 gives up to +/-15 ms.
    """

    if profile.microtiming_depth <= 0:
        return 0.0

    payload = f"{step_index}|{seed}".encode()
    digest = hashlib.sha256(payload).digest()
    raw = int.from_bytes(digest[:4], "big")
    normalised = (raw / 0xFFFFFFFF) * 2.0 - 1.0  # [-1, 1]
    max_ms = 15.0 * profile.microtiming_depth
    return round(normalised * max_ms, 3)


# ---------------------------------------------------------------------------
# Breath points
# ---------------------------------------------------------------------------


def breath_points_for_phrase(
    phrase_length_beats: int,
    profile: GrooveProfile,
) -> tuple[int, ...]:
    """Return beat indices where the phrase should breathe.

    Uses the profile's static breath_points filtered to the phrase length,
    or generates default points at 1/4 and 3/4 if none are specified.
    """

    length = max(1, int(phrase_length_beats))

    if profile.breath_points:
        return tuple(bp for bp in profile.breath_points if 0 <= bp < length)

    # Default: breathe at quarter and three-quarter marks
    if length >= 8:
        return (length // 4, 3 * length // 4)
    if length >= 4:
        return (length // 2,)
    return ()


def is_breath_beat(beat_index: int, breath_points: Sequence[int]) -> bool:
    """Check whether *beat_index* falls on a breath point."""
    return int(beat_index) in breath_points


# ---------------------------------------------------------------------------
# Polyrhythm helpers
# ---------------------------------------------------------------------------


def polyrhythm_accent_mask(
    length: int,
    grouping: tuple[int, int],
) -> tuple[bool, ...]:
    """Build an accent mask for a polyrhythm overlay.

    For grouping ``(a, b)`` over *length* steps, accents land where either
    the *a*-grid or *b*-grid fires.

    >>> polyrhythm_accent_mask(12, (3, 4))
    (True, False, False, True, True, False, True, False, True, True, False, False)
    """

    a, b = max(1, grouping[0]), max(1, grouping[1])
    mask: list[bool] = []
    for i in range(length):
        mask.append(i % a == 0 or i % b == 0)
    return tuple(mask)


def polyrhythm_cycle_length(grouping: tuple[int, int]) -> int:
    """Return the LCM of *grouping*, i.e. steps before the pattern repeats."""

    a, b = max(1, grouping[0]), max(1, grouping[1])
    return abs(a * b) // math.gcd(a, b)


# ---------------------------------------------------------------------------
# Polymeter helpers
# ---------------------------------------------------------------------------


def polymeter_phase_offset(
    beat_index: int,
    meter_pair: tuple[int, int],
) -> float:
    """Compute the phase offset (0.0-1.0) between two simultaneous meters.

    Useful for voices that need to drift in/out of alignment.
    """

    a, b = max(1, meter_pair[0]), max(1, meter_pair[1])
    lcm = abs(a * b) // math.gcd(a, b)
    pos = beat_index % lcm
    phase_a = (pos % a) / a
    phase_b = (pos % b) / b
    return round(abs(phase_a - phase_b), 6)


# ---------------------------------------------------------------------------
# Entrainment
# ---------------------------------------------------------------------------


def entrainment_tempo_nudge(
    current_bpm: float,
    entrainment_bpm: float | None,
    *,
    strength: float = 0.15,
) -> float:
    """Nudge *current_bpm* toward an entrainment pulse.

    Returns adjusted BPM. *strength* 0-1 controls how strongly the tempo
    is pulled (0 = no change, 1 = snap to entrainment).
    """

    if entrainment_bpm is None or entrainment_bpm <= 0:
        return float(current_bpm)

    target = float(entrainment_bpm)
    current = float(current_bpm)
    strength = max(0.0, min(1.0, strength))

    # Find nearest harmonic of entrainment that's close to current tempo
    best_target = target
    best_distance = abs(current - target)
    for multiplier in (0.5, 1.0, 2.0, 3.0, 4.0):
        candidate = target * multiplier
        distance = abs(current - candidate)
        if distance < best_distance:
            best_distance = distance
            best_target = candidate

    return round(current + (best_target - current) * strength, 3)


# ---------------------------------------------------------------------------
# Meter and subdivision helpers
# ---------------------------------------------------------------------------


def meter_rows_per_bar(meter: str, rows_per_beat: int = 4) -> int:
    """Return the number of tracker rows in one bar for *meter*.

    Quarter-note meters (X/4) use *rows_per_beat* per beat.
    Eighth-note meters (X/8) use half *rows_per_beat* per beat.
    ``"free"`` defaults to 4/4.
    """

    if meter == "free":
        return 4 * rows_per_beat

    parts = meter.split("/")
    if len(parts) != 2:
        return 4 * rows_per_beat

    try:
        numerator = int(parts[0])
        denominator = int(parts[1])
    except ValueError:
        return 4 * rows_per_beat

    if denominator == 8:
        return numerator * max(1, rows_per_beat // 2)
    return numerator * rows_per_beat


_SUBDIVISION_DEFAULT_RATIOS: dict[str, float] = {
    "straight": 1.0,
    "swing": 1.5,
    "shuffle": 2.0,
    "dotted": 3.0,
    "triplet": 1.5,
    "rubato": 1.0,
    "polyrhythmic": 1.0,
}


def ioi_ratios_for_subdivision(
    subdivision: str,
    swing_ratio: float | None = None,
) -> tuple[float, float]:
    """Return a ``(long, short)`` IOI pair for a subdivision feel.

    Uses *swing_ratio* when given, otherwise falls back to the canonical
    ratio for the named subdivision.  Sum of the pair is always 2.0.
    """

    ratio = swing_ratio if swing_ratio is not None else _SUBDIVISION_DEFAULT_RATIOS.get(subdivision, 1.0)
    return swing_ioi_pair(1.0, max(1.0, ratio))


_PHASE_METER_POLICIES: dict[str, GrooveProfile] = {
    "Divination": GrooveProfile(
        groove_type="pull",
        meter="free",
        subdivision="rubato",
        groove_timing="rubato",
        phrase_breath="open",
    ),
    "Emergence": GrooveProfile(
        groove_type="straight",
        meter="4/4",
        subdivision="straight",
        groove_timing="grid",
    ),
    "Theme": GrooveProfile(
        groove_type="straight",
        meter="4/4",
        subdivision="straight",
        groove_timing="grid",
    ),
    "Development": GrooveProfile(
        groove_type="push",
        meter="4/4",
        subdivision="swing",
        groove_timing="push",
        phrase_breath="regular",
    ),
    "Convergence": GrooveProfile(
        groove_type="straight",
        meter="7/8",
        subdivision="polyrhythmic",
        groove_timing="metric_modulation",
        polyrhythm=(3, 4),
        metric_modulation="7:8",
        phrase_breath="asymmetric",
    ),
    "Recap": GrooveProfile(
        groove_type="straight",
        meter="4/4",
        subdivision="straight",
        groove_timing="grid",
        phrase_breath="regular",
    ),
    "Resolution": GrooveProfile(
        groove_type="pull",
        meter="4/4",
        subdivision="straight",
        groove_timing="pull",
        phrase_breath="open",
    ),
}


def meter_policy_for_phase(phase_name: str) -> GrooveProfile:
    """Return a :class:`GrooveProfile` encoding the meter policy for *phase_name*."""

    return _PHASE_METER_POLICIES.get(phase_name, _DEFAULT_PROFILE)


# ---------------------------------------------------------------------------
# Step metadata stamping
# ---------------------------------------------------------------------------


def groove_metadata_for_step(
    *,
    step_index: int,
    profile: GrooveProfile,
    tempo_bpm: float = 120.0,
    phrase_length_beats: int = 8,
    seed: int = 0,
    role: str = "",
) -> dict[str, str]:
    """Build metadata dict entries for one :class:`TrackerStep`.

    All values are strings to match the existing metadata convention.
    """

    meta: dict[str, str] = {}
    meta["groove_type"] = profile.groove_type
    meta["groove_section_identity"] = profile.section_identity or "default"

    # Swing IOI ratio -- use Friberg curve when tempo-dependent
    if profile.tempo_dependent_swing:
        effective_ratio = tempo_swing_ratio(
            tempo_bpm, role=role, max_ratio=_FRIBERG_MAX_RATIO,
        )
    else:
        effective_ratio = profile.swing_ratio

    if effective_ratio != 1.0:
        meta["groove_swing_ratio"] = f"{effective_ratio:.3f}"
        position = "long" if step_index % 2 == 0 else "short"
        meta["groove_swing_position"] = position
    if profile.tempo_dependent_swing:
        meta["groove_tempo_swing"] = "true"

    # Push/pull
    if profile.push_pull_ms != 0.0:
        meta["groove_push_pull_ms"] = f"{profile.push_pull_ms:.1f}"

    # Microtiming
    offset = microtiming_offset_ms(step_index=step_index, profile=profile, seed=seed)
    if offset != 0.0:
        meta["groove_microtiming_ms"] = f"{offset:.3f}"

    # Breath
    bps = breath_points_for_phrase(phrase_length_beats, profile)
    if is_breath_beat(step_index, bps):
        meta["groove_breath"] = "true"

    # Polyrhythm
    if profile.polyrhythm is not None:
        mask = polyrhythm_accent_mask(max(step_index + 1, 1), profile.polyrhythm)
        if step_index < len(mask) and mask[step_index]:
            meta["groove_polyrhythm_accent"] = "true"
        meta["groove_polyrhythm"] = f"{profile.polyrhythm[0]}:{profile.polyrhythm[1]}"

    # Polymeter
    if profile.polymeter is not None:
        phase = polymeter_phase_offset(step_index, profile.polymeter)
        meta["groove_polymeter"] = f"{profile.polymeter[0]}:{profile.polymeter[1]}"
        meta["groove_polymeter_phase"] = f"{phase:.4f}"

    # Entrainment
    if profile.entrainment_bpm is not None and profile.entrainment_bpm > 0:
        meta["groove_entrainment_bpm"] = f"{profile.entrainment_bpm:.1f}"

    # Meter / subdivision / timing policy
    meta["groove_meter"] = profile.meter
    meta["groove_subdivision"] = profile.subdivision
    meta["groove_timing"] = profile.groove_timing
    meta["groove_phrase_breath"] = profile.phrase_breath
    if profile.metric_modulation:
        meta["groove_metric_modulation"] = profile.metric_modulation

    return meta
