"""Section arrangement planning for CypherClaw tracker songs.

Scenes carry an optional *ArrangementTimeline* that describes time-based
lane entries/exits, doubles, dropouts, foreground/background roles,
register bands, density gates, and automation curves — replacing the
earlier static-role model with decisions that evolve across a scene.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence


# ── Time-based arrangement types ──────────────────────────────────


@dataclass(frozen=True)
class LaneEvent:
    """A voice action at a normalised time point within a scene."""

    voice: str
    action: str  # "enter" | "exit" | "double" | "dropout" | "return"
    t: float  # normalised time 0.0–1.0
    role: str = "support"  # "primary" | "support" | "background"


@dataclass(frozen=True)
class RegisterBand:
    """MIDI register constraints for a voice."""

    voice: str
    low_midi: int
    high_midi: int


@dataclass(frozen=True)
class DensityGate:
    """Density level at a normalised time point."""

    t: float
    density: float


@dataclass(frozen=True)
class AutomationCurve:
    """Named automation parameter with time-varying points."""

    name: str
    points: tuple[tuple[float, float], ...]  # (t, value) pairs


@dataclass(frozen=True)
class ArrangementTimeline:
    """Time-based arrangement decisions for one scene."""

    lane_events: tuple[LaneEvent, ...]
    register_bands: tuple[RegisterBand, ...]
    density_gates: tuple[DensityGate, ...]
    automation_curves: tuple[AutomationCurve, ...]


# ── Scene / plan dataclasses ──────────────────────────────────────


@dataclass(frozen=True)
class ArrangementScenePlan:
    entry_intent: str
    automation_overrides: dict[str, float]
    timeline: ArrangementTimeline | None = None


@dataclass(frozen=True)
class ArrangementPlan:
    groove_family: str
    scenes: dict[str, ArrangementScenePlan]


# ── Static arrangement constants ──────────────────────────────────

_GROOVE_BY_PATCH = {
    "house_monastery": "suspended",
    "house_chamber": "lyric",
    "house_garden": "rolling",
    "house_procession": "procession",
    "house_workshop": "study",
}

_ENTRY_INTENTS = {
    "Emergence": "arrive gently",
    "Arrival": "appear briefly",
    "Theme": "state the song",
    "Development": "widen the field",
    "Bridge": "tilt the room",
    "Recap": "remember the line",
    "Resolution": "let it settle",
    "Release": "fold it inward",
    "Afterglow": "leave a trace",
}

_CADENCE_DENSITY_SCALE = {
    "sleep": 0.45,
    "wind_down": 0.62,
    "wake_ramp": 0.84,
    "occupied_day": 1.0,
    "away_practice": 1.08,
}


# ── Time-based arrangement constants ─────────────────────────────

_REGISTER_DEFAULTS: dict[str, tuple[int, int]] = {
    "gong": (36, 60),
    "bowed": (48, 72),
    "pluck": (48, 84),
    "kotekan": (60, 96),
    "choir": (60, 84),
    "bell": (72, 108),
    "breath": (48, 72),
}

_PRIMARY_VOICES = frozenset({"bowed", "choir", "gong"})

# Staged entry order — centre outward (mirrors orchestral_form DIVERGE_ORDER)
_STAGE_ORDER: list[list[str]] = [
    ["bowed", "choir"],
    ["pluck", "bell"],
    ["gong", "kotekan"],
    ["breath"],
]


def _variant_for_polyphony(max_polyphony: int) -> str:
    if max_polyphony <= 2:
        return "sparse"
    if max_polyphony <= 4:
        return "medium"
    return "full"


def _pick_voices(variant: str) -> list[str]:
    """Select voices for *variant*, in staged entry order."""
    limit = {"sparse": 2, "medium": 4, "full": 7}[variant]
    voices: list[str] = []
    for group in _STAGE_ORDER:
        for v in group:
            if len(voices) < limit:
                voices.append(v)
    return voices


def _role_for_voice(voice: str) -> str:
    return "primary" if voice in _PRIMARY_VOICES else "support"


# ── Timeline builder ──────────────────────────────────────────────


def build_scene_timeline(
    scene_name: str,
    max_polyphony: int,
    base_density: float,
    base_amp: float,
) -> ArrangementTimeline:
    """Build a time-based arrangement timeline for one scene.

    *max_polyphony* selects a sparse / medium / full variant that
    determines how many voices participate and how they stage in.
    """
    variant = _variant_for_polyphony(max_polyphony)
    voices = _pick_voices(variant)

    # -- Lane events: staged entry --
    events: list[LaneEvent] = []
    n_voices = len(voices)
    entry_span = 0.6
    spacing = entry_span / max(1, n_voices - 1) if n_voices > 1 else 0.0

    for i, voice in enumerate(voices):
        t = round(min(i * spacing, entry_span), 3)
        events.append(LaneEvent(voice=voice, action="enter", t=t, role=_role_for_voice(voice)))

    # Support dropout / return (texture breathing)
    support_voices = [v for v in voices if _role_for_voice(v) == "support"]
    if support_voices and variant != "sparse":
        dv = support_voices[-1]
        events.append(LaneEvent(voice=dv, action="dropout", t=0.65, role="support"))
        events.append(LaneEvent(voice=dv, action="return", t=0.82, role="support"))

    # Doubles in full variant — first support doubles the melody
    if variant == "full" and support_voices:
        events.append(LaneEvent(voice=support_voices[0], action="double", t=0.5, role="support"))

    # Support exit before scene end (medium only, different voice from dropout)
    if variant == "medium" and len(support_voices) > 1:
        events.append(LaneEvent(voice=support_voices[0], action="exit", t=0.9, role="support"))

    events.sort(key=lambda e: (e.t, e.action != "enter"))

    # -- Register bands --
    bands: list[RegisterBand] = []
    for v in voices:
        if v in _REGISTER_DEFAULTS:
            lo, hi = _REGISTER_DEFAULTS[v]
            bands.append(RegisterBand(voice=v, low_midi=lo, high_midi=hi))

    # -- Density gates (non-flat arc) --
    peak_density = min(1.0, base_density * 1.25)
    gates = (
        DensityGate(t=0.0, density=round(base_density * 0.6, 3)),
        DensityGate(t=0.3, density=round(base_density, 3)),
        DensityGate(t=0.65, density=round(peak_density, 3)),
        DensityGate(t=1.0, density=round(base_density * 0.85, 3)),
    )

    # -- Automation curves (non-flat arc) --
    amp_peak = min(1.0, base_amp * 1.15)
    curves = (
        AutomationCurve(
            name="master_amp",
            points=(
                (0.0, round(base_amp * 0.8, 3)),
                (0.35, round(base_amp, 3)),
                (0.65, round(amp_peak, 3)),
                (1.0, round(base_amp * 0.9, 3)),
            ),
        ),
        AutomationCurve(
            name="density",
            points=tuple((g.t, g.density) for g in gates),
        ),
    )

    return ArrangementTimeline(
        lane_events=tuple(events),
        register_bands=tuple(bands),
        density_gates=gates,
        automation_curves=curves,
    )


# ── Runtime helpers ───────────────────────────────────────────────


def _direction_profile(values: Sequence[float], tolerance: float) -> tuple[int, ...]:
    profile: list[int] = []
    for previous, current in zip(values, values[1:]):
        delta = current - previous
        if abs(delta) <= tolerance:
            profile.append(0)
        elif delta > 0:
            profile.append(1)
        else:
            profile.append(-1)
    return tuple(profile)


def contours_independent(
    voice_contours: Mapping[str, Sequence[float]],
    *,
    tolerance: float = 0.0,
) -> bool:
    """Verify voices are not locked to the same directional contour."""
    profiles: dict[tuple[int, ...], str] = {}
    for voice, contour in voice_contours.items():
        profile = _direction_profile(contour, tolerance)
        if not profile:
            continue
        if profile in profiles:
            return False
        profiles[profile] = voice
    return True


def climaxes_staggered(
    lane_activity: Mapping[str, Sequence[tuple[float, float]]],
    *,
    min_separation: float = 0.05,
) -> bool:
    """Verify lane activity peaks land at distinct normalised times."""
    peak_times: list[float] = []
    for points in lane_activity.values():
        if not points:
            continue
        peak_time, _peak_value = max(points, key=lambda point: point[1])
        peak_times.append(peak_time)

    for i, peak_time in enumerate(peak_times):
        for other_time in peak_times[i + 1 :]:
            if abs(peak_time - other_time) < min_separation:
                return False
    return True


def register_crowding_detected(
    bands: Sequence[RegisterBand],
    *,
    unison_tolerance: int = 1,
    masking_overlap: int = 6,
) -> bool:
    """Detect register bands that risk unison doubling or masking."""
    for i, first in enumerate(bands):
        if first.low_midi >= first.high_midi:
            return True
        first_center = (first.low_midi + first.high_midi) / 2
        for second in bands[i + 1 :]:
            if second.low_midi >= second.high_midi:
                return True
            second_center = (second.low_midi + second.high_midi) / 2
            overlap = min(first.high_midi, second.high_midi) - max(first.low_midi, second.low_midi)
            if overlap <= 0:
                continue
            same_band = (
                abs(first.low_midi - second.low_midi) <= unison_tolerance
                and abs(first.high_midi - second.high_midi) <= unison_tolerance
            )
            same_center = abs(first_center - second_center) <= unison_tolerance
            if same_band or same_center or overlap >= masking_overlap:
                return True
    return False


def active_voices_at(timeline: ArrangementTimeline, t: float) -> list[str]:
    """Return voices that are active (entered and not exited/dropped) at time *t*."""
    state: dict[str, bool] = {}
    for ev in timeline.lane_events:
        if ev.t > t:
            break
        if ev.action in ("enter", "return"):
            state[ev.voice] = True
        elif ev.action in ("exit", "dropout"):
            state[ev.voice] = False
    return [v for v, active in state.items() if active]


def thin_events(
    timeline: ArrangementTimeline,
    voices_to_keep: Sequence[str] | None = None,
) -> ArrangementTimeline:
    """Remove support lane events while preserving primary voice continuity.

    If *voices_to_keep* is given those voices are always preserved.
    Otherwise all primary-role voices are preserved.
    """
    keep = frozenset(voices_to_keep) if voices_to_keep is not None else frozenset(
        ev.voice for ev in timeline.lane_events if ev.role == "primary"
    )
    thinned = tuple(ev for ev in timeline.lane_events if ev.voice in keep)
    kept_voices = {ev.voice for ev in thinned}
    bands = tuple(b for b in timeline.register_bands if b.voice in kept_voices)
    return ArrangementTimeline(
        lane_events=thinned,
        register_bands=bands,
        density_gates=timeline.density_gates,
        automation_curves=timeline.automation_curves,
    )


def registers_safe(bands: Sequence[RegisterBand]) -> bool:
    """Verify register bands are valid and have sufficient range."""
    for b in bands:
        if b.low_midi >= b.high_midi:
            return False
        if b.high_midi - b.low_midi < 12:
            return False
        if b.low_midi < 21 or b.high_midi > 127:
            return False
    return True


def interpolate_automation(curve: AutomationCurve, t: float) -> float:
    """Linearly interpolate the automation value at normalised time *t*."""
    points = curve.points
    if not points:
        return 0.0
    if t <= points[0][0]:
        return points[0][1]
    if t >= points[-1][0]:
        return points[-1][1]
    for i in range(len(points) - 1):
        t0, v0 = points[i]
        t1, v1 = points[i + 1]
        if t0 <= t <= t1:
            span = t1 - t0
            frac = (t - t0) / span if span > 0 else 0.0
            return round(v0 + frac * (v1 - v0), 3)
    return points[-1][1]


# ── Plan builder ──────────────────────────────────────────────────


def build_arrangement_plan(
    *,
    patch_name: str,
    family_name: str,
    cadence_state: str,
    progression_profile: str,
    form_templates: Sequence[object],
    density_bias: float = 0.0,
    payoff_scene: str = "",
    payoff_bias: float = 0.0,
) -> ArrangementPlan:
    """Build a bounded section-arrangement plan for one tracker form."""

    groove_family = _GROOVE_BY_PATCH.get(
        patch_name,
        "study" if progression_profile == "experiment" else "rolling" if family_name in {"bloom", "drift"} else "lyric",
    )
    density_scale = _CADENCE_DENSITY_SCALE.get(cadence_state, 1.0)
    scenes: dict[str, ArrangementScenePlan] = {}
    for index, template in enumerate(form_templates):
        name = str(getattr(template, "name", f"Scene {index + 1}"))
        defaults = dict(getattr(template, "automation_defaults", {}))
        density = float(defaults.get("density", 0.35)) * density_scale
        if name in {"Development", "Bridge"}:
            density *= 1.08
        if name in {"Resolution", "Release", "Afterglow"}:
            density *= 0.8
        entry_intent = _ENTRY_INTENTS.get(name, "shape the section")
        if payoff_scene and name == payoff_scene:
            density += payoff_bias
            entry_intent = f"{entry_intent} and arrive"
        density = max(0.05, min(1.0, density + density_bias))
        master_amp = float(defaults.get("master_amp", 0.6))
        if cadence_state in {"sleep", "wind_down"}:
            master_amp *= 0.86
        if payoff_scene and name == payoff_scene:
            master_amp *= 1.0 + min(0.18, payoff_bias)
        automation: dict[str, float] = {**defaults, "density": round(density, 3), "master_amp": round(master_amp, 3)}
        max_poly = int(getattr(template, "max_polyphony", 3))
        timeline = build_scene_timeline(name, max_poly, density, master_amp)
        scenes[name] = ArrangementScenePlan(
            entry_intent=entry_intent,
            automation_overrides=automation,
            timeline=timeline,
        )
    return ArrangementPlan(groove_family=groove_family, scenes=scenes)
