from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterator

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools"))

from senseweave.generation.budget import (  # noqa: E402
    DEFAULT_DAILY_CAP_USD,
    DEFAULT_MONTHLY_CAP_USD,
    ENV_DAILY_CAP,
    ENV_MONTHLY_CAP,
    OVERHEAD_FACTOR,
    PER_SECOND_USD,
    BudgetState,
    GenerationBudget,
)


@dataclass(frozen=True)
class _Req:
    model: str = "musicgen-medium"
    duration_sec: float = 30.0


@dataclass(frozen=True)
class _Result:
    cost_usd: float


class _MockClock:
    def __init__(self, start: datetime) -> None:
        self.now = start

    def __call__(self) -> datetime:
        return self.now

    def advance(self, **kwargs: float) -> None:
        self.now = self.now + timedelta(**kwargs)


@pytest.fixture
def clean_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.delenv(ENV_DAILY_CAP, raising=False)
    monkeypatch.delenv(ENV_MONTHLY_CAP, raising=False)
    yield


def _path(tmp_path: Path) -> Path:
    return tmp_path / "generation_budget.json"


def test_defaults_when_no_env_or_args(tmp_path: Path, clean_env: None) -> None:
    budget = GenerationBudget(_path(tmp_path))
    assert budget.daily_cap_usd == DEFAULT_DAILY_CAP_USD
    assert budget.monthly_cap_usd == DEFAULT_MONTHLY_CAP_USD


def test_constructor_args_override_defaults(tmp_path: Path, clean_env: None) -> None:
    budget = GenerationBudget(_path(tmp_path), daily_cap_usd=2.0, monthly_cap_usd=20.0)
    assert budget.daily_cap_usd == 2.0
    assert budget.monthly_cap_usd == 20.0


def test_env_vars_override_defaults_and_args(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(ENV_DAILY_CAP, "1.25")
    monkeypatch.setenv(ENV_MONTHLY_CAP, "42.5")
    budget = GenerationBudget(
        _path(tmp_path), daily_cap_usd=99.0, monthly_cap_usd=999.0
    )
    assert budget.daily_cap_usd == 1.25
    assert budget.monthly_cap_usd == 42.5


def test_estimate_cost_uses_per_model_rate_and_overhead(
    tmp_path: Path, clean_env: None
) -> None:
    budget = GenerationBudget(_path(tmp_path))
    estimate = budget.estimate_cost_usd(_Req(model="musicgen-medium", duration_sec=30.0))
    expected = PER_SECOND_USD["musicgen-medium"] * 30.0 * OVERHEAD_FACTOR
    assert estimate == pytest.approx(expected)

    estimate2 = budget.estimate_cost_usd(
        _Req(model="stable-audio-open", duration_sec=10.0)
    )
    expected2 = PER_SECOND_USD["stable-audio-open"] * 10.0 * OVERHEAD_FACTOR
    assert estimate2 == pytest.approx(expected2)


def test_allow_returns_true_under_caps(tmp_path: Path, clean_env: None) -> None:
    budget = GenerationBudget(_path(tmp_path))
    allowed, reason = budget.allow(_Req())
    assert allowed is True
    assert reason == "ok"


def test_allow_blocks_when_daily_cap_exceeded(tmp_path: Path, clean_env: None) -> None:
    clock = _MockClock(datetime(2026, 4, 26, 12, 0, tzinfo=timezone.utc))
    budget = GenerationBudget(
        _path(tmp_path), daily_cap_usd=0.10, monthly_cap_usd=100.0, clock=clock
    )
    budget.record(_Result(cost_usd=0.09))
    allowed, reason = budget.allow(_Req(duration_sec=30.0))
    assert allowed is False
    assert "daily cap" in reason


def test_allow_blocks_when_monthly_cap_exceeded(
    tmp_path: Path, clean_env: None
) -> None:
    clock = _MockClock(datetime(2026, 4, 26, 12, 0, tzinfo=timezone.utc))
    budget = GenerationBudget(
        _path(tmp_path), daily_cap_usd=1000.0, monthly_cap_usd=0.10, clock=clock
    )
    budget.record(_Result(cost_usd=0.09))
    allowed, reason = budget.allow(_Req(duration_sec=30.0))
    assert allowed is False
    assert "monthly cap" in reason


def test_record_increments_today_and_month(tmp_path: Path, clean_env: None) -> None:
    clock = _MockClock(datetime(2026, 4, 26, 12, 0, tzinfo=timezone.utc))
    budget = GenerationBudget(_path(tmp_path), clock=clock)
    budget.record(_Result(cost_usd=0.42))
    budget.record(_Result(cost_usd=0.08))
    state = budget.state
    assert state.today_spent_usd == pytest.approx(0.50)
    assert state.month_spent_usd == pytest.approx(0.50)


def test_record_ignores_zero_or_missing_cost(tmp_path: Path, clean_env: None) -> None:
    budget = GenerationBudget(_path(tmp_path))
    budget.record(None)
    budget.record({"audio_path": "/tmp/x.wav"})
    budget.record(_Result(cost_usd=0.0))
    state = budget.state
    assert state.today_spent_usd == 0.0
    assert state.month_spent_usd == 0.0


def test_state_persists_across_instances(tmp_path: Path, clean_env: None) -> None:
    clock = _MockClock(datetime(2026, 4, 26, 12, 0, tzinfo=timezone.utc))
    path = _path(tmp_path)
    first = GenerationBudget(path, clock=clock)
    first.record(_Result(cost_usd=1.23))

    second = GenerationBudget(path, clock=clock)
    state = second.state
    assert state.today_spent_usd == pytest.approx(1.23)
    assert state.month_spent_usd == pytest.approx(1.23)
    assert state.today_date == "2026-04-26"
    assert state.month_key == "2026-04"


def test_persistence_file_is_json_and_atomic_write_temp_cleaned(
    tmp_path: Path, clean_env: None
) -> None:
    path = _path(tmp_path)
    budget = GenerationBudget(path)
    budget.record(_Result(cost_usd=0.50))

    assert path.exists()
    payload = json.loads(path.read_text())
    assert "today_spent_usd" in payload
    assert "month_spent_usd" in payload
    assert "today_date" in payload
    assert "month_key" in payload
    # The temp sidecar created during atomic write must not linger.
    assert not path.with_name(f"{path.name}.tmp").exists()


def test_daily_rollover_resets_today_spent_only(
    tmp_path: Path, clean_env: None
) -> None:
    clock = _MockClock(datetime(2026, 4, 26, 23, 0, tzinfo=timezone.utc))
    budget = GenerationBudget(_path(tmp_path), clock=clock)
    budget.record(_Result(cost_usd=2.0))
    assert budget.state.today_spent_usd == pytest.approx(2.0)
    assert budget.state.month_spent_usd == pytest.approx(2.0)

    clock.advance(days=1)  # now 2026-04-27, same month
    state = budget.state
    assert state.today_date == "2026-04-27"
    assert state.month_key == "2026-04"
    assert state.today_spent_usd == 0.0
    assert state.month_spent_usd == pytest.approx(2.0)


def test_monthly_rollover_resets_both_counters(
    tmp_path: Path, clean_env: None
) -> None:
    clock = _MockClock(datetime(2026, 4, 30, 23, 0, tzinfo=timezone.utc))
    budget = GenerationBudget(_path(tmp_path), clock=clock)
    budget.record(_Result(cost_usd=10.0))
    assert budget.state.month_spent_usd == pytest.approx(10.0)

    clock.advance(days=2)  # crosses into 2026-05
    state = budget.state
    assert state.today_date == "2026-05-02"
    assert state.month_key == "2026-05"
    assert state.today_spent_usd == 0.0
    assert state.month_spent_usd == 0.0


def test_rollover_applies_when_loaded_from_disk(
    tmp_path: Path, clean_env: None
) -> None:
    path = _path(tmp_path)
    clock = _MockClock(datetime(2026, 4, 26, 12, 0, tzinfo=timezone.utc))
    first = GenerationBudget(path, clock=clock)
    first.record(_Result(cost_usd=1.0))

    later = _MockClock(datetime(2026, 4, 28, 9, 0, tzinfo=timezone.utc))
    second = GenerationBudget(path, clock=later)
    state = second.state
    assert state.today_date == "2026-04-28"
    assert state.today_spent_usd == 0.0
    # Same month: month_spent_usd carries over.
    assert state.month_spent_usd == pytest.approx(1.0)


def test_allow_after_rollover_recovers(tmp_path: Path, clean_env: None) -> None:
    clock = _MockClock(datetime(2026, 4, 26, 12, 0, tzinfo=timezone.utc))
    budget = GenerationBudget(
        _path(tmp_path), daily_cap_usd=0.10, monthly_cap_usd=100.0, clock=clock
    )
    budget.record(_Result(cost_usd=0.09))
    blocked, _ = budget.allow(_Req(duration_sec=10.0))
    assert blocked is False

    clock.advance(days=1)
    allowed, reason = budget.allow(_Req(duration_sec=10.0))
    assert allowed is True
    assert reason == "ok"


def test_state_snapshot_does_not_alias_internal(
    tmp_path: Path, clean_env: None
) -> None:
    budget = GenerationBudget(_path(tmp_path))
    budget.record(_Result(cost_usd=1.0))
    snapshot = budget.state
    snapshot.today_spent_usd = 9999.0
    assert budget.state.today_spent_usd == pytest.approx(1.0)


def test_unknown_model_falls_back_to_max_rate(
    tmp_path: Path, clean_env: None
) -> None:
    budget = GenerationBudget(_path(tmp_path))
    estimate = budget.estimate_cost_usd(_Req(model="unknown-model", duration_sec=30.0))
    expected = max(PER_SECOND_USD.values()) * 30.0 * OVERHEAD_FACTOR
    assert estimate == pytest.approx(expected)


def test_budget_state_round_trip() -> None:
    state = BudgetState(
        today_date="2026-04-26",
        today_spent_usd=1.5,
        month_key="2026-04",
        month_spent_usd=12.5,
    )
    assert BudgetState.from_dict(state.to_dict()) == state
