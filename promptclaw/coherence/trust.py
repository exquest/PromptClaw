"""Trust scoring for the Coherence Engine."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass
class TrustScore:
    """Per-agent trust score tracking."""

    agent: str
    score: float  # 0.0 to 1.0
    hard_violations: int = 0
    soft_violations: int = 0
    compliant_actions: int = 0
    last_updated: str = ""


@dataclass(frozen=True)
class TrustEventPlan:
    """Typed canonical description of one trust mutation event."""

    name: str
    delta: float
    counter_field: str
    description: str


_COUNTER_FIELDS: frozenset[str] = frozenset(
    {"hard_violations", "soft_violations", "compliant_actions"}
)


def trust_event_plans() -> tuple[TrustEventPlan, ...]:
    """Return the canonical trust event plans sourced from TrustManager constants."""
    specs: tuple[tuple[str, float, str, str], ...] = (
        (
            "hard_violation",
            TrustManager.HARD_PENALTY,
            "hard_violations",
            "Hard constitutional violation: large penalty.",
        ),
        (
            "soft_violation",
            TrustManager.SOFT_PENALTY,
            "soft_violations",
            "Soft guidance violation: small penalty.",
        ),
        (
            "compliant_action",
            TrustManager.COMPLIANT_REWARD,
            "compliant_actions",
            "Compliant action observed: small reward.",
        ),
    )
    plans: list[TrustEventPlan] = []
    for name, delta, counter_field, description in specs:
        plans.append(
            TrustEventPlan(
                name=name,
                delta=delta,
                counter_field=counter_field,
                description=description,
            )
        )
    return tuple(plans)


class TrustManager:
    """Manages per-agent trust scores with penalty/reward mechanics."""

    INITIAL_SCORE = 0.5
    HARD_PENALTY = -0.3
    SOFT_PENALTY = -0.05
    COMPLIANT_REWARD = 0.02
    RESTRICTION_THRESHOLD = 0.2

    _SCHEMA = """
    CREATE TABLE IF NOT EXISTS trust_scores (
        agent TEXT PRIMARY KEY,
        score REAL NOT NULL,
        hard_violations INTEGER NOT NULL DEFAULT 0,
        soft_violations INTEGER NOT NULL DEFAULT 0,
        compliant_actions INTEGER NOT NULL DEFAULT 0,
        last_updated TEXT NOT NULL DEFAULT ''
    );
    """

    def __init__(self, db_path: Path | None = None) -> None:
        self.scores: dict[str, TrustScore] = {}
        self._db_path = db_path
        self._conn: sqlite3.Connection | None = None
        if db_path is not None:
            self._migrate()
            self._load()

    # --- Optional SQLite persistence (in-memory when db_path is None) ---

    def _get_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(str(self._db_path), timeout=30)
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA busy_timeout=30000")
            self._conn.execute("PRAGMA synchronous=NORMAL")
            self._conn.row_factory = sqlite3.Row
        return self._conn

    def _migrate(self) -> None:
        assert self._db_path is not None
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = self._get_conn()
        conn.executescript(self._SCHEMA)
        conn.commit()

    def _load(self) -> None:
        for row in self._get_conn().execute("SELECT * FROM trust_scores"):
            self.scores[row["agent"]] = TrustScore(
                agent=row["agent"],
                score=row["score"],
                hard_violations=row["hard_violations"],
                soft_violations=row["soft_violations"],
                compliant_actions=row["compliant_actions"],
                last_updated=row["last_updated"],
            )

    def _persist(self, ts: TrustScore) -> None:
        if self._db_path is None:
            return
        conn = self._get_conn()
        conn.execute(
            "INSERT INTO trust_scores "
            "(agent, score, hard_violations, soft_violations, compliant_actions, last_updated) "
            "VALUES (?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(agent) DO UPDATE SET score=excluded.score, "
            "hard_violations=excluded.hard_violations, soft_violations=excluded.soft_violations, "
            "compliant_actions=excluded.compliant_actions, last_updated=excluded.last_updated",
            (ts.agent, ts.score, ts.hard_violations, ts.soft_violations,
             ts.compliant_actions, ts.last_updated),
        )
        conn.commit()

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

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
        if value < 0.0:
            return 0.0
        if value > 1.0:
            return 1.0
        return value

    def _touch(self, ts: TrustScore) -> None:
        ts.last_updated = datetime.now(timezone.utc).isoformat()

    def apply_event(self, agent: str, plan: TrustEventPlan) -> float:
        """Apply one canonical trust plan: clamp, increment counter, touch, return score."""
        if plan.counter_field not in _COUNTER_FIELDS:
            raise ValueError(
                f"Unknown trust counter field on plan: {plan.counter_field!r}"
            )
        ts = self.get_score(agent)
        ts.score = self._clamp(ts.score + plan.delta)
        current = getattr(ts, plan.counter_field)
        setattr(ts, plan.counter_field, current + 1)
        self._touch(ts)
        self._persist(ts)
        return ts.score

    def apply_event_by_name(self, agent: str, plan_name: str) -> float:
        """Look up a canonical plan by name and apply it to ``agent``."""
        plan = _PLAN_BY_NAME.get(plan_name)
        if plan is None:
            raise ValueError(f"Unknown trust plan name: {plan_name!r}")
        return self.apply_event(agent, plan)

    def apply_hard_violation(self, agent: str) -> float:
        """Penalize by HARD_PENALTY, clamp to [0.0, 1.0], return new score."""
        return self.apply_event(agent, _PLAN_BY_NAME["hard_violation"])

    def apply_soft_violation(self, agent: str) -> float:
        """Penalize by SOFT_PENALTY, clamp to [0.0, 1.0], return new score."""
        return self.apply_event(agent, _PLAN_BY_NAME["soft_violation"])

    def apply_compliant_action(self, agent: str) -> float:
        """Reward by COMPLIANT_REWARD, clamp to [0.0, 1.0], return new score."""
        return self.apply_event(agent, _PLAN_BY_NAME["compliant_action"])

    def should_restrict(self, agent: str) -> bool:
        """True if score < RESTRICTION_THRESHOLD."""
        return self.get_score(agent).score < self.RESTRICTION_THRESHOLD

    def all_scores(self) -> dict[str, TrustScore]:
        """Return a copy of all tracked scores."""
        return dict(self.scores)

    def restricted_agents(self) -> list[str]:
        """Return alphabetically-sorted agents whose score is below the threshold."""
        restricted: list[str] = []
        for agent in sorted(self.scores):
            if self.scores[agent].score < self.RESTRICTION_THRESHOLD:
                restricted.append(agent)
        return restricted

    def summarize_agent(self, agent: str) -> dict[str, Any]:
        """Return a JSON-safe per-agent summary including restriction status."""
        ts = self.get_score(agent)
        if ts.score < self.RESTRICTION_THRESHOLD:
            restricted = True
        else:
            restricted = False
        return {
            "agent": ts.agent,
            "score": ts.score,
            "hard_violations": ts.hard_violations,
            "soft_violations": ts.soft_violations,
            "compliant_actions": ts.compliant_actions,
            "last_updated": ts.last_updated,
            "restricted": restricted,
        }

    def fleet_summary(self) -> dict[str, Any]:
        """Return a JSON-safe operator summary of trust state across all agents."""
        rows: list[dict[str, Any]] = []
        restricted_count = 0
        for agent in sorted(self.scores):
            row = self.summarize_agent(agent)
            if row["restricted"]:
                restricted_count += 1
            rows.append(row)
        return {
            "initial_score": self.INITIAL_SCORE,
            "hard_penalty": self.HARD_PENALTY,
            "soft_penalty": self.SOFT_PENALTY,
            "compliant_reward": self.COMPLIANT_REWARD,
            "restriction_threshold": self.RESTRICTION_THRESHOLD,
            "agent_count": len(rows),
            "restricted_count": restricted_count,
            "agents": rows,
        }


_PLAN_BY_NAME: dict[str, TrustEventPlan] = {plan.name: plan for plan in trust_event_plans()}
