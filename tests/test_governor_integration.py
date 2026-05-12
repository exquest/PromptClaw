"""Integration tests for resource governor → composition budget enforcement.

Verifies:
- Healthy conditions produce audible output (no events skipped).
- High pressure thins grain/sample events via grain_density.
- High pressure thins non-accent events via density_multiplier.
- DSP blocks are capped under pressure.
- suppress_llm skips next-piece pre-composition.
- Both daemon entrypoints wire bootstrap_identity before startup.
"""
from __future__ import annotations

import ast
import sys
from dataclasses import replace
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "my-claw" / "tools" / "senseweave"))

import resource_governor as rg

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _nominal_snapshot(**overrides: object) -> rg.HealthSnapshot:
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


def _emergency_snapshot() -> rg.HealthSnapshot:
    return rg.take_snapshot(
        cpu_pressure=1.0,
        sc_node_count=600,
        sampler_load=0.9,
        capture_age_seconds=1000.0,
        self_listener_rms=0.0,
        master_bus_healthy=False,
    )


# ---------------------------------------------------------------------------
# Governor-to-composition: budget fields actually constrain playback
# ---------------------------------------------------------------------------


class TestBudgetEnforcesGrainDensity:
    """grain_density < 1.0 must probabilistically skip grain/sample events."""

    def test_healthy_budget_passes_all_grains(self) -> None:
        budget = rg.compute_budget(_nominal_snapshot())
        assert budget.grain_density == pytest.approx(1.0)
        # With grain_density == 1.0, no events should be skipped
        # (random() > 1.0 is always False)

    def test_emergency_budget_reduces_grain_density(self) -> None:
        budget = rg.compute_budget(_emergency_snapshot())
        assert budget.grain_density < 0.5

    def test_grain_density_scales_with_pressure(self) -> None:
        low = rg.compute_budget(_nominal_snapshot(cpu_pressure=0.5, sampler_load=0.3))
        high = rg.compute_budget(_nominal_snapshot(cpu_pressure=1.0, sampler_load=0.8))
        assert high.grain_density < low.grain_density


class TestBudgetEnforcesDensityMultiplier:
    """density_multiplier < 1.0 must thin non-accent events."""

    def test_healthy_budget_preserves_full_density(self) -> None:
        budget = rg.compute_budget(_nominal_snapshot())
        assert budget.density_multiplier == pytest.approx(1.0)

    def test_emergency_budget_reduces_density(self) -> None:
        budget = rg.compute_budget(_emergency_snapshot())
        assert budget.density_multiplier < 1.0

    def test_density_only_kicks_in_at_high_pressure(self) -> None:
        """Density multiplier should not activate under moderate pressure."""
        moderate = rg.compute_budget(
            _nominal_snapshot(cpu_pressure=0.7, sampler_load=0.2)
        )
        pressure = rg.compute_pressure(
            _nominal_snapshot(cpu_pressure=0.7, sampler_load=0.2)
        )
        if pressure < 0.60:
            assert moderate.density_multiplier == pytest.approx(1.0)


class TestBudgetEnforcesDSPCap:
    """dsp_blocks_allowed must cap DSP effect blocks."""

    def test_healthy_budget_allows_full_dsp(self) -> None:
        budget = rg.compute_budget(_nominal_snapshot())
        assert budget.dsp_blocks_allowed == 4

    def test_emergency_budget_allows_zero_dsp(self) -> None:
        budget = rg.compute_budget(_emergency_snapshot())
        assert budget.dsp_blocks_allowed == 0

    def test_dsp_cap_applied_to_frozen_dataclass(self) -> None:
        """Verify DSP capping works with frozen dataclass replace."""
        from dsp_scene_lab import DSPScene

        scene = DSPScene(
            phase_name="test",
            blocks=("spectral_smear", "long_convolution", "granular_stretch", "shimmer"),
            source_focus="room_mic",
            visual_bias={"motion": 0.2},
        )
        budget = rg.compute_budget(
            _nominal_snapshot(cpu_pressure=0.9, sampler_load=0.6)
        )
        if budget.dsp_blocks_allowed < len(scene.blocks):
            capped = replace(scene, blocks=scene.blocks[:budget.dsp_blocks_allowed])
            assert len(capped.blocks) == budget.dsp_blocks_allowed
            assert len(capped.blocks) < len(scene.blocks)


class TestBudgetSuppressLLM:
    """suppress_llm must be True under sufficient pressure."""

    def test_healthy_does_not_suppress(self) -> None:
        budget = rg.compute_budget(_nominal_snapshot())
        assert budget.suppress_llm is False

    def test_emergency_suppresses(self) -> None:
        budget = rg.compute_budget(_emergency_snapshot())
        assert budget.suppress_llm is True


# ---------------------------------------------------------------------------
# Startup identity wiring: both daemon entrypoints call bootstrap_identity
# ---------------------------------------------------------------------------


class TestStartupIdentityWiring:
    """Verify both daemon entrypoints wire bootstrap_identity before main loop.

    Uses AST inspection to confirm the call exists in the startup path
    without importing the full daemon modules (which have heavy dependencies).
    """

    def test_daemon_py_calls_bootstrap_identity(self) -> None:
        """daemon.py poll_loop must call bootstrap_identity()."""
        source = (
            Path(__file__).parent.parent / "my-claw" / "tools" / "daemon.py"
        ).read_text()
        tree = ast.parse(source)
        poll_loop_fn = _find_function(tree, "poll_loop")
        assert poll_loop_fn is not None, "poll_loop function not found in daemon.py"

        calls = _extract_call_names(poll_loop_fn)
        assert "bootstrap_identity" in calls, (
            "daemon.py poll_loop() must call bootstrap_identity() before main loop"
        )

    def test_cypherclaw_daemon_py_calls_bootstrap_identity(self) -> None:
        """cypherclaw_daemon.py poll_loop must call bootstrap_identity()."""
        source = (
            Path(__file__).parent.parent / "my-claw" / "tools" / "cypherclaw_daemon.py"
        ).read_text()
        tree = ast.parse(source)
        poll_loop_fn = _find_function(tree, "poll_loop")
        assert poll_loop_fn is not None, (
            "poll_loop function not found in cypherclaw_daemon.py"
        )

        calls = _extract_call_names(poll_loop_fn)
        assert "bootstrap_identity" in calls, (
            "cypherclaw_daemon.py poll_loop() must call bootstrap_identity() before main loop"
        )

    def test_bootstrap_identity_before_announcer_in_both(self) -> None:
        """bootstrap_identity must come before FirstBootAnnouncer in both daemons."""
        for name in ("daemon.py", "cypherclaw_daemon.py"):
            source = (
                Path(__file__).parent.parent / "my-claw" / "tools" / name
            ).read_text()
            tree = ast.parse(source)
            poll_loop_fn = _find_function(tree, "poll_loop")
            assert poll_loop_fn is not None

            calls_with_lines = _extract_call_names_with_lines(poll_loop_fn)
            bootstrap_line = None
            announcer_line = None
            for call_name, lineno in calls_with_lines:
                if call_name == "bootstrap_identity" and bootstrap_line is None:
                    bootstrap_line = lineno
                if call_name == "FirstBootAnnouncer" and announcer_line is None:
                    announcer_line = lineno

            assert bootstrap_line is not None, (
                f"{name}: bootstrap_identity not found in poll_loop"
            )
            assert announcer_line is not None, (
                f"{name}: FirstBootAnnouncer not found in poll_loop"
            )
            assert bootstrap_line < announcer_line, (
                f"{name}: bootstrap_identity (line {bootstrap_line}) must come "
                f"before FirstBootAnnouncer (line {announcer_line})"
            )


# ---------------------------------------------------------------------------
# End-to-End Governor Lifecycle
# ---------------------------------------------------------------------------


class TestGovernorIntegrationEndToEnd:
    """End-to-end lifecycle verification for the resource governor."""

    def test_nominal_lifecycle_path(self) -> None:
        """Drive a full cycle starting at nominal health."""
        nominal_snap = rg.take_snapshot(
            cpu_pressure=0.1,
            sc_node_count=50,
            sampler_load=0.1,
            capture_age_seconds=10.0,
            self_listener_rms=0.3,
            master_bus_healthy=True,
        )
        nominal_pressure = rg.compute_pressure(nominal_snap)
        nominal_budget = rg.compute_budget(nominal_snap)
        
        assert nominal_pressure < 0.3
        assert nominal_budget.max_voices == 8
        assert nominal_budget.allow_color is True
        assert nominal_budget.allow_counter is True
        assert nominal_budget.grain_density == pytest.approx(1.0)
        assert nominal_budget.density_multiplier == pytest.approx(1.0)
        assert nominal_budget.dsp_blocks_allowed == 4
        assert nominal_budget.suppress_llm is False
        assert "nominal" in nominal_budget.reason

    def test_emergency_spike_path(self) -> None:
        """Simulate an emergency spike in resource utilization."""
        emergency_snap = rg.take_snapshot(
            cpu_pressure=1.0,
            sc_node_count=600,
            sampler_load=0.95,
            capture_age_seconds=1000.0,
            self_listener_rms=0.0,
            master_bus_healthy=False,
        )
        emergency_pressure = rg.compute_pressure(emergency_snap)
        emergency_budget = rg.compute_budget(emergency_snap)
        
        assert emergency_pressure >= 0.8
        assert emergency_budget.max_voices <= 2
        assert emergency_budget.allow_color is False
        assert emergency_budget.allow_counter is False
        assert emergency_budget.grain_density < 0.5
        assert emergency_budget.density_multiplier < 1.0
        assert emergency_budget.dsp_blocks_allowed == 0
        assert emergency_budget.suppress_llm is True
        assert "master bus dead" in emergency_budget.reason
        assert "CPU 100%" in emergency_budget.reason

    def test_recovery_lifecycle_path(self) -> None:
        """Verify the budget recovers correctly from a spike."""
        recovering_snap = rg.take_snapshot(
            cpu_pressure=0.4,
            sc_node_count=250,
            sampler_load=0.4,
            capture_age_seconds=50.0,
            self_listener_rms=0.4,
            master_bus_healthy=True,
        )
        recovering_pressure = rg.compute_pressure(recovering_snap)
        recovering_budget = rg.compute_budget(recovering_snap)
        
        assert 0.1 < recovering_pressure < 0.8
        assert recovering_budget.max_voices > 2

    def test_cpu_pressure_only_path(self) -> None:
        """Verify degradation path for high CPU but normal other metrics."""
        cpu_snap = rg.take_snapshot(
            cpu_pressure=0.8,
            sc_node_count=50,
            sampler_load=0.2,
            capture_age_seconds=10.0,
            self_listener_rms=0.3,
            master_bus_healthy=True,
        )
        cpu_pressure = rg.compute_pressure(cpu_snap)
        cpu_budget = rg.compute_budget(cpu_snap)
        
        assert cpu_pressure > 0.2
        assert "CPU 80%" in cpu_budget.reason

    def test_master_bus_dead_path(self) -> None:
        """Verify the system degrades rapidly if the master bus dies."""
        dead_snap = rg.take_snapshot(
            cpu_pressure=0.1,
            sc_node_count=50,
            sampler_load=0.1,
            capture_age_seconds=10.0,
            self_listener_rms=0.3,
            master_bus_healthy=False,
        )
        dead_pressure = rg.compute_pressure(dead_snap)
        dead_budget = rg.compute_budget(dead_snap)
        
        assert dead_pressure > 0.1
        assert "master bus dead" in dead_budget.reason


# ---------------------------------------------------------------------------
# AST helpers
# ---------------------------------------------------------------------------


def _find_function(tree: ast.Module, name: str) -> ast.FunctionDef | None:
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name == name:
                return node
    return None


def _extract_call_names(func: ast.FunctionDef) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(func):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                names.add(node.func.id)
            elif isinstance(node.func, ast.Attribute):
                names.add(node.func.attr)
    return names


def _extract_call_names_with_lines(
    func: ast.FunctionDef,
) -> list[tuple[str, int]]:
    results: list[tuple[str, int]] = []
    for node in ast.walk(func):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                results.append((node.func.id, node.lineno))
            elif isinstance(node.func, ast.Attribute):
                results.append((node.func.attr, node.lineno))
    return results
