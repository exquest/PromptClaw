"""Daily/monthly USD budget for external generation backends (CCG-006)."""

from __future__ import annotations

import json
import os
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


DEFAULT_DAILY_CAP_USD = 5.0
DEFAULT_MONTHLY_CAP_USD = 100.0
DEFAULT_STATE_PATH = "/home/user/cypherclaw-data/state/generation_budget.json"

ENV_DAILY_CAP = "CYPHERCLAW_GENERATION_DAILY_CAP_USD"
ENV_MONTHLY_CAP = "CYPHERCLAW_GENERATION_MONTHLY_CAP_USD"

OVERHEAD_FACTOR = 1.5

# Per-audio-second cost estimate in USD (Replicate pricing for ~30 s clips,
# inflated by the OVERHEAD_FACTOR at call sites).
PER_SECOND_USD: dict[str, float] = {
    "musicgen-medium": 0.0050,
    "stable-audio-open": 0.0035,
}

_FALLBACK_PER_SECOND_USD = max(PER_SECOND_USD.values())


@dataclass
class BudgetState:
    """Persistent counters tracked by :class:`GenerationBudget`."""

    today_date: str
    today_spent_usd: float
    month_key: str
    month_spent_usd: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "today_date": self.today_date,
            "today_spent_usd": float(self.today_spent_usd),
            "month_key": self.month_key,
            "month_spent_usd": float(self.month_spent_usd),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "BudgetState":
        return cls(
            today_date=str(data["today_date"]),
            today_spent_usd=float(data.get("today_spent_usd", 0.0)),
            month_key=str(data["month_key"]),
            month_spent_usd=float(data.get("month_spent_usd", 0.0)),
        )


def _today_key(now: datetime) -> str:
    return now.strftime("%Y-%m-%d")


def _month_key(now: datetime) -> str:
    return now.strftime("%Y-%m")


def _coerce_cap(value: float | int | str | None, default: float) -> float:
    if value is None:
        return float(default)
    return float(value)


def _resolve_cap(
    explicit: float | int | None,
    env_var: str,
    default: float,
) -> float:
    env_value = os.environ.get(env_var)
    if env_value is not None and env_value != "":
        try:
            return float(env_value)
        except ValueError:
            pass
    return _coerce_cap(explicit, default)


class GenerationBudget:
    """USD-capped budget gate for the generation queue.

    Persists ``today_spent_usd`` and ``month_spent_usd`` to a JSON file via
    atomic ``os.replace``. ``allow(req)`` estimates the cost of a request
    using ``PER_SECOND_USD[req.model] * req.duration_sec * OVERHEAD_FACTOR``
    and refuses the request if either cap would be crossed. ``record(result)``
    adds the realized ``cost_usd`` from a generation result back into the
    counters. Date and month boundaries roll the relevant counter back to
    zero on the first call after the boundary is crossed.
    """

    def __init__(
        self,
        path: str | Path = DEFAULT_STATE_PATH,
        *,
        daily_cap_usd: float | int | None = None,
        monthly_cap_usd: float | int | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.path = Path(path)
        self.daily_cap_usd = _resolve_cap(
            daily_cap_usd, ENV_DAILY_CAP, DEFAULT_DAILY_CAP_USD
        )
        self.monthly_cap_usd = _resolve_cap(
            monthly_cap_usd, ENV_MONTHLY_CAP, DEFAULT_MONTHLY_CAP_USD
        )
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._lock = threading.Lock()
        self._state = self._load()

    @property
    def state(self) -> BudgetState:
        """Return a snapshot of the current (rolled-over) state."""
        with self._lock:
            self._state = self._roll_over(self._state)
            return BudgetState(
                today_date=self._state.today_date,
                today_spent_usd=self._state.today_spent_usd,
                month_key=self._state.month_key,
                month_spent_usd=self._state.month_spent_usd,
            )

    def estimate_cost_usd(self, req: Any) -> float:
        """Estimate USD cost for ``req`` with the 1.5x overhead factor."""
        model = getattr(req, "model", None) or "musicgen-medium"
        duration = float(getattr(req, "duration_sec", 0.0))
        rate = PER_SECOND_USD.get(str(model), _FALLBACK_PER_SECOND_USD)
        return rate * duration * OVERHEAD_FACTOR

    def allow(self, req: Any) -> tuple[bool, str]:
        """Return ``(allowed, reason)`` for ``req`` against the current caps."""
        estimate = self.estimate_cost_usd(req)
        with self._lock:
            self._state = self._roll_over(self._state)
            today_after = self._state.today_spent_usd + estimate
            month_after = self._state.month_spent_usd + estimate
            if today_after > self.daily_cap_usd:
                return (
                    False,
                    (
                        f"daily cap reached: spent ${self._state.today_spent_usd:.2f} "
                        f"+ est ${estimate:.2f} > cap ${self.daily_cap_usd:.2f}"
                    ),
                )
            if month_after > self.monthly_cap_usd:
                return (
                    False,
                    (
                        f"monthly cap reached: spent ${self._state.month_spent_usd:.2f} "
                        f"+ est ${estimate:.2f} > cap ${self.monthly_cap_usd:.2f}"
                    ),
                )
            return True, "ok"

    def record(self, result: Any) -> None:
        """Add the realized ``cost_usd`` of ``result`` to the counters."""
        cost = _extract_cost_usd(result)
        if cost <= 0.0:
            return
        with self._lock:
            rolled = self._roll_over(self._state)
            self._state = BudgetState(
                today_date=rolled.today_date,
                today_spent_usd=rolled.today_spent_usd + cost,
                month_key=rolled.month_key,
                month_spent_usd=rolled.month_spent_usd + cost,
            )
            self._save(self._state)

    def _now(self) -> datetime:
        return self._clock()

    def _load(self) -> BudgetState:
        try:
            if self.path.exists():
                data = json.loads(self.path.read_text())
                return self._roll_over(BudgetState.from_dict(data))
        except (OSError, json.JSONDecodeError, KeyError, ValueError, TypeError):
            pass
        now = self._now()
        return BudgetState(
            today_date=_today_key(now),
            today_spent_usd=0.0,
            month_key=_month_key(now),
            month_spent_usd=0.0,
        )

    def _roll_over(self, state: BudgetState) -> BudgetState:
        now = self._now()
        today = _today_key(now)
        month = _month_key(now)
        if state.today_date == today and state.month_key == month:
            return state
        return BudgetState(
            today_date=today,
            today_spent_usd=state.today_spent_usd if state.today_date == today else 0.0,
            month_key=month,
            month_spent_usd=state.month_spent_usd if state.month_key == month else 0.0,
        )

    def _save(self, state: BudgetState) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_name(f"{self.path.name}.tmp")
        tmp.write_text(json.dumps(state.to_dict(), indent=2))
        os.replace(str(tmp), str(self.path))


def _extract_cost_usd(result: Any) -> float:
    if result is None:
        return 0.0
    if isinstance(result, (int, float)):
        return float(result)
    if isinstance(result, dict):
        return float(result.get("cost_usd", 0.0))
    cost = getattr(result, "cost_usd", None)
    if cost is None:
        return 0.0
    return float(cost)


__all__ = (
    "BudgetState",
    "DEFAULT_DAILY_CAP_USD",
    "DEFAULT_MONTHLY_CAP_USD",
    "DEFAULT_STATE_PATH",
    "ENV_DAILY_CAP",
    "ENV_MONTHLY_CAP",
    "GenerationBudget",
    "OVERHEAD_FACTOR",
    "PER_SECOND_USD",
)
