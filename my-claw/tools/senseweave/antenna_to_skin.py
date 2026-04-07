"""Antenna-to-Skin — maps network/external signals to organism skin sensations.

How the internet and external data *feel* to CypherClaw's house.
Network traffic becomes warmth, latency becomes pressure, Telegram
messages become touch.  All values are normalised for downstream
consumption by the mood engine and face renderer.

Reads:
  /proc/net/dev     — bytes in/out per interface
  /proc/net/tcp     — active TCP connections (state 01 = ESTABLISHED)

Produces:
  Unified skin-sensation dict for sensor_fusion.
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Bytes-per-second thresholds for activity classification (total in+out)
_BPS_QUIET = 10_000          # < 10 KB/s
_BPS_MODERATE = 100_000      # < 100 KB/s
_BPS_BUSY = 1_000_000        # < 1 MB/s
# >= 1 MB/s = storm

# Connection count used to normalise warmth (this many = warmth 1.0)
_WARMTH_MAX_CONNECTIONS = 200

# Latency (ms) at which pressure saturates to 1.0
_PRESSURE_MAX_LATENCY_MS = 500.0

# Telegram recency threshold: messages younger than this (seconds) = "touched"
_TELEGRAM_RECENT_S = 300.0

# Telegram message count that saturates intensity to 1.0
_TELEGRAM_MAX_MESSAGES = 20


# ---------------------------------------------------------------------------
# NetworkPulse dataclass
# ---------------------------------------------------------------------------


@dataclass
class NetworkPulse:
    """Snapshot of network activity at a point in time."""
    bytes_in: int
    bytes_out: int
    latency_ms: float
    connections_active: int
    timestamp: float


# ---------------------------------------------------------------------------
# read_network_stats
# ---------------------------------------------------------------------------


def read_network_stats(
    proc_path: str = "/proc/net/dev",
    tcp_path: str = "/proc/net/tcp",
) -> NetworkPulse:
    """Read network stats from /proc files.  Stdlib only, no psutil.

    Parses /proc/net/dev for bytes in/out (summing all non-loopback
    interfaces) and /proc/net/tcp for established connection count.

    Returns a zero-valued pulse if files are missing or unparseable
    (graceful degradation on non-Linux hosts).
    """
    bytes_in = 0
    bytes_out = 0
    connections_active = 0

    # --- Parse /proc/net/dev ---
    try:
        with open(proc_path, "r") as f:
            lines = f.readlines()
        for line in lines:
            # Lines look like: "  eth0: 12345  ..."
            if ":" not in line:
                continue
            iface, data = line.split(":", 1)
            iface = iface.strip()
            if iface == "lo":
                continue
            fields = data.split()
            if len(fields) >= 9:
                bytes_in += int(fields[0])
                bytes_out += int(fields[8])
    except (OSError, ValueError):
        pass

    # --- Parse /proc/net/tcp for ESTABLISHED connections ---
    try:
        with open(tcp_path, "r") as f:
            lines = f.readlines()
        for line in lines[1:]:  # skip header
            fields = line.split()
            if len(fields) >= 4:
                state = fields[3]
                if state == "01":  # TCP ESTABLISHED
                    connections_active += 1
    except (OSError, ValueError, IndexError):
        pass

    return NetworkPulse(
        bytes_in=bytes_in,
        bytes_out=bytes_out,
        latency_ms=0.0,  # latency requires active probing; default to 0
        connections_active=connections_active,
        timestamp=time.time(),
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _clamp(v: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, v))


# ---------------------------------------------------------------------------
# network_to_sensation
# ---------------------------------------------------------------------------


def network_to_sensation(
    pulse: NetworkPulse,
    baseline: NetworkPulse | None = None,
) -> dict:
    """Map a NetworkPulse to sensory parameters.

    Parameters
    ----------
    pulse : NetworkPulse
        Current network snapshot.
    baseline : NetworkPulse | None
        Previous snapshot for delta-based activity classification.
        If None, absolute byte counts are used (less accurate but
        still functional).

    Returns
    -------
    dict with keys:
        activity : "quiet" | "moderate" | "busy" | "storm"
        warmth   : 0.0-1.0 (more connections = warmer)
        pressure : 0.0-1.0 (higher latency = more pressure)
    """
    # --- Activity from bytes-per-second delta ---
    if baseline is not None:
        dt = pulse.timestamp - baseline.timestamp
        if dt <= 0:
            dt = 1.0
        delta_in = max(0, pulse.bytes_in - baseline.bytes_in)
        delta_out = max(0, pulse.bytes_out - baseline.bytes_out)
        bps = (delta_in + delta_out) / dt
    else:
        # Without baseline, use absolute values as rough proxy
        bps = float(pulse.bytes_in + pulse.bytes_out)

    if bps >= _BPS_BUSY:
        activity = "storm" if bps >= _BPS_BUSY * 5 else "busy"
    elif bps >= _BPS_MODERATE:
        activity = "busy" if bps >= _BPS_MODERATE * 5 else "moderate"
    elif bps >= _BPS_QUIET:
        activity = "moderate" if bps >= _BPS_QUIET * 5 else "quiet"
    else:
        activity = "quiet"

    # --- Warmth from connection count ---
    warmth = _clamp(pulse.connections_active / _WARMTH_MAX_CONNECTIONS)

    # --- Pressure from latency ---
    pressure = _clamp(pulse.latency_ms / _PRESSURE_MAX_LATENCY_MS)

    return {
        "activity": activity,
        "warmth": warmth,
        "pressure": pressure,
    }


# ---------------------------------------------------------------------------
# telegram_to_sensation
# ---------------------------------------------------------------------------


def telegram_to_sensation(message_count: int, last_message_age_s: float) -> dict:
    """Map Telegram activity to a skin sensation.

    Parameters
    ----------
    message_count : int
        Number of recent messages in the inbox window.
    last_message_age_s : float
        Seconds since the most recent message.

    Returns
    -------
    dict with keys:
        feeling   : "touched" | "quiet"
        intensity : 0.0-1.0
    """
    if message_count <= 0:
        return {"feeling": "quiet", "intensity": 0.0}

    # Recency factor: 1.0 when very recent, decays toward 0 as age grows
    recency = _clamp(1.0 - (last_message_age_s / _TELEGRAM_RECENT_S))

    # Volume factor: more messages = higher intensity, saturates at max
    volume = _clamp(message_count / _TELEGRAM_MAX_MESSAGES)

    intensity = _clamp(recency * 0.6 + volume * 0.4)

    feeling = "touched" if intensity > 0.0 or last_message_age_s < _TELEGRAM_RECENT_S else "quiet"

    return {
        "feeling": feeling,
        "intensity": intensity,
    }


# ---------------------------------------------------------------------------
# combine_skin_sensations
# ---------------------------------------------------------------------------

_ACTIVITY_RANK = {"quiet": 0, "moderate": 1, "busy": 2, "storm": 3}
_ACTIVITY_LABELS = ["quiet", "moderate", "busy", "storm"]


def combine_skin_sensations(network: dict, telegram: dict) -> dict:
    """Merge network and Telegram sensations into unified skin state.

    Returns
    -------
    dict with keys:
        overall_activity : "quiet" | "moderate" | "busy" | "storm"
        network          : the original network sensation dict
        telegram         : the original telegram sensation dict
    """
    # Compute a combined score from both sources
    net_rank = _ACTIVITY_RANK.get(network.get("activity", "quiet"), 0)
    tg_intensity = telegram.get("intensity", 0.0)

    # Telegram intensity can bump overall activity by up to 1 level
    tg_bump = 0
    if tg_intensity >= 0.7:
        tg_bump = 2
    elif tg_intensity >= 0.3:
        tg_bump = 1

    combined_rank = min(3, net_rank + tg_bump)
    overall = _ACTIVITY_LABELS[combined_rank]

    return {
        "overall_activity": overall,
        "network": network,
        "telegram": telegram,
    }
