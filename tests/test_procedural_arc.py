"""Tests for the EMSD procedural arc layer."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools", "senseweave"))

from senseweave.procedural_arc import ARC_PHASES, directive_for_elapsed, phase_for_elapsed


def test_arc_phase_boundaries_follow_the_five_stage_cycle() -> None:
    assert phase_for_elapsed(0.1).name == "Divination"
    assert phase_for_elapsed(6.0).name == "Emergence"
    assert phase_for_elapsed(13.0).name == "Conversation"
    assert phase_for_elapsed(22.0).name == "Convergence"
    assert phase_for_elapsed(28.0).name == "Crystallization"


def test_cpu_pressure_thins_the_arc_directive() -> None:
    normal = directive_for_elapsed(13.0, cadence_state="occupied_day", cpu_pressure=0.0)
    stressed = directive_for_elapsed(13.0, cadence_state="occupied_day", cpu_pressure=0.9)

    assert stressed.density_target < normal.density_target
    assert stressed.max_active_roles <= normal.max_active_roles


def test_arc_exposes_phase_specific_production_metadata() -> None:
    divination = directive_for_elapsed(2.0, cadence_state="occupied_day")
    assert divination.dynamic_target == "p"
    assert divination.harmonic_target == "open"
    assert divination.rhythm_target == "free"
    assert divination.timbre_target == "sparse"
    assert divination.spatial_target == "wide"
    assert divination.compression_target == 0.1
    assert divination.senseweave_target == 0.8
    assert divination.synthesis_target == "spectral"

    emergence = directive_for_elapsed(8.0, cadence_state="occupied_day")
    assert emergence.dynamic_target == "mp"
    assert emergence.harmonic_target == "modal"
    assert emergence.rhythm_target == "pulse"
    assert emergence.timbre_target == "warm"
    assert emergence.spatial_target == "clear"
    assert emergence.compression_target == 0.3
    assert emergence.senseweave_target == 0.6
    assert emergence.synthesis_target == "fm"

    conversation = directive_for_elapsed(15.0, cadence_state="occupied_day")
    assert conversation.dynamic_target == "mf"
    assert conversation.harmonic_target == "functional"
    assert conversation.rhythm_target == "groove"
    assert conversation.timbre_target == "complex"
    assert conversation.spatial_target == "focused"
    assert conversation.compression_target == 0.5
    assert conversation.senseweave_target == 0.4
    assert conversation.synthesis_target == "subtractive"

    convergence = directive_for_elapsed(23.0, cadence_state="occupied_day")
    assert convergence.dynamic_target == "f"
    assert convergence.harmonic_target == "chromatic"
    assert convergence.rhythm_target == "polyrhythm"
    assert convergence.timbre_target == "bright"
    assert convergence.spatial_target == "intimate"
    assert convergence.compression_target == 0.6
    assert convergence.senseweave_target == 0.2
    assert convergence.synthesis_target == "additive"

    crystallization = directive_for_elapsed(28.0, cadence_state="occupied_day")
    assert crystallization.dynamic_target == "pp"
    assert crystallization.harmonic_target == "static"
    assert crystallization.rhythm_target == "drone"
    assert crystallization.timbre_target == "pure"
    assert crystallization.spatial_target == "expansive"
    assert crystallization.compression_target == 0.2
    assert crystallization.senseweave_target == 0.9
    assert crystallization.synthesis_target == "granular"


def test_arc_phases_expose_production_target_payloads() -> None:
    targets = [phase.production_targets() for phase in ARC_PHASES]

    assert [target["phase"] for target in targets] == [
        "Divination",
        "Emergence",
        "Conversation",
        "Convergence",
        "Crystallization",
    ]
    assert targets[0] == {
        "phase": "Divination",
        "density": 0.24,
        "dynamic": "p",
        "harmonic": "open",
        "rhythm": "free",
        "timbre": "sparse",
        "spatial": "wide",
        "compression": 0.1,
        "senseweave": 0.8,
        "synthesis": "spectral",
    }


def test_five_minute_proxy_cycle_maps_all_phases() -> None:
    phase_names = [
        phase_for_elapsed(m, cycle_minutes=5.0).name
        for m in (0.5, 1.2, 2.5, 3.8, 4.5)
    ]
    assert phase_names == [
        "Divination", "Emergence", "Conversation", "Convergence", "Crystallization",
    ]
    d = directive_for_elapsed(0.5, cadence_state="occupied_day", cycle_minutes=5.0)
    assert d.phase.name == "Divination"
    assert d.dynamic_target == "p"
