"""Resource Governor -- live performance degradation for music quality.

Reads system and audio health signals and computes a ResourceBudget that
the composer uses to shed optional voices, grains, and DSP before
interrupting primary musical form.

Degradation order (least → most impactful):
    1. color / texture voices
    2. counter voices and ornaments
    3. grain density and sample count
    4. overall voice count cap
    5. density multiplier on primary melody/bass (last resort)

Inputs sampled each song:
    - cpu_pressure          0.0–1.0   load / cores
    - sc_node_count         int       live SuperCollider node count
    - sampler_load          0.0–1.0   DSP buffer utilisation
    - capture_age_seconds   float     seconds since last room capture
    - self_listener_rms     float     RMS of CypherClaw's own output
    - master_bus_healthy    bool      master bus node alive?

Stdlib only.
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


# ---------------------------------------------------------------------------
# ResourceBudget — the output the composer consumes
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ResourceBudget:
    """Constraints the composer must honour this song cycle."""

    max_voices: int             # hard cap on simultaneous voices (2–8)
    allow_color: bool           # may use color / texture roles?
    allow_counter: bool         # may use counter-melody role?
    grain_density: float        # 0.0–1.0  multiplier on grain count / sample count
    density_multiplier: float   # 0.0–1.0  multiplier on overall note density
    suppress_llm: bool          # skip LLM advisor calls (save CPU)
    dsp_blocks_allowed: int     # max DSP effect blocks (0–4)
    reason: str                 # human-readable summary of degradation


# ---------------------------------------------------------------------------
# Signal readers — read live state files written by other daemons
# ---------------------------------------------------------------------------

_SELF_LISTEN_PATH = "/tmp/self_listen.json"
_MASTER_BUS_STATE_PATH = "/tmp/master_bus_state.json"
_ROOM_ACTIVITY_PATH = "/tmp/room_activity.json"


def read_cpu_pressure() -> float:
    """Return normalised CPU pressure: load_avg[0] / cpu_count, clamped 0–1."""
    try:
        load = os.getloadavg()[0]
        cores = max(1, os.cpu_count() or 1)
        return _clamp(load / cores, 0.0, 1.0)
    except (OSError, AttributeError):
        return 0.0


def read_sc_node_count() -> int:
    """Estimate SuperCollider node count from /tmp/sc_status.json."""
    try:
        data = json.loads(Path("/tmp/sc_status.json").read_text())
        return int(data.get("node_count", 0))
    except (json.JSONDecodeError, OSError, TypeError, ValueError):
        return 0


def read_sampler_load() -> float:
    """Read DSP buffer utilisation from /tmp/sc_status.json."""
    try:
        data = json.loads(Path("/tmp/sc_status.json").read_text())
        return _clamp(float(data.get("cpu_usage", 0.0)), 0.0, 1.0)
    except (json.JSONDecodeError, OSError, TypeError, ValueError):
        return 0.0


def read_capture_age() -> float:
    """Seconds since the last room/camera capture."""
    for path in ["/tmp/room_presence.json", "/tmp/porch_eye_state.json"]:
        try:
            data = json.loads(Path(path).read_text())
            ts = float(data.get("last_capture_time", 0) or data.get("timestamp", 0))
            if ts > 0:
                return max(0.0, time.time() - ts)
        except (json.JSONDecodeError, OSError, TypeError, ValueError):
            continue
    return 999.0  # no capture data → treat as stale


def read_self_listener_rms() -> float:
    """RMS of CypherClaw's own audio output."""
    try:
        data = json.loads(Path(_SELF_LISTEN_PATH).read_text())
        return _clamp(float(data.get("amplitude", 0.0) or data.get("rms", 0.0)), 0.0, 1.0)
    except (json.JSONDecodeError, OSError, TypeError, ValueError):
        return 0.0


def read_master_bus_healthy() -> bool:
    """Check whether the master bus node is alive and writing state."""
    try:
        data = json.loads(Path(_MASTER_BUS_STATE_PATH).read_text())
        ts = float(data.get("timestamp", 0) or data.get("updated", 0))
        return (time.time() - ts) < 10.0
    except (json.JSONDecodeError, OSError, TypeError, ValueError):
        return False


# ---------------------------------------------------------------------------
# Composite pressure score
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class HealthSnapshot:
    """Raw health signals captured at a point in time."""

    cpu_pressure: float
    sc_node_count: int
    sampler_load: float
    capture_age_seconds: float
    self_listener_rms: float
    master_bus_healthy: bool


def take_snapshot(
    *,
    cpu_pressure: float | None = None,
    sc_node_count: int | None = None,
    sampler_load: float | None = None,
    capture_age_seconds: float | None = None,
    self_listener_rms: float | None = None,
    master_bus_healthy: bool | None = None,
) -> HealthSnapshot:
    """Read all signals, allowing explicit overrides for testing."""
    return HealthSnapshot(
        cpu_pressure=cpu_pressure if cpu_pressure is not None else read_cpu_pressure(),
        sc_node_count=sc_node_count if sc_node_count is not None else read_sc_node_count(),
        sampler_load=sampler_load if sampler_load is not None else read_sampler_load(),
        capture_age_seconds=(
            capture_age_seconds if capture_age_seconds is not None else read_capture_age()
        ),
        self_listener_rms=(
            self_listener_rms if self_listener_rms is not None else read_self_listener_rms()
        ),
        master_bus_healthy=(
            master_bus_healthy if master_bus_healthy is not None else read_master_bus_healthy()
        ),
    )


# Maximum reasonable SC node count before we start shedding
_NODE_PRESSURE_THRESHOLD = 200
_NODE_PRESSURE_CEILING = 500

# Capture older than this many seconds is "stale"
_CAPTURE_STALE_SECONDS = 120.0
_CAPTURE_DEAD_SECONDS = 600.0

# Self-listener RMS below this means we're clipping or silent (both bad)
_SELF_RMS_SILENCE = 0.001
_SELF_RMS_LOUD = 0.85


def compute_pressure(snapshot: HealthSnapshot) -> float:
    """Collapse all signals into a single 0.0–1.0 composite pressure score.

    Each dimension contributes a weighted term; the result is clamped.
    """
    pressure = 0.0

    # CPU: direct pass-through, strongest signal
    pressure += snapshot.cpu_pressure * 0.35

    # SC node count: ramp from threshold to ceiling
    if snapshot.sc_node_count > _NODE_PRESSURE_THRESHOLD:
        node_ratio = _clamp(
            (snapshot.sc_node_count - _NODE_PRESSURE_THRESHOLD)
            / max(1, _NODE_PRESSURE_CEILING - _NODE_PRESSURE_THRESHOLD),
            0.0,
            1.0,
        )
        pressure += node_ratio * 0.20

    # Sampler / DSP load
    pressure += snapshot.sampler_load * 0.20

    # Stale capture: ramps from 0 at threshold to 1 at dead
    if snapshot.capture_age_seconds > _CAPTURE_STALE_SECONDS:
        stale_ratio = _clamp(
            (snapshot.capture_age_seconds - _CAPTURE_STALE_SECONDS)
            / max(1.0, _CAPTURE_DEAD_SECONDS - _CAPTURE_STALE_SECONDS),
            0.0,
            1.0,
        )
        pressure += stale_ratio * 0.10

    # Self-listener anomaly: silence or very loud both add pressure
    if snapshot.self_listener_rms < _SELF_RMS_SILENCE:
        pressure += 0.10  # dead output
    elif snapshot.self_listener_rms > _SELF_RMS_LOUD:
        pressure += 0.05  # clipping risk

    # Master bus dead: immediate significant pressure
    if not snapshot.master_bus_healthy:
        pressure += 0.15

    return _clamp(pressure, 0.0, 1.0)


# ---------------------------------------------------------------------------
# Budget computation — the degradation rules
# ---------------------------------------------------------------------------

# Thresholds (pressure score)
_SHED_COLOR = 0.30       # drop color/texture roles
_SHED_COUNTER = 0.45     # drop counter-melody
_SHED_GRAINS = 0.35      # start reducing grain density
_SUPPRESS_LLM = 0.50     # skip LLM calls
_REDUCE_DSP = 0.40       # start reducing DSP blocks
_REDUCE_DENSITY = 0.60   # reduce overall note density
_EMERGENCY = 0.80        # emergency mode — bare minimum


def compute_budget(snapshot: HealthSnapshot) -> ResourceBudget:
    """Turn a health snapshot into a resource budget.

    The budget degrades optional voices, samples, and grains before
    reducing primary musical form.
    """
    pressure = compute_pressure(snapshot)

    # Voices: 8 at zero pressure → 2 at emergency
    if pressure >= _EMERGENCY:
        max_voices = 2
    elif pressure >= _SHED_COUNTER:
        max_voices = 3
    elif pressure >= _SHED_COLOR:
        max_voices = 5
    else:
        max_voices = 8

    allow_color = pressure < _SHED_COLOR
    allow_counter = pressure < _SHED_COUNTER

    # Grain density: full at 0, linearly reduce above threshold
    if pressure >= _SHED_GRAINS:
        grain_density = _clamp(1.0 - (pressure - _SHED_GRAINS) / (1.0 - _SHED_GRAINS), 0.1, 1.0)
    else:
        grain_density = 1.0

    # Density multiplier: only kicks in at high pressure
    if pressure >= _REDUCE_DENSITY:
        density_multiplier = _clamp(
            1.0 - (pressure - _REDUCE_DENSITY) / (1.0 - _REDUCE_DENSITY) * 0.5,
            0.5,
            1.0,
        )
    else:
        density_multiplier = 1.0

    suppress_llm = pressure >= _SUPPRESS_LLM

    # DSP blocks: 4 full, scale down above threshold
    if pressure >= _REDUCE_DSP:
        dsp_blocks_allowed = max(0, int(4 * (1.0 - (pressure - _REDUCE_DSP) / (1.0 - _REDUCE_DSP))))
    else:
        dsp_blocks_allowed = 4

    # Build reason string
    reasons: list[str] = []
    if not snapshot.master_bus_healthy:
        reasons.append("master bus dead")
    if snapshot.cpu_pressure >= 0.7:
        reasons.append(f"CPU {snapshot.cpu_pressure:.0%}")
    if snapshot.sc_node_count > _NODE_PRESSURE_THRESHOLD:
        reasons.append(f"{snapshot.sc_node_count} SC nodes")
    if snapshot.sampler_load >= 0.6:
        reasons.append(f"sampler {snapshot.sampler_load:.0%}")
    if snapshot.capture_age_seconds > _CAPTURE_STALE_SECONDS:
        reasons.append(f"capture {snapshot.capture_age_seconds:.0f}s stale")
    if snapshot.self_listener_rms < _SELF_RMS_SILENCE:
        reasons.append("self-listener silent")
    if not reasons:
        reasons.append("nominal")

    return ResourceBudget(
        max_voices=max_voices,
        allow_color=allow_color,
        allow_counter=allow_counter,
        grain_density=round(grain_density, 3),
        density_multiplier=round(density_multiplier, 3),
        suppress_llm=suppress_llm,
        dsp_blocks_allowed=dsp_blocks_allowed,
        reason="; ".join(reasons),
    )
