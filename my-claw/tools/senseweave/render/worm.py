"""Performance-worm logger: 2D trajectory in tempo–loudness space.

Emits per-piece worm JSON and optional PNG to artifacts/worms/<piece_id>/.
Computes convex-hull area and rejects mechanical (point-worm) and
space-filling (random) trajectories.
"""
from __future__ import annotations

import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    _HAS_MPL = True
except ImportError:
    _HAS_MPL = False

MECHANICAL_AREA_THRESHOLD = 1.0
SATURATION_AREA_THRESHOLD = 50.0


@dataclass(frozen=True)
class WormResult:
    """Analysis result for a single piece's performance worm."""

    piece_id: str
    points: tuple[tuple[float, float], ...]
    hull_area: float
    rejected: bool
    rejection_reason: str | None = None


def compute_worm(
    piece_id: str,
    tempo: Sequence[float],
    loudness: Sequence[float],
    *,
    mechanical_threshold: float = MECHANICAL_AREA_THRESHOLD,
    saturation_threshold: float = SATURATION_AREA_THRESHOLD,
) -> WormResult:
    """Build a performance worm from parallel tempo and loudness series.

    Returns a WormResult with convex-hull area and rejection status.
    """
    length = min(len(tempo), len(loudness))
    points = tuple((float(tempo[i]), float(loudness[i])) for i in range(length))
    area = convex_hull_area(points)

    rejected = False
    reason: str | None = None
    if area < mechanical_threshold:
        rejected = True
        reason = f"point-worm: hull area {area:.4f} < {mechanical_threshold}"
    elif area > saturation_threshold:
        rejected = True
        reason = f"space-filling: hull area {area:.4f} > {saturation_threshold}"

    return WormResult(
        piece_id=piece_id,
        points=points,
        hull_area=area,
        rejected=rejected,
        rejection_reason=reason,
    )


def emit_worm(
    result: WormResult,
    artifacts_dir: str | Path = "artifacts",
) -> Path:
    """Write worm JSON (and PNG if matplotlib is available) to disk."""
    base = Path(artifacts_dir) / "worms" / result.piece_id
    base.mkdir(parents=True, exist_ok=True)

    json_path = base / "worm.json"
    json_path.write_text(
        json.dumps(_result_to_dict(result), indent=2) + "\n",
        encoding="utf-8",
    )

    if _HAS_MPL:
        _render_png(result, base / "worm.png")

    return base


def convex_hull_area(points: Sequence[tuple[float, float]]) -> float:
    """Compute convex-hull area via Andrew's monotone chain algorithm."""
    unique = sorted(set(points))
    if len(unique) < 3:
        return 0.0

    def cross(
        o: tuple[float, float],
        a: tuple[float, float],
        b: tuple[float, float],
    ) -> float:
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower: list[tuple[float, float]] = []
    for p in unique:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0.0:
            lower.pop()
        lower.append(p)

    upper: list[tuple[float, float]] = []
    for p in reversed(unique):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0.0:
            upper.pop()
        upper.append(p)

    hull = lower[:-1] + upper[:-1]
    area = 0.0
    for i, pt in enumerate(hull):
        nxt = hull[(i + 1) % len(hull)]
        area += pt[0] * nxt[1] - nxt[0] * pt[1]
    return abs(area) / 2.0


def _result_to_dict(result: WormResult) -> dict[str, Any]:
    return {
        "piece_id": result.piece_id,
        "points": [list(p) for p in result.points],
        "hull_area": result.hull_area,
        "rejected": result.rejected,
        "rejection_reason": result.rejection_reason,
    }


def _render_png(result: WormResult, path: Path) -> None:
    if not result.points:
        return

    tempo_vals = [p[0] for p in result.points]
    loudness_vals = [p[1] for p in result.points]

    fig, ax = plt.subplots(figsize=(6, 4))
    ax.plot(tempo_vals, loudness_vals, "-o", markersize=3, linewidth=1, alpha=0.7)
    ax.set_xlabel("Tempo")
    ax.set_ylabel("Loudness")
    title = f"Worm: {result.piece_id} (area={result.hull_area:.2f})"
    if result.rejected:
        title += f" [REJECTED: {result.rejection_reason}]"
    ax.set_title(title, fontsize=9)
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(str(path), dpi=150)
    plt.close(fig)


__all__ = [
    "MECHANICAL_AREA_THRESHOLD",
    "SATURATION_AREA_THRESHOLD",
    "WormResult",
    "compute_worm",
    "convex_hull_area",
    "emit_worm",
]
