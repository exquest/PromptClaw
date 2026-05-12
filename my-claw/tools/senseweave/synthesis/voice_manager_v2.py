"""Korsakov Ch.5 — Orchestral combination: voice selection, balance, and blending.

Determines which synth voices play together, at what octave and amplitude,
and plans crescendo/diminuendo voice entries across bars.

Voices are sent to SuperCollider (scsynth) via OSC. Each voice corresponds
to a SynthDef: sw_pluck, sw_bowed, sw_kotekan, sw_gong, sw_bell_warm,
sw_choir, sw_breath.

The core principle: balance by inverse weight (heavy voices play quieter),
maintain octave separation, and add/remove voices gradually.
"""
from __future__ import annotations

import copy
import random
from dataclasses import dataclass, field


@dataclass
class Voice:
    """A single orchestral voice mapped to a SuperCollider synth."""

    name: str
    synth: str
    weight: float
    octave_home: int  # preferred octave 1–5
    current_octave: int = 0  # 0 means "use octave_home"
    active: bool = False
    amplitude: float = 0.0

    def __post_init__(self) -> None:
        if self.current_octave == 0:
            self.current_octave = self.octave_home


def _make_voices() -> dict[str, Voice]:
    """Build the canonical voice registry."""
    specs = [
        ("gong", "sw_gong", 4.0, 1),
        ("pluck", "sw_pluck", 1.0, 2),
        ("bowed", "sw_bowed", 2.0, 3),
        ("bell", "sw_bell_warm", 1.5, 4),
        ("kotekan", "sw_kotekan", 1.0, 5),
        ("choir", "sw_choir", 2.0, 3),
        ("breath", "sw_breath", 0.5, 4),
    ]
    return {
        name: Voice(name=name, synth=synth, weight=weight, octave_home=home)
        for name, synth, weight, home in specs
    }


VOICES: dict[str, Voice] = _make_voices()

# Canonical register order (lowest to highest)
_REGISTER_ORDER: list[str] = ["gong", "pluck", "bowed", "choir", "bell", "breath", "kotekan"]


# === AMPLITUDE BALANCE ===


def balance_amplitudes(
    active_voices: list[Voice],
    target_total: float = 0.5,
) -> list[Voice]:
    """Scale amplitudes inversely by weight so heavier voices are quieter.

    Total amplitude across all voices sums to *target_total*.
    Returns new Voice objects (originals are not mutated).
    """
    if not active_voices:
        return []

    # Inverse weights: lighter voices get proportionally more amplitude
    inv_weights = [1.0 / v.weight for v in active_voices]
    inv_total = sum(inv_weights)

    result: list[Voice] = []
    for v, iw in zip(active_voices, inv_weights):
        vc = copy.copy(v)
        vc.amplitude = (iw / inv_total) * target_total
        result.append(vc)
    return result


# === OCTAVE SEPARATION ===


def enforce_octave_separation(
    voices: list[Voice],
    min_separation: int = 1,
) -> list[Voice]:
    """Ensure active voices are at least *min_separation* octaves apart.

    When two voices collide, the lighter one is shifted up or down.
    Octaves are clamped to range [1, 5].
    Returns new Voice objects.
    """
    if len(voices) <= 1:
        return [copy.copy(v) for v in voices]

    # Sort by weight descending so heavier voices keep their position
    pool = [copy.copy(v) for v in voices]
    pool.sort(key=lambda v: v.weight, reverse=True)

    for i in range(1, len(pool)):
        _resolve_conflicts(pool, i, min_separation)

    # Restore original order
    order = {v.name: idx for idx, v in enumerate(voices)}
    pool.sort(key=lambda v: order.get(v.name, 0))
    return pool


def _resolve_conflicts(
    pool: list[Voice],
    idx: int,
    min_sep: int,
) -> None:
    """Shift pool[idx] until it has min_sep distance from all placed voices.

    Only checks against voices at indices 0..idx-1 (already placed).
    """
    max_attempts = 10
    for _ in range(max_attempts):
        conflict = False
        for j in range(idx):
            if abs(pool[idx].current_octave - pool[j].current_octave) < min_sep:
                conflict = True
                # Try each octave 1-5, prefer closest to home
                best = _find_free_octave(pool, idx, min_sep)
                if best is not None:
                    pool[idx].current_octave = best
                break
        if not conflict:
            break


def _find_free_octave(
    pool: list[Voice],
    idx: int,
    min_sep: int,
) -> int | None:
    """Find the best free octave for pool[idx], closest to its home octave."""
    home = pool[idx].octave_home
    # Try octaves in order of distance from home
    candidates = sorted(range(1, 6), key=lambda o: abs(o - home))
    for octave in candidates:
        if not _collides_placed(pool, idx, octave, min_sep):
            return octave
    return None


def _collides_placed(
    pool: list[Voice],
    skip_idx: int,
    octave: int,
    min_sep: int,
) -> bool:
    """Check if placing pool[skip_idx] at *octave* collides with already-placed voices."""
    for j in range(skip_idx):
        if abs(octave - pool[j].current_octave) < min_sep:
            return True
    return False


# === CRESCENDO / DIMINUENDO PLANNING ===


def plan_crescendo(
    start_voices: int,
    peak_voices: int,
    total_bars: int,
) -> list[list[str]]:
    """Plan which voices enter at which bar for an orchestral crescendo.

    Voices enter from bottom register up, one per ~2 bars.
    Returns a list (length *total_bars*) of voice-name lists per bar.
    """
    start_voices = max(1, min(start_voices, len(_REGISTER_ORDER)))
    peak_voices = max(start_voices, min(peak_voices, len(_REGISTER_ORDER)))

    voices_to_add = _REGISTER_ORDER[:peak_voices]
    initial = voices_to_add[:start_voices]
    remaining = voices_to_add[start_voices:]

    if not remaining:
        return [list(initial) for _ in range(total_bars)]

    # Space entries evenly across bars
    bars_per_entry = max(1, total_bars // (len(remaining) + 1))
    plan: list[list[str]] = []
    current = list(initial)
    next_entry_bar = bars_per_entry
    add_idx = 0

    for bar in range(total_bars):
        if bar >= next_entry_bar and add_idx < len(remaining):
            current.append(remaining[add_idx])
            add_idx += 1
            next_entry_bar += bars_per_entry
        plan.append(list(current))

    return plan


def plan_diminuendo(
    voices_at_peak: list[str],
    total_bars: int,
) -> list[list[str]]:
    """Strip voices from top register down over *total_bars*.

    Returns a list (length *total_bars*) of voice-name lists per bar.
    """
    if len(voices_at_peak) <= 1:
        return [list(voices_at_peak) for _ in range(total_bars)]

    # Sort by register: top voices exit first
    sorted_voices = sorted(
        voices_at_peak,
        key=lambda n: _REGISTER_ORDER.index(n) if n in _REGISTER_ORDER else 99,
    )

    # Voices to remove (from top = end of sorted list)
    to_remove = list(reversed(sorted_voices[1:]))  # keep at least the lowest

    bars_per_exit = max(1, total_bars // (len(to_remove) + 1))
    plan: list[list[str]] = []
    current = list(voices_at_peak)
    next_exit_bar = bars_per_exit
    remove_idx = 0

    for bar in range(total_bars):
        if bar >= next_exit_bar and remove_idx < len(to_remove):
            voice_to_remove = to_remove[remove_idx]
            if voice_to_remove in current:
                current.remove(voice_to_remove)
            remove_idx += 1
            next_exit_bar += bars_per_exit
        plan.append(list(current))

    return plan


# === FUSION PAIRS ===

_FUSION_MAP: dict[str, tuple[str, str]] = {
    "calm": ("bowed", "choir"),
    "excited": ("pluck", "kotekan"),
    "anxious": ("breath", "bell"),
    "solemn": ("gong", "bowed"),
    "playful": ("pluck", "bell"),
    "meditative": ("choir", "breath"),
    "majestic": ("gong", "choir"),
}


def suggest_fusion_pair(mood: str) -> tuple[str, str]:
    """Suggest a voice pair that creates a fused timbre for the given mood.

    Returns a pair of voice names. Unknown moods return a sensible default.
    """
    mood_lower = mood.lower()
    if mood_lower in _FUSION_MAP:
        return _FUSION_MAP[mood_lower]
    # Default: bowed + bell — warm mid-range blend
    return ("bowed", "bell")


# === MOVEMENT VOICE COUNT ===

_MOVEMENT_RANGES: dict[str, tuple[int, int]] = {
    "emergence": (1, 2),
    "theme": (2, 3),
    "development": (3, 5),
    "recap": (2, 3),
    "resolution": (1, 2),
}


def voice_count_for_movement(movement: str) -> int:
    """How many voices should be active for a movement section.

    Returns a random count within the range for the movement.
    Unknown movements default to (2, 3).
    """
    lo, hi = _MOVEMENT_RANGES.get(movement.lower(), (2, 3))
    return random.randint(lo, hi)


# === VOICE SELECTION FOR MOVEMENT ===


def select_voices_for_movement(
    movement: str,
    key: str = "C",
) -> list[Voice]:
    """Select and configure voices for a movement section.

    Uses voice_count_for_movement to decide how many voices, picks from
    the register order biased toward the movement's character, assigns
    octaves, and balances amplitudes.
    """
    count = voice_count_for_movement(movement)
    mvmt = movement.lower()

    # Choose voices biased by movement character
    if mvmt == "emergence":
        # Start sparse — low register
        candidates = ["gong", "bowed", "breath"]
    elif mvmt == "theme":
        # Core melodic voices
        candidates = ["bowed", "pluck", "bell", "choir"]
    elif mvmt == "development":
        # Full palette available
        candidates = list(_REGISTER_ORDER)
    elif mvmt in ("recap", "resolution"):
        # Winding down — core + colour
        candidates = ["bowed", "choir", "pluck", "gong"]
    else:
        candidates = list(_REGISTER_ORDER)

    # Ensure we don't ask for more than available
    count = min(count, len(candidates))
    chosen_names = random.sample(candidates, count)

    # Build voice instances
    selected: list[Voice] = []
    for name in chosen_names:
        template = VOICES[name]
        v = Voice(
            name=template.name,
            synth=template.synth,
            weight=template.weight,
            octave_home=template.octave_home,
            current_octave=template.octave_home,
            active=True,
            amplitude=0.0,
        )
        selected.append(v)

    # Enforce octave separation then balance amplitudes
    selected = enforce_octave_separation(selected)
    selected = balance_amplitudes(selected, target_total=0.5)

    # Mark all active (balance_amplitudes copies may reset)
    for v in selected:
        v.active = True

    return selected
