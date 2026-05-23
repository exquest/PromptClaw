"""Music tracker primitives for quantized CypherClaw scene planning.

This module turns phrase-level :class:`Score` material into row-based tracker
scenes. The intent is to give the live composer a bounded framework:

- generation fills lanes instead of spraying free-form OSC events
- scenes declare their own role limits and polyphony ceilings
- a future scheduler can emit rows deterministically from this structure

Pure stdlib logic only. No runtime audio dependencies live here.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, replace
from typing import Mapping, Sequence

from cypherclaw.composer_vocabulary_bridge import VOCABULARY_METADATA_KEYS

from .arrangement_engine import (
    RegisterBand,
    build_arrangement_plan,
    climaxes_staggered,
    contours_independent,
    register_crowding_detected,
)
from .counterpoint_rules import resolve_rule
from .groove_engine import GrooveProfile, groove_for_section, groove_metadata_for_step, meter_policy_for_phase
from .generative_scores import (
    Note,
    Phrase,
    Score,
    generate_bass_line,
    generate_countermelody,
)
from .harmonic_planner import is_minorish_key
from .instrument_patches import (
    InstrumentPatch,
    normalize_patch_voice,
    select_instrument_patch,
)


_ROLE_TO_LANE_NAME = {
    "bass": "foundation",
    "color": "texture",
}

_DYNAMIC_TO_VELOCITY = {
    "pp": 0.25,
    "p": 0.4,
    "mp": 0.55,
    "mf": 0.7,
    "f": 0.85,
    "ff": 1.0,
}

_VOICE_LEADING_LIMITS = {
    "bass": 4,
    "melody": 3,
    "counter": 3,
    "color": 2,
    "sample": 1,
}

_CADENCE_ROLE_TARGETS = {
    "authentic": {
        "bass": 1,
        "melody": 1,
        "counter": 3,
        "color": 5,
    },
    "plagal": {
        "bass": 1,
        "melody": 1,
        "counter": 3,
        "color": 4,
    },
    "half": {
        "bass": 5,
        "melody": 5,
        "counter": 7,
        "color": 2,
    },
    "deceptive": {
        "bass": 6,
        "melody": 6,
        "counter": 3,
        "color": 4,
    },
    "suspended": {
        "bass": 1,
        "melody": 2,
        "counter": 5,
        "color": 4,
    },
}

_MOOD_TO_ENERGY = {
    "sleeping": 0.08,
    "calm": 0.25,
    "melancholy": 0.32,
    "happy": 0.55,
    "energetic": 0.75,
    "excited": 0.88,
}

_ROLE_SORT_ORDER = {
    "melody": 0,
    "bass": 1,
    "counter": 2,
    "color": 3,
    "sample": 4,
}

_SCENE_ROLE_FLOORS = {
    "Theme": ("bass", "color"),
    "Development": ("bass", "color"),
    "Recap": ("bass", "color"),
    "Resolution": ("color",),
}

_TRACKER_ROLE_PRIORITY = {
    "melody": ("melody", "harmony"),
    "bass": ("foundation", "rhythm", "punctuation", "harmony"),
    "color": ("texture", "color", "counter_melody", "harmony", "accent", "punctuation"),
    "counter": ("counter_melody", "harmony", "melody", "texture", "color", "accent"),
}

_TRACKER_ROLE_ALLOWED_VOICES = {
    "melody": frozenset({"pluck", "bowed", "bell", "kotekan"}),
    "bass": frozenset({"gong", "pluck", "tabla_ge", "tabla_tin", "kotekan", "bowed"}),
    "color": frozenset({"breath", "grain", "choir"}),
    "counter": frozenset({"bell", "metal", "bowed", "choir", "grain", "kotekan"}),
    "sample": frozenset({"sample_grain", "sample_slice", "sample_freeze", "sample_window"}),
}

_TRACKER_ROLE_SAFE_REMAP = {
    ("bass", "pad"): "bowed",
    ("color", "bell"): "breath",
    ("color", "metal"): "breath",
    ("color", "pad"): "breath",
    ("counter", "pad"): "choir",
}

_TRACKER_ROLE_FALLBACK_VOICE = {
    "melody": "pluck",
    "bass": "bowed",
    "color": "breath",
    "counter": "choir",
    "sample": "sample_grain",
}

_CADENCE_ROLE_SAFE_REMAP = {
    "sleep": {
        ("melody", "pluck"): "bowed",
        ("melody", "kotekan"): "bowed",
        ("melody", "bell"): "bowed",
        ("bass", "pluck"): "bowed",
        ("bass", "kotekan"): "bowed",
        ("bass", "tabla_tin"): "bowed",
        ("color", "grain"): "breath",
        ("color", "choir"): "breath",
        ("counter", "bell"): "choir",
        ("counter", "metal"): "choir",
        ("counter", "kotekan"): "bowed",
    },
    "wind_down": {
        ("melody", "pluck"): "bowed",
        ("melody", "kotekan"): "bowed",
        ("melody", "bell"): "bowed",
        ("bass", "pluck"): "bowed",
        ("bass", "kotekan"): "bowed",
        ("color", "grain"): "breath",
        ("counter", "bell"): "choir",
        ("counter", "metal"): "choir",
        ("counter", "kotekan"): "bowed",
    },
}

_SCENE_MOTIF_RECALL = {
    "Recap": (("Theme", "Arrival"), "answer"),
    "Release": (("Theme", "Arrival"), "answer"),
    "Afterglow": (("Recap", "Release", "Theme"), "echo"),
}

_RHYTHM_TO_ARRANGEMENT_CURVE = {
    "sparse_breath": "emergence_breath",
    "steady_statement": "statement_swell",
    "forward_push": "forward_lift",
    "arrival_drive": "arrival_peak",
    "refrain_pulse": "statement_swell",
    "syncopated_fragment": "development_rise",
    "half_time_displacement": "bridge_suspension",
    "call_response": "response_wave",
    "recall_groove": "recap_release",
    "liquidation_slowdown": "resolution_fade",
    "residue_breath": "residue_fade",
}

_SCENE_TO_ARRANGEMENT_CURVE = {
    "Emergence": "emergence_breath",
    "Theme": "statement_swell",
    "Lift": "forward_lift",
    "Arrival": "arrival_peak",
    "Development": "development_rise",
    "Bridge": "bridge_suspension",
    "Recap": "recap_release",
    "Release": "resolution_fade",
    "Resolution": "resolution_fade",
    "Afterglow": "residue_fade",
}

_AUTOMATION_CURVE_FACTORS = {
    "emergence_breath": {
        "density": (0.55, 0.82, 1.0),
        "master_amp": (0.82, 0.94, 1.0),
        "reverb_send": (1.2, 1.05, 0.9),
    },
    "statement_swell": {
        "density": (0.88, 1.04, 0.98),
        "master_amp": (0.92, 1.03, 1.0),
        "reverb_send": (0.95, 1.0, 1.06),
    },
    "forward_lift": {
        "density": (0.78, 1.02, 1.16),
        "master_amp": (0.9, 1.02, 1.08),
        "reverb_send": (0.92, 0.98, 1.05),
    },
    "arrival_peak": {
        "density": (0.9, 1.12, 1.02),
        "master_amp": (0.96, 1.1, 1.02),
        "reverb_send": (0.82, 0.92, 1.08),
    },
    "development_rise": {
        "density": (0.68, 1.0, 1.18),
        "master_amp": (0.86, 1.0, 1.08),
        "reverb_send": (0.86, 1.0, 1.18),
    },
    "bridge_suspension": {
        "density": (0.92, 0.68, 0.94),
        "master_amp": (0.94, 0.82, 0.92),
        "reverb_send": (1.02, 1.22, 1.34),
    },
    "response_wave": {
        "density": (0.72, 1.08, 0.86),
        "master_amp": (0.88, 1.04, 0.96),
        "reverb_send": (0.96, 1.1, 1.16),
    },
    "recap_release": {
        "density": (0.96, 1.02, 0.78),
        "master_amp": (1.02, 1.0, 0.88),
        "reverb_send": (0.92, 1.05, 1.2),
    },
    "resolution_fade": {
        "density": (0.9, 0.62, 0.42),
        "master_amp": (0.96, 0.78, 0.58),
        "reverb_send": (1.02, 1.18, 1.36),
    },
    "residue_fade": {
        "density": (0.78, 0.46, 0.24),
        "master_amp": (0.86, 0.64, 0.42),
        "reverb_send": (1.12, 1.34, 1.5),
    },
}

_STEP_VELOCITY_CURVES = {
    "emergence_breath": (0.82, 0.94, 1.0),
    "statement_swell": (0.94, 1.04, 1.0),
    "forward_lift": (0.9, 1.02, 1.1),
    "arrival_peak": (0.98, 1.12, 1.04),
    "development_rise": (0.9, 1.02, 1.14),
    "bridge_suspension": (0.94, 0.78, 0.9),
    "response_wave": (0.88, 1.06, 0.94),
    "recap_release": (1.0, 1.02, 0.86),
    "resolution_fade": (0.92, 0.74, 0.54),
    "residue_fade": (0.8, 0.54, 0.34),
}

_AUTOMATION_BOUNDS = {
    "density": (0.02, 1.0),
    "master_amp": (0.05, 1.0),
    "reverb_send": (0.0, 0.8),
}


@dataclass
class TrackerStep:
    """A quantized note event within a lane."""

    row: int
    length_rows: int
    scale_degree: int
    velocity: float
    accent: bool = False
    octave_shift: int = 0
    metadata: dict[str, str] = field(default_factory=dict)


@dataclass
class TrackerLane:
    """One track/lane of notes in a tracker pattern."""

    name: str
    role: str
    voice: str
    steps: list[TrackerStep]
    metadata: dict[str, str] = field(default_factory=dict)


@dataclass
class AutomationLane:
    """A per-scene automation lane such as density or master_amp."""

    name: str
    default: float
    points: list[tuple[int, float]] = field(default_factory=list)


@dataclass
class TrackerPattern:
    """A set of lanes sharing the same row grid."""

    rows: int
    lanes: list[TrackerLane]
    automation: list[AutomationLane] = field(default_factory=list)


@dataclass
class SceneConstraint:
    """Hard limits the runtime scheduler should respect."""

    max_polyphony: int
    allowed_roles: tuple[str, ...]


@dataclass
class TrackerScene:
    """A quantized scene that can be scheduled deterministically."""

    name: str
    key: str
    tempo_bpm: float
    rows_per_beat: int
    pattern: TrackerPattern
    constraints: SceneConstraint
    metadata: dict[str, str] = field(default_factory=dict)


@dataclass
class TrackerSong:
    """A multi-scene tracker song plan."""

    title: str
    scenes: list[TrackerScene]
    metadata: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class SceneTemplate:
    """High-level scene template matching the current solo form."""

    name: str
    allowed_roles: tuple[str, ...]
    tempo_multiplier: float
    max_polyphony: int
    automation_defaults: Mapping[str, float]
    length_multiplier: float = 1.0
    repeat_count: int = 1


KORSAKOV_TRACKER_FORM: tuple[SceneTemplate, ...] = (
    SceneTemplate(
        name="Emergence",
        allowed_roles=("bass", "melody"),
        tempo_multiplier=0.92,
        max_polyphony=2,
        automation_defaults={"density": 0.2, "master_amp": 0.52, "reverb_send": 0.1},
    ),
    SceneTemplate(
        name="Theme",
        allowed_roles=("bass", "melody", "color"),
        tempo_multiplier=1.0,
        max_polyphony=3,
        automation_defaults={"density": 0.45, "master_amp": 0.65, "reverb_send": 0.14},
    ),
    SceneTemplate(
        name="Development",
        allowed_roles=("bass", "melody", "counter", "color"),
        tempo_multiplier=1.08,
        max_polyphony=5,
        automation_defaults={"density": 0.78, "master_amp": 0.72, "reverb_send": 0.18},
    ),
    SceneTemplate(
        name="Recap",
        allowed_roles=("bass", "melody", "counter", "color"),
        tempo_multiplier=0.96,
        max_polyphony=3,
        automation_defaults={"density": 0.4, "master_amp": 0.58, "reverb_send": 0.16},
    ),
    SceneTemplate(
        name="Resolution",
        allowed_roles=("melody", "color"),
        tempo_multiplier=0.84,
        max_polyphony=2,
        automation_defaults={"density": 0.15, "master_amp": 0.42, "reverb_send": 0.12},
    ),
)

TRACKER_FAMILY_FORMS: dict[str, tuple[SceneTemplate, ...]] = {
    "default": KORSAKOV_TRACKER_FORM,
    "nocturne": (
        SceneTemplate(
            name="Emergence",
            allowed_roles=("melody", "color"),
            tempo_multiplier=0.82,
            max_polyphony=2,
            automation_defaults={"density": 0.1, "master_amp": 0.38, "reverb_send": 0.18},
        ),
        SceneTemplate(
            name="Theme",
            allowed_roles=("bass", "melody", "color"),
            tempo_multiplier=0.88,
            max_polyphony=2,
            automation_defaults={"density": 0.16, "master_amp": 0.44, "reverb_send": 0.2},
        ),
        SceneTemplate(
            name="Development",
            allowed_roles=("bass", "melody", "color"),
            tempo_multiplier=0.92,
            max_polyphony=3,
            automation_defaults={"density": 0.2, "master_amp": 0.48, "reverb_send": 0.22},
        ),
        SceneTemplate(
            name="Recap",
            allowed_roles=("bass", "melody", "color"),
            tempo_multiplier=0.86,
            max_polyphony=2,
            automation_defaults={"density": 0.14, "master_amp": 0.4, "reverb_send": 0.2},
        ),
        SceneTemplate(
            name="Resolution",
            allowed_roles=("melody", "color"),
            tempo_multiplier=0.78,
            max_polyphony=2,
            automation_defaults={"density": 0.08, "master_amp": 0.34, "reverb_send": 0.24},
        ),
    ),
    "ember": (
        SceneTemplate(
            name="Emergence",
            allowed_roles=("bass", "melody"),
            tempo_multiplier=0.9,
            max_polyphony=2,
            automation_defaults={"density": 0.18, "master_amp": 0.46, "reverb_send": 0.12},
        ),
        SceneTemplate(
            name="Theme",
            allowed_roles=("bass", "melody", "color"),
            tempo_multiplier=0.98,
            max_polyphony=3,
            automation_defaults={"density": 0.34, "master_amp": 0.56, "reverb_send": 0.14},
        ),
        SceneTemplate(
            name="Development",
            allowed_roles=("bass", "melody", "counter", "color"),
            tempo_multiplier=1.04,
            max_polyphony=4,
            automation_defaults={"density": 0.52, "master_amp": 0.62, "reverb_send": 0.16},
        ),
        SceneTemplate(
            name="Recap",
            allowed_roles=("bass", "melody", "color"),
            tempo_multiplier=0.94,
            max_polyphony=3,
            automation_defaults={"density": 0.3, "master_amp": 0.5, "reverb_send": 0.16},
        ),
        SceneTemplate(
            name="Resolution",
            allowed_roles=("melody", "color"),
            tempo_multiplier=0.86,
            max_polyphony=2,
            automation_defaults={"density": 0.12, "master_amp": 0.38, "reverb_send": 0.18},
        ),
    ),
    "drift": (
        SceneTemplate(
            name="Emergence",
            allowed_roles=("bass", "melody"),
            tempo_multiplier=0.9,
            max_polyphony=2,
            automation_defaults={"density": 0.16, "master_amp": 0.48, "reverb_send": 0.14},
        ),
        SceneTemplate(
            name="Theme",
            allowed_roles=("bass", "melody", "color"),
            tempo_multiplier=0.98,
            max_polyphony=3,
            automation_defaults={"density": 0.3, "master_amp": 0.58, "reverb_send": 0.18},
        ),
        SceneTemplate(
            name="Development",
            allowed_roles=("bass", "melody", "counter", "color"),
            tempo_multiplier=1.03,
            max_polyphony=4,
            automation_defaults={"density": 0.5, "master_amp": 0.64, "reverb_send": 0.2},
        ),
        SceneTemplate(
            name="Recap",
            allowed_roles=("bass", "melody", "counter", "color"),
            tempo_multiplier=0.95,
            max_polyphony=3,
            automation_defaults={"density": 0.28, "master_amp": 0.54, "reverb_send": 0.19},
        ),
        SceneTemplate(
            name="Resolution",
            allowed_roles=("melody", "color"),
            tempo_multiplier=0.88,
            max_polyphony=2,
            automation_defaults={"density": 0.1, "master_amp": 0.4, "reverb_send": 0.2},
        ),
    ),
    "bloom": (
        SceneTemplate(
            name="Emergence",
            allowed_roles=("bass", "melody", "color"),
            tempo_multiplier=0.96,
            max_polyphony=3,
            automation_defaults={"density": 0.26, "master_amp": 0.54, "reverb_send": 0.18},
        ),
        SceneTemplate(
            name="Theme",
            allowed_roles=("bass", "melody", "counter", "color"),
            tempo_multiplier=1.04,
            max_polyphony=4,
            automation_defaults={"density": 0.5, "master_amp": 0.66, "reverb_send": 0.2},
        ),
        SceneTemplate(
            name="Development",
            allowed_roles=("bass", "melody", "counter", "color"),
            tempo_multiplier=1.1,
            max_polyphony=5,
            automation_defaults={"density": 0.68, "master_amp": 0.72, "reverb_send": 0.22},
        ),
        SceneTemplate(
            name="Recap",
            allowed_roles=("bass", "melody", "counter", "color"),
            tempo_multiplier=1.0,
            max_polyphony=4,
            automation_defaults={"density": 0.44, "master_amp": 0.62, "reverb_send": 0.2},
        ),
        SceneTemplate(
            name="Resolution",
            allowed_roles=("melody", "color"),
            tempo_multiplier=0.92,
            max_polyphony=2,
            automation_defaults={"density": 0.16, "master_amp": 0.46, "reverb_send": 0.22},
        ),
    ),
    "pulse": (
        SceneTemplate(
            name="Emergence",
            allowed_roles=("bass", "melody"),
            tempo_multiplier=1.0,
            max_polyphony=2,
            automation_defaults={"density": 0.3, "master_amp": 0.58, "reverb_send": 0.08},
        ),
        SceneTemplate(
            name="Theme",
            allowed_roles=("bass", "melody", "counter", "color"),
            tempo_multiplier=1.08,
            max_polyphony=4,
            automation_defaults={"density": 0.58, "master_amp": 0.7, "reverb_send": 0.1},
        ),
        SceneTemplate(
            name="Development",
            allowed_roles=("bass", "melody", "counter", "color"),
            tempo_multiplier=1.18,
            max_polyphony=5,
            automation_defaults={"density": 0.82, "master_amp": 0.78, "reverb_send": 0.12},
        ),
        SceneTemplate(
            name="Recap",
            allowed_roles=("bass", "melody", "counter", "color"),
            tempo_multiplier=1.06,
            max_polyphony=4,
            automation_defaults={"density": 0.52, "master_amp": 0.68, "reverb_send": 0.12},
        ),
        SceneTemplate(
            name="Resolution",
            allowed_roles=("melody", "color"),
            tempo_multiplier=0.96,
            max_polyphony=2,
            automation_defaults={"density": 0.22, "master_amp": 0.5, "reverb_send": 0.1},
        ),
    ),
    "forge": (
        SceneTemplate(
            name="Emergence",
            allowed_roles=("bass", "melody", "color"),
            tempo_multiplier=1.02,
            max_polyphony=3,
            automation_defaults={"density": 0.36, "master_amp": 0.6, "reverb_send": 0.1},
        ),
        SceneTemplate(
            name="Theme",
            allowed_roles=("bass", "melody", "counter", "color"),
            tempo_multiplier=1.12,
            max_polyphony=4,
            automation_defaults={"density": 0.64, "master_amp": 0.72, "reverb_send": 0.12},
        ),
        SceneTemplate(
            name="Development",
            allowed_roles=("bass", "melody", "counter", "color"),
            tempo_multiplier=1.26,
            max_polyphony=5,
            automation_defaults={"density": 0.9, "master_amp": 0.82, "reverb_send": 0.14},
        ),
        SceneTemplate(
            name="Recap",
            allowed_roles=("bass", "melody", "counter", "color"),
            tempo_multiplier=1.08,
            max_polyphony=4,
            automation_defaults={"density": 0.56, "master_amp": 0.7, "reverb_send": 0.14},
        ),
        SceneTemplate(
            name="Resolution",
            allowed_roles=("melody", "color"),
            tempo_multiplier=0.94,
            max_polyphony=2,
            automation_defaults={"density": 0.2, "master_amp": 0.48, "reverb_send": 0.12},
        ),
    ),
}

# Scene-level spatial automation defaults.  These express spatial *intent*
# per tracker scene name.  Values are merged into automation_defaults when a
# template doesn't already carry them, so family-specific overrides can
# still be set directly on individual SceneTemplate automation_defaults.
_SCENE_SPATIAL_DEFAULTS: dict[str, dict[str, float]] = {
    "Emergence": {"stereo_width": 0.8, "depth": 0.7, "delay_send": 0.0},
    "Theme": {"stereo_width": 0.6, "depth": 0.5, "delay_send": 0.08},
    "Lift": {"stereo_width": 0.55, "depth": 0.45, "delay_send": 0.1},
    "Arrival": {"stereo_width": 0.45, "depth": 0.35, "delay_send": 0.1},
    "Development": {"stereo_width": 0.45, "depth": 0.35, "delay_send": 0.1},
    "Bridge": {"stereo_width": 0.55, "depth": 0.5, "delay_send": 0.08},
    "Recap": {"stereo_width": 0.55, "depth": 0.45, "delay_send": 0.08},
    "Release": {"stereo_width": 0.65, "depth": 0.6, "delay_send": 0.12},
    "Resolution": {"stereo_width": 0.75, "depth": 0.7, "delay_send": 0.15},
    "Afterglow": {"stereo_width": 0.8, "depth": 0.75, "delay_send": 0.18},
}


def _variant_scene(
    template: SceneTemplate,
    *,
    name: str | None = None,
    tempo_multiplier: float | None = None,
    max_polyphony: int | None = None,
    density_scale: float = 1.0,
    master_amp_scale: float = 1.0,
    reverb_add: float = 0.0,
    length_multiplier: float | None = None,
) -> SceneTemplate:
    automation = dict(template.automation_defaults)
    if "density" in automation:
        automation["density"] = round(automation["density"] * density_scale, 3)
    if "master_amp" in automation:
        automation["master_amp"] = round(automation["master_amp"] * master_amp_scale, 3)
    if "reverb_send" in automation:
        automation["reverb_send"] = round(automation["reverb_send"] + reverb_add, 3)
    return replace(
        template,
        name=name or template.name,
        tempo_multiplier=tempo_multiplier or template.tempo_multiplier,
        max_polyphony=max_polyphony or template.max_polyphony,
        automation_defaults=automation,
        length_multiplier=length_multiplier if length_multiplier is not None else template.length_multiplier,
        repeat_count=template.repeat_count,
    )


def _bridge_variant(base: tuple[SceneTemplate, ...]) -> tuple[SceneTemplate, ...]:
    development = base[min(2, len(base) - 1)]
    bridge = _variant_scene(
        development,
        name="Bridge",
        tempo_multiplier=round(development.tempo_multiplier * 0.93, 3),
        max_polyphony=max(2, development.max_polyphony - 1),
        density_scale=0.72,
        master_amp_scale=0.92,
        reverb_add=0.02,
        length_multiplier=0.78,
    )
    return (
        _variant_scene(base[0], length_multiplier=1.08),
        _variant_scene(base[1], length_multiplier=1.04),
        _variant_scene(base[2], length_multiplier=0.92),
        bridge,
        _variant_scene(base[3], length_multiplier=0.96),
        _variant_scene(base[4], length_multiplier=1.18),
    )


def _concise_variant(base: tuple[SceneTemplate, ...]) -> tuple[SceneTemplate, ...]:
    return (
        _variant_scene(base[0], name="Arrival", length_multiplier=0.82, density_scale=0.92),
        _variant_scene(base[1], length_multiplier=0.9),
        _variant_scene(base[2], length_multiplier=0.94),
        _variant_scene(base[4], name="Release", length_multiplier=0.86, density_scale=0.86),
    )


def _afterglow_variant(base: tuple[SceneTemplate, ...]) -> tuple[SceneTemplate, ...]:
    afterglow = _variant_scene(
        base[4],
        name="Afterglow",
        tempo_multiplier=round(base[4].tempo_multiplier * 0.9, 3),
        max_polyphony=1,
        density_scale=0.65,
        master_amp_scale=0.82,
        reverb_add=0.03,
        length_multiplier=0.74,
    )
    return (
        _variant_scene(base[0], length_multiplier=1.14),
        _variant_scene(base[1], length_multiplier=1.02),
        _variant_scene(base[2], length_multiplier=1.1),
        _variant_scene(base[3], length_multiplier=0.92),
        _variant_scene(base[4], length_multiplier=0.88),
        afterglow,
    )


def tracker_form_for_family(
    family_name: str,
    *,
    song_num: int = 0,
    variant_hint: str = "",
) -> tuple[SceneTemplate, ...]:
    """Return the scene template set for one tracker family."""

    base = TRACKER_FAMILY_FORMS.get(family_name, KORSAKOV_TRACKER_FORM)
    if variant_hint == "bridge":
        return _bridge_variant(base)
    if variant_hint == "concise":
        return _concise_variant(base)
    if variant_hint == "afterglow":
        return _afterglow_variant(base)
    if variant_hint == "base":
        return base
    if song_num <= 0:
        return base

    variant_index = (song_num - 1) % 4
    if variant_index == 1:
        return _bridge_variant(base)
    if variant_index == 2:
        return _concise_variant(base)
    if variant_index == 3:
        return _afterglow_variant(base)
    return base


def rows_for_beats(duration_beats: float, rows_per_beat: int = 4) -> int:
    """Quantize beat durations to tracker rows."""

    rows = int(round(duration_beats * rows_per_beat))
    return max(1, rows)


# Default per-role lane phase offsets in tracker rows (bass, melody, counter, color, texture).
# Bass anchors on row 0; other lanes stagger by 1-3 rows to create polyrhythmic-cross feel
# without changing absolute note durations. Bass is exempted in _quantize_phrase_to_lane.
DEFAULT_LANE_PHASE_OFFSETS: tuple[int, ...] = (0, 1, 2, 3, 1)


def _parse_lane_phase_offsets(value: object) -> tuple[int, ...]:
    """Parse 'groove_lane_phase_offsets' metadata: '0,1,2,3,1' → (0,1,2,3,1)."""
    if not value:
        return ()
    if isinstance(value, (list, tuple)):
        try:
            return tuple(max(0, int(v)) for v in value)
        except (TypeError, ValueError):
            return ()
    text = str(value).strip()
    if not text:
        return ()
    parts: list[int] = []
    for raw in text.split(","):
        raw = raw.strip()
        if not raw:
            continue
        try:
            parts.append(max(0, int(raw)))
        except ValueError:
            return ()
    return tuple(parts)


def _clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def _arrangement_curve_for_scene(scene_name: str, metadata: Mapping[str, str]) -> str:
    rhythm_development = str(metadata.get("rhythm_development", "") or "")
    if rhythm_development in _RHYTHM_TO_ARRANGEMENT_CURVE:
        return _RHYTHM_TO_ARRANGEMENT_CURVE[rhythm_development]
    return _SCENE_TO_ARRANGEMENT_CURVE.get(scene_name, "statement_swell")


def _curve_value(position: float, values: tuple[float, float, float]) -> float:
    bounded = _clamp(position, 0.0, 1.0)
    start, middle, end = values
    if bounded <= 0.5:
        return start + ((middle - start) * (bounded / 0.5))
    return middle + ((end - middle) * ((bounded - 0.5) / 0.5))


def _automation_curve_points(
    *,
    lane_name: str,
    default: float,
    rows: int,
    curve_name: str,
) -> list[tuple[int, float]]:
    factors = _AUTOMATION_CURVE_FACTORS.get(curve_name, {}).get(lane_name)
    if factors is None:
        return [(0, round(default, 3))]

    lower, upper = _AUTOMATION_BOUNDS.get(lane_name, (0.0, 1.0))
    last_row = max(0, rows - 1)
    midpoint = last_row // 2
    raw_points = (
        (0, default * factors[0]),
        (midpoint, default * factors[1]),
        (last_row, default * factors[2]),
    )
    points: list[tuple[int, float]] = []
    for row, value in raw_points:
        point = (row, round(_clamp(float(value), lower, upper), 3))
        if points and points[-1][0] == row:
            points[-1] = point
        else:
            points.append(point)
    return points


def _arrangement_step_position(step: TrackerStep, *, start_row: int, end_row: int) -> float:
    span = max(1, end_row - start_row)
    if end_row <= start_row:
        return 0.0
    return _clamp((step.row + step.length_rows - start_row) / span, 0.0, 1.0)


def _arrangement_register_delta(curve_name: str, role: str, step: TrackerStep, position: float) -> int:
    if curve_name in {"bridge_suspension", "resolution_fade", "residue_fade"}:
        if role in {"melody", "counter"} and (position >= 0.5 or step.scale_degree >= 6):
            return -1
        if role == "color" and position >= 0.5:
            return -1
    return 0


def _shape_step_for_arrangement(
    step: TrackerStep,
    *,
    role: str,
    start_row: int,
    end_row: int,
    curve_name: str,
) -> TrackerStep:
    position = _arrangement_step_position(step, start_row=start_row, end_row=end_row)
    velocity_curve = _STEP_VELOCITY_CURVES.get(curve_name, _STEP_VELOCITY_CURVES["statement_swell"])
    velocity_scale = _curve_value(position, velocity_curve)
    velocity = round(_clamp(step.velocity * velocity_scale, 0.04, 1.0), 3)
    register_delta = _arrangement_register_delta(curve_name, role, step, position)
    metadata = {
        **step.metadata,
        "arrangement_curve": curve_name,
        "arrangement_position": f"{position:.3f}",
        "arrangement_velocity_scale": f"{velocity_scale:.3f}",
    }
    if register_delta:
        metadata["arrangement_register_delta"] = str(register_delta)
    return replace(
        step,
        velocity=velocity,
        octave_shift=step.octave_shift + register_delta,
        metadata=metadata,
    )


def _apply_arrangement_curve_to_lanes(
    lanes: Sequence[TrackerLane],
    *,
    rows: int,
    curve_name: str,
) -> list[TrackerLane]:
    shaped: list[TrackerLane] = []
    for lane in lanes:
        start_row = min((step.row for step in lane.steps), default=0)
        end_row = max((step.row + step.length_rows for step in lane.steps), default=rows)
        shaped.append(
            replace(
                lane,
                steps=[
                    _shape_step_for_arrangement(
                        step,
                        role=lane.role,
                        start_row=start_row,
                        end_row=end_row,
                        curve_name=curve_name,
                    )
                    for step in lane.steps
                ],
            )
        )
    return shaped


def _metadata_json_map(value: str | None) -> dict[str, str]:
    if not value:
        return {}
    try:
        data = json.loads(value)
    except (TypeError, ValueError):
        return {}
    if not isinstance(data, Mapping):
        return {}
    return {str(key): str(item) for key, item in data.items()}


def _metadata_int_tuple(value: str | None) -> tuple[int, ...]:
    if not value:
        return ()
    try:
        data = json.loads(value)
    except (TypeError, ValueError):
        return ()
    if not isinstance(data, Sequence) or isinstance(data, (str, bytes)):
        return ()
    parsed: list[int] = []
    for item in data:
        try:
            parsed.append(int(item))
        except (TypeError, ValueError):
            continue
    return tuple(parsed)


def _ensemble_role_metadata(
    score_metadata: Mapping[str, str],
    scene_metadata: Mapping[str, str] | None = None,
) -> dict[str, str]:
    scene_metadata = scene_metadata or {}
    lead_role = (
        scene_metadata.get("current_lead_role")
        or scene_metadata.get("ensemble_lead_role")
        or score_metadata.get("current_lead_role")
        or score_metadata.get("ensemble_lead_role")
        or "cypherclaw"
    )
    support_role = (
        scene_metadata.get("current_support_role")
        or scene_metadata.get("ensemble_support_role")
        or score_metadata.get("current_support_role")
        or score_metadata.get("ensemble_support_role")
        or "none"
    )
    return {
        "current_lead_role": str(lead_role),
        "current_support_role": str(support_role),
        "ensemble_lead_role": str(lead_role),
        "ensemble_support_role": str(support_role),
    }


def _phrase_total_beats(phrase: Phrase) -> float:
    return sum(note.duration_beats for note in phrase.notes)


def _energy_hint(score: Score, mood: Mapping[str, float] | None) -> float:
    if mood is not None:
        energy = mood.get("energy")
        if isinstance(energy, (int, float)):
            return _clamp(float(energy), 0.0, 1.0)

    if score.mood in _MOOD_TO_ENERGY:
        return _MOOD_TO_ENERGY[score.mood]

    return _clamp((score.tempo_bpm - 50.0) / 90.0, 0.0, 1.0)


def _select_progression(score: Score, energy: float) -> list[int]:
    is_minor = is_minorish_key(score.key)
    if ":mixolydian" in score.key:
        if energy >= 0.7:
            return [1, 7, 4, 1]
        if energy >= 0.4:
            return [1, 7, 4, 5]
        return [1, 4, 1, 7]
    if ":lydian" in score.key:
        if energy >= 0.7:
            return [1, 2, 5, 1]
        if energy >= 0.4:
            return [1, 2, 4, 1]
        return [1, 5, 2, 1]
    if ":dorian" in score.key:
        if energy >= 0.7:
            return [1, 4, 7, 1]
        if energy >= 0.4:
            return [1, 7, 4, 1]
        return [1, 5, 1, 7]
    if energy >= 0.7:
        return [1, 6, 4, 5] if not is_minor else [1, 6, 7, 5]
    if energy >= 0.4:
        return [1, 4, 5, 1] if not is_minor else [1, 4, 7, 1]
    return [1, 5, 1, 4] if not is_minor else [1, 5, 1, 6]


def _ordered_phrases_for_tracker(phrases: Sequence[Phrase]) -> list[Phrase]:
    indexed = list(enumerate(phrases))
    indexed.sort(key=lambda pair: (_ROLE_SORT_ORDER.get(pair[1].role, 99), pair[0]))
    return [phrase for _, phrase in indexed]


def build_role_hints_from_cast(
    cast: Sequence[Mapping[str, object]],
    *,
    synth_voice_map: Mapping[str, str],
    cadence_state: str | None = None,
    family_name: str | None = None,
    occupancy_state: str | None = None,
    patch_name: str | None = None,
) -> dict[str, dict[str, str]]:
    """Translate the active CypherClaw cast into tracker role hints."""

    patch: InstrumentPatch | None = None
    if any(value is not None for value in (cadence_state, family_name, occupancy_state, patch_name)):
        patch = select_instrument_patch(
            cadence_state=cadence_state,
            family_name=family_name,
            occupancy_state=occupancy_state,
            patch_name=patch_name,
        )
    hints: dict[str, dict[str, str]] = {}
    for tracker_role, priorities in _TRACKER_ROLE_PRIORITY.items():
        for cast_role in priorities:
            match = next(
                (
                    char for char in cast
                    if char.get("role") == cast_role
                    and isinstance(char.get("synth"), str)
                    and char.get("synth") in synth_voice_map
                ),
                None,
            )
            if match is None:
                continue
            raw_voice = synth_voice_map[str(match["synth"])]
            hints[tracker_role] = {
                "voice": _normalize_tracker_voice(
                    tracker_role,
                    raw_voice,
                    cadence_state=cadence_state,
                    patch=patch,
                ),
                "character_id": str(match.get("id", "")),
                "character_role": str(match.get("role", "")),
            }
            break
    return hints


def _normalize_tracker_voice(
    role: str,
    voice: str,
    *,
    cadence_state: str | None = None,
    patch: InstrumentPatch | None = None,
) -> str:
    cadence_remap = _CADENCE_ROLE_SAFE_REMAP.get(cadence_state or "")
    if cadence_remap is not None:
        remapped = cadence_remap.get((role, voice))
        if remapped is not None:
            return remapped

    remapped = _TRACKER_ROLE_SAFE_REMAP.get((role, voice))
    if remapped is not None:
        voice = remapped

    if patch is not None:
        return normalize_patch_voice(role, voice, patch=patch)

    allowed = _TRACKER_ROLE_ALLOWED_VOICES.get(role)
    if allowed is None or voice in allowed:
        return voice
    return _TRACKER_ROLE_FALLBACK_VOICE.get(role, voice)


def _build_foundation_phrase(
    score: Score,
    melody: Phrase,
    energy: float,
    *,
    quiet: bool = False,
) -> Phrase:
    total_beats = max(4.0, _phrase_total_beats(melody))
    progression = _select_progression(score, energy)
    beats_per_chord = max(1, int(round(total_beats / max(1, len(progression)))))
    bass = generate_bass_line(score.key, progression, beats_per_chord=beats_per_chord)
    return Phrase(
        notes=bass.notes,
        voice="bowed" if quiet or energy < 0.35 else "pluck",
        dynamic="p" if quiet else ("mp" if energy < 0.6 else "mf"),
        role="bass",
    )


def _build_counter_phrase(melody: Phrase, energy: float) -> Phrase:
    counter = generate_countermelody(melody)
    return Phrase(
        notes=counter.notes,
        voice="bowed" if energy < 0.7 else "bell",
        dynamic="mp",
        role="counter",
    )


def _build_texture_phrase(score: Score, melody: Phrase, energy: float) -> Phrase:
    total_beats = max(4.0, _phrase_total_beats(melody))
    note_count = 2 if energy < 0.55 else 3
    degrees = [1, 3, 5][:note_count]
    beat_span = round(total_beats / note_count, 2)
    notes = [
        Note(scale_degree=degree, duration_beats=beat_span, accent=False)
        for degree in degrees
    ]
    return Phrase(
        notes=notes,
        voice="pad",
        dynamic="pp" if energy < 0.35 else "p",
        role="color",
    )


def syncopate_phrase(
    phrase: Phrase,
    *,
    intensity: float,
    rng_seed: int = 0,
) -> Phrase:
    """Displace on-beat hits to off-beats by inserting leading rests.

    For each note >= 1 beat with probability `intensity`, split into a
    leading rest (scale_degree=0) followed by the note shortened by the
    rest length. The rest delays the attack from the downbeat to the
    "and" of the beat — audible syncopation.

    Pure: same `phrase` + `intensity` + `rng_seed` is deterministic.
    Bass and texture get half intensity to keep the harmonic anchor
    solid; color/counter/melody get full intensity.
    """
    if intensity <= 0.0 or not phrase.notes:
        return phrase
    import random as _random

    rng = _random.Random(rng_seed or hash((phrase.role, phrase.voice, len(phrase.notes))))
    role_scale = 0.5 if phrase.role in {"bass", "texture"} else 1.0
    effective = max(0.0, min(1.0, intensity * role_scale))
    new_notes: list[Note] = []
    for note in phrase.notes:
        if (
            note.duration_beats >= 1.0
            and note.scale_degree > 0
            and rng.random() < effective
        ):
            rest_len = 0.5
            remaining = round(note.duration_beats - rest_len, 2)
            if remaining < 0.25:
                new_notes.append(note)
                continue
            new_notes.append(Note(scale_degree=0, duration_beats=rest_len, accent=False))
            new_notes.append(Note(scale_degree=note.scale_degree, duration_beats=remaining, accent=True))
        else:
            new_notes.append(note)
    if [(n.scale_degree, n.duration_beats, n.accent) for n in new_notes] == [
        (n.scale_degree, n.duration_beats, n.accent) for n in phrase.notes
    ]:
        return phrase
    metadata = dict(phrase.metadata)
    metadata.setdefault("syncopated", "true")
    return Phrase(
        notes=new_notes,
        voice=phrase.voice,
        dynamic=phrase.dynamic,
        role=phrase.role,
        metadata=metadata,
    )


# Default per-role syncopation intensity used by enrich_score_for_tracker when
# no groove-driven override is present. Bass/texture stay anchored; melody and
# counter get audible off-beat displacement.
DEFAULT_SYNCOPATION_INTENSITY: dict[str, float] = {
    "melody": 0.35,
    "counter": 0.45,
    "color": 0.30,
    "bass": 0.10,
    "texture": 0.10,
}


def enrich_score_for_tracker(
    score: Score,
    *,
    mood: Mapping[str, float] | None = None,
) -> Score:
    """Fill sparse scores into bounded multi-lane tracker material.

    The tracker wants at least a foundation and texture lane for calm states,
    while higher-energy states benefit from a countermelody lane as well.
    Sleeping states stay intentionally sparse.
    """

    if not score.phrases:
        return score

    energy = _energy_hint(score, mood)
    phrases = list(score.phrases)
    roles = {phrase.role for phrase in phrases}
    melody = next((phrase for phrase in phrases if phrase.role == "melody"), phrases[0])

    if energy >= 0.12 and "bass" not in roles:
        phrases.append(_build_foundation_phrase(score, melody, energy))
        roles.add("bass")

    if energy >= 0.55 and "counter" not in roles:
        phrases.append(_build_counter_phrase(melody, energy))
        roles.add("counter")

    if "color" not in roles:
        phrases.append(_build_texture_phrase(score, melody, energy))

    # Apply per-role syncopation. Energy-scaled: low-energy moods get less
    # displacement so calm moments stay calm.
    energy_factor = max(0.3, min(1.0, energy * 1.4))
    syncopated_phrases: list[Phrase] = []
    for phrase in phrases:
        intensity = DEFAULT_SYNCOPATION_INTENSITY.get(phrase.role, 0.0) * energy_factor
        syncopated_phrases.append(
            syncopate_phrase(phrase, intensity=intensity)
            if intensity > 0.0
            else phrase
        )

    return Score(
        phrases=_ordered_phrases_for_tracker(syncopated_phrases),
        key=score.key,
        tempo_bpm=score.tempo_bpm,
        mood=score.mood,
        created_at=score.created_at,
        metadata=dict(score.metadata),
    )


def _ensure_scene_role_floors(
    score: Score,
    template: SceneTemplate,
    *,
    mood: Mapping[str, float] | None = None,
) -> tuple[Score, tuple[str, ...]]:
    if not score.phrases:
        return score, ()

    energy = _energy_hint(score, mood)
    phrases = list(score.phrases)
    roles = {phrase.role for phrase in phrases}
    melody = next((phrase for phrase in phrases if phrase.role == "melody"), phrases[0])
    enforced_roles: list[str] = []

    for role in _SCENE_ROLE_FLOORS.get(template.name, ()):
        if role in roles:
            continue
        if role == "bass":
            phrases.append(_build_foundation_phrase(score, melody, energy, quiet=True))
        elif role == "counter":
            phrases.append(_build_counter_phrase(melody, energy))
        elif role == "color":
            phrases.append(_build_texture_phrase(score, melody, energy))
        else:
            continue
        roles.add(role)
        enforced_roles.append(role)

    return (
        Score(
            phrases=_ordered_phrases_for_tracker(phrases),
            key=score.key,
            tempo_bpm=score.tempo_bpm,
            mood=score.mood,
            created_at=score.created_at,
            metadata=dict(score.metadata),
        ),
        tuple(enforced_roles),
    )


def _velocity_for_dynamic(dynamic: str, accent: bool) -> float:
    base = _DYNAMIC_TO_VELOCITY.get(dynamic, _DYNAMIC_TO_VELOCITY["mf"])
    if accent:
        return min(1.0, round(base * 1.12, 3))
    return round(base, 3)


def _lane_name_for_role(role: str) -> str:
    return _ROLE_TO_LANE_NAME.get(role, role)


def _transform_recalled_degrees(
    role: str,
    degrees: Sequence[int],
    *,
    transform: str,
) -> list[int]:
    recalled = [int(_clamp(degree, 1, 8)) for degree in degrees]
    if not recalled:
        return recalled

    if transform == "answer":
        if role in {"melody", "counter"} and len(recalled) >= 2:
            if len(recalled) >= 3 and abs(recalled[-2] - recalled[-3]) > 2:
                direction = 1 if recalled[-2] > recalled[-3] else -1
                recalled[-2] = int(_clamp(recalled[-3] + direction, 1, 8))
            recalled[-1] = 1 if recalled[-2] <= 3 else 3
        elif role == "bass":
            recalled[-1] = 1
        return recalled

    if transform == "echo" and len(recalled) >= 2:
        recalled[-1] = recalled[-2]
    return recalled


def _recalled_steps_for_lane(
    source_lane: TrackerLane,
    *,
    target_rows: int,
    role: str,
    transform: str,
    transition_profile: Mapping[str, str] | None = None,
    section_profile: Mapping[str, str] | None = None,
) -> list[TrackerStep]:
    if not source_lane.steps:
        return []

    source_rows = max(
        (step.row + step.length_rows) for step in source_lane.steps
    )
    if source_rows <= 0:
        return []

    degrees = _transform_recalled_degrees(
        role,
        [step.scale_degree for step in source_lane.steps],
        transform=transform,
    )
    scale = max(target_rows, 1) / max(source_rows, 1)
    section_progression: tuple[int, ...] = ()
    if section_profile and section_profile.get("section_progression"):
        try:
            section_progression_raw = json.loads(section_profile["section_progression"])
        except (TypeError, ValueError):
            section_progression_raw = ()
        if isinstance(section_progression_raw, Sequence) and not isinstance(section_progression_raw, (str, bytes)):
            parsed: list[int] = []
            for value in section_progression_raw:
                try:
                    parsed.append(int(_clamp(int(value), 1, 7)))
                except (TypeError, ValueError):
                    continue
            section_progression = tuple(parsed)
    recalled_steps: list[TrackerStep] = []
    last_end = 0
    for index, (source_step, degree) in enumerate(zip(source_lane.steps, degrees)):
        row = max(last_end, int(round(source_step.row * scale)))
        if index == len(source_lane.steps) - 1:
            length_rows = max(1, target_rows - row)
        else:
            length_rows = max(1, int(round(source_step.length_rows * scale)))
            length_rows = min(length_rows, max(1, target_rows - row))
        metadata = {
            key: value
            for key, value in source_step.metadata.items()
            if not str(key).startswith("transition_")
            and key not in _SECTION_PHRASE_METADATA_KEYS
            and not str(key).startswith("section_progression_")
        }
        metadata.update(
            {
                "motif_source_row": str(source_step.row),
                "motif_transform": transform,
            }
        )
        if section_profile:
            metadata.update({str(key): str(value) for key, value in section_profile.items() if str(value).strip()})
        if section_progression:
            metadata.update(
                _section_progression_metadata_for_role(
                    role,
                    note_index=index,
                    note_count=len(source_lane.steps),
                    progression=section_progression,
                )
            )
        if transition_profile and index == len(source_lane.steps) - 1:
            metadata.update({str(key): str(value) for key, value in transition_profile.items() if str(value).strip()})
            metadata["transition_role"] = "preparation"
            metadata["transition_tail_index"] = "0"
            try:
                root_degree = int(transition_profile.get("transition_target_root_degree", "0"))
            except (TypeError, ValueError):
                root_degree = 0
            if root_degree > 0:
                degree = _transition_prepared_degree(role, root_degree, 0, 1)
        recalled_steps.append(
            replace(
                source_step,
                row=row,
                length_rows=length_rows,
                scale_degree=degree,
                metadata=metadata,
            )
        )
        last_end = row + length_rows
    return recalled_steps


def _metadata_for_lane(
    role: str,
    *,
    role_hints: Mapping[str, Mapping[str, str]] | None,
    source: str,
) -> dict[str, str]:
    metadata = {"source": source}
    if role_hints is None:
        return metadata

    hint = role_hints.get(role)
    if hint is None:
        return metadata

    for key in ("character_id", "character_role"):
        value = hint.get(key)
        if value:
            metadata[key] = value
    return metadata


def _voice_for_phrase(
    phrase: Phrase,
    *,
    role_hints: Mapping[str, Mapping[str, str]] | None,
) -> str:
    if role_hints is not None:
        hint = role_hints.get(phrase.role)
        if hint is not None and hint.get("voice"):
            return hint["voice"]
    return phrase.voice


def _shift_scale_degree(degree: int, delta: int) -> int:
    shifted = degree + delta
    while shifted < 1:
        shifted += 7
    while shifted > 8:
        shifted -= 7
    return shifted


def _voice_leading_limit(role: str) -> int:
    return _VOICE_LEADING_LIMITS.get(role, 3)


def _bounded_voice_degree(
    previous_degree: int | None,
    target_degree: int,
    *,
    max_leap: int,
) -> tuple[int, str]:
    target = int(_clamp(target_degree, 1, 8))
    if previous_degree is None:
        return target, "start"

    interval = target - previous_degree
    if abs(interval) <= max_leap:
        return target, "direct"

    bounded = previous_degree + (max_leap if interval > 0 else -max_leap)
    return int(_clamp(bounded, 1, 8)), "bounded"


def _cadence_target_degree(role: str, cadence_type: str) -> int | None:
    targets = _CADENCE_ROLE_TARGETS.get(cadence_type)
    if targets is None:
        return None
    return targets.get(role)


def _guide_tone_degree(role: str, root_degree: int) -> int:
    root = int(_clamp(root_degree, 1, 7))
    if role == "bass":
        return root
    if role == "counter":
        return _shift_scale_degree(root, 2)
    if role == "color":
        return _shift_scale_degree(root, 4)
    return _shift_scale_degree(root, 2)


def _voice_leading_metadata(
    role: str,
    *,
    previous_degree: int | None,
    target_degree: int,
    resolved_degree: int,
    status: str,
    max_leap: int,
    root_degree: int,
) -> dict[str, str]:
    interval = 0 if previous_degree is None else resolved_degree - previous_degree
    return {
        "voice_leading_role": role,
        "voice_leading_previous_degree": str(previous_degree if previous_degree is not None else resolved_degree),
        "voice_leading_target_degree": str(target_degree),
        "voice_leading_interval": str(interval),
        "voice_leading_max_leap": str(max_leap),
        "voice_leading_status": status,
        "guide_tone_degree": str(_guide_tone_degree(role, root_degree)),
    }


def _internal_phrase_family_bounds(phrase: Phrase) -> list[tuple[int, int, str]]:
    families_raw = phrase.metadata.get("internal_phrase_families") if hasattr(phrase, "metadata") else None
    lengths_raw = phrase.metadata.get("internal_phrase_family_lengths") if hasattr(phrase, "metadata") else None
    if not families_raw or not lengths_raw:
        return []
    try:
        families = json.loads(families_raw)
        lengths = json.loads(lengths_raw)
    except (TypeError, ValueError):
        return []
    if not isinstance(families, Sequence) or isinstance(families, (str, bytes)):
        return []
    if not isinstance(lengths, Sequence) or isinstance(lengths, (str, bytes)):
        return []
    bounds: list[tuple[int, int, str]] = []
    cursor = 0
    for family, length in zip(families, lengths):
        try:
            segment_length = int(length)
        except (TypeError, ValueError):
            continue
        if segment_length <= 0:
            continue
        label = str(family)
        bounds.append((cursor, cursor + segment_length, label))
        cursor += segment_length
    return bounds


def _internal_phrase_family_for_index(index: int, bounds: Sequence[tuple[int, int, str]]) -> str | None:
    for start, end, label in bounds:
        if start <= index < end:
            return label
    return None


def _internal_phrase_family_profiles(phrase: Phrase) -> dict[str, dict[str, str]]:
    profiles_raw = phrase.metadata.get("internal_phrase_family_profiles") if hasattr(phrase, "metadata") else None
    if not profiles_raw:
        return {}
    try:
        data = json.loads(profiles_raw)
    except (TypeError, ValueError):
        return {}
    if not isinstance(data, Mapping):
        return {}
    profiles: dict[str, dict[str, str]] = {}
    for label, profile in data.items():
        if not isinstance(profile, Mapping):
            continue
        profiles[str(label)] = {str(key): str(value) for key, value in profile.items()}
    return profiles


_TRANSITION_METADATA_KEYS = (
    "transition_target_scene",
    "transition_target_function",
    "transition_target_cadence",
    "transition_target_root_degree",
    "transition_motion",
    "transition_prepare_count",
    "transition_technique",
    "transition_techniques",
    "transition_continuity_elements",
    "transition_hard_cut",
    "transition_pivot_event",
    "transition_breath_rows",
    "transition_metric_ratio",
    "transition_timbral_morph",
    "transition_pivot_chord_degree",
    "transition_common_tone_degree",
)

_SECTION_PHRASE_METADATA_KEYS = (
    "motif_development",
    "motif_id",
    "rhythm_development",
    "rhythm",
    "section_function",
    "section_progression",
    "harmonic_charge",
    "melodic_charge",
    "metric_weight",
    "is_cadential",
    "contour_apex",
    "contour_apex_index",
    *VOCABULARY_METADATA_KEYS,
)

_SAMPLE_GESTURE_METADATA_KEYS = (
    "sample_gesture_voice",
    "sample_gesture_source",
    "source_kind",
    "sample_gesture_mode",
    "sample_gesture_transforms",
    "sample_gesture_density",
    "sample_gesture_max_events",
)

_ARC_METADATA_KEYS = (
    "arc_phase",
    "arc_density",
    "arc_dynamic",
    "arc_harmonic",
    "arc_rhythm",
    "arc_timbre",
    "arc_spatial",
    "arc_compression",
    "arc_senseweave",
    "arc_synthesis",
)

_PRODUCTION_COURSE_METADATA_KEYS = (
    "production_mode_scale",
    "production_harmonic_function",
    "production_meter_groove",
    "production_counterpoint_relation",
    "production_synthesis_architecture",
    "production_mix_role",
    "production_spatial_intent",
    "production_genre_strategy",
    "production_phase_profile",
    "production_transition_type",
)

_COUNTERPOINT_RELATION_TO_RULE_ID: dict[str, str] = {
    "unison_shadow": "parallel",
    "parallel_thirds": "parallel",
    "contrary_motion": "contrary",
    "oblique_pedal": "oblique",
    "imitative_canon": "echo",
}


def _resolve_counterpoint_rule_id(relation: str) -> str:
    return _COUNTERPOINT_RELATION_TO_RULE_ID.get(relation, "parallel")


def _counterpoint_metadata_for_lane(
    relation: str,
    role: str,
) -> dict[str, str]:
    rule_id = _resolve_counterpoint_rule_id(relation)
    rule = resolve_rule(rule_id)
    return {
        "counterpoint_relation": relation,
        "counterpoint_rule_id": rule.relationship_id,
        "counterpoint_max_leap": str(rule.intervals.max_leap),
        "counterpoint_preferred_intervals": json.dumps(list(rule.intervals.preferred_semitones)),
        "counterpoint_allow_parallel_fifths": str(rule.intervals.allow_parallel_fifths).lower(),
        "counterpoint_allow_unison": str(rule.intervals.allow_unison).lower(),
    }


def _transition_profile_for_phrase(phrase: Phrase) -> dict[str, str]:
    if not hasattr(phrase, "metadata"):
        return {}
    profile = {
        key: str(phrase.metadata.get(key, "") or "")
        for key in _TRANSITION_METADATA_KEYS
        if str(phrase.metadata.get(key, "") or "").strip()
    }
    if "transition_target_root_degree" not in profile:
        return {}
    return profile


def _transition_prepare_count(phrase: Phrase) -> int:
    raw = phrase.metadata.get("transition_prepare_count", "1") if hasattr(phrase, "metadata") else "1"
    try:
        count = int(raw)
    except (TypeError, ValueError):
        count = 1
    return max(1, min(count, max(1, len(phrase.notes))))


def _transition_prepared_degree(role: str, root_degree: int, tail_index: int, tail_count: int) -> int:
    final_tail = tail_index >= tail_count - 1
    if role == "bass":
        return root_degree
    if role == "melody":
        return root_degree if final_tail else _shift_scale_degree(root_degree, 2)
    if role == "counter":
        return _shift_scale_degree(root_degree, 2 if final_tail else 4)
    if role == "color":
        return root_degree if final_tail else _shift_scale_degree(root_degree, 4)
    return root_degree


def _section_progression_for_phrase(phrase: Phrase) -> tuple[int, ...]:
    raw = phrase.metadata.get("section_progression") if hasattr(phrase, "metadata") else None
    if not raw:
        return ()
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        return ()
    if not isinstance(data, Sequence) or isinstance(data, (str, bytes)):
        return ()
    progression: list[int] = []
    for value in data:
        try:
            degree = int(value)
        except (TypeError, ValueError):
            continue
        progression.append(int(_clamp(degree, 1, 7)))
    return tuple(progression)


def _section_progression_span(phrase: Phrase, progression: Sequence[int]) -> int:
    raw = phrase.metadata.get("section_progression_span", "") if hasattr(phrase, "metadata") else ""
    try:
        span = int(raw)
    except (TypeError, ValueError):
        span = 0
    if span <= 0:
        span = max(1, int(round(max(1, len(phrase.notes)) / max(1, len(progression)))))
    return max(1, span)


def _section_progression_metadata(
    phrase: Phrase,
    *,
    note_index: int,
    progression: Sequence[int],
    span: int,
) -> dict[str, str]:
    if not progression:
        return {}
    progression_index = min(len(progression) - 1, note_index // max(1, span))
    root = int(progression[progression_index])
    role = "chord_tone"
    if phrase.role == "bass" and note_index % max(1, span) == 0:
        role = "root"
    elif phrase.role == "color":
        role = "pad_tone"
    elif phrase.role == "melody" and note_index % max(1, span) == 0:
        role = "arrival_tone"
    return {
        "section_progression_index": str(progression_index),
        "section_progression_root": str(root),
        "section_progression_role": role,
    }


def _section_progression_metadata_for_role(
    role_name: str,
    *,
    note_index: int,
    note_count: int,
    progression: Sequence[int],
) -> dict[str, str]:
    if not progression:
        return {}
    span = max(1, int(round(max(1, note_count) / max(1, len(progression)))))
    progression_index = min(len(progression) - 1, note_index // span)
    root = int(progression[progression_index])
    role = "chord_tone"
    if role_name == "bass" and note_index % span == 0:
        role = "root"
    elif role_name == "color":
        role = "pad_tone"
    elif role_name == "melody" and note_index % span == 0:
        role = "arrival_tone"
    return {
        "section_progression_index": str(progression_index),
        "section_progression_root": str(root),
        "section_progression_role": role,
    }


def _lane_cycle_window(scene_name: str, role: str, repeat_count: int) -> tuple[int, int]:
    total = max(1, int(repeat_count))
    if total <= 2:
        return 0, total

    entry = 0
    exit_cycle = total
    if scene_name in {"Development", "Bridge", "Lift"}:
        if role == "counter":
            entry = max(1, total // 4)
        elif role == "color":
            entry = max(1, total // 3)
    elif scene_name == "Emergence":
        if role == "melody" and total >= 4:
            entry = 1
        elif role == "color":
            entry = max(1, total // 2)
    elif scene_name in {"Theme", "Arrival"}:
        if role == "counter":
            entry = 1
        elif role == "color" and total >= 4:
            entry = 1
    elif scene_name in {"Recap", "Release"}:
        if role == "counter":
            entry = 1
            exit_cycle = max(entry + 1, total - 1)
        elif role == "color" and total >= 5:
            entry = 1
    elif scene_name in {"Resolution", "Afterglow"} and role == "melody" and total >= 4:
        exit_cycle = max(1, total - 1)

    entry = max(0, min(entry, total - 1))
    exit_cycle = max(entry + 1, min(exit_cycle, total))
    return entry, exit_cycle


def _quantize_phrase_to_lane(
    phrase: Phrase,
    *,
    lane_name: str,
    rows_per_beat: int = 4,
    octave_shift: int = 0,
    length_multiplier: float = 1.0,
    repeat_count: int = 1,
    entry_cycle: int = 0,
    exit_cycle: int | None = None,
    role_hints: Mapping[str, Mapping[str, str]] | None = None,
    lane_source: str = "score",
    cadence_type: str = "",
    phase_offset_rows: int = 0,
) -> TrackerLane:
    """Convert a phrase into one tracker lane.

    `phase_offset_rows` shifts the lane's first attack by N rows after
    cycle start. Used by polyrhythmic groove profiles to de-align lane
    entries (e.g. bass on row 0, melody on row 1, counter on row 2).
    Bass-role lanes ignore the offset to keep the harmonic anchor solid.
    """

    steps: list[TrackerStep] = []
    total_cycles = max(1, int(repeat_count))
    active_entry_cycle = max(0, min(int(entry_cycle), total_cycles - 1))
    active_exit_cycle = total_cycles if exit_cycle is None else int(exit_cycle)
    active_exit_cycle = max(active_entry_cycle + 1, min(active_exit_cycle, total_cycles))
    note_lengths = [
        rows_for_beats(note.duration_beats * length_multiplier, rows_per_beat)
        for note in phrase.notes
    ]
    cycle_rows = sum(note_lengths)
    effective_offset = 0
    if phase_offset_rows > 0 and phrase.role != "bass" and cycle_rows > phase_offset_rows:
        effective_offset = int(phase_offset_rows)
    internal_family_bounds = _internal_phrase_family_bounds(phrase)
    internal_family_profiles = _internal_phrase_family_profiles(phrase)
    section_progression = _section_progression_for_phrase(phrase)
    section_progression_span = _section_progression_span(phrase, section_progression) if section_progression else 0
    transition_profile = _transition_profile_for_phrase(phrase)
    transition_prepare_count = _transition_prepare_count(phrase) if transition_profile else 0
    transition_root = 0
    if transition_profile:
        try:
            transition_root = int(transition_profile["transition_target_root_degree"])
        except (KeyError, TypeError, ValueError):
            transition_root = 0
    voice_limit = _voice_leading_limit(phrase.role)
    previous_degree: int | None = None
    for cycle in range(active_entry_cycle, active_exit_cycle):
        row = cycle * cycle_rows + effective_offset
        for note_index, note in enumerate(phrase.notes):
            length_rows = note_lengths[note_index]
            accent = note.accent or (cycle > 0 and note_index == 0 and phrase.role in {"melody", "bass", "counter"})
            scale_degree = note.scale_degree
            if cycle > 0 and note.scale_degree > 0:
                if phrase.role == "melody":
                    if note_index == len(phrase.notes) - 1:
                        scale_degree = _shift_scale_degree(note.scale_degree, -1 if cycle % 2 else 1)
                    elif note_index % 2 == 1:
                        scale_degree = _shift_scale_degree(note.scale_degree, 1 if cycle % 2 else -1)
                elif phrase.role == "bass" and note_index % 2 == 1:
                    scale_degree = _shift_scale_degree(note.scale_degree, 2 if cycle % 2 else 4)
                elif phrase.role == "counter" and note_index % 2 == 0:
                    scale_degree = _shift_scale_degree(note.scale_degree, -1 if cycle % 2 else 1)
                elif phrase.role == "color" and note_index == len(phrase.notes) - 1:
                    scale_degree = _shift_scale_degree(note.scale_degree, 2 if cycle % 2 else -2)
            transition_tail_index: int | None = None
            if (
                transition_profile
                and transition_root > 0
                and cycle == total_cycles - 1
                and note_index >= len(phrase.notes) - transition_prepare_count
            ):
                transition_tail_index = note_index - (len(phrase.notes) - transition_prepare_count)
                scale_degree = _transition_prepared_degree(
                    phrase.role,
                    transition_root,
                    transition_tail_index,
                    transition_prepare_count,
                )
                accent = accent or transition_tail_index == transition_prepare_count - 1 or phrase.role in {"bass", "melody"}
            if note.scale_degree > 0:
                cadence_target: int | None = None
                raw_target_degree = scale_degree
                if (
                    cadence_type
                    and transition_tail_index is None
                    and cycle == active_exit_cycle - 1
                    and note_index == len(phrase.notes) - 1
                ):
                    cadence_target = _cadence_target_degree(phrase.role, cadence_type)
                    if cadence_target is not None:
                        raw_target_degree = cadence_target
                        accent = accent or phrase.role in {"bass", "melody"}
                scale_degree, voice_status = _bounded_voice_degree(
                    previous_degree,
                    raw_target_degree,
                    max_leap=voice_limit,
                )
                metadata = {"dynamic": phrase.dynamic}
                if total_cycles > 1:
                    metadata["repeat_cycle"] = str(cycle)
                for key in _SECTION_PHRASE_METADATA_KEYS:
                    value = phrase.metadata.get(key) if hasattr(phrase, "metadata") else None
                    if value:
                        metadata[key] = str(value)
                section_metadata: dict[str, str] = {}
                if section_progression:
                    section_metadata = _section_progression_metadata(
                        phrase,
                        note_index=note_index,
                        progression=section_progression,
                        span=section_progression_span,
                    )
                    metadata.update(section_metadata)
                root_degree = int(section_metadata.get("section_progression_root", "1") or 1)
                metadata.update(
                    _voice_leading_metadata(
                        phrase.role,
                        previous_degree=previous_degree,
                        target_degree=raw_target_degree,
                        resolved_degree=scale_degree,
                        status=voice_status,
                        max_leap=voice_limit,
                        root_degree=root_degree,
                    )
                )
                internal_family = _internal_phrase_family_for_index(note_index, internal_family_bounds)
                if internal_family is not None:
                    metadata["internal_phrase_family"] = internal_family
                    profile = internal_family_profiles.get(internal_family, {})
                    profile_root_degree = profile.get("root_degree")
                    function = profile.get("function")
                    if profile_root_degree is not None:
                        metadata["internal_family_root_degree"] = str(profile_root_degree)
                    if function:
                        metadata["internal_family_function"] = str(function)
                if transition_tail_index is not None:
                    metadata.update(transition_profile)
                    metadata["transition_role"] = "preparation"
                    metadata["transition_tail_index"] = str(transition_tail_index)
                if cadence_target is not None:
                    metadata["cadence_type"] = cadence_type
                    metadata["cadence_target_degree"] = str(cadence_target)
                    metadata["cadence_role"] = "resolution" if scale_degree == cadence_target else "approach"
                steps.append(
                    TrackerStep(
                        row=row,
                        length_rows=length_rows,
                        scale_degree=scale_degree,
                        velocity=_velocity_for_dynamic(phrase.dynamic, accent),
                        accent=accent,
                        octave_shift=octave_shift,
                        metadata=metadata,
                    )
                )
                previous_degree = scale_degree
            row += length_rows

    lane_metadata = _metadata_for_lane(
        phrase.role,
        role_hints=role_hints,
        source=lane_source,
    )
    if total_cycles > 1:
        lane_metadata["entry_cycle"] = str(active_entry_cycle)
        lane_metadata["exit_cycle"] = str(active_exit_cycle)
    lane_metadata["voice_leading"] = "bounded"
    lane_metadata["voice_leading_max_leap"] = str(voice_limit)
    if cadence_type:
        lane_metadata["cadence_type"] = cadence_type
    for key in _SECTION_PHRASE_METADATA_KEYS:
        value = phrase.metadata.get(key) if hasattr(phrase, "metadata") else None
        if value:
            lane_metadata[key] = str(value)
    return TrackerLane(
        name=lane_name,
        role=phrase.role,
        voice=_voice_for_phrase(phrase, role_hints=role_hints),
        steps=steps,
        metadata=lane_metadata,
    )


def _apply_groove_to_lanes(
    lanes: list[TrackerLane],
    *,
    profile: GrooveProfile,
    tempo_bpm: float,
    rows_per_beat: int,
    seed: int = 0,
) -> list[TrackerLane]:
    """Stamp groove metadata onto every step in *lanes*."""

    result: list[TrackerLane] = []
    for lane in lanes:
        phrase_beats = 0
        for step in lane.steps:
            phrase_beats = max(phrase_beats, step.row + step.length_rows)
        phrase_length_beats = max(1, phrase_beats // max(1, rows_per_beat))
        new_steps: list[TrackerStep] = []
        for step in lane.steps:
            beat_index = step.row // max(1, rows_per_beat)
            gmeta = groove_metadata_for_step(
                step_index=beat_index,
                profile=profile,
                tempo_bpm=tempo_bpm,
                phrase_length_beats=phrase_length_beats,
                seed=seed,
            )
            new_steps.append(
                replace(step, metadata={**step.metadata, **gmeta})
            )
        result.append(replace(lane, steps=new_steps))
    return result


def _metadata_sample_gesture(scene_metadata: Mapping[str, str] | None) -> dict[str, str]:
    if scene_metadata is None:
        return {}
    return {
        key: str(scene_metadata.get(key, "") or "")
        for key in _SAMPLE_GESTURE_METADATA_KEYS
        if str(scene_metadata.get(key, "") or "").strip()
    }


def _float_metadata(value: str, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _int_metadata(value: str, default: int) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _sample_voice_for_mode(mode: str) -> str:
    return {
        "grain_cloud": "sample_grain",
        "slice_accents": "sample_slice",
        "window_echo": "sample_window",
        "freeze_bed": "sample_freeze",
        "lowpass_wash": "sample_freeze",
        "texture_bed": "sample_freeze",
    }.get(mode, "sample_grain")


def _sample_quantum_for_mode(mode: str, rows_per_beat: int) -> tuple[int, int]:
    bar_rows = max(1, rows_per_beat * 4)
    if mode == "grain_cloud":
        return max(1, rows_per_beat * 2), max(1, rows_per_beat)
    if mode == "slice_accents":
        return max(1, rows_per_beat), max(1, rows_per_beat // 2)
    if mode == "window_echo":
        return bar_rows, max(1, rows_per_beat * 2)
    if mode in {"freeze_bed", "lowpass_wash", "texture_bed"}:
        return bar_rows * 2, bar_rows
    return bar_rows, max(1, rows_per_beat)


def _sample_gesture_lane(
    *,
    scene_name: str,
    rows: int,
    rows_per_beat: int,
    scene_metadata: Mapping[str, str] | None,
) -> TrackerLane | None:
    metadata = _metadata_sample_gesture(scene_metadata)
    if not metadata:
        return None

    mode = metadata.get("sample_gesture_mode", "grain_cloud") or "grain_cloud"
    density = _clamp(_float_metadata(metadata.get("sample_gesture_density", ""), 0.32), 0.05, 1.0)
    max_events = max(1, min(16, _int_metadata(metadata.get("sample_gesture_max_events", ""), 6)))
    quantum_rows, length_rows = _sample_quantum_for_mode(mode, max(1, rows_per_beat))
    total_rows = max(rows, quantum_rows)
    bar_rows = max(1, rows_per_beat * 4)
    requested_count = max(1, int(round((total_rows / bar_rows) * density)))
    event_count = min(max_events, requested_count)
    candidate_rows = list(range(0, total_rows, quantum_rows)) or [0]
    while len(candidate_rows) < event_count:
        candidate_rows.append(min(total_rows - 1, candidate_rows[-1] + quantum_rows))

    source = metadata.get("sample_gesture_source", "room_mic") or "room_mic"
    voice = metadata.get("sample_gesture_voice") or _sample_voice_for_mode(mode)
    transforms = metadata.get("sample_gesture_transforms", "[]") or "[]"
    lane_metadata = {
        **metadata,
        "sample_gesture_source": source,
        "sample_gesture_mode": mode,
        "sample_gesture_transforms": transforms,
        "sample_gesture_density": f"{density:.3f}",
        "sample_gesture_max_events": str(max_events),
        "source": "sample_gesture",
    }
    steps = [
        TrackerStep(
            row=row,
            length_rows=min(length_rows, max(1, total_rows - row)),
            scale_degree=1,
            velocity=round(_clamp(0.32 + density * 0.42, 0.24, 0.82), 3),
            accent=index == 0,
            metadata={
                **lane_metadata,
                "sample_gesture_index": str(index),
                "sample_trigger_key": f"{scene_name}:{mode}:{index}",
            },
        )
        for index, row in enumerate(candidate_rows[:event_count])
    ]
    return TrackerLane(
        name="sample_gesture",
        role="sample",
        voice=voice,
        steps=steps,
        metadata=lane_metadata,
    )


def build_scene_from_score(
    score: Score,
    *,
    name: str,
    scene_key: str | None = None,
    allowed_roles: Sequence[str] | None = None,
    rows_per_beat: int = 4,
    tempo_multiplier: float = 1.0,
    length_multiplier: float = 1.0,
    repeat_count: int = 1,
    max_polyphony: int = 4,
    automation_defaults: Mapping[str, float] | None = None,
    role_hints: Mapping[str, Mapping[str, str]] | None = None,
    enforced_roles: Sequence[str] = (),
    scene_metadata: Mapping[str, str] | None = None,
) -> TrackerScene:
    """Build a tracker scene by quantizing selected roles from a score."""

    allowed = tuple(allowed_roles) if allowed_roles is not None else tuple(
        dict.fromkeys(phrase.role for phrase in score.phrases)
    )
    cadence_type = str((scene_metadata or {}).get("cadence_type", "") or "")
    lanes: list[TrackerLane] = []
    lane_counts: dict[str, int] = {}

    groove_profile = groove_for_section(
        groove_state=str((scene_metadata or {}).get("groove_state", "") or ""),
        groove_identity=str((scene_metadata or {}).get("groove_identity", "") or ""),
        groove_family=str((scene_metadata or {}).get("groove_family", "") or ""),
    )
    lane_phase_offsets = _parse_lane_phase_offsets(
        (scene_metadata or {}).get("groove_lane_phase_offsets", "")
    ) or groove_profile.lane_phase_offsets or DEFAULT_LANE_PHASE_OFFSETS
    role_offset_index = {"bass": 0, "melody": 1, "counter": 2, "color": 3, "texture": 4}
    for phrase in score.phrases:
        if allowed_roles is not None and phrase.role not in allowed_roles:
            continue

        base_name = _lane_name_for_role(phrase.role)
        idx = lane_counts.get(base_name, 0)
        lane_counts[base_name] = idx + 1
        lane_name = base_name if idx == 0 else f"{base_name}_{idx + 1}"
        entry_cycle, exit_cycle = _lane_cycle_window(name, phrase.role, repeat_count)
        offset_idx = role_offset_index.get(phrase.role, 0)
        phase_offset = lane_phase_offsets[offset_idx] if offset_idx < len(lane_phase_offsets) else 0
        lanes.append(
            _quantize_phrase_to_lane(
                phrase,
                lane_name=lane_name,
                rows_per_beat=rows_per_beat,
                length_multiplier=length_multiplier,
                repeat_count=repeat_count,
                entry_cycle=entry_cycle,
                exit_cycle=exit_cycle,
                role_hints=role_hints,
                lane_source="scene_floor" if phrase.role in enforced_roles else "score",
                cadence_type=cadence_type,
                phase_offset_rows=phase_offset,
            )
        )

    counterpoint_relation = str((scene_metadata or {}).get("production_counterpoint_relation", "") or "")
    if counterpoint_relation:
        for lane in lanes:
            lane.metadata.update(_counterpoint_metadata_for_lane(counterpoint_relation, lane.role))

    total_rows = 0
    for lane in lanes:
        for step in lane.steps:
            total_rows = max(total_rows, step.row + step.length_rows)

    sample_lane = _sample_gesture_lane(
        scene_name=name,
        rows=total_rows,
        rows_per_beat=rows_per_beat,
        scene_metadata=scene_metadata,
    )
    if sample_lane is not None:
        lanes.append(sample_lane)
        if "sample" not in allowed:
            allowed = (*allowed, "sample")
        for step in sample_lane.steps:
            total_rows = max(total_rows, step.row + step.length_rows)

    metadata = {
        "source_mood": score.mood,
        "phrase_count": str(len(lanes)),
    }
    patch_name = score.metadata.get("patch_name")
    if patch_name:
        metadata["patch_name"] = patch_name
    metadata["length_multiplier"] = f"{length_multiplier:.2f}"
    metadata["repeat_count"] = str(max(1, int(repeat_count)))
    if scene_metadata:
        metadata.update({str(key): str(value) for key, value in scene_metadata.items() if str(value).strip()})
    metadata.update(_ensemble_role_metadata(score.metadata, scene_metadata))
    arrangement_curve = _arrangement_curve_for_scene(name, metadata)
    metadata["arrangement_curve"] = arrangement_curve
    lanes = _apply_arrangement_curve_to_lanes(
        lanes,
        rows=total_rows,
        curve_name=arrangement_curve,
    )
    arc_phase = str((scene_metadata or {}).get("arc_phase", "") or "")
    if arc_phase:
        _meter_policy = meter_policy_for_phase(arc_phase)
        groove_profile = replace(
            groove_profile,
            meter=_meter_policy.meter,
            subdivision=_meter_policy.subdivision,
            groove_timing=_meter_policy.groove_timing,
            phrase_breath=_meter_policy.phrase_breath,
            polyrhythm=_meter_policy.polyrhythm,
            metric_modulation=_meter_policy.metric_modulation,
        )
    transition_ratio = str((scene_metadata or {}).get("transition_metric_ratio", "") or "")
    if transition_ratio:
        groove_profile = replace(groove_profile, metric_modulation=transition_ratio)
    scene_tempo = round(score.tempo_bpm * tempo_multiplier, 2)
    lanes = _apply_groove_to_lanes(
        lanes,
        profile=groove_profile,
        tempo_bpm=scene_tempo,
        rows_per_beat=rows_per_beat,
    )
    metadata["groove_type"] = groove_profile.groove_type
    metadata["groove_section_identity"] = groove_profile.section_identity or "default"
    if groove_profile.swing_ratio != 1.0:
        metadata["groove_swing_ratio"] = f"{groove_profile.swing_ratio:.3f}"
    metadata["groove_meter"] = groove_profile.meter
    metadata["groove_subdivision"] = groove_profile.subdivision
    if groove_profile.metric_modulation:
        metadata["groove_metric_modulation"] = groove_profile.metric_modulation
    automation = [
        AutomationLane(
            name=lane_name,
            default=value,
            points=_automation_curve_points(
                lane_name=lane_name,
                default=value,
                rows=total_rows,
                curve_name=arrangement_curve,
            ),
        )
        for lane_name, value in (automation_defaults or {}).items()
    ]

    pattern = TrackerPattern(rows=total_rows, lanes=lanes, automation=automation)
    constraints = SceneConstraint(
        max_polyphony=max_polyphony,
        allowed_roles=allowed,
    )
    return TrackerScene(
        name=name,
        key=scene_key or score.key,
        tempo_bpm=round(score.tempo_bpm * tempo_multiplier, 2),
        rows_per_beat=rows_per_beat,
        pattern=pattern,
        constraints=constraints,
        metadata=metadata,
    )


def _motif_source_scene(
    scene_name: str,
    prior_scenes: Sequence[TrackerScene],
) -> tuple[TrackerScene | None, str | None]:
    config = _SCENE_MOTIF_RECALL.get(scene_name)
    if config is None:
        return None, None
    candidates, transform = config
    for candidate in candidates:
        match = next((scene for scene in prior_scenes if scene.name == candidate), None)
        if match is not None:
            return match, transform
    return None, None


def _apply_scene_motif_recall(
    scene: TrackerScene,
    *,
    source_scene: TrackerScene,
    transform: str,
) -> TrackerScene:
    source_by_role = {lane.role: lane for lane in source_scene.pattern.lanes}
    transition_profile = {
        key: scene.metadata[key]
        for key in _TRANSITION_METADATA_KEYS
        if scene.metadata.get(key)
    }
    section_profile = {
        key: scene.metadata[key]
        for key in _SECTION_PHRASE_METADATA_KEYS
        if scene.metadata.get(key)
    }
    recalled_lanes: list[TrackerLane] = []
    for lane in scene.pattern.lanes:
        source_lane = source_by_role.get(lane.role)
        if source_lane is None or not source_lane.steps:
            recalled_lanes.append(lane)
            continue
        if lane.role not in {"melody", "bass", "counter"}:
            recalled_lanes.append(lane)
            continue
        steps = _recalled_steps_for_lane(
            source_lane,
            target_rows=scene.pattern.rows,
            role=lane.role,
            transform=transform,
            transition_profile=transition_profile,
            section_profile=section_profile,
        )
        if not steps:
            recalled_lanes.append(lane)
            continue
        recalled_lanes.append(
            replace(
                lane,
                steps=steps,
                metadata={
                    **lane.metadata,
                    **section_profile,
                    "motif_source_scene": source_scene.name,
                    "motif_transform": transform,
                },
            )
        )

    return replace(
        scene,
        pattern=replace(scene.pattern, lanes=recalled_lanes),
        metadata={
            **scene.metadata,
            "motif_source_scene": source_scene.name,
            "motif_transform": transform,
        },
    )


def _apply_hook_answer_degrees(
    scene: TrackerScene,
    *,
    answer_degrees: Sequence[int],
) -> TrackerScene:
    if not answer_degrees:
        return scene
    adjusted_lanes: list[TrackerLane] = []
    changed = False
    for lane in scene.pattern.lanes:
        if lane.role not in {"melody", "counter"} or not lane.steps:
            adjusted_lanes.append(lane)
            continue
        steps = list(lane.steps)
        span = min(len(steps), len(answer_degrees))
        for index in range(span):
            target = int(_clamp(answer_degrees[index], 1, 8))
            current = steps[index].scale_degree
            next_degree = target if index == 0 else int(_clamp(round((current + target) / 2.0), 1, 8))
            if next_degree == current:
                continue
            steps[index] = replace(
                steps[index],
                scale_degree=next_degree,
                metadata={
                    **steps[index].metadata,
                    "hook_phrase_role": "answer",
                    "hook_target_degree": str(target),
                },
            )
            changed = True
        adjusted_lanes.append(
            replace(
                lane,
                steps=steps,
                metadata={
                    **lane.metadata,
                    "hook_phrase_role": "answer",
                },
            )
        )
    if not changed:
        return scene
    return replace(
        scene,
        pattern=replace(scene.pattern, lanes=adjusted_lanes),
        metadata={
            **scene.metadata,
            "hook_phrase_role": "answer",
        },
    )


def validate_scene(scene: TrackerScene) -> list[str]:
    """Return human-readable constraint violations for a scene."""

    violations: list[str] = []
    allowed_roles = set(scene.constraints.allowed_roles)
    for lane in scene.pattern.lanes:
        if allowed_roles and lane.role not in allowed_roles:
            violations.append(
                f"lane role {lane.role!r} is not allowed in scene {scene.name}"
            )

    occupancy: dict[int, int] = {}
    for lane in scene.pattern.lanes:
        for step in lane.steps:
            for row in range(step.row, step.row + step.length_rows):
                occupancy[row] = occupancy.get(row, 0) + 1

    peak_polyphony = max(occupancy.values(), default=0)
    if peak_polyphony > scene.constraints.max_polyphony:
        offending_row = min(
            row for row, count in occupancy.items() if count == peak_polyphony
        )
        violations.append(
            f"polyphony {peak_polyphony} exceeds limit "
            f"{scene.constraints.max_polyphony} at row {offending_row}"
        )
    return violations


def _lane_contour(lane: TrackerLane) -> list[float]:
    return [float(step.scale_degree) for step in lane.steps if step.scale_degree > 0]


def _lane_activity(lane: TrackerLane, total_rows: int) -> list[tuple[float, float]]:
    if total_rows <= 0:
        return []
    return [
        (step.row / total_rows, step.velocity)
        for step in lane.steps
        if step.scale_degree > 0
    ]


_ROLE_REGISTER_DEFAULTS: dict[str, tuple[int, int]] = {
    "bass": (36, 55),
    "counter": (55, 67),
    "melody": (62, 82),
    "color": (82, 102),
    "sample": (48, 84),
}


def _lane_register_band(lane: TrackerLane) -> RegisterBand | None:
    degrees = [step.scale_degree for step in lane.steps if step.scale_degree > 0]
    if not degrees:
        return None
    low, high = _ROLE_REGISTER_DEFAULTS.get(lane.role, (60, 84))
    return RegisterBand(voice=lane.name, low_midi=low, high_midi=high)


def validate_scene_counterpoint(scene: TrackerScene) -> list[str]:
    """Check the three counterpoint acceptance criteria for a scene."""
    violations: list[str] = []
    note_lanes = [lane for lane in scene.pattern.lanes if lane.role != "sample"]
    if len(note_lanes) < 2:
        return violations

    contours: dict[str, list[float]] = {}
    for lane in note_lanes:
        contour = _lane_contour(lane)
        if len(contour) >= 2:
            contours[lane.name] = contour
    if len(contours) >= 2 and not contours_independent(contours):
        violations.append(f"scene {scene.name}: lanes have locked contours (not independent)")

    total_rows = scene.pattern.rows
    activity: dict[str, list[tuple[float, float]]] = {}
    for lane in note_lanes:
        points = _lane_activity(lane, total_rows)
        if points:
            activity[lane.name] = points
    if len(activity) >= 2 and not climaxes_staggered(activity):
        violations.append(f"scene {scene.name}: lane climaxes are not staggered")

    bands: list[RegisterBand] = []
    for lane in note_lanes:
        band = _lane_register_band(lane)
        if band is not None:
            bands.append(band)
    if len(bands) >= 2 and register_crowding_detected(bands):
        violations.append(f"scene {scene.name}: register crowding detected between lanes")

    return violations


def build_korsakov_tracker_song(
    score: Score,
    *,
    title: str = "CypherClaw Tracker Form",
    rows_per_beat: int = 4,
    mood: Mapping[str, float] | None = None,
    role_hints: Mapping[str, Mapping[str, str]] | None = None,
    form_templates: Sequence[SceneTemplate] | None = None,
    family_name: str | None = None,
    scene_keys: Mapping[str, str] | None = None,
    scene_scores: Mapping[str, Score] | None = None,
) -> TrackerSong:
    """Project one phrase-level score onto the current five-movement form."""

    templates = tuple(form_templates) if form_templates is not None else KORSAKOV_TRACKER_FORM
    patch_name = str(score.metadata.get("patch_name", "") or "")
    progression_profile = str(score.metadata.get("progression_profile", "") or "")
    cadence_state = str(score.metadata.get("cadence_state", "") or "")
    arrangement = build_arrangement_plan(
        patch_name=patch_name,
        family_name=family_name or "default",
        cadence_state=cadence_state,
        progression_profile=progression_profile,
        form_templates=templates,
        density_bias=float(score.metadata.get("repertoire_density_bias", 0.0) or 0.0),
        payoff_scene=str(score.metadata.get("repertoire_payoff_scene", "") or ""),
        payoff_bias=float(score.metadata.get("repertoire_payoff_bias", 0.0) or 0.0),
    )
    section_functions = _metadata_json_map(score.metadata.get("section_functions"))
    section_cadences = _metadata_json_map(score.metadata.get("section_cadences"))
    hook_answer_degrees = _metadata_int_tuple(score.metadata.get("hook_answer_degrees"))
    repertoire_source_title = str(score.metadata.get("repertoire_source_title", "") or "")
    scenes: list[TrackerScene] = []
    for template in templates:
        source_score = scene_scores.get(template.name, score) if scene_scores is not None else score
        scene_score, enforced_roles = _ensure_scene_role_floors(
            source_score,
            template,
            mood=mood,
        )
        arrangement_scene = arrangement.scenes.get(template.name)
        automation_defaults = dict(template.automation_defaults)
        # Merge scene-level spatial defaults for keys not already present.
        for k, v in _SCENE_SPATIAL_DEFAULTS.get(template.name, {}).items():
            automation_defaults.setdefault(k, v)
        if arrangement_scene is not None:
            automation_defaults.update(arrangement_scene.automation_overrides)
        scene_metadata = {
            "groove_family": str(score.metadata.get("groove_family", arrangement.groove_family) or arrangement.groove_family),
            "text_hook": str(score.metadata.get("text_hook", "") or ""),
        }
        for key in _TRANSITION_METADATA_KEYS:
            value = source_score.metadata.get(key)
            if value:
                scene_metadata[key] = str(value)
        for key in ("motif_development", "rhythm_development", "rhythm", "section_progression"):
            value = source_score.metadata.get(key)
            if value:
                scene_metadata[key] = str(value)
        for key in _SAMPLE_GESTURE_METADATA_KEYS:
            value = source_score.metadata.get(key)
            if value:
                scene_metadata[key] = str(value)
        for key in _ARC_METADATA_KEYS:
            value = source_score.metadata.get(key, score.metadata.get(key))
            if value:
                scene_metadata[key] = str(value)
        for key in _PRODUCTION_COURSE_METADATA_KEYS:
            value = source_score.metadata.get(key)
            if value:
                scene_metadata[key] = str(value)
        for key in VOCABULARY_METADATA_KEYS:
            value = source_score.metadata.get(key)
            if value:
                scene_metadata[key] = str(value)
        if arrangement_scene is not None:
            scene_metadata["entry_intent"] = arrangement_scene.entry_intent
        section_function = section_functions.get(template.name)
        cadence_type = section_cadences.get(template.name)
        if section_function:
            scene_metadata["section_function"] = section_function
        if cadence_type:
            scene_metadata["cadence_type"] = cadence_type
        if repertoire_source_title:
            scene_metadata["repertoire_source_title"] = repertoire_source_title
        payoff_scene = str(score.metadata.get("repertoire_payoff_scene", "") or "")
        if payoff_scene and template.name == payoff_scene:
            scene_metadata["payoff_focus"] = "primary"
        role_source_metadata = {**score.metadata, **source_score.metadata}
        scene_metadata.update(_ensemble_role_metadata(role_source_metadata, scene_metadata))
        scene = build_scene_from_score(
            scene_score,
            name=template.name,
            scene_key=(scene_keys or {}).get(template.name),
            allowed_roles=template.allowed_roles,
            rows_per_beat=rows_per_beat,
            tempo_multiplier=template.tempo_multiplier,
            length_multiplier=template.length_multiplier,
            repeat_count=template.repeat_count,
            max_polyphony=template.max_polyphony,
            automation_defaults=automation_defaults,
            role_hints=role_hints,
            enforced_roles=enforced_roles,
            scene_metadata=scene_metadata,
        )
        source_scene, transform = _motif_source_scene(template.name, scenes)
        if source_scene is not None and transform is not None:
            scene = _apply_scene_motif_recall(
                scene,
                source_scene=source_scene,
                transform=transform,
            )
        if hook_answer_degrees and template.name in {"Recap", "Release", "Resolution", "Afterglow"}:
            scene = _apply_hook_answer_degrees(
                scene,
                answer_degrees=hook_answer_degrees,
            )
        if enforced_roles:
            scene.metadata["enforced_roles"] = ",".join(enforced_roles)
        scenes.append(scene)

    ensemble_metadata = _ensemble_role_metadata(score.metadata)
    return TrackerSong(
        title=title,
        scenes=scenes,
        metadata={
            "source_key": score.key,
            "source_mood": score.mood,
            "form": f"tracker-{len(scenes)}-scene",
            "family": family_name or "default",
            "scene_count": str(len(scenes)),
            "groove_family": arrangement.groove_family,
            **ensemble_metadata,
            **({"patch_name": score.metadata["patch_name"]} if score.metadata.get("patch_name") else {}),
            **({"song_title": score.metadata["song_title"]} if score.metadata.get("song_title") else {}),
            **({"text_hook": score.metadata["text_hook"]} if score.metadata.get("text_hook") else {}),
        },
    )
