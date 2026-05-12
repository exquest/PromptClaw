"""Mix and mastering verification for CypherClaw EMSD.

Pure functions that check mix profiles, master-bus values, and rendered
audio proxies for clipping, silence, harshness, and frequency masking.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from .mix_engine import FrequencyLane, MasteringPolicy, MixProfile, VoiceMixTarget


def _clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


# ---------------------------------------------------------------------------
# Audio measurement helpers (float samples in [-1, 1])
# ---------------------------------------------------------------------------


def peak_dbfs(samples: list[float]) -> float:
    """Return peak level in dBFS for float samples."""
    if not samples:
        return -math.inf
    peak = max(abs(s) for s in samples)
    if peak < 1e-12:
        return -math.inf
    return 20.0 * math.log10(peak)


def rms_dbfs(samples: list[float]) -> float:
    """Return RMS level in dBFS."""
    if not samples:
        return -math.inf
    mean_sq = sum(s * s for s in samples) / len(samples)
    if mean_sq < 1e-24:
        return -math.inf
    return 10.0 * math.log10(mean_sq)


def estimate_lufs_proxy(samples: list[float], sample_rate: int) -> float:
    """Simplified integrated-loudness proxy (un-gated RMS with K-weight bias).

    Not ITU-R BS.1770 compliant — this is a deterministic proxy suitable for
    regression tests on synthetic renders.  The K-weighting shelf lifts
    energy above 1.5 kHz by ~2 dB and rolls off below 100 Hz, approximated
    here with a single-pole high-pass and a proportional bias term.
    """
    if not samples or sample_rate <= 0:
        return -math.inf

    # single-pole high-pass at 100 Hz (K-weight low-frequency roll-off proxy)
    rc = 1.0 / (2.0 * math.pi * 100.0)
    alpha = rc / (rc + 1.0 / sample_rate)
    prev_in = 0.0
    prev_out = 0.0
    filtered: list[float] = []
    for s in samples:
        out = alpha * (prev_out + s - prev_in)
        prev_in = s
        prev_out = out
        filtered.append(out)

    mean_sq = sum(s * s for s in filtered) / len(filtered)
    if mean_sq < 1e-24:
        return -math.inf

    # +2 dB shelf bias above 1.5 kHz approximated as constant offset
    return 10.0 * math.log10(mean_sq) - 0.691 + 2.0


# ---------------------------------------------------------------------------
# Verification checks
# ---------------------------------------------------------------------------


def check_clipping(samples: list[float], peak_ceiling_dbtp: float) -> bool:
    """Return *True* when peak exceeds *peak_ceiling_dbtp* (a problem)."""
    return peak_dbfs(samples) > peak_ceiling_dbtp


def check_silence(samples: list[float], floor_db: float = -60.0) -> bool:
    """Return *True* when RMS is below *floor_db* (a problem)."""
    return rms_dbfs(samples) < floor_db


@dataclass(frozen=True)
class HarshnessReport:
    score: float
    over_threshold: bool


def check_harshness_proxy(
    *,
    drive: float,
    saturation: float,
    brightness: float = 1.0,
    threshold: float = 0.70,
) -> HarshnessReport:
    """Score combined harshness from bus drive, saturation, and brightness.

    The score is a 0-1 proxy: ``drive * 1.2 + saturation * 2.5 + max(0, brightness - 1) * 1.5``,
    clamped to [0, 1].  Returns *over_threshold=True* when this exceeds *threshold*.
    """
    score = _clamp(
        drive * 1.2 + saturation * 2.5 + max(0.0, brightness - 1.0) * 1.5,
        0.0,
        1.0,
    )
    return HarshnessReport(score=round(score, 4), over_threshold=score > threshold)


@dataclass(frozen=True)
class LowEndReport:
    low_rms_db: float
    full_rms_db: float
    low_end_ratio: float
    over_threshold: bool


def check_low_end_runaway(
    samples: list[float],
    sample_rate: int,
    *,
    cutoff_hz: float = 120.0,
    ratio_threshold: float = 0.70,
    min_low_rms_db: float = -42.0,
) -> LowEndReport:
    """Return a low-band dominance proxy for catching runaway bass."""
    full_rms = rms_dbfs(samples)
    if not samples or sample_rate <= 0 or full_rms == -math.inf:
        return LowEndReport(
            low_rms_db=-math.inf,
            full_rms_db=full_rms,
            low_end_ratio=0.0,
            over_threshold=False,
        )

    rc = 1.0 / (2.0 * math.pi * cutoff_hz)
    alpha = (1.0 / sample_rate) / (rc + (1.0 / sample_rate))
    low_band: list[float] = []
    out = 0.0
    for sample in samples:
        out += alpha * (sample - out)
        low_band.append(out)

    low_rms = rms_dbfs(low_band)
    if low_rms == -math.inf:
        return LowEndReport(
            low_rms_db=low_rms,
            full_rms_db=full_rms,
            low_end_ratio=0.0,
            over_threshold=False,
        )

    low_linear = 10.0 ** (low_rms / 20.0)
    full_linear = 10.0 ** (full_rms / 20.0)
    ratio = low_linear / full_linear if full_linear > 0.0 else 0.0
    return LowEndReport(
        low_rms_db=round(low_rms, 4),
        full_rms_db=round(full_rms, 4),
        low_end_ratio=round(ratio, 4),
        over_threshold=ratio > ratio_threshold and low_rms > min_low_rms_db,
    )


def lane_overlap_ratio(a: FrequencyLane, b: FrequencyLane) -> float:
    """Return overlap / narrower-lane-width, 0.0 when disjoint."""
    lo = max(a.low_hz, b.low_hz)
    hi = min(a.high_hz, b.high_hz)
    if lo >= hi:
        return 0.0
    overlap = hi - lo
    narrow = min(a.high_hz - a.low_hz, b.high_hz - b.low_hz)
    if narrow <= 0.0:
        return 0.0
    return round(overlap / narrow, 4)


@dataclass(frozen=True)
class MaskingPair:
    role_a: str
    role_b: str
    overlap: float


def check_masking(
    voice_targets: tuple[VoiceMixTarget, ...],
    threshold: float = 0.55,
) -> list[MaskingPair]:
    """Return role pairs whose frequency-lane overlap exceeds *threshold*."""
    pairs: list[MaskingPair] = []
    for i, a in enumerate(voice_targets):
        for b in voice_targets[i + 1 :]:
            overlap = lane_overlap_ratio(a.lane, b.lane)
            if overlap > threshold:
                pairs.append(MaskingPair(a.role, b.role, overlap))
    return pairs


# ---------------------------------------------------------------------------
# Composite profile verification
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MixProfileIssue:
    field: str
    message: str


def verify_mastering_policy(policy: MasteringPolicy) -> list[MixProfileIssue]:
    """Validate installation-safe mastering-policy bounds."""
    issues: list[MixProfileIssue] = []
    min_lufs, max_lufs = policy.target_lufs_range
    min_peak, max_peak = policy.true_peak_range_dbtp
    eq = policy.eq_intent

    if (
        min_lufs > max_lufs
        or min_lufs < -26.0
        or max_lufs > -13.0
        or not min_lufs <= policy.target_lufs <= max_lufs
    ):
        issues.append(
            MixProfileIssue(
                "mastering.target_lufs_range",
                f"unsafe LUFS target/range ({policy.target_lufs}, {policy.target_lufs_range})",
            )
        )

    if min_peak > max_peak or min_peak < -8.0 or max_peak > -1.0:
        issues.append(
            MixProfileIssue(
                "mastering.true_peak_range_dbtp",
                f"unsafe true-peak range ({policy.true_peak_range_dbtp})",
            )
        )

    if not min_peak <= policy.limiter_ceiling_dbtp <= max_peak or policy.limiter_ceiling_dbtp > -1.0:
        issues.append(
            MixProfileIssue(
                "mastering.limiter_ceiling_dbtp",
                f"unsafe limiter ceiling ({policy.limiter_ceiling_dbtp} dBTP)",
            )
        )

    if (
        not 25.0 <= eq.low_cut_hz <= 60.0
        or not -6.0 <= eq.low_shelf_db <= 0.5
        or not -2.0 <= eq.presence_tilt_db <= 2.0
        or not -2.0 <= eq.air_shelf_db <= 2.0
    ):
        issues.append(
            MixProfileIssue(
                "mastering.eq_intent",
                (
                    "broad EQ intent outside installation-safe bounds "
                    f"(low_cut={eq.low_cut_hz}, low_shelf={eq.low_shelf_db}, "
                    f"presence={eq.presence_tilt_db}, air={eq.air_shelf_db})"
                ),
            )
        )

    if not 8.0 <= policy.dynamic_contrast_db <= 24.0:
        issues.append(
            MixProfileIssue(
                "mastering.dynamic_contrast_db",
                f"dynamic contrast outside phase-safe range ({policy.dynamic_contrast_db} dB)",
            )
        )

    return issues


def verify_mix_profile(profile: MixProfile) -> list[MixProfileIssue]:
    """Validate internal consistency of a *MixProfile*.

    Returns an empty list when the profile is clean.
    """
    issues: list[MixProfileIssue] = []

    if profile.target_lufs > -10.0:
        issues.append(MixProfileIssue("target_lufs", f"dangerously loud target ({profile.target_lufs} LUFS)"))
    if profile.target_lufs < -40.0:
        issues.append(MixProfileIssue("target_lufs", f"inaudibly quiet target ({profile.target_lufs} LUFS)"))

    if profile.peak_ceiling_dbtp > 0.0:
        issues.append(MixProfileIssue("peak_ceiling_dbtp", "ceiling above 0 dBTP invites clipping"))
    if profile.peak_ceiling_dbtp < -6.0:
        issues.append(MixProfileIssue("peak_ceiling_dbtp", f"ceiling too restrictive ({profile.peak_ceiling_dbtp} dBTP)"))

    if profile.bus_comp_ratio < 1.0:
        issues.append(MixProfileIssue("bus_comp_ratio", "compression ratio below 1:1 is expansion"))
    if profile.bus_comp_ratio > 8.0:
        issues.append(MixProfileIssue("bus_comp_ratio", f"extreme compression ({profile.bus_comp_ratio}:1)"))

    if profile.theramini_duck_db < 0.0:
        issues.append(MixProfileIssue("theramini_duck_db", "negative ducking would boost"))

    if profile.mastering is not None:
        issues.extend(verify_mastering_policy(profile.mastering))
        if profile.target_lufs != profile.mastering.target_lufs:
            issues.append(MixProfileIssue("mastering.target_lufs", "mix target and mastering target disagree"))
        if profile.peak_ceiling_dbtp != profile.mastering.limiter_ceiling_dbtp:
            issues.append(MixProfileIssue("mastering.limiter_ceiling_dbtp", "mix ceiling and limiter ceiling disagree"))

    for target in profile.voice_targets:
        if target.lane.low_hz >= target.lane.high_hz:
            issues.append(MixProfileIssue(f"voice_targets.{target.role}", "inverted frequency lane"))
        if not 0.0 <= target.stereo_width <= 1.0:
            issues.append(MixProfileIssue(f"voice_targets.{target.role}", f"stereo width out of range ({target.stereo_width})"))
        if not 0.0 <= target.reverb_send <= 1.0:
            issues.append(MixProfileIssue(f"voice_targets.{target.role}", f"reverb send out of range ({target.reverb_send})"))

    masking = check_masking(profile.voice_targets)
    for pair in masking:
        issues.append(
            MixProfileIssue(
                "masking",
                f"{pair.role_a}/{pair.role_b} lane overlap {pair.overlap:.0%}",
            )
        )

    return issues


def verify_render_loudness(
    samples: list[float],
    sample_rate: int,
    target_lufs: float,
    tolerance: float = 3.0,
) -> bool:
    """Return *True* when estimated loudness is within *tolerance* dB of target."""
    measured = estimate_lufs_proxy(samples, sample_rate)
    if measured == -math.inf:
        return False
    return abs(measured - target_lufs) <= tolerance
