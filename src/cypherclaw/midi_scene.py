"""Faithful MIDI scene mapping for CypherClaw intake manifests."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

try:
    from cypherclaw.midi_loader import FaithfulMidiEvent
except ImportError:
    from midi_loader import FaithfulMidiEvent  # type: ignore[no-redef,import-not-found]


DEFAULT_SCENE_NAME = "Faithful MIDI Import"
DEFAULT_KEY = "C"
DEFAULT_TEMPO_BPM = 120.0
DEFAULT_ROWS_PER_BEAT = 4
DEFAULT_TICKS_PER_BEAT = 480
FAITHFUL_SCENE_TRANSFORM = "midi_whole_file_scene"


@dataclass(frozen=True)
class FaithfulSceneStep:
    """One scheduled source MIDI event in a faithful scene."""

    row: int
    length_rows: int
    pitch: int
    duration_ticks: int
    velocity: float
    metadata: Mapping[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        """Return the JSON-safe scene-step payload."""

        return {
            "row": self.row,
            "length_rows": self.length_rows,
            "pitch": self.pitch,
            "duration_ticks": self.duration_ticks,
            "velocity": self.velocity,
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
) -> FaithfulMidiScene:
    """Map parsed faithful MIDI events to a CypherClaw scene structure."""

    safe_rows_per_beat = max(1, int(rows_per_beat))
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
        steps.append(
            FaithfulSceneStep(
                row=row,
                length_rows=length_rows,
                pitch=pitch,
                duration_ticks=duration_ticks,
                velocity=velocity,
                metadata={
                    "faithful_sequence_index": str(index),
                    "source_midi_pitch": str(pitch),
                    "source_velocity": str(_clamp_int(event.velocity, 0, 127)),
                    "source_duration_ticks": str(duration_ticks),
                    "source_transform": FAITHFUL_SCENE_TRANSFORM,
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


def _normalize_velocity(value: int) -> float:
    return _clamp_int(value, 0, 127) / 127.0


def _clamp_int(value: int, lower: int, upper: int) -> int:
    return max(lower, min(upper, int(value)))
