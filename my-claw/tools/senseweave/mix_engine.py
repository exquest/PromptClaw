"""Mix-planning helpers for CypherClaw EMSD work."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


@dataclass(frozen=True)
class FrequencyLane:
    low_hz: float
    high_hz: float
    name: str = "custom"


@dataclass(frozen=True)
class VoiceMixTarget:
    role: str
    lane: FrequencyLane
    stereo_width: float
    reverb_send: float
    level_db: float
    production_role: str = ""


@dataclass(frozen=True)
class MasterEqIntent:
    """Broad mastering EQ intent for installation playback."""

    low_cut_hz: float
    low_shelf_db: float
    presence_tilt_db: float
    air_shelf_db: float


@dataclass(frozen=True)
class MasteringPolicy:
    """Installation-safe master policy targets for a cadence/phase pair."""

    cadence_state: str
    phase_name: str
    target_lufs: float
    target_lufs_range: tuple[float, float]
    true_peak_range_dbtp: tuple[float, float]
    limiter_ceiling_dbtp: float
    eq_intent: MasterEqIntent
    dynamic_contrast_db: float


DelayStyle = Literal[
    "none", "slapback", "dotted_eighth", "quarter", "ping_pong", "tape_echo"
]
TransitionSpace = Literal["dissolve", "crossfade", "morph", "cut"]
TransientPolicy = Literal["preserve", "soften", "shape"]
DeferenceAction = Literal["duck", "silence", "thin"]
DeferenceSource = Literal["theramini", "environmental", "any"]
DeferenceTrigger = Literal["onset", "sustained", "silence_request"]


@dataclass(frozen=True)
class DeferenceRule:
    """When and how generated material should yield to external input."""

    source: DeferenceSource
    trigger: DeferenceTrigger
    action: DeferenceAction
    duck_db: float
    attack_ms: float
    release_ms: float
    priority: int


@dataclass(frozen=True)
class SpatialProfile:
    """Phase-aware spatial, reverb, and delay production targets."""

    phase_name: str
    stereo_width: float
    depth: float
    reverb_size: float
    reverb_decay_s: float
    reverb_damping: float
    delay_style: DelayStyle
    delay_send: float
    transition_space: TransitionSpace


@dataclass(frozen=True)
class DynamicsProfile:
    """Phase-aware dynamics, compression, and deference targets."""

    phase_name: str
    dynamic_range_db: float
    comp_threshold_db: float
    comp_ratio: float
    comp_attack_ms: float
    comp_release_ms: float
    transient_policy: TransientPolicy
    deference_rules: tuple[DeferenceRule, ...]


@dataclass(frozen=True)
class MixProfile:
    cadence_state: str
    patch_name: str
    target_lufs: float
    peak_ceiling_dbtp: float
    bus_comp_ratio: float
    theramini_duck_db: float
    voice_targets: tuple[VoiceMixTarget, ...]
    dynamics: DynamicsProfile | None = None
    spatial: SpatialProfile | None = None
    mastering: MasteringPolicy | None = None
    role_frequency_lanes: dict[str, tuple[str, ...]] = field(default_factory=dict)
    production_metadata: dict[str, dict[str, object]] = field(default_factory=dict)


_BASE_LEVELS = {
    "sleep": -22.5,
    "wind_down": -20.0,
    "wake_ramp": -18.5,
    "occupied_day": -16.0,
    "away_practice": -15.0,
}

_MASTER_LUFS_RANGES = {
    "sleep": (-24.5, -20.5),
    "wind_down": (-22.0, -18.0),
    "wake_ramp": (-20.5, -16.5),
    "occupied_day": (-18.0, -14.5),
    "away_practice": (-17.0, -14.0),
}

_MASTER_TRUE_PEAK_RANGES = {
    "sleep": (-5.0, -1.0),
    "wind_down": (-4.5, -1.0),
    "wake_ramp": (-4.0, -1.0),
    "occupied_day": (-3.5, -1.0),
    "away_practice": (-3.0, -1.0),
}

_MASTER_LIMITER_CEILINGS = {
    "sleep": -1.0,
    "wind_down": -1.0,
    "wake_ramp": -1.0,
    "occupied_day": -1.0,
    "away_practice": -1.0,
}

_MASTER_EQ_INTENTS = {
    "sleep": MasterEqIntent(low_cut_hz=35.0, low_shelf_db=-1.5, presence_tilt_db=-0.8, air_shelf_db=-0.4),
    "wind_down": MasterEqIntent(low_cut_hz=35.0, low_shelf_db=-1.2, presence_tilt_db=-0.4, air_shelf_db=-0.2),
    "wake_ramp": MasterEqIntent(low_cut_hz=35.0, low_shelf_db=-1.0, presence_tilt_db=0.0, air_shelf_db=0.0),
    "occupied_day": MasterEqIntent(low_cut_hz=40.0, low_shelf_db=-1.0, presence_tilt_db=0.4, air_shelf_db=0.2),
    "away_practice": MasterEqIntent(low_cut_hz=40.0, low_shelf_db=-1.5, presence_tilt_db=0.2, air_shelf_db=0.0),
}

FREQUENCY_LANES = {
    "sub": FrequencyLane(20.0, 60.0, "sub"),
    "bass": FrequencyLane(60.0, 160.0, "bass"),
    "low-mid": FrequencyLane(160.0, 350.0, "low-mid"),
    "midrange": FrequencyLane(350.0, 1200.0, "midrange"),
    "upper-mid": FrequencyLane(1200.0, 3500.0, "upper-mid"),
    "presence": FrequencyLane(3500.0, 8000.0, "presence"),
    "air": FrequencyLane(8000.0, 16000.0, "air"),
}

PRODUCTION_ROLE_FREQUENCY_LANES = {
    "bass": ("sub", "bass"),
    "pad": ("low-mid", "midrange"),
    "lead": ("upper-mid", "presence"),
    "texture": ("presence", "air"),
    "noise": ("air",),
    "sample": ("midrange", "presence"),
    "theramini": ("upper-mid", "presence"),
}

_PRODUCTION_METADATA = {
    "bass": {
        "frequency_lanes": PRODUCTION_ROLE_FREQUENCY_LANES["bass"],
        "hpf_hz": 28.0,
        "lpf_hz": 180.0,
        "eq_intent": "protect centered fundamentals; clear low-mid mud before 220 Hz",
        "stereo_policy": "mono-center",
    },
    "pad": {
        "frequency_lanes": PRODUCTION_ROLE_FREQUENCY_LANES["pad"],
        "hpf_hz": 140.0,
        "lpf_hz": 9000.0,
        "eq_intent": "support harmony while scooping the lead and bass lanes",
        "stereo_policy": "wide-support",
    },
    "lead": {
        "frequency_lanes": PRODUCTION_ROLE_FREQUENCY_LANES["lead"],
        "hpf_hz": 150.0,
        "lpf_hz": 12000.0,
        "eq_intent": "hold upper-mid identity with controlled presence lift",
        "stereo_policy": "focused-center",
    },
    "texture": {
        "frequency_lanes": PRODUCTION_ROLE_FREQUENCY_LANES["texture"],
        "hpf_hz": 250.0,
        "lpf_hz": 16000.0,
        "eq_intent": "thin lows and leave shimmer above the primary voice",
        "stereo_policy": "wide-air",
    },
    "noise": {
        "frequency_lanes": PRODUCTION_ROLE_FREQUENCY_LANES["noise"],
        "hpf_hz": 600.0,
        "lpf_hz": 16000.0,
        "eq_intent": "shape hiss as air, not midrange masking",
        "stereo_policy": "wide-air",
    },
    "sample": {
        "frequency_lanes": PRODUCTION_ROLE_FREQUENCY_LANES["sample"],
        "hpf_hz": 90.0,
        "lpf_hz": 11000.0,
        "eq_intent": "band-limit source gestures and notch around the current lead",
        "stereo_policy": "source-dependent",
    },
    "theramini": {
        "frequency_lanes": PRODUCTION_ROLE_FREQUENCY_LANES["theramini"],
        "hpf_hz": 120.0,
        "lpf_hz": 10000.0,
        "eq_intent": "reserve presence for human gesture; duck generated lead support",
        "stereo_policy": "focused-center",
    },
}

_PHASE_MASTER_CONTRAST = {
    "Divination": 18.0,
    "Emergence": 14.0,
    "Conversation": 10.0,
    "Convergence": 12.0,
    "Crystallization": 16.0,
}

# Per-phase dynamics targets.  Divination and Crystallization are sparse,
# contemplative phases -- wide dynamic range, gentle compression, preserved
# transients.  Conversation is the densest dialogue phase -- tighter control.
_PHASE_DYNAMICS: dict[str, dict[str, object]] = {
    "Divination": {
        "dynamic_range_db": 18.0,
        "comp_threshold_db": -18.0,
        "comp_ratio": 1.2,
        "comp_attack_ms": 80.0,
        "comp_release_ms": 400.0,
        "transient_policy": "preserve",
    },
    "Emergence": {
        "dynamic_range_db": 14.0,
        "comp_threshold_db": -16.0,
        "comp_ratio": 1.5,
        "comp_attack_ms": 40.0,
        "comp_release_ms": 350.0,
        "transient_policy": "soften",
    },
    "Conversation": {
        "dynamic_range_db": 10.0,
        "comp_threshold_db": -14.0,
        "comp_ratio": 2.0,
        "comp_attack_ms": 15.0,
        "comp_release_ms": 200.0,
        "transient_policy": "shape",
    },
    "Convergence": {
        "dynamic_range_db": 12.0,
        "comp_threshold_db": -15.0,
        "comp_ratio": 1.8,
        "comp_attack_ms": 25.0,
        "comp_release_ms": 300.0,
        "transient_policy": "soften",
    },
    "Crystallization": {
        "dynamic_range_db": 16.0,
        "comp_threshold_db": -17.0,
        "comp_ratio": 1.3,
        "comp_attack_ms": 60.0,
        "comp_release_ms": 500.0,
        "transient_policy": "preserve",
    },
}

# Default deference rules per phase.  The Theramini (human player) always gets
# priority; environmental transients get lighter treatment in dense phases.
_PHASE_DEFERENCE: dict[str, tuple[DeferenceRule, ...]] = {
    "Divination": (
        DeferenceRule("theramini", "onset", "duck", 4.0, 10.0, 600.0, 10),
        DeferenceRule("theramini", "silence_request", "silence", 0.0, 5.0, 0.0, 20),
        DeferenceRule("environmental", "onset", "duck", 3.0, 15.0, 500.0, 5),
    ),
    "Emergence": (
        DeferenceRule("theramini", "onset", "duck", 3.5, 12.0, 450.0, 10),
        DeferenceRule("theramini", "silence_request", "silence", 0.0, 5.0, 0.0, 20),
        DeferenceRule("environmental", "onset", "thin", 2.0, 20.0, 400.0, 5),
    ),
    "Conversation": (
        DeferenceRule("theramini", "onset", "duck", 5.0, 8.0, 350.0, 10),
        DeferenceRule("theramini", "sustained", "duck", 3.0, 15.0, 300.0, 8),
        DeferenceRule("theramini", "silence_request", "silence", 0.0, 5.0, 0.0, 20),
        DeferenceRule("environmental", "onset", "thin", 1.5, 25.0, 300.0, 3),
    ),
    "Convergence": (
        DeferenceRule("theramini", "onset", "duck", 3.5, 12.0, 400.0, 10),
        DeferenceRule("theramini", "silence_request", "silence", 0.0, 5.0, 0.0, 20),
        DeferenceRule("environmental", "onset", "thin", 2.0, 20.0, 350.0, 5),
    ),
    "Crystallization": (
        DeferenceRule("theramini", "onset", "duck", 4.0, 10.0, 550.0, 10),
        DeferenceRule("theramini", "silence_request", "silence", 0.0, 5.0, 0.0, 20),
        DeferenceRule("environmental", "onset", "duck", 3.0, 15.0, 450.0, 5),
    ),
}


# Per-phase spatial targets.  Divination and Crystallization are wide and
# deep -- big reverb tails, generous stereo field.  Conversation narrows the
# image and shortens tails so the ensemble dialogue stays clear.
_PHASE_SPATIAL: dict[str, dict[str, object]] = {
    "Divination": {
        "stereo_width": 0.85,
        "depth": 0.8,
        "reverb_size": 0.9,
        "reverb_decay_s": 4.5,
        "reverb_damping": 0.3,
        "delay_style": "none",
        "delay_send": 0.0,
        "transition_space": "dissolve",
    },
    "Emergence": {
        "stereo_width": 0.65,
        "depth": 0.5,
        "reverb_size": 0.6,
        "reverb_decay_s": 2.8,
        "reverb_damping": 0.45,
        "delay_style": "slapback",
        "delay_send": 0.15,
        "transition_space": "crossfade",
    },
    "Conversation": {
        "stereo_width": 0.45,
        "depth": 0.3,
        "reverb_size": 0.35,
        "reverb_decay_s": 1.2,
        "reverb_damping": 0.65,
        "delay_style": "dotted_eighth",
        "delay_send": 0.1,
        "transition_space": "crossfade",
    },
    "Convergence": {
        "stereo_width": 0.5,
        "depth": 0.4,
        "reverb_size": 0.5,
        "reverb_decay_s": 2.0,
        "reverb_damping": 0.5,
        "delay_style": "quarter",
        "delay_send": 0.12,
        "transition_space": "morph",
    },
    "Crystallization": {
        "stereo_width": 0.8,
        "depth": 0.75,
        "reverb_size": 0.85,
        "reverb_decay_s": 5.5,
        "reverb_damping": 0.25,
        "delay_style": "tape_echo",
        "delay_send": 0.2,
        "transition_space": "dissolve",
    },
}


def build_spatial_profile(
    phase_name: str,
    *,
    cadence_state: str = "occupied_day",
) -> SpatialProfile:
    """Build a phase-aware spatial production profile."""
    params = dict(_PHASE_SPATIAL.get(phase_name, _PHASE_SPATIAL["Emergence"]))

    # Quiet cadences push further into depth and widen the image.
    if cadence_state in {"sleep", "wind_down"}:
        params["stereo_width"] = min(1.0, float(params["stereo_width"]) + 0.1)  # type: ignore[arg-type]
        params["depth"] = min(1.0, float(params["depth"]) + 0.1)  # type: ignore[arg-type]
        params["reverb_decay_s"] = float(params["reverb_decay_s"]) + 0.8  # type: ignore[arg-type]
        params["reverb_damping"] = max(0.1, float(params["reverb_damping"]) - 0.1)  # type: ignore[arg-type]

    return SpatialProfile(
        phase_name=phase_name,
        stereo_width=float(params["stereo_width"]),  # type: ignore[arg-type]
        depth=float(params["depth"]),  # type: ignore[arg-type]
        reverb_size=float(params["reverb_size"]),  # type: ignore[arg-type]
        reverb_decay_s=float(params["reverb_decay_s"]),  # type: ignore[arg-type]
        reverb_damping=float(params["reverb_damping"]),  # type: ignore[arg-type]
        delay_style=params["delay_style"],  # type: ignore[arg-type]
        delay_send=float(params["delay_send"]),  # type: ignore[arg-type]
        transition_space=params["transition_space"],  # type: ignore[arg-type]
    )


def build_dynamics_profile(
    phase_name: str,
    *,
    cadence_state: str = "occupied_day",
) -> DynamicsProfile:
    """Build a phase-aware dynamics profile with deference rules."""
    params = dict(_PHASE_DYNAMICS.get(phase_name, _PHASE_DYNAMICS["Emergence"]))
    deference = _PHASE_DEFERENCE.get(phase_name, _PHASE_DEFERENCE["Emergence"])

    # Quiet cadences widen dynamic range and soften compression further.
    if cadence_state in {"sleep", "wind_down"}:
        params["dynamic_range_db"] = min(24.0, float(params["dynamic_range_db"]) + 3.0)  # type: ignore[arg-type]
        params["comp_ratio"] = max(1.1, float(params["comp_ratio"]) - 0.2)  # type: ignore[arg-type]
        params["comp_attack_ms"] = float(params["comp_attack_ms"]) + 15.0  # type: ignore[arg-type]

    return DynamicsProfile(
        phase_name=phase_name,
        dynamic_range_db=float(params["dynamic_range_db"]),  # type: ignore[arg-type]
        comp_threshold_db=float(params["comp_threshold_db"]),  # type: ignore[arg-type]
        comp_ratio=float(params["comp_ratio"]),  # type: ignore[arg-type]
        comp_attack_ms=float(params["comp_attack_ms"]),  # type: ignore[arg-type]
        comp_release_ms=float(params["comp_release_ms"]),  # type: ignore[arg-type]
        transient_policy=params["transient_policy"],  # type: ignore[arg-type]
        deference_rules=deference,
    )


def build_mastering_policy(
    *,
    cadence_state: str,
    phase_name: str | None = None,
) -> MasteringPolicy:
    """Build an installation-safe master policy for one cadence/phase."""
    target_lufs = _BASE_LEVELS.get(cadence_state, -16.5)
    target_lufs_range = _MASTER_LUFS_RANGES.get(cadence_state, (target_lufs - 1.5, target_lufs + 1.5))
    true_peak_range = _MASTER_TRUE_PEAK_RANGES.get(cadence_state, (-3.5, -1.0))
    limiter_ceiling = _MASTER_LIMITER_CEILINGS.get(cadence_state, -1.0)
    eq_intent = _MASTER_EQ_INTENTS.get(
        cadence_state,
        MasterEqIntent(low_cut_hz=40.0, low_shelf_db=-1.0, presence_tilt_db=0.0, air_shelf_db=0.0),
    )
    resolved_phase = phase_name or "Emergence"
    dynamic_contrast = _PHASE_MASTER_CONTRAST.get(resolved_phase, _PHASE_MASTER_CONTRAST["Emergence"])
    if cadence_state in {"sleep", "wind_down"}:
        dynamic_contrast = min(24.0, dynamic_contrast + 2.0)

    return MasteringPolicy(
        cadence_state=cadence_state,
        phase_name=resolved_phase,
        target_lufs=target_lufs,
        target_lufs_range=target_lufs_range,
        true_peak_range_dbtp=true_peak_range,
        limiter_ceiling_dbtp=limiter_ceiling,
        eq_intent=eq_intent,
        dynamic_contrast_db=dynamic_contrast,
    )


def _role_frequency_lanes() -> dict[str, tuple[str, ...]]:
    return {role: tuple(lanes) for role, lanes in PRODUCTION_ROLE_FREQUENCY_LANES.items()}


def _production_metadata() -> dict[str, dict[str, object]]:
    return {role: dict(metadata) for role, metadata in _PRODUCTION_METADATA.items()}


def build_mix_profile(
    *,
    cadence_state: str,
    patch_name: str,
    theramini_present: bool = False,
    phase_name: str | None = None,
) -> MixProfile:
    target_lufs = _BASE_LEVELS.get(cadence_state, -16.5)
    comp_ratio = 1.35 if cadence_state in {"sleep", "wind_down"} else 1.6 if cadence_state == "occupied_day" else 1.75
    targets = (
        VoiceMixTarget(
            "bass",
            FrequencyLane(30.0, 150.0, "bass"),
            0.08,
            0.12,
            -10.0 if patch_name == "house_procession" else -12.0,
            "bass",
        ),
        VoiceMixTarget(
            "melody",
            FrequencyLane(1200.0, 3500.0, "upper-mid"),
            0.42 if patch_name != "house_monastery" else 0.28,
            0.18,
            -11.0,
            "lead",
        ),
        VoiceMixTarget(
            "counter",
            FrequencyLane(180.0, 900.0, "low-mid"),
            0.58,
            0.24,
            -15.0,
            "pad",
        ),
        VoiceMixTarget(
            "color",
            FrequencyLane(3500.0, 8000.0, "presence"),
            0.78,
            0.34,
            -17.0,
            "texture",
        ),
    )
    duck_db = 2.5 if theramini_present else 0.0
    if cadence_state == "sleep":
        duck_db = max(duck_db, 1.5)
    dynamics = build_dynamics_profile(phase_name, cadence_state=cadence_state) if phase_name else None
    spatial = build_spatial_profile(phase_name, cadence_state=cadence_state) if phase_name else None
    mastering = build_mastering_policy(cadence_state=cadence_state, phase_name=phase_name)
    return MixProfile(
        cadence_state=cadence_state,
        patch_name=patch_name,
        target_lufs=target_lufs,
        peak_ceiling_dbtp=mastering.limiter_ceiling_dbtp,
        bus_comp_ratio=comp_ratio,
        theramini_duck_db=duck_db,
        voice_targets=targets,
        dynamics=dynamics,
        spatial=spatial,
        mastering=mastering,
        role_frequency_lanes=_role_frequency_lanes(),
        production_metadata=_production_metadata(),
    )
