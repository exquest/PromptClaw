"""Korsakov Ch.4 Accompaniment — density-reactive patterns for the composer.

Six accompaniment types ranked by energy:
1. Sustained (held note, no rhythm)
2. Repeated chords (waltz oom-pah-pah)
3. Tremolo (rapid alternation)
4. Arpeggiated (chord tones spread across time)
5. Broken figures (irregular arpeggio)
6. Ostinato (repeating melodic cell, transposed per chord)

The inverse rule: when melody is dense, accompaniment simplifies.
When melody rests, accompaniment fills.

Diagnostic surface (depth-2): AccompanimentPatternSnapshot and
AccompanimentPlanReport turn one accompaniment decision into a stable
operator-readable summary without changing the live pattern helpers.
"""
from __future__ import annotations

import math
import random
import time
from dataclasses import dataclass
from typing import Any

AccompanimentEvent = tuple[float, float, float, float]
PedalEvent = tuple[float, float, float]

_REGISTER_BANDS = ("pedal", "bass", "middle", "upper")


# === DENSITY TRACKING ===

class DensityTracker:
    """Track melody note density over a sliding window."""

    def __init__(self, window_seconds: float = 4.0) -> None:
        self.window = window_seconds
        self._timestamps: list[float] = []

    def note_played(self) -> None:
        """Record that a melody note was just played."""
        self._timestamps.append(time.time())
        self._prune()

    def density(self) -> float:
        """Notes per second over the window."""
        self._prune()
        if not self._timestamps:
            return 0.0
        return len(self._timestamps) / self.window

    def is_resting(self, silence_threshold: float = 1.5) -> bool:
        """True if no notes played in the last silence_threshold seconds."""
        if not self._timestamps:
            return True
        return (time.time() - self._timestamps[-1]) > silence_threshold

    def _prune(self) -> None:
        cutoff = time.time() - self.window
        self._timestamps = [t for t in self._timestamps if t > cutoff]


def select_accompaniment_type(density: float, is_resting: bool) -> int:
    """Select accompaniment type (1-6) based on melody density.

    Inverse rule: high melody density → low accompaniment type.
    Melody resting → higher accompaniment type (fill the gap).
    """
    if is_resting:
        return random.choice([4, 5])  # arpeggiated or broken
    if density > 3.0:
        return 1  # sustained — get out of the way
    if density > 2.0:
        return 2  # repeated chords
    if density > 1.0:
        return 3  # tremolo or simple arpeggio
    return random.choice([2, 4])  # moderate — waltz or arpeggio


# === ACCOMPANIMENT PATTERNS ===
# Each returns a list of (freq, amp, release) tuples to play

def make_scale(root: float) -> list[float]:
    """Major scale from root, 2 octaves."""
    semitones = [0, 2, 4, 5, 7, 9, 11]
    return [root * (2 ** ((s + 12 * o) / 12)) for o in range(3) for s in semitones]


def sustained(root: float, fifth: float, beat: float, loud: float = 0.5) -> list[tuple[float, float, float, float]]:
    """Type 1: Held chord tone. One note, long release.
    Returns [(freq, amp, release, wait)]"""
    frequency = root / 2
    amp = 0.06 * loud
    release = beat * 6
    wait_after = beat * 3
    return [(frequency, amp, release, wait_after)]


def repeated_chords(root: float, fifth: float, beat: float, loud: float = 0.7) -> list[tuple[float, float, float, float]]:
    """Type 2: Waltz oom-pah-pah."""
    bass = root / 2
    chord_tone = fifth / 2
    downbeat_amp = 0.18 * loud
    upbeat_amp = 0.08 * loud
    tail_amp = 0.06 * loud
    return [
        (bass, downbeat_amp, 0.45, beat),
        (chord_tone, upbeat_amp, 0.3, beat),
        (chord_tone, tail_amp, 0.25, beat),
    ]


def tremolo(root: float, fifth: float, beat: float, loud: float = 0.5) -> list[tuple[float, float, float, float]]:
    """Type 3: Rapid alternation between third and fifth."""
    scale = make_scale(root)
    third = scale[2] if len(scale) > 2 else root * 1.26
    notes = []
    for _ in range(6):
        notes.append((third, 0.03 * loud, 0.15, beat / 2))
        notes.append((fifth, 0.03 * loud, 0.15, beat / 2))
    return notes


def arpeggiated(root: float, fifth: float, beat: float, loud: float = 0.6) -> list[tuple[float, float, float, float]]:
    """Type 4: Chord tones spread across time — root, third, fifth ascending."""
    scale = make_scale(root)
    third = scale[2] if len(scale) > 2 else root * 1.26
    low_root = root / 2
    low_third = third / 2
    low_fifth = fifth / 2
    root_amp = 0.12 * loud
    third_amp = 0.08 * loud
    fifth_amp = 0.06 * loud
    return [
        (low_root, root_amp, 0.5, beat),
        (low_third, third_amp, 0.4, beat),
        (low_fifth, fifth_amp, 0.35, beat),
    ]


def broken_figure(root: float, fifth: float, beat: float, loud: float = 0.5) -> list[tuple[float, float, float, float]]:
    """Type 5: Irregular arpeggio — fifth, root, third, fifth(up)."""
    scale = make_scale(root)
    third = scale[2] if len(scale) > 2 else root * 1.26
    low_fifth = fifth / 2
    low_root = root / 2
    low_third = third / 2
    upper_fifth = fifth
    return [
        (low_fifth, 0.08 * loud, 0.3, beat * 0.75),
        (low_root, 0.10 * loud, 0.35, beat * 0.5),
        (low_third, 0.06 * loud, 0.3, beat * 0.75),
        (upper_fifth, 0.04 * loud, 0.25, beat),
    ]


def ostinato_cell(root: float, fifth: float, beat: float, loud: float = 0.4) -> list[tuple[float, float, float, float]]:
    """Type 6: Short repeating melodic cell — 3 descending scale notes.
    Transposed to chord root."""
    scale = make_scale(root)
    # Pick 3 descending notes from mid-scale
    start = min(4, len(scale) - 3)
    upper = scale[start + 2]
    middle = scale[start + 1]
    lower = scale[start]
    wait_after = beat * 0.67
    return [
        (upper, 0.05 * loud, 0.25, wait_after),
        (middle, 0.04 * loud, 0.2, wait_after),
        (lower, 0.05 * loud, 0.3, wait_after),
    ]


PATTERNS = {
    1: sustained,
    2: repeated_chords,
    3: tremolo,
    4: arpeggiated,
    5: broken_figure,
    6: ostinato_cell,
}


def get_pattern(
    pattern_type: int,
    root: float,
    fifth: float,
    beat: float,
    loud: float = 0.7,
) -> list[tuple[float, float, float, float]]:
    """Get accompaniment pattern by type number.

    Returns list of (freq, amp, release, wait_after) tuples.
    """
    fn = PATTERNS.get(pattern_type, repeated_chords)
    return fn(root, fifth, beat, loud)


# === PEDAL POINT ===

def pedal_note(root: float, beat: float, loud: float = 0.4) -> tuple[float, float, float]:
    """Gong pedal point — strike on tonic, let it ring.
    Returns (freq, amp, release)."""
    frequency = root / 4
    amp = 0.015 * loud
    release = beat * 12
    event = (frequency, amp, release)
    return event


def should_pedal(bar_number: int, bars_per_phrase: int = 4) -> bool:
    """True at phrase boundaries (every N bars)."""
    return bar_number % bars_per_phrase == 0


# === BREATHING ===

def breathing_swell(
    melody_density: float,
    melody_resting: bool,
    current_type: int,
) -> int:
    """Adjust accompaniment type based on breathing.

    Melody resting → swell up (higher type number = more activity).
    Melody active → thin out (lower type number).
    """
    if melody_resting and current_type < 5:
        return current_type + 1
    if melody_density > 2.0 and current_type > 1:
        return current_type - 1
    return current_type


# === TRANSITION ===

def should_transition_gradually(
    current_type: int,
    target_type: int,
) -> bool:
    """True if the type change is small enough for gradual transition.
    Large jumps (>2) signal section boundaries and should be abrupt."""
    return abs(current_type - target_type) <= 2


# === DIAGNOSTIC REPORTING ===

@dataclass(frozen=True)
class AccompanimentPatternSnapshot:
    """Resolved diagnostic view for one generated accompaniment pattern."""

    pattern_type: int
    pattern_name: str
    energy_band: str
    root_hz: float
    fifth_hz: float
    beat_seconds: float
    loud: float
    events: tuple[AccompanimentEvent, ...]
    event_count: int
    total_wait_seconds: float
    max_release_seconds: float
    mean_amp: float
    min_frequency_hz: float
    max_frequency_hz: float
    register_band_counts: dict[str, int]


@dataclass(frozen=True)
class AccompanimentPlanReport:
    """End-to-end accompaniment decision and aggregate event diagnostics."""

    melody_density: float
    melody_resting: bool
    density_band: str
    current_type: int
    selected_type: int
    target_type: int
    transition_mode: str
    pedal_enabled: bool
    pedal_event: PedalEvent | None
    pattern: AccompanimentPatternSnapshot
    total_event_count: int
    total_wait_seconds: float
    max_release_seconds: float
    mean_amp: float
    lowest_frequency_hz: float
    highest_frequency_hz: float
    active_pattern_names: tuple[str, ...]


def accompaniment_density_band(melody_density: float, melody_resting: bool) -> str:
    """Classify melody density into a stable accompaniment pressure band."""
    if melody_resting:
        return "resting"
    if melody_density <= 1.0:
        return "sparse"
    if melody_density <= 2.0:
        return "balanced"
    if melody_density <= 3.0:
        return "busy"
    return "dense"


def accompaniment_pattern_name(pattern_type: int) -> str:
    """Return the canonical pattern name, matching get_pattern fallback."""
    if pattern_type == 1:
        return "sustained"
    if pattern_type == 2:
        return "repeated_chords"
    if pattern_type == 3:
        return "tremolo"
    if pattern_type == 4:
        return "arpeggiated"
    if pattern_type == 5:
        return "broken_figure"
    if pattern_type == 6:
        return "ostinato_cell"
    return "repeated_chords"


def accompaniment_energy_band(pattern_type: int) -> str:
    """Classify a pattern type by its accompaniment energy level."""
    if pattern_type == 1:
        return "thin"
    if pattern_type in {2, 3}:
        return "supporting"
    if pattern_type in {4, 5}:
        return "filling"
    if pattern_type == 6:
        return "foreground"
    return "supporting"


def frequency_register_band(frequency_hz: float) -> str:
    """Classify a frequency into pedal, bass, middle, or upper register."""
    if frequency_hz < 65.4:
        return "pedal"
    if frequency_hz < 130.8:
        return "bass"
    if frequency_hz < 523.3:
        return "middle"
    return "upper"


def accompaniment_transition_mode(current_type: int, target_type: int) -> str:
    """Return the named transition mode between accompaniment types."""
    if should_transition_gradually(current_type, target_type):
        return "gradual"
    return "section_cut"


def summarize_pattern_events(events: tuple[AccompanimentEvent, ...]) -> dict[str, Any]:
    """Aggregate generated accompaniment events into stable numeric metrics."""
    register_counts = {band: 0 for band in _REGISTER_BANDS}
    event_count = 0
    total_wait = 0.0
    max_release = 0.0
    amp_total = 0.0
    min_frequency = 0.0
    max_frequency = 0.0

    for frequency, amp, release, wait_after in events:
        band = frequency_register_band(frequency)
        register_counts[band] += 1
        min_frequency = frequency if event_count == 0 else min(min_frequency, frequency)
        max_frequency = frequency if event_count == 0 else max(max_frequency, frequency)
        max_release = max(max_release, release)
        amp_total += amp
        total_wait += wait_after
        event_count += 1

    mean_amp = amp_total / event_count if event_count else 0.0
    return {
        "event_count": event_count,
        "total_wait_seconds": round(total_wait, 4),
        "max_release_seconds": round(max_release, 4),
        "mean_amp": round(mean_amp, 4),
        "min_frequency_hz": round(min_frequency, 4),
        "max_frequency_hz": round(max_frequency, 4),
        "register_band_counts": register_counts,
    }


def build_pattern_snapshot(
    pattern_type: int,
    root: float,
    fifth: float,
    beat: float,
    loud: float = 0.7,
) -> AccompanimentPatternSnapshot:
    """Resolve one existing accompaniment pattern into a diagnostic snapshot."""
    events = tuple(get_pattern(pattern_type, root, fifth, beat, loud))
    summary = summarize_pattern_events(events)
    return AccompanimentPatternSnapshot(
        pattern_type=pattern_type,
        pattern_name=accompaniment_pattern_name(pattern_type),
        energy_band=accompaniment_energy_band(pattern_type),
        root_hz=root,
        fifth_hz=fifth,
        beat_seconds=beat,
        loud=loud,
        events=events,
        event_count=int(summary["event_count"]),
        total_wait_seconds=float(summary["total_wait_seconds"]),
        max_release_seconds=float(summary["max_release_seconds"]),
        mean_amp=float(summary["mean_amp"]),
        min_frequency_hz=float(summary["min_frequency_hz"]),
        max_frequency_hz=float(summary["max_frequency_hz"]),
        register_band_counts=dict(summary["register_band_counts"]),
    )


def build_accompaniment_plan_report(
    *,
    melody_density: float,
    melody_resting: bool,
    current_type: int,
    root: float,
    fifth: float,
    beat: float,
    loud: float = 0.7,
    bar_number: int = 0,
    bars_per_phrase: int = 4,
) -> AccompanimentPlanReport:
    """Build one end-to-end accompaniment decision report from live inputs."""
    selected_type = select_accompaniment_type(melody_density, melody_resting)
    target_type = breathing_swell(melody_density, melody_resting, selected_type)
    pattern = build_pattern_snapshot(target_type, root, fifth, beat, loud)
    pedal_enabled = should_pedal(bar_number, bars_per_phrase)
    pedal_event = pedal_note(root, beat, loud) if pedal_enabled else None

    frequencies = [event[0] for event in pattern.events]
    amps = [event[1] for event in pattern.events]
    releases = [event[2] for event in pattern.events]
    active_names = [pattern.pattern_name]
    if pedal_event is not None:
        frequencies.append(pedal_event[0])
        amps.append(pedal_event[1])
        releases.append(pedal_event[2])
        active_names.append("pedal_point")

    total_event_count = len(amps)
    mean_amp = sum(amps) / total_event_count if total_event_count else 0.0
    return AccompanimentPlanReport(
        melody_density=melody_density,
        melody_resting=melody_resting,
        density_band=accompaniment_density_band(melody_density, melody_resting),
        current_type=current_type,
        selected_type=selected_type,
        target_type=target_type,
        transition_mode=accompaniment_transition_mode(current_type, target_type),
        pedal_enabled=pedal_enabled,
        pedal_event=pedal_event,
        pattern=pattern,
        total_event_count=total_event_count,
        total_wait_seconds=pattern.total_wait_seconds,
        max_release_seconds=round(max(releases) if releases else 0.0, 4),
        mean_amp=round(mean_amp, 4),
        lowest_frequency_hz=round(min(frequencies) if frequencies else 0.0, 4),
        highest_frequency_hz=round(max(frequencies) if frequencies else 0.0, 4),
        active_pattern_names=tuple(active_names),
    )


def summarize_accompaniment_plan_report(
    report: AccompanimentPlanReport,
) -> dict[str, Any]:
    """Return a JSON-safe operator summary for an accompaniment report."""
    pattern = report.pattern
    pattern_summary = {
        "pattern_type": pattern.pattern_type,
        "pattern_name": pattern.pattern_name,
        "energy_band": pattern.energy_band,
        "root_hz": pattern.root_hz,
        "fifth_hz": pattern.fifth_hz,
        "beat_seconds": pattern.beat_seconds,
        "loud": pattern.loud,
        "events": [[round(value, 4) for value in event] for event in pattern.events],
        "event_count": pattern.event_count,
        "total_wait_seconds": pattern.total_wait_seconds,
        "max_release_seconds": pattern.max_release_seconds,
        "mean_amp": pattern.mean_amp,
        "min_frequency_hz": pattern.min_frequency_hz,
        "max_frequency_hz": pattern.max_frequency_hz,
        "register_band_counts": dict(pattern.register_band_counts),
    }
    return {
        "melody_density": report.melody_density,
        "melody_resting": report.melody_resting,
        "density_band": report.density_band,
        "current_type": report.current_type,
        "selected_type": report.selected_type,
        "target_type": report.target_type,
        "transition_mode": report.transition_mode,
        "pedal_enabled": report.pedal_enabled,
        "pedal_event": (
            [round(value, 4) for value in report.pedal_event]
            if report.pedal_event is not None
            else None
        ),
        "pattern": pattern_summary,
        "total_event_count": report.total_event_count,
        "total_wait_seconds": report.total_wait_seconds,
        "max_release_seconds": report.max_release_seconds,
        "mean_amp": report.mean_amp,
        "lowest_frequency_hz": report.lowest_frequency_hz,
        "highest_frequency_hz": report.highest_frequency_hz,
        "active_pattern_names": list(report.active_pattern_names),
    }
