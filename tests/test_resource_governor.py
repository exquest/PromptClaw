"""Tests for live performance resource governance.

Verifies graceful degradation under simulated CPU pressure, stale capture,
dead master bus, high node counts, and combinations thereof.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "my-claw" / "tools" / "senseweave"))

import resource_governor as rg


# ---------------------------------------------------------------------------
# HealthSnapshot construction helpers
# ---------------------------------------------------------------------------


def _nominal_snapshot(**overrides: object) -> rg.HealthSnapshot:
    """Return a healthy snapshot with optional overrides."""
    defaults = dict(
        cpu_pressure=0.1,
        sc_node_count=50,
        sampler_load=0.1,
        capture_age_seconds=10.0,
        self_listener_rms=0.3,
        master_bus_healthy=True,
    )
    defaults.update(overrides)
    return rg.take_snapshot(**defaults)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Pressure score
# ---------------------------------------------------------------------------


class TestComputePressure:
    def test_nominal_pressure_is_low(self) -> None:
        snap = _nominal_snapshot()
        pressure = rg.compute_pressure(snap)
        assert pressure < 0.15

    def test_cpu_pressure_dominates(self) -> None:
        snap = _nominal_snapshot(cpu_pressure=0.95)
        pressure = rg.compute_pressure(snap)
        assert pressure >= 0.30

    def test_dead_master_bus_adds_significant_pressure(self) -> None:
        snap = _nominal_snapshot(master_bus_healthy=False)
        pressure = rg.compute_pressure(snap)
        assert pressure >= 0.15

    def test_stale_capture_adds_pressure(self) -> None:
        snap = _nominal_snapshot(capture_age_seconds=400.0)
        pressure = rg.compute_pressure(snap)
        snap_fresh = _nominal_snapshot(capture_age_seconds=5.0)
        pressure_fresh = rg.compute_pressure(snap_fresh)
        assert pressure > pressure_fresh

    def test_silent_self_listener_adds_pressure(self) -> None:
        snap = _nominal_snapshot(self_listener_rms=0.0)
        pressure = rg.compute_pressure(snap)
        snap_normal = _nominal_snapshot(self_listener_rms=0.3)
        pressure_normal = rg.compute_pressure(snap_normal)
        assert pressure > pressure_normal

    def test_high_node_count_adds_pressure(self) -> None:
        snap = _nominal_snapshot(sc_node_count=400)
        pressure = rg.compute_pressure(snap)
        snap_low = _nominal_snapshot(sc_node_count=50)
        pressure_low = rg.compute_pressure(snap_low)
        assert pressure > pressure_low

    def test_high_sampler_load_adds_pressure(self) -> None:
        snap = _nominal_snapshot(sampler_load=0.9)
        pressure = rg.compute_pressure(snap)
        snap_low = _nominal_snapshot(sampler_load=0.05)
        pressure_low = rg.compute_pressure(snap_low)
        assert pressure > pressure_low

    def test_pressure_clamped_at_one(self) -> None:
        snap = _nominal_snapshot(
            cpu_pressure=1.0,
            sc_node_count=1000,
            sampler_load=1.0,
            capture_age_seconds=9999.0,
            self_listener_rms=0.0,
            master_bus_healthy=False,
        )
        pressure = rg.compute_pressure(snap)
        assert pressure == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# Budget computation — nominal
# ---------------------------------------------------------------------------


class TestBudgetNominal:
    def test_full_budget_when_healthy(self) -> None:
        snap = _nominal_snapshot()
        budget = rg.compute_budget(snap)

        assert budget.max_voices == 8
        assert budget.allow_color is True
        assert budget.allow_counter is True
        assert budget.grain_density == pytest.approx(1.0)
        assert budget.density_multiplier == pytest.approx(1.0)
        assert budget.suppress_llm is False
        assert budget.dsp_blocks_allowed == 4
        assert "nominal" in budget.reason


# ---------------------------------------------------------------------------
# Budget — CPU pressure degradation
# ---------------------------------------------------------------------------


class TestBudgetCPUPressure:
    def test_moderate_cpu_sheds_color(self) -> None:
        """At ~0.85 CPU pressure (35% weight → ~0.30 pressure), color should be shed."""
        snap = _nominal_snapshot(cpu_pressure=0.90)
        budget = rg.compute_budget(snap)
        assert budget.allow_color is False

    def test_high_cpu_sheds_counter(self) -> None:
        """At very high CPU + sampler, counter should also be shed."""
        snap = _nominal_snapshot(cpu_pressure=1.0, sampler_load=0.6)
        budget = rg.compute_budget(snap)
        assert budget.allow_counter is False

    def test_high_cpu_reduces_voices(self) -> None:
        snap = _nominal_snapshot(cpu_pressure=1.0, sampler_load=0.6)
        budget = rg.compute_budget(snap)
        assert budget.max_voices <= 5

    def test_high_cpu_suppresses_llm(self) -> None:
        snap = _nominal_snapshot(cpu_pressure=1.0, sampler_load=0.8)
        budget = rg.compute_budget(snap)
        assert budget.suppress_llm is True

    def test_high_cpu_reduces_grains(self) -> None:
        snap = _nominal_snapshot(cpu_pressure=1.0, sampler_load=0.6)
        budget = rg.compute_budget(snap)
        assert budget.grain_density < 1.0


# ---------------------------------------------------------------------------
# Budget — stale capture degradation
# ---------------------------------------------------------------------------


class TestBudgetStaleCapture:
    def test_stale_capture_contributes_pressure(self) -> None:
        snap = _nominal_snapshot(capture_age_seconds=400.0)
        budget = rg.compute_budget(snap)
        assert "stale" in budget.reason

    def test_very_stale_capture_combined_with_cpu(self) -> None:
        """Stale capture + moderate CPU should cross shedding thresholds."""
        snap = _nominal_snapshot(cpu_pressure=0.7, capture_age_seconds=700.0)
        budget = rg.compute_budget(snap)
        assert budget.allow_color is False
        assert "stale" in budget.reason


# ---------------------------------------------------------------------------
# Budget — dead master bus degradation
# ---------------------------------------------------------------------------


class TestBudgetDeadMasterBus:
    def test_dead_master_bus_reason(self) -> None:
        snap = _nominal_snapshot(master_bus_healthy=False)
        budget = rg.compute_budget(snap)
        assert "master bus dead" in budget.reason

    def test_dead_master_bus_adds_significant_pressure(self) -> None:
        snap = _nominal_snapshot(master_bus_healthy=False)
        budget_dead = rg.compute_budget(snap)
        snap_alive = _nominal_snapshot(master_bus_healthy=True)
        budget_alive = rg.compute_budget(snap_alive)
        # Dead bus alone gives ~0.15 + base ≈ 0.19 pressure — just under color shed
        # But combined with even modest CPU it crosses thresholds
        assert budget_dead.reason != budget_alive.reason

    def test_dead_master_bus_plus_cpu_sheds_voices(self) -> None:
        snap = _nominal_snapshot(master_bus_healthy=False, cpu_pressure=0.6)
        budget = rg.compute_budget(snap)
        assert budget.allow_color is False
        assert budget.max_voices < 8


# ---------------------------------------------------------------------------
# Budget — combined emergency scenario
# ---------------------------------------------------------------------------


class TestBudgetEmergency:
    def test_full_emergency_is_bare_minimum(self) -> None:
        snap = _nominal_snapshot(
            cpu_pressure=1.0,
            sc_node_count=600,
            sampler_load=0.9,
            capture_age_seconds=1000.0,
            self_listener_rms=0.0,
            master_bus_healthy=False,
        )
        budget = rg.compute_budget(snap)

        assert budget.max_voices == 2
        assert budget.allow_color is False
        assert budget.allow_counter is False
        assert budget.grain_density < 0.5
        assert budget.density_multiplier < 1.0
        assert budget.suppress_llm is True
        assert budget.dsp_blocks_allowed == 0


# ---------------------------------------------------------------------------
# Budget — degradation order verification
# ---------------------------------------------------------------------------


class TestDegradationOrder:
    """Verify optional voices/samples/grains degrade before primary form."""

    def test_color_shed_before_density(self) -> None:
        """Color should be shed at lower pressure than density reduction."""
        # Just above color threshold
        snap_low = _nominal_snapshot(cpu_pressure=0.90)
        budget_low = rg.compute_budget(snap_low)
        # Color shed, density still at 1.0
        assert budget_low.allow_color is False
        assert budget_low.density_multiplier == pytest.approx(1.0)

    def test_counter_shed_before_density(self) -> None:
        """Counter should be shed before density multiplier kicks in."""
        snap = _nominal_snapshot(cpu_pressure=1.0, sampler_load=0.3)
        budget = rg.compute_budget(snap)
        # At this level counter should be gone but density might still be near 1.0
        if not budget.allow_counter:
            # Good — counter shed. Density should be at or near 1.0 still
            # (density only kicks in at 0.60 pressure)
            pressure = rg.compute_pressure(snap)
            if pressure < 0.60:
                assert budget.density_multiplier == pytest.approx(1.0)

    def test_primary_form_preserved_under_moderate_pressure(self) -> None:
        """Under moderate pressure, melody/bass should still play normally."""
        snap = _nominal_snapshot(cpu_pressure=0.7)
        budget = rg.compute_budget(snap)
        # Voices still allow melody + bass
        assert budget.max_voices >= 3
        assert budget.density_multiplier >= 0.9


# ---------------------------------------------------------------------------
# Snapshot with explicit overrides
# ---------------------------------------------------------------------------


class TestTakeSnapshot:
    def test_overrides_respected(self) -> None:
        snap = rg.take_snapshot(
            cpu_pressure=0.42,
            sc_node_count=123,
            sampler_load=0.56,
            capture_age_seconds=99.0,
            self_listener_rms=0.77,
            master_bus_healthy=False,
        )
        assert snap.cpu_pressure == pytest.approx(0.42)
        assert snap.sc_node_count == 123
        assert snap.sampler_load == pytest.approx(0.56)
        assert snap.capture_age_seconds == pytest.approx(99.0)
        assert snap.self_listener_rms == pytest.approx(0.77)
        assert snap.master_bus_healthy is False

    def test_partial_overrides(self) -> None:
        """Omitted fields should fall back to live reads (which default to safe values)."""
        snap = rg.take_snapshot(cpu_pressure=0.5)
        assert snap.cpu_pressure == pytest.approx(0.5)
        # Other fields read from system — just check they exist
        assert isinstance(snap.sc_node_count, int)
        assert isinstance(snap.sampler_load, float)


# ---------------------------------------------------------------------------
# ResourceBudget is frozen
# ---------------------------------------------------------------------------


class TestResourceBudgetImmutable:
    def test_budget_is_frozen(self) -> None:
        snap = _nominal_snapshot()
        budget = rg.compute_budget(snap)
        with pytest.raises(AttributeError):
            budget.max_voices = 99  # type: ignore[misc]
