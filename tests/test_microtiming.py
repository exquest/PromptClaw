import statistics

import pytest

from cypherclaw.render.events import Event
from cypherclaw.render.role_gate import GRID_LOCKED_ROLES
from cypherclaw.render.rules.microtiming import (
    LISTENER_JND_MS,
    MicrotimingRule,
    _gaussian_jitter,
)


class TestGaussianJitter:
    def test_zero_sigma_returns_zero(self) -> None:
        assert _gaussian_jitter(0, 42, 0.0) == 0.0

    def test_deterministic(self) -> None:
        a = _gaussian_jitter(7, 99, 3.0)
        b = _gaussian_jitter(7, 99, 3.0)
        assert a == b

    def test_different_steps_differ(self) -> None:
        a = _gaussian_jitter(0, 42, 3.0)
        b = _gaussian_jitter(1, 42, 3.0)
        assert a != b

    def test_distribution_matches_sigma(self) -> None:
        sigma = 3.0
        samples = [_gaussian_jitter(i, 0, sigma) for i in range(5000)]
        observed_std = statistics.stdev(samples)
        assert abs(observed_std - sigma) < 0.3


class TestMicrotimingRule:
    def _make_event(self, role: str, step_index: int = 0) -> Event:
        event = Event(role=role)
        event.step_index = step_index  # type: ignore[attr-defined]
        return event

    @pytest.mark.parametrize("role", sorted(GRID_LOCKED_ROLES))
    def test_grid_locked_zero_deviation(self, role: str) -> None:
        rule = MicrotimingRule(seed=42)
        event = self._make_event(role, step_index=7)
        rule.apply(event)
        assert event.timing_deviation_ms == 0.0  # type: ignore[attr-defined]

    def test_melodic_nonzero_deviation(self) -> None:
        rule = MicrotimingRule(seed=1)
        deviations = []
        for i in range(100):
            event = self._make_event("melody", step_index=i)
            rule.apply(event)
            deviations.append(event.timing_deviation_ms)  # type: ignore[attr-defined]
        assert any(d != 0.0 for d in deviations)

    def test_melodic_sigma(self) -> None:
        rule = MicrotimingRule(seed=0)
        deviations = [
            (rule.apply(e := self._make_event("melody", i)), e.timing_deviation_ms)[1]  # type: ignore[attr-defined]
            for i in range(5000)
        ]
        observed_std = statistics.stdev(deviations)
        assert abs(observed_std - 3.0) < 0.3

    def test_ostinato_zero_deviation(self) -> None:
        rule = MicrotimingRule(seed=0)
        for i in range(100):
            event = self._make_event("ostinato", step_index=i)
            rule.apply(event)
            assert event.timing_deviation_ms == 0.0  # type: ignore[attr-defined]

    def test_sigma_below_jnd(self) -> None:
        rule = MicrotimingRule()
        assert rule.sigma_melodic_ms < LISTENER_JND_MS

    def test_sigma_exceeding_jnd_raises(self) -> None:
        with pytest.raises(ValueError, match="exceeds JND"):
            MicrotimingRule(sigma_melodic_ms=15.0)

    def test_deterministic_across_applies(self) -> None:
        rule = MicrotimingRule(seed=77)
        e1 = self._make_event("melody", step_index=5)
        e2 = self._make_event("melody", step_index=5)
        rule.apply(e1)
        rule.apply(e2)
        assert e1.timing_deviation_ms == e2.timing_deviation_ms  # type: ignore[attr-defined]

    def test_missing_role_filtered_out(self) -> None:
        rule = MicrotimingRule(seed=0)
        event = Event()
        event.step_index = 3  # type: ignore[attr-defined]
        rule.apply(event)
        assert event.timing_deviation_ms == 0.0  # type: ignore[attr-defined]

    def test_counter_melody_is_melodic(self) -> None:
        rule = MicrotimingRule(seed=0)
        deviations = [
            (rule.apply(e := self._make_event("counter", i)), e.timing_deviation_ms)[1]  # type: ignore[attr-defined]
            for i in range(2000)
        ]
        observed_std = statistics.stdev(deviations)
        assert abs(observed_std - 3.0) < 0.5
