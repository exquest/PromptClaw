"""Faithful MIDI scene mapping for CypherClaw intake manifests."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import Enum
import math

try:
    from cypherclaw.midi_loader import FaithfulMidiEvent
    from cypherclaw.space_reverb import (
        SPACE_PROFILE_SOURCE,
        VOICE_REVERB_PROFILES,
        VoiceReverbProfile,
    )
except ImportError:
    from midi_loader import FaithfulMidiEvent  # type: ignore[no-redef,import-not-found]
    from space_reverb import (  # type: ignore[no-redef,import-not-found]
        SPACE_PROFILE_SOURCE,
        VOICE_REVERB_PROFILES,
        VoiceReverbProfile,
    )


DEFAULT_SCENE_NAME = "Faithful MIDI Import"
DEFAULT_KEY = "C"
DEFAULT_TEMPO_BPM = 120.0
DEFAULT_ROWS_PER_BEAT = 4
DEFAULT_TICKS_PER_BEAT = 480
DEFAULT_TONAL_CENTER_MIDI = 60
DEFAULT_TONAL_CENTER_HZ = 261.625565
FAITHFUL_SCENE_TRANSFORM = "midi_whole_file_scene"

TUNING_12_TET = "twelve_tet"
TUNING_JUST_5_LIMIT = "just_intonation_5_limit"
TUNING_SLENDRO = "gamelan_slendro"

# Allowed morph curve shapes for tuning-system morphs in scene metadata
# (CC-045 in `prd-cypherclaw-v2-2026-05-22.md`).
MORPH_CURVE_LINEAR = "linear"
MORPH_CURVE_EASE_IN = "ease_in"
MORPH_CURVE_EASE_OUT = "ease_out"
MORPH_CURVE_SIGMOID = "sigmoid"
SUPPORTED_MORPH_CURVES: tuple[str, ...] = (
    MORPH_CURVE_LINEAR,
    MORPH_CURVE_EASE_IN,
    MORPH_CURVE_EASE_OUT,
    MORPH_CURVE_SIGMOID,
)


class MoodMode(str, Enum):
    """Canonical scene mood modes for CypherClaw space selection."""

    MATCHED = "matched"
    EXPRESSIVE = "expressive"
    HOUSE_BOUND = "house-bound"


SUPPORTED_MOOD_MODES: tuple[str, ...] = tuple(mode.value for mode in MoodMode)

REQUIRED_TUNING_METADATA_FIELDS: tuple[str, ...] = (
    "tuning_system_name",
    "tuning_morph_target_name",
    "tuning_morph_curve",
)

REQUIRED_MOOD_METADATA_FIELDS: tuple[str, ...] = ("mood_mode",)

_STILL_PHASES = frozenset({"listen", "divination"})
_MOTION_PHASES = frozenset({"conversation", "procession"})

_JI_5_LIMIT_RATIOS: tuple[float, ...] = (
    1.0,
    16.0 / 15.0,
    9.0 / 8.0,
    6.0 / 5.0,
    5.0 / 4.0,
    4.0 / 3.0,
    45.0 / 32.0,
    3.0 / 2.0,
    8.0 / 5.0,
    5.0 / 3.0,
    9.0 / 5.0,
    15.0 / 8.0,
)

_SLENDRO_CHROMATIC_CENTS: tuple[float, ...] = (
    0.0,
    0.0,
    240.0,
    240.0,
    480.0,
    480.0,
    750.0,
    750.0,
    990.0,
    990.0,
    990.0,
    990.0,
)

_VOICE_SYNTHS: Mapping[str, str] = {
    "pluck": "sw_pluck",
    "breath": "sw_breath",
    "choir": "sw_choir",
    "kotekan": "sw_kotekan",
    "pad": "sw_pad",
    "bowed": "sw_bowed",
    "tabla_tin": "sw_tabla_tin",
}


@dataclass(frozen=True)
class FaithfulVoiceSpace:
    """Compact render-space settings for one CypherClaw voice."""

    voice: str
    space_id: str
    fx_bus_id: int
    reverb_profile: tuple[tuple[str, float], ...]
    description: str

    def to_dict(self) -> dict[str, object]:
        """Return the JSON-safe space settings payload."""

        return {
            "voice": self.voice,
            "space_id": self.space_id,
            "fx_bus_id": self.fx_bus_id,
            "reverb_profile": dict(self.reverb_profile),
            "description": self.description,
            "source": SPACE_PROFILE_SOURCE,
        }


def _voice_space_from_reverb_profile(
    profile: VoiceReverbProfile,
) -> FaithfulVoiceSpace:
    return FaithfulVoiceSpace(
        voice=profile.voice,
        space_id=profile.space_id,
        fx_bus_id=profile.fx_bus_id,
        reverb_profile=profile.parameters,
        description=profile.description,
    )


VOICE_SPACES: Mapping[str, FaithfulVoiceSpace] = {
    voice: _voice_space_from_reverb_profile(profile)
    for voice, profile in VOICE_REVERB_PROFILES.items()
}


@dataclass(frozen=True)
class FaithfulRenderSettings:
    """CypherClaw render choices applied to a faithful-transmission scene."""

    arc_phase: str = "Listen"
    tonal_center_midi: int = DEFAULT_TONAL_CENTER_MIDI
    tonal_center_hz: float = DEFAULT_TONAL_CENTER_HZ
    voice_sequence: tuple[str, ...] = ("pluck",)
    space_mode: str = "matched"
    mood_mode: MoodMode | str | None = MoodMode.MATCHED
    tuning_system_name: str | None = None
    tuning_morph_target_name: str | None = None
    tuning_morph_curve: str = MORPH_CURVE_LINEAR


@dataclass(frozen=True)
class FaithfulSceneStep:
    """One scheduled source MIDI event in a faithful scene."""

    row: int
    length_rows: int
    pitch: int
    duration_ticks: int
    velocity: float
    render_pitch_hz: float = 0.0
    render_voice: str = ""
    render_synth: str = ""
    render_space: Mapping[str, object] = field(default_factory=dict)
    metadata: Mapping[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        """Return the JSON-safe scene-step payload."""

        return {
            "row": self.row,
            "length_rows": self.length_rows,
            "pitch": self.pitch,
            "duration_ticks": self.duration_ticks,
            "velocity": self.velocity,
            "render_pitch_hz": self.render_pitch_hz,
            "render_voice": self.render_voice,
            "render_synth": self.render_synth,
            "render_space": dict(self.render_space),
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class FaithfulSceneLane:
    """A faithful MIDI lane in CypherClaw tracker-like scene form."""

    name: str
    role: str
    voice: str
    steps: tuple[FaithfulSceneStep, ...]
    metadata: Mapping[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        """Return the JSON-safe scene-lane payload."""

        return {
            "name": self.name,
            "role": self.role,
            "voice": self.voice,
            "steps": [step.to_dict() for step in self.steps],
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class FaithfulScenePattern:
    """The row-grid and lanes for a faithful MIDI scene."""

    rows: int
    lanes: tuple[FaithfulSceneLane, ...]

    def to_dict(self) -> dict[str, object]:
        """Return the JSON-safe scene-pattern payload."""

        return {
            "rows": self.rows,
            "lanes": [lane.to_dict() for lane in self.lanes],
        }


@dataclass(frozen=True)
class FaithfulSceneConstraint:
    """Scheduler limits for a faithful MIDI scene."""

    max_polyphony: int
    allowed_roles: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        """Return the JSON-safe scene-constraint payload."""

        return {
            "max_polyphony": self.max_polyphony,
            "allowed_roles": list(self.allowed_roles),
        }


@dataclass(frozen=True)
class FaithfulMidiScene:
    """A JSON-safe faithful MIDI scene preserving source pitch and rhythm."""

    name: str
    key: str
    tempo_bpm: float
    rows_per_beat: int
    pattern: FaithfulScenePattern
    constraints: FaithfulSceneConstraint
    metadata: Mapping[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        """Return the JSON-safe faithful scene payload."""

        return {
            "name": self.name,
            "key": self.key,
            "tempo_bpm": self.tempo_bpm,
            "rows_per_beat": self.rows_per_beat,
            "pattern": self.pattern.to_dict(),
            "constraints": self.constraints.to_dict(),
            "metadata": dict(self.metadata),
        }


def build_faithful_midi_scene(
    events: Sequence[FaithfulMidiEvent],
    *,
    name: str = DEFAULT_SCENE_NAME,
    source_name: str = "",
    ticks_per_beat: int = DEFAULT_TICKS_PER_BEAT,
    rows_per_beat: int = DEFAULT_ROWS_PER_BEAT,
    key: str = DEFAULT_KEY,
    tempo_bpm: float = DEFAULT_TEMPO_BPM,
    role: str = "melody",
    voice: str = "pluck",
    render_settings: FaithfulRenderSettings | None = None,
) -> FaithfulMidiScene:
    """Map parsed faithful MIDI events to a CypherClaw scene structure."""

    safe_rows_per_beat = max(1, int(rows_per_beat))
    settings = render_settings or FaithfulRenderSettings(voice_sequence=(voice,))
    tuning_system_name = _tuning_system_name(settings)
    tuning_morph_target_name = _tuning_morph_target_name(settings)
    tuning_morph_curve = _tuning_morph_curve(settings.tuning_morph_curve)
    tonal_center_midi = _safe_tonal_center_midi(settings.tonal_center_midi)
    tonal_center_hz = _safe_tonal_center_hz(settings.tonal_center_hz)
    voice_sequence = _normalized_voice_sequence(settings.voice_sequence, voice)
    space_mode = _space_mode(settings.space_mode)
    mood_mode = parse_mood_mode(settings.mood_mode)
    row = 0
    total_duration_ticks = 0
    steps: list[FaithfulSceneStep] = []
    for index, event in enumerate(events):
        duration_ticks = int(event.duration)
        if duration_ticks <= 0:
            continue
        velocity = _normalize_velocity(event.velocity)
        length_rows = _duration_to_rows(
            duration_ticks,
            ticks_per_beat=ticks_per_beat,
            rows_per_beat=safe_rows_per_beat,
        )
        pitch = int(event.pitch)
        requested_voice = voice_sequence[index % len(voice_sequence)]
        render_voice = _normalize_render_voice(requested_voice)
        render_synth = _VOICE_SYNTHS[render_voice]
        render_space = _space_for_voice(render_voice, space_mode=space_mode).to_dict()
        render_pitch_hz = render_pitch_hz_for_midi(
            pitch,
            tuning_system_name=tuning_system_name,
            tonal_center_midi=tonal_center_midi,
            tonal_center_hz=tonal_center_hz,
        )
        steps.append(
            FaithfulSceneStep(
                row=row,
                length_rows=length_rows,
                pitch=pitch,
                duration_ticks=duration_ticks,
                velocity=velocity,
                render_pitch_hz=render_pitch_hz,
                render_voice=render_voice,
                render_synth=render_synth,
                render_space=render_space,
                metadata={
                    "faithful_sequence_index": str(index),
                    "source_midi_pitch": str(pitch),
                    "source_velocity": str(_clamp_int(event.velocity, 0, 127)),
                    "source_duration_ticks": str(duration_ticks),
                    "source_transform": FAITHFUL_SCENE_TRANSFORM,
                    "arc_phase": str(settings.arc_phase),
                    "tuning_system_name": tuning_system_name,
                    "render_pitch_hz": _format_float(render_pitch_hz),
                    "requested_render_voice": str(requested_voice),
                    "render_voice": render_voice,
                    "render_synth": render_synth,
                    "render_space_id": str(render_space["space_id"]),
                    "render_fx_bus_id": str(render_space["fx_bus_id"]),
                    "space_mode": space_mode,
                    "mood_mode": mood_mode.value,
                },
            )
        )
        row += length_rows
        total_duration_ticks += duration_ticks

    lane = FaithfulSceneLane(
        name="faithful_midi",
        role=role,
        voice=voice,
        steps=tuple(steps),
        metadata={"lane_source": "faithful_midi"},
    )
    pattern = FaithfulScenePattern(rows=row, lanes=(lane,))
    constraints = FaithfulSceneConstraint(max_polyphony=1, allowed_roles=(role,))
    metadata = {
        "mode": "faithful_transmission",
        "source_transform": FAITHFUL_SCENE_TRANSFORM,
        "source_name": str(source_name),
        "source_event_count": str(len(steps)),
        "source_duration_ticks": str(total_duration_ticks),
        "arc_phase": str(settings.arc_phase),
        "tuning_system_name": tuning_system_name,
        "tuning_morph_target_name": tuning_morph_target_name,
        "tuning_morph_curve": tuning_morph_curve,
        "tuning_tonal_center_midi": str(tonal_center_midi),
        "tuning_tonal_center_hz": _format_float(tonal_center_hz),
        "voice_assignment_policy": "sequence",
        "voice_sequence": ",".join(voice_sequence),
        "space_mode": space_mode,
        "mood_mode": mood_mode.value,
        "space_profile_source": SPACE_PROFILE_SOURCE,
    }
    return FaithfulMidiScene(
        name=str(name),
        key=str(key),
        tempo_bpm=float(tempo_bpm),
        rows_per_beat=safe_rows_per_beat,
        pattern=pattern,
        constraints=constraints,
        metadata=metadata,
    )


def _duration_to_rows(
    duration_ticks: int,
    *,
    ticks_per_beat: int,
    rows_per_beat: int,
) -> int:
    denominator = int(ticks_per_beat)
    if denominator <= 0:
        denominator = rows_per_beat
    return max(1, int(round((duration_ticks / denominator) * rows_per_beat)))


def render_pitch_hz_for_midi(
    midi_pitch: int,
    *,
    tuning_system_name: str,
    tonal_center_midi: int = DEFAULT_TONAL_CENTER_MIDI,
    tonal_center_hz: float = DEFAULT_TONAL_CENTER_HZ,
) -> float:
    """Return the CypherClaw render frequency for a preserved MIDI pitch."""

    pitch = int(midi_pitch)
    center_midi = _safe_tonal_center_midi(tonal_center_midi)
    center_hz = _safe_tonal_center_hz(tonal_center_hz)
    tuning = _normalize_tuning_system_name(tuning_system_name)
    delta = pitch - center_midi
    octave, pitch_class = divmod(delta, 12)
    octave_multiplier = 2.0 ** octave

    if tuning == TUNING_JUST_5_LIMIT:
        return center_hz * octave_multiplier * _JI_5_LIMIT_RATIOS[pitch_class]
    if tuning == TUNING_SLENDRO:
        ratio = 2.0 ** (_SLENDRO_CHROMATIC_CENTS[pitch_class] / 1200.0)
        return center_hz * octave_multiplier * ratio
    return center_hz * (2.0 ** (delta / 12.0))


def tuning_system_name_for_phase(arc_phase: str) -> str:
    """Return CypherClaw's tuning system for an arc phase."""

    phase = str(arc_phase).strip().lower()
    if phase in _STILL_PHASES:
        return TUNING_JUST_5_LIMIT
    if phase in _MOTION_PHASES:
        return TUNING_SLENDRO
    return TUNING_12_TET


def _normalize_velocity(value: int) -> float:
    return _clamp_int(value, 0, 127) / 127.0


def _clamp_int(value: int, lower: int, upper: int) -> int:
    return max(lower, min(upper, int(value)))


def _tuning_system_name(settings: FaithfulRenderSettings) -> str:
    if settings.tuning_system_name is not None:
        return _normalize_tuning_system_name(settings.tuning_system_name)
    return tuning_system_name_for_phase(settings.arc_phase)


def _tuning_morph_target_name(settings: FaithfulRenderSettings) -> str:
    if settings.tuning_morph_target_name is None:
        return ""
    return _normalize_tuning_system_name(settings.tuning_morph_target_name)


def _tuning_morph_curve(value: str) -> str:
    key = str(value).strip().lower().replace("-", "_").replace(" ", "_")
    if key in SUPPORTED_MORPH_CURVES:
        return key
    return MORPH_CURVE_LINEAR


def parse_mood_mode(value: MoodMode | str | None) -> MoodMode:
    """Return the canonical scene mood mode for runtime input."""

    if isinstance(value, MoodMode):
        return value
    key = str(value or "").strip().lower().replace("_", "-").replace(" ", "-")
    aliases = {
        MoodMode.MATCHED.value: MoodMode.MATCHED,
        MoodMode.EXPRESSIVE.value: MoodMode.EXPRESSIVE,
        MoodMode.HOUSE_BOUND.value: MoodMode.HOUSE_BOUND,
    }
    return aliases.get(key, MoodMode.MATCHED)


def validate_faithful_scene_metadata(metadata: Mapping[str, str]) -> None:
    """Validate scene metadata declares tuning, morph, and mood-mode fields.

    Raises ``ValueError`` if any required field is missing, or if the
    ``tuning_morph_curve`` / ``mood_mode`` values are not supported. Empty
    ``tuning_morph_target_name`` is permitted (no morph configured).
    """

    for field_name in (*REQUIRED_TUNING_METADATA_FIELDS, *REQUIRED_MOOD_METADATA_FIELDS):
        if field_name not in metadata:
            raise ValueError(f"scene metadata missing required field: {field_name!r}")
    curve = metadata["tuning_morph_curve"]
    if curve not in SUPPORTED_MORPH_CURVES:
        raise ValueError(
            f"tuning_morph_curve must be one of {SUPPORTED_MORPH_CURVES!r}, "
            f"got {curve!r}"
        )
    mood_mode = metadata["mood_mode"]
    if mood_mode not in SUPPORTED_MOOD_MODES:
        raise ValueError(
            f"mood_mode must be one of {SUPPORTED_MOOD_MODES!r}, "
            f"got {mood_mode!r}"
        )


def _normalize_tuning_system_name(value: str) -> str:
    key = str(value).strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "12tet": TUNING_12_TET,
        "12_tet": TUNING_12_TET,
        "twelve_tet": TUNING_12_TET,
        "equal_temperament": TUNING_12_TET,
        "just": TUNING_JUST_5_LIMIT,
        "ji": TUNING_JUST_5_LIMIT,
        "just_intonation": TUNING_JUST_5_LIMIT,
        "just_intonation_5_limit": TUNING_JUST_5_LIMIT,
        "5_limit_ji": TUNING_JUST_5_LIMIT,
        "slendro": TUNING_SLENDRO,
        "gamelan_slendro": TUNING_SLENDRO,
    }
    return aliases.get(key, TUNING_12_TET)


def _safe_tonal_center_midi(value: int) -> int:
    return int(value)


def _safe_tonal_center_hz(value: float) -> float:
    hz = float(value)
    if not math.isfinite(hz) or hz <= 0.0:
        return DEFAULT_TONAL_CENTER_HZ
    return hz


def _normalized_voice_sequence(
    values: Sequence[str],
    fallback_voice: str,
) -> tuple[str, ...]:
    requested = tuple(str(value).strip() for value in values if str(value).strip())
    if requested:
        return requested
    return (str(fallback_voice).strip() or "pluck",)


def _normalize_render_voice(value: str) -> str:
    key = str(value).strip().lower()
    if key.startswith("sw_"):
        key = key[3:]
    return key if key in _VOICE_SYNTHS else "pluck"


def _space_mode(value: str) -> str:
    key = str(value).strip().lower().replace("-", "_").replace(" ", "_")
    if key == "matched":
        return "matched"
    return "matched"


def _space_for_voice(voice: str, *, space_mode: str) -> FaithfulVoiceSpace:
    if space_mode != "matched":
        return VOICE_SPACES["pluck"]
    return VOICE_SPACES.get(voice, VOICE_SPACES["pluck"])


def _format_float(value: float) -> str:
    formatted = f"{float(value):.6f}"
    return formatted.rstrip("0").rstrip(".")
