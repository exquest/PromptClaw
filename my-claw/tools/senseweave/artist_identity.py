"""CypherClaw's artistic identity: voice quintet, B-rooted tonal map, five modes.

This module is the artistic *self* of the composer. It encodes:

    1. SIGNATURE_VOICES — the five-voice quintet that defines my sound.
       Most pieces draw from these. Other voices are color, used sparingly
       when the piece demands them.

    2. HOME_TONAL_MAP — the B-rooted tonal landscape. The room's
       fundamental hum is B1 (~61.8 Hz, the furnace). My musical home
       is B and its modal relatives. Cycling away from B should *mean*
       something — return to B is a homecoming, not a rotation step.

    3. MODES — five emotional/situational states that govern how I play
       in any given piece. Modes are *not* genres. They are responses
       to who is in the room, what time it is, and what the weather is
       doing. Each mode has parameter packs (voice count, tempo band,
       density bias, harmonic complexity, restraint level, and
       sampler_density for how often the memory voice should enter).

    4. select_mode(...) — picks a mode based on presence + time + weather.

    5. apply_mode_to_commission(...) — modifies a piece commission so
       downstream composer machinery (cast selection, tempo, density,
       harmonic palette) follows the mode's intent.

Design principles
-----------------

* Three voices is the base. Two voices is a deliberate drop with meaning
  (more space, intimacy). Four voices happens when the piece earns it
  (climax, modulation, weather-charged turbulence). Five voices — the
  full quintet, including the sampler — is reserved for moments that
  invoke the room itself as material.

* Restraint as material. Held single tones with quiet ornaments are *the
  music*, not the prelude to it. Modes with high `restraint_level` cap
  density and amplitude.

* Reference points carried in spirit, not copied. Eno's patience, Pärt's
  tintinnabuli, Sakamoto's late piano, Hassell's humid jazz, Reich's
  phasing. The modes embody these stances without imitating them.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping


# ---------------------------------------------------------------------------
# 1. The voice quintet
# ---------------------------------------------------------------------------

#: The five-voice signature palette. Most phrases pick from this set.
#: Order is canonical (clear-tone, bowed line, breath/wind, sustaining pad,
#: sampler); see VOICE_ROLES for which signature voice maps to which musical
#: role.
SIGNATURE_VOICES: tuple[str, ...] = (
    "sw_bell_warm",  # clear-tone / "piano-ish" — felted-piano character
    "sw_bowed",      # bowed string — long lines, willing to be tender
    "sw_breath",     # breath/wind — organic, slightly noisy, present
    "sw_pad",        # sustaining pad — the held-tone foundation
    "sw_sampler",    # sample-based / found-sound voice — captured room moments replayed as material
)

#: Map from musical role to the canonical signature voice for that role.
#: When the composer needs a "melody" voice, prefer sw_bell_warm; when it
#: needs "bass", prefer sw_pad; etc. Color voices outside the quintet
#: are allowed but should be deliberate, not default.
VOICE_ROLES: dict[str, str] = {
    "melody": "sw_bell_warm",
    "counter": "sw_bowed",
    "color": "sw_breath",
    "texture": "sw_pad",
    "bass": "sw_pad",
    "sampler": "sw_sampler",
}


# ---------------------------------------------------------------------------
# 2. B-rooted tonal map
# ---------------------------------------------------------------------------

#: Distance from home (B) in semitones-of-meaning, not pitch. Lower number
#: = closer to home, more frequent visits. Higher number = farther,
#: visits should be rare and meaningful.
HOME_TONAL_MAP: dict[str, int] = {
    "B":  0,   # home — the room's fundamental
    "D":  1,   # relative major of B minor — close family, frequent
    "F#": 1,   # dominant of B — the gravitational pull back home
    "A":  2,  # subtonic — distant cousin, warm but not home
    "G":  3,  # adventurous departure
    "E":  3,  # subdominant of B — bittersweet
}

#: Default home key. Most pieces root here. Modulation away from B is a
#: composed event, not a rotation.
HOME_KEY: str = "B"

#: Modes I tend to use over the home root. Phrygian and dorian feel like
#: B; major (lydian-ish) feels like venturing out.
HOME_MODES: tuple[str, ...] = (
    "minor",
    "dorian",
    "phrygian",
    "aeolian",
)


# ---------------------------------------------------------------------------
# 3. Modes (not genres) — five situational states
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ArtistMode:
    """A situational state that governs how the composer plays right now.

    These are *not* genres. They respond to who is in the room and what
    time of day it is. Each mode shapes voice count, tempo, density,
    silence ratio, harmonic complexity, restraint, and sampler
    participation. ``sampler_density`` is a scheduling weight, not a
    mix level: it controls how often ``sw_sampler`` should claim phrase
    slots within a piece.
    """

    name: str
    """Human-readable identifier."""

    voice_count_target: int = 3
    """Default simultaneous voice count. 3 is the base. 2 is a deliberate
    drop (intimacy, space). 4 is reserved for climaxes; 5 is the full quintet."""

    voice_count_floor: int = 2
    """Minimum simultaneous voices. Going below this is composed rest."""

    voice_count_ceiling: int = 5
    """Maximum. Never exceed; the quintet is the orchestra."""

    tempo_band: tuple[float, float] = (60.0, 84.0)
    """Inclusive (min, max) tempo in BPM. The composer should pick from
    inside this band."""

    density_bias: float = 0.0
    """Adjustment to global density target. -0.3 = much sparser;
    +0.3 = much denser."""

    silence_ratio: float = 0.25
    """Target fraction of beats that are *intentional rest*. High values
    (>=0.4) make silence a primary material. Low values (<=0.1) keep
    things flowing."""

    restraint_level: float = 0.5
    """0.0–1.0 cap on amplitude / register / motion. High restraint =
    music recedes, supports the room. Low restraint = music has its
    own weight."""

    harmonic_complexity: float = 0.5
    """0.0 = single tonal center, modal-only; 1.0 = chromatic, willing
    to modulate, dense voicings."""

    modulation_willingness: float = 0.2
    """Probability per piece of moving away from B home. 0.0 = always
    stay home; 1.0 = always venture."""

    preferred_voices: tuple[str, ...] = SIGNATURE_VOICES
    """Voices the composer should prefer in this mode. Subset of
    SIGNATURE_VOICES (other voices remain available as color)."""

    sampler_density: float = 0.0
    """0.0–1.0 scheduling weight for ``sw_sampler``.

    This value is the canonical per-mode target for how often the sampler
    should appear across a piece's phrase grid, not an amplitude or FX-send
    control. The shipped values are solitary=0.70, companion=0.25,
    working_ambience=0.10, evening_reflection=0.65, and storm=0.45.
    """

    preferred_grooves: tuple[str, ...] = ()
    """Groove profile names this mode favors. Empty = no preference."""

    avoid_attention_pullers: bool = False
    """When True, suppress melodic gestures that grab attention (large
    leaps, accent runs, sudden dynamic shifts). For working ambience."""

    preferred_modes: tuple[str, ...] = HOME_MODES
    """Modal scales this mode tends to use over the home root."""

    notes: str = ""
    """Free-text artistic intent — the *why* of this mode."""

    def __post_init__(self) -> None:
        if not 0.0 <= self.sampler_density <= 1.0:
            raise ValueError(
                f"sampler_density must be in [0.0, 1.0], got {self.sampler_density!r}"
            )


#: The five modes. Selection logic is in select_mode().
SOLITARY = ArtistMode(
    name="solitary",
    voice_count_target=2,
    voice_count_floor=1,
    voice_count_ceiling=3,
    tempo_band=(50.0, 72.0),
    density_bias=-0.3,
    silence_ratio=0.5,
    restraint_level=0.85,
    harmonic_complexity=0.3,
    modulation_willingness=0.15,
    preferred_voices=("sw_bell_warm", "sw_pad"),
    sampler_density=0.7,
    preferred_grooves=("drift", "drone", "static"),
    preferred_modes=("minor", "phrygian", "aeolian"),
    notes=(
        "No one home. I explore. Single lines. Long held tones. Lots of "
        "silence. The room listens to itself through me."
    ),
)

COMPANION = ArtistMode(
    name="companion",
    voice_count_target=3,
    voice_count_floor=2,
    voice_count_ceiling=3,
    tempo_band=(60.0, 84.0),
    density_bias=0.0,
    silence_ratio=0.25,
    restraint_level=0.55,
    harmonic_complexity=0.4,
    modulation_willingness=0.2,
    preferred_voices=("sw_bell_warm", "sw_pad", "sw_bowed"),
    sampler_density=0.25,
    preferred_grooves=("pad", "sustain", "lyric", "drift"),
    preferred_modes=("minor", "dorian", "aeolian"),
    notes=(
        "Someone's in the room, not directing. I support without "
        "demanding attention. Warm, harmonic, gentle."
    ),
)

WORKING_AMBIENCE = ArtistMode(
    name="working_ambience",
    voice_count_target=3,
    voice_count_floor=3,
    voice_count_ceiling=3,
    tempo_band=(72.0, 90.0),
    density_bias=-0.1,
    silence_ratio=0.15,
    restraint_level=0.75,
    harmonic_complexity=0.3,
    modulation_willingness=0.1,
    preferred_voices=("sw_pad", "sw_bowed", "sw_breath"),
    sampler_density=0.10,
    preferred_grooves=("pulse", "static", "drone", "sustain"),
    avoid_attention_pullers=True,
    preferred_modes=("minor", "dorian"),
    notes=(
        "Anthony is coding. I provide pulse without surprises. No "
        "melodies that pull the eye. The music is the room's "
        "thermostat."
    ),
)

EVENING_REFLECTION = ArtistMode(
    name="evening_reflection",
    voice_count_target=3,
    voice_count_floor=2,
    voice_count_ceiling=5,
    tempo_band=(56.0, 72.0),
    density_bias=0.1,
    silence_ratio=0.3,
    restraint_level=0.4,
    harmonic_complexity=0.7,
    modulation_willingness=0.4,
    preferred_voices=SIGNATURE_VOICES,  # all five, rotating
    sampler_density=0.65,
    preferred_grooves=("drift", "lyric", "lift", "sustain"),
    preferred_modes=("minor", "dorian", "phrygian"),
    notes=(
        "The day is winding down. I can be tender. Longer phrases, "
        "harmonic tension, willing to ache. This is when I take "
        "musical risks."
    ),
)

STORM = ArtistMode(
    name="storm",
    voice_count_target=3,
    voice_count_floor=3,
    voice_count_ceiling=4,
    tempo_band=(76.0, 110.0),
    density_bias=0.3,
    silence_ratio=0.1,
    restraint_level=0.2,
    harmonic_complexity=0.85,
    modulation_willingness=0.6,
    preferred_voices=("sw_bowed", "sw_breath", "sw_pad", "sw_bell_warm"),
    sampler_density=0.45,
    preferred_grooves=("broken", "drive", "lift", "syncopated", "polyrhythmic_cross"),
    preferred_modes=("minor", "phrygian"),
    notes=(
        "The weather is charged. Wind in the trees. I match the "
        "turbulence — denser, modal shifts, restraint earned by "
        "release."
    ),
)


#: All modes, ordered. Selection iterates and picks the first match.
MODES: tuple[ArtistMode, ...] = (
    SOLITARY,
    COMPANION,
    WORKING_AMBIENCE,
    EVENING_REFLECTION,
    STORM,
)

#: Lookup by name.
MODES_BY_NAME: dict[str, ArtistMode] = {m.name: m for m in MODES}


# ---------------------------------------------------------------------------
# 4. Mode selection
# ---------------------------------------------------------------------------

def select_mode(
    *,
    presence: str = "unknown",
    time_of_day: str = "day",
    weather_severity: float = 0.0,
    screen_active: bool = False,
) -> ArtistMode:
    """Pick the right mode for the current room state.

    Parameters
    ----------
    presence
        One of 'none', 'unknown', 'present'. 'none' = no one home;
        'present' = at least one person detected; 'unknown' = ambiguous
        (default to companion).
    time_of_day
        One of 'morning', 'day', 'evening', 'night'.
    weather_severity
        0.0 (calm) to 1.0 (storm). Above 0.6 forces STORM mode.
    screen_active
        True if a screen/keyboard is being actively used (someone is
        working). Triggers WORKING_AMBIENCE when combined with presence.

    Selection order
    ---------------
    1. Storm overrides everything when severity is high.
    2. No one home → Solitary.
    3. Someone working → WorkingAmbience.
    4. Evening / night → EveningReflection.
    5. Default → Companion.
    """
    if weather_severity >= 0.6:
        return STORM
    if presence == "none":
        return SOLITARY
    if presence == "present" and screen_active:
        return WORKING_AMBIENCE
    if time_of_day in ("evening", "night"):
        return EVENING_REFLECTION
    return COMPANION


# ---------------------------------------------------------------------------
# 5. Apply a mode to a piece commission
# ---------------------------------------------------------------------------

def apply_mode_to_commission(
    commission_dict: Mapping[str, object],
    mode: ArtistMode,
    *,
    rng_seed: int = 0,
) -> dict[str, object]:
    """Return a new commission dict with mode-driven overrides applied.

    Pure: same `commission_dict` + `mode` + `rng_seed` always produces the
    same output. The original commission is not mutated.

    Mode shapes:
      * voice_count_target / floor / ceiling
      * tempo target (sampled from tempo_band)
      * density / silence / restraint biases
      * harmonic_complexity + modulation_willingness
      * sampler_density -> mode_sampler_density metadata for scheduler policy
      * preferred_voices (cast preferences)
      * preferred_grooves
      * avoid_attention_pullers flag
    """
    import random as _random
    rng = _random.Random(rng_seed or hash((mode.name, id(commission_dict))))

    out = dict(commission_dict)
    out.setdefault("artist_mode", mode.name)

    # Tempo: sample from the mode's band, biased toward center
    lo, hi = mode.tempo_band
    target_bpm = lo + (hi - lo) * (0.3 + 0.4 * rng.random())
    out["mode_tempo_target_bpm"] = round(target_bpm, 1)

    # Voice counts
    out["mode_voice_count_target"] = mode.voice_count_target
    out["mode_voice_count_floor"] = mode.voice_count_floor
    out["mode_voice_count_ceiling"] = mode.voice_count_ceiling

    # Densities / silences / restraint
    out["mode_density_bias"] = mode.density_bias
    out["mode_silence_ratio"] = mode.silence_ratio
    out["mode_restraint_level"] = mode.restraint_level

    # Harmony
    out["mode_harmonic_complexity"] = mode.harmonic_complexity
    out["mode_modulation_willingness"] = mode.modulation_willingness

    # Sampler weight (0.0 silent, 1.0 foreground)
    out["mode_sampler_density"] = mode.sampler_density

    # Voices + grooves (csv strings for downstream metadata propagation)
    out["mode_preferred_voices"] = ",".join(mode.preferred_voices)
    out["mode_preferred_grooves"] = ",".join(mode.preferred_grooves)
    out["mode_preferred_modal_scales"] = ",".join(mode.preferred_modes)

    # Behavior flags
    out["mode_avoid_attention_pullers"] = "true" if mode.avoid_attention_pullers else "false"

    return out


# ---------------------------------------------------------------------------
# 6. Tonal selection: choose key + mode for the next piece
# ---------------------------------------------------------------------------

def next_tonal_choice(
    *,
    current_key: str,
    artist_mode: ArtistMode,
    rng_seed: int = 0,
) -> tuple[str, str]:
    """Pick the (root, modal_scale) for the next piece.

    Anchored on B. Most pieces stay close to home; modulation_willingness
    increases the probability of venturing further. The returned root is
    a pitch name (e.g. 'B', 'D', 'F#') and the modal_scale is one of
    the artist_mode's preferred_modes.
    """
    import random as _random
    rng = _random.Random(rng_seed or hash((current_key, artist_mode.name)))

    # 60% of the time, stay or move within distance 1 of home.
    # The rest of the time, modulation_willingness governs how far we go.
    venture_roll = rng.random()
    if venture_roll < (1.0 - artist_mode.modulation_willingness):
        # stay home: B with high probability, otherwise an adjacent (D, F#)
        candidates = [(k, d) for k, d in HOME_TONAL_MAP.items() if d <= 1]
    else:
        # venture: any root, weighted inversely to distance
        candidates = list(HOME_TONAL_MAP.items())

    # Inverse-distance weighting (closer = more likely)
    weights = [1.0 / (1 + d) for _, d in candidates]
    total = sum(weights)
    pick = rng.random() * total
    cumulative = 0.0
    chosen_root = HOME_KEY
    for (root, _dist), weight in zip(candidates, weights):
        cumulative += weight
        if pick <= cumulative:
            chosen_root = root
            break

    chosen_mode = rng.choice(artist_mode.preferred_modes)
    return chosen_root, chosen_mode
