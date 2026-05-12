from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools", "senseweave"))

from inner_life.world_model import WorldModel
from senseweave.piece_brief import build_piece_brief
from senseweave.piece_commission import commission_piece


def _make_world(**overrides: object) -> WorldModel:
    defaults = dict(
        observer_description="dim room with one person listening near the window",
        identity_hint="known_guest",
        attention_score=0.66,
        occupancy_state="occupied_quiet",
        current_movement="turning inward",
        cadence_state="occupied_day",
        day_phase="day",
        time_of_day="day",
    )
    defaults.update(overrides)
    return WorldModel(**defaults)  # type: ignore[arg-type]


def _make_commission(**overrides: object) -> object:
    defaults = dict(
        cadence_state="occupied_day",
        day_phase="day",
        weekly_phase="midweek",
        attention_score=0.66,
        song_num=7,
        hour=13,
    )
    defaults.update(overrides)
    return commission_piece(**defaults)  # type: ignore[arg-type]


def test_piece_brief_creates_concrete_narrative_handoff() -> None:
    commission = _make_commission()
    world = _make_world()

    brief = build_piece_brief(
        world=world,
        commission=commission,
        family="ember",
        cadence_state="occupied_day",
        progression_profile="lift",
    )

    assert brief.image_field
    assert any(word in " ".join(brief.image_field).lower() for word in ("room", "window", "listening"))
    assert len(brief.section_beats) >= 4
    assert "room" in brief.dramatic_premise.lower() or "window" in brief.dramatic_premise.lower()
    assert brief.desired_payoff
    assert brief.residue


def test_stable_degradation_without_narrative() -> None:
    """All narrative-derived fields are empty when no narrative state is passed."""
    commission = _make_commission()
    world = _make_world()

    brief = build_piece_brief(
        world=world,
        commission=commission,
        family="ember",
        cadence_state="occupied_day",
        progression_profile="lift",
    )

    # Core fields still populated
    assert brief.dramatic_premise
    assert brief.conflict
    assert brief.desired_payoff
    assert brief.residue
    assert brief.section_beats
    assert brief.hook_pressure > 0
    assert brief.through_composed_pressure > 0

    # Narrative-derived fields are empty
    assert brief.opening_beat == ""
    assert brief.turn_beat == ""
    assert brief.payoff_beat == ""
    assert brief.residue_beat == ""
    assert brief.motif_development == ""
    assert brief.sound_palette == ""


def test_stable_degradation_with_empty_narrative() -> None:
    """Empty or partial narrative mapping degrades the same as None."""
    commission = _make_commission()
    world = _make_world()

    brief_none = build_piece_brief(
        world=world,
        commission=commission,
        family="ember",
        cadence_state="occupied_day",
        progression_profile="lift",
        narrative=None,
    )
    brief_empty = build_piece_brief(
        world=world,
        commission=commission,
        family="ember",
        cadence_state="occupied_day",
        progression_profile="lift",
        narrative={},
    )
    brief_partial = build_piece_brief(
        world=world,
        commission=commission,
        family="ember",
        cadence_state="occupied_day",
        progression_profile="lift",
        narrative={"mood": 0.5},  # arc_phase missing → no derivation
    )

    for brief in (brief_none, brief_empty, brief_partial):
        assert brief.opening_beat == ""
        assert brief.motif_development == ""
        assert brief.sound_palette == ""


def test_narrative_produces_concrete_beats() -> None:
    """When narrative state is present, all beat fields are populated."""
    commission = _make_commission()
    world = _make_world()

    narrative = {
        "arc_phase": "rise",
        "arc_position": 0.35,
        "mood": 0.4,
        "creative_energy": 0.7,
        "curiosity": 0.8,
        "mode": "engaged",
    }

    brief = build_piece_brief(
        world=world,
        commission=commission,
        family="ember",
        cadence_state="occupied_day",
        progression_profile="lift",
        narrative=narrative,
    )

    # All four beat fields filled with lead image
    assert brief.opening_beat
    assert brief.turn_beat
    assert brief.payoff_beat
    assert brief.residue_beat

    # Beats reference the lead image from the world
    lead = brief.image_field[0]
    assert lead in brief.opening_beat
    assert lead in brief.turn_beat

    # Motif development and palette derived from phase
    assert "expansive" in brief.motif_development  # rise phase
    assert "exploratory" in brief.motif_development  # high curiosity
    assert brief.sound_palette  # non-empty


def test_narrative_phase_changes_beats() -> None:
    """Different arc phases produce different beat content."""
    commission = _make_commission()
    world = _make_world()

    briefs = {}
    for phase in ("build", "rise", "climax", "resolve", "rest"):
        briefs[phase] = build_piece_brief(
            world=world,
            commission=commission,
            family="ember",
            cadence_state="occupied_day",
            progression_profile="lift",
            narrative={"arc_phase": phase, "mood": 0.0, "creative_energy": 0.5, "curiosity": 0.5},
        )

    # Each phase should produce distinct opening beats
    opening_beats = {phase: brief.opening_beat for phase, brief in briefs.items()}
    assert len(set(opening_beats.values())) == 5, "each phase must produce a unique opening beat"

    # Motif development differs per phase
    motif_devs = {phase: brief.motif_development for phase, brief in briefs.items()}
    assert "germinal" in motif_devs["build"]
    assert "declarative" in motif_devs["climax"]
    assert "minimal" in motif_devs["rest"]


def test_narrative_adjusts_hook_pressure() -> None:
    """High creative energy nudges hook pressure up; low nudges it down."""
    commission = _make_commission()
    world = _make_world()

    brief_high = build_piece_brief(
        world=world, commission=commission, family="ember",
        cadence_state="occupied_day", progression_profile="lift",
        narrative={"arc_phase": "rise", "creative_energy": 0.9, "curiosity": 0.5},
    )
    brief_low = build_piece_brief(
        world=world, commission=commission, family="ember",
        cadence_state="occupied_day", progression_profile="lift",
        narrative={"arc_phase": "rise", "creative_energy": 0.1, "curiosity": 0.5},
    )
    brief_none = build_piece_brief(
        world=world, commission=commission, family="ember",
        cadence_state="occupied_day", progression_profile="lift",
    )

    assert brief_high.hook_pressure > brief_none.hook_pressure
    assert brief_low.hook_pressure < brief_none.hook_pressure


def test_narrative_curiosity_boosts_through_pressure() -> None:
    """High curiosity increases through-composed pressure."""
    commission = _make_commission()
    world = _make_world()

    brief_curious = build_piece_brief(
        world=world, commission=commission, family="ember",
        cadence_state="occupied_day", progression_profile="lift",
        narrative={"arc_phase": "rise", "curiosity": 0.9, "creative_energy": 0.5},
    )
    brief_baseline = build_piece_brief(
        world=world, commission=commission, family="ember",
        cadence_state="occupied_day", progression_profile="lift",
    )

    assert brief_curious.through_composed_pressure > brief_baseline.through_composed_pressure


def test_mood_affects_sound_palette() -> None:
    """Mood extremes add tonal modifiers to the sound palette."""
    commission = _make_commission()
    world = _make_world()

    brief_bright = build_piece_brief(
        world=world, commission=commission, family="ember",
        cadence_state="occupied_day", progression_profile="lift",
        narrative={"arc_phase": "climax", "mood": 0.6, "creative_energy": 0.8, "curiosity": 0.5},
    )
    brief_dark = build_piece_brief(
        world=world, commission=commission, family="ember",
        cadence_state="occupied_day", progression_profile="lift",
        narrative={"arc_phase": "climax", "mood": -0.6, "creative_energy": 0.2, "curiosity": 0.5},
    )

    assert "bright" in brief_bright.sound_palette
    assert "dark" in brief_dark.sound_palette

