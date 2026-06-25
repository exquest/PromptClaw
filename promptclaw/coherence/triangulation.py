"""Triangulation — independence-of-angle scoring for verification (P6).

"Three views from the same spot are one view repeated." Agreement among verifiers is only
real confirmation when the verifiers are independent — a different model / role / angle.
This primitive discounts correlated agreement (the same angle counted more than once) and
counts independent support separately, so a fan-out path can reward genuine triangulation
rather than echoes. The in-repo orchestrator verifies singly; the consumers are the
multi-verifier paths (SDP pair-rotate, Workflow fan-outs).
See docs/Shadowland2/promptclaw-integration-proposal.md (P6).
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass


@dataclass
class TriangulationResult:
    majority_verdict: str
    total_votes: int
    distinct_angles: int  # how many genuinely different viewpoints voted
    independent_support: int  # distinct angles backing the majority verdict
    correlated: bool  # at least one angle voted more than once (echo, not confirmation)
    note: str


def assess_triangulation(verdicts: list[dict]) -> TriangulationResult:
    """Score a set of verifier verdicts for independence of angle.

    Each verdict dict carries a ``verdict`` and an angle key (``model`` preferred, then
    ``angle``, then ``agent``). Agreement counts by *distinct angle*, not by raw vote count.
    """
    if not verdicts:
        return TriangulationResult("", 0, 0, 0, False, "no verdicts to triangulate")

    normalized = [(_angle(v), _verdict(v)) for v in verdicts]
    counts = Counter(verdict for _, verdict in normalized)
    majority = counts.most_common(1)[0][0]

    angles = [a for a, _ in normalized if a]
    distinct = len(set(angles))
    independent_support = len({a for a, verdict in normalized if a and verdict == majority})
    correlated = len(verdicts) > distinct

    if correlated:
        note = (
            f"{len(verdicts)} verdicts from {distinct} distinct angle(s): repeated angles are "
            f"one view, not independent confirmation. Independent support for {majority!r}: "
            f"{independent_support}."
        )
    else:
        note = (
            f"{independent_support} independent angle(s) support {majority!r} "
            f"(of {distinct} distinct)."
        )
    return TriangulationResult(
        majority_verdict=majority,
        total_votes=len(verdicts),
        distinct_angles=distinct,
        independent_support=independent_support,
        correlated=correlated,
        note=note,
    )


def _angle(v: dict) -> str:
    return str(v.get("model") or v.get("angle") or v.get("agent") or "").strip()


def _verdict(v: dict) -> str:
    return str(v.get("verdict", "")).strip().upper()
