"""Trust scoring for the Coherence Engine."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class TrustScore:
    """Per-agent trust score tracking."""

    agent: str
    score: float  # 0.0 to 1.0
    hard_violations: int = 0
    soft_violations: int = 0
    compliant_actions: int = 0
    last_updated: str = ""


class TrustManager:
    """Manages per-agent trust scores with penalty/reward mechanics."""

    INITIAL_SCORE = 0.5
    HARD_PENALTY = -0.3
    SOFT_PENALTY = -0.05
    COMPLIANT_REWARD = 0.02
    RESTRICTION_THRESHOLD = 0.2

    def __init__(self) -> None:
        self.scores: dict[str, TrustScore] = {}

    def get_score(self, agent: str) -> TrustScore:
        """Return existing score or create new one with INITIAL_SCORE."""
        if agent not in self.scores:
            self.scores[agent] = TrustScore(
                agent=agent,
                score=self.INITIAL_SCORE,
                last_updated=datetime.now(timezone.utc).isoformat(),
            )
        return self.scores[agent]

    def _clamp(self, value: float) -> float:
        return max(0.0, min(1.0, value))

    def _touch(self, ts: TrustScore) -> None:
        ts.last_updated = datetime.now(timezone.utc).isoformat()

    def apply_hard_violation(self, agent: str) -> float:
        """Penalize by HARD_PENALTY, clamp to [0.0, 1.0], return new score."""
        ts = self.get_score(agent)
        ts.score = self._clamp(ts.score + self.HARD_PENALTY)
        ts.hard_violations += 1
        self._touch(ts)
        return ts.score

    def apply_soft_violation(self, agent: str) -> float:
        """Penalize by SOFT_PENALTY, clamp to [0.0, 1.0], return new score."""
        ts = self.get_score(agent)
        ts.score = self._clamp(ts.score + self.SOFT_PENALTY)
        ts.soft_violations += 1
        self._touch(ts)
        return ts.score

    def apply_compliant_action(self, agent: str) -> float:
        """Reward by COMPLIANT_REWARD, clamp to [0.0, 1.0], return new score."""
        ts = self.get_score(agent)
        ts.score = self._clamp(ts.score + self.COMPLIANT_REWARD)
        ts.compliant_actions += 1
        self._touch(ts)
        return ts.score

    def should_restrict(self, agent: str) -> bool:
        """True if score < RESTRICTION_THRESHOLD."""
        return self.get_score(agent).score < self.RESTRICTION_THRESHOLD

    def all_scores(self) -> dict[str, TrustScore]:
        """Return a copy of all tracked scores."""
        return dict(self.scores)
