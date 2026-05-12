"""Weekly KL-divergence audit for the generation IDyOM LTM (T-031).

This module compares the current IDyOM long-term model against an
immutable week-0 seed snapshot, persists an 8-week rolling history of
three correlated signals (KL divergence, generated-audio ratio, CLAP
centroid variance), and writes a single operator-actionable alert file
when the conjunction of all three signals indicates *generation
collapse-drift*. The audit never auto-rollbacks the LTM — operators
keep that decision.
"""

from __future__ import annotations

import json
import math
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Sequence

import numpy as np


DEFAULT_HISTORY_PATH = "/home/user/cypherclaw-data/state/idyom_kl_audit.json"
DEFAULT_ALERT_PATH = "/tmp/generation_collapse_alert.json"
DEFAULT_HISTORY_WINDOW = 8
DEFAULT_GENERATED_RATIO_THRESHOLD = 0.5
DEFAULT_LAPLACE_ALPHA = 1.0
MIN_TREND_POINTS = 3


NgramKey = tuple[int, ...]


@dataclass(frozen=True)
class AuditEntry:
    """One persisted weekly observation."""

    week_index: int
    timestamp: str
    kl_divergence: float
    generated_ratio: float
    clap_centroid_variance: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AuditEntry":
        return cls(
            week_index=int(data["week_index"]),
            timestamp=str(data["timestamp"]),
            kl_divergence=float(data["kl_divergence"]),
            generated_ratio=float(data["generated_ratio"]),
            clap_centroid_variance=float(data["clap_centroid_variance"]),
        )


@dataclass(frozen=True)
class AuditReport:
    """Result of one weekly KL-divergence audit run."""

    week_index: int
    timestamp: str
    kl_divergence: float
    generated_ratio: float
    clap_centroid_variance: float
    history: tuple[AuditEntry, ...] = field(default_factory=tuple)
    flagged: bool = False
    flag_reason: str = ""
    alert_path: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "week_index": self.week_index,
            "timestamp": self.timestamp,
            "kl_divergence": self.kl_divergence,
            "generated_ratio": self.generated_ratio,
            "clap_centroid_variance": self.clap_centroid_variance,
            "history": [entry.to_dict() for entry in self.history],
            "flagged": self.flagged,
            "flag_reason": self.flag_reason,
            "alert_path": self.alert_path,
        }


def _load_ltm(path: Path) -> dict[NgramKey, float]:
    if not path.exists():
        raise FileNotFoundError(f"LTM file not found: {path}")
    raw = json.loads(path.read_text())
    if not isinstance(raw, dict):
        raise ValueError(f"LTM file is not a JSON object: {path}")
    parsed: dict[NgramKey, float] = {}
    for key, value in raw.items():
        ngram = tuple(int(part) for part in str(key).split(",") if part != "")
        parsed[ngram] = float(value)
    return parsed


def _smoothed_distribution(
    counts: dict[NgramKey, float],
    test_ngrams: Sequence[NgramKey],
    alpha: float,
) -> np.ndarray:
    """Laplace-smoothed probability vector over (test_ngrams + "other")."""
    masses = np.empty(len(test_ngrams) + 1, dtype=np.float64)
    test_set = set(test_ngrams)
    for i, ngram in enumerate(test_ngrams):
        masses[i] = float(counts.get(ngram, 0.0)) + alpha
    other = sum(v for k, v in counts.items() if k not in test_set)
    masses[-1] = float(other) + alpha
    total = float(masses.sum())
    return masses / total


def _symmetric_kl(p: np.ndarray, q: np.ndarray) -> float:
    """Symmetric KL in nats: 0.5 * (KL(p||q) + KL(q||p))."""
    return 0.5 * float(
        np.sum(p * np.log(p / q)) + np.sum(q * np.log(q / p))
    )


def _slope(values: Sequence[float]) -> float:
    """Linear-regression slope of `values` against integer time indices."""
    n = len(values)
    if n < 2:
        return 0.0
    x = np.arange(n, dtype=np.float64)
    y = np.asarray(values, dtype=np.float64)
    x_mean = x.mean()
    y_mean = y.mean()
    denom = float(np.sum((x - x_mean) ** 2))
    if denom == 0.0:
        return 0.0
    return float(np.sum((x - x_mean) * (y - y_mean)) / denom)


def _load_history(path: Path) -> list[AuditEntry]:
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return []
    raw = payload.get("history", []) if isinstance(payload, dict) else []
    out: list[AuditEntry] = []
    for item in raw:
        try:
            out.append(AuditEntry.from_dict(item))
        except (KeyError, ValueError, TypeError):
            continue
    return out


def _save_history(path: Path, history: Sequence[AuditEntry]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"history": [entry.to_dict() for entry in history]}
    tmp = path.with_name(f"{path.name}.tmp")
    tmp.write_text(json.dumps(payload, indent=2))
    os.replace(str(tmp), str(path))


def _evaluate_collapse(
    history: Sequence[AuditEntry],
    *,
    generated_ratio_threshold: float,
) -> tuple[bool, str]:
    if len(history) < MIN_TREND_POINTS:
        return False, "insufficient history"
    kl_slope = _slope([e.kl_divergence for e in history])
    var_slope = _slope([e.clap_centroid_variance for e in history])
    latest_generated = history[-1].generated_ratio

    kl_increasing = kl_slope > 0.0
    generated_high = latest_generated >= generated_ratio_threshold
    variance_decreasing = var_slope < 0.0

    if kl_increasing and generated_high and variance_decreasing:
        return True, (
            f"collapse-drift: KL slope {kl_slope:.4f} > 0, "
            f"generated_ratio {latest_generated:.2f} >= {generated_ratio_threshold:.2f}, "
            f"clap_centroid_variance slope {var_slope:.4f} < 0"
        )
    return False, (
        f"healthy: kl_increasing={kl_increasing}, "
        f"generated_high={generated_high}, "
        f"variance_decreasing={variance_decreasing}"
    )


def _write_alert(
    alert_path: Path,
    report: AuditReport,
) -> None:
    alert_path.parent.mkdir(parents=True, exist_ok=True)
    alert_path.write_text(json.dumps(report.to_dict(), indent=2))


def idyom_kl_divergence_audit(
    *,
    current_ltm_path: str | Path,
    snapshot_path: str | Path,
    test_ngrams: Sequence[Sequence[int]],
    generated_ratio: float,
    clap_centroid_variance: float,
    history_path: str | Path = DEFAULT_HISTORY_PATH,
    alert_path: str | Path = DEFAULT_ALERT_PATH,
    generated_ratio_threshold: float = DEFAULT_GENERATED_RATIO_THRESHOLD,
    history_window: int = DEFAULT_HISTORY_WINDOW,
    laplace_alpha: float = DEFAULT_LAPLACE_ALPHA,
    clock: Callable[[], datetime] | None = None,
) -> AuditReport:
    """Run one weekly IDyOM KL-divergence audit.

    Loads the current LTM and the immutable seed snapshot, computes the
    symmetric KL over the supplied fixed test set of melodic n-grams,
    appends the observation to a rolling 8-week history persisted at
    ``history_path``, and flags ``collapse-drift`` only when KL is
    increasing AND ``generated_ratio`` is at/above
    ``generated_ratio_threshold`` AND ``clap_centroid_variance`` is
    decreasing across the visible history. Writes a JSON alert file at
    ``alert_path`` on flag and never modifies the LTM or snapshot.
    """
    if not test_ngrams:
        raise ValueError("empty test set")
    if not (0.0 <= generated_ratio <= 1.0):
        raise ValueError(
            f"generated_ratio must be in [0, 1], got {generated_ratio}"
        )
    if clap_centroid_variance < 0.0 or math.isnan(clap_centroid_variance):
        raise ValueError(
            f"clap_centroid_variance must be non-negative, got {clap_centroid_variance}"
        )

    current = _load_ltm(Path(current_ltm_path))
    snapshot = _load_ltm(Path(snapshot_path))

    canonical_ngrams: tuple[NgramKey, ...] = tuple(tuple(n) for n in test_ngrams)
    p = _smoothed_distribution(current, canonical_ngrams, laplace_alpha)
    q = _smoothed_distribution(snapshot, canonical_ngrams, laplace_alpha)
    kl = _symmetric_kl(p, q)

    now = (clock or (lambda: datetime.now(timezone.utc)))()
    history_path_obj = Path(history_path)
    alert_path_obj = Path(alert_path)

    history = _load_history(history_path_obj)
    next_index = (history[-1].week_index + 1) if history else 0
    entry = AuditEntry(
        week_index=next_index,
        timestamp=now.isoformat(),
        kl_divergence=float(kl),
        generated_ratio=float(generated_ratio),
        clap_centroid_variance=float(clap_centroid_variance),
    )
    history.append(entry)
    if len(history) > history_window:
        history = history[-history_window:]
    _save_history(history_path_obj, history)

    flagged, reason = _evaluate_collapse(
        history, generated_ratio_threshold=generated_ratio_threshold
    )

    report = AuditReport(
        week_index=entry.week_index,
        timestamp=entry.timestamp,
        kl_divergence=entry.kl_divergence,
        generated_ratio=entry.generated_ratio,
        clap_centroid_variance=entry.clap_centroid_variance,
        history=tuple(history),
        flagged=flagged,
        flag_reason=reason,
        alert_path=str(alert_path_obj) if flagged else None,
    )
    if flagged:
        _write_alert(alert_path_obj, report)
    return report


__all__ = (
    "DEFAULT_ALERT_PATH",
    "DEFAULT_GENERATED_RATIO_THRESHOLD",
    "DEFAULT_HISTORY_PATH",
    "DEFAULT_HISTORY_WINDOW",
    "DEFAULT_LAPLACE_ALPHA",
    "MIN_TREND_POINTS",
    "AuditEntry",
    "AuditReport",
    "idyom_kl_divergence_audit",
)


def _main() -> int:
    """Entry point for the systemd weekly audit unit.

    Reads the path to a JSON config file from the
    ``IDYOM_KL_AUDIT_CONFIG`` environment variable. The JSON must
    supply ``current_ltm_path``, ``snapshot_path``, ``test_ngrams``,
    ``generated_ratio`` and ``clap_centroid_variance``; ``history_path``
    and ``alert_path`` are optional and fall back to module defaults.
    See ``idyom_kl_audit_config.json.example`` for a template.
    Intended to be invoked as ``python3 -m senseweave.generation.health``.
    """
    cfg_path = os.environ.get("IDYOM_KL_AUDIT_CONFIG")
    if not cfg_path:
        raise SystemExit(
            "IDYOM_KL_AUDIT_CONFIG must point to a JSON config file "
            "with current_ltm_path, snapshot_path, test_ngrams, "
            "generated_ratio, clap_centroid_variance "
            "(see idyom_kl_audit_config.json.example)"
        )
    config = json.loads(Path(cfg_path).read_text())
    report = idyom_kl_divergence_audit(
        current_ltm_path=config["current_ltm_path"],
        snapshot_path=config["snapshot_path"],
        test_ngrams=[tuple(int(p) for p in ng) for ng in config["test_ngrams"]],
        generated_ratio=float(config["generated_ratio"]),
        clap_centroid_variance=float(config["clap_centroid_variance"]),
        history_path=config.get("history_path", DEFAULT_HISTORY_PATH),
        alert_path=config.get("alert_path", DEFAULT_ALERT_PATH),
    )
    print(json.dumps(report.to_dict(), indent=2))
    return 0


if __name__ == "__main__":  # pragma: no cover - systemd entry point
    raise SystemExit(_main())
