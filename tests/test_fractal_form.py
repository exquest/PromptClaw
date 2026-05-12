"""Tests for fractal form expansion: phrase families, seed derivation, anti-looping."""
from __future__ import annotations

from dataclasses import replace
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools", "senseweave"))

from inner_life.world_model import WorldModel
from senseweave.form_grammar import minimum_function_count, phrase_family_slots, plan_form
from senseweave.piece_brief import build_piece_brief
from senseweave.piece_commission import commission_piece
from senseweave.recursive_composer import compose_score_tree


def _build_tree(*, form_class: str):
    """Build a score tree for a given form class."""
    # Pick parameters that reliably produce the target form class.
    params = {
        "song": dict(cadence_state="occupied_day", hour=14, narrative_pressure=0.35),
        "extended": dict(cadence_state="wind_down", hour=23, narrative_pressure=0.85),
        "suite": dict(cadence_state="wind_down", hour=23, narrative_pressure=0.95),
    }
    cfg = params[form_class]
    commission = commission_piece(
        cadence_state=cfg["cadence_state"],
        day_phase="day" if cfg["hour"] < 18 else "late_evening",
        weekly_phase="weekend" if form_class == "suite" else "midweek",
        attention_score=0.15 if form_class == "suite" else 0.48,
        narrative_pressure=cfg["narrative_pressure"],
        song_num=5,
        hour=cfg["hour"],
    )
    world = WorldModel(
        observer_description="quiet room, lamp, long hallway",
        cadence_state=cfg["cadence_state"],
        day_phase="day" if cfg["hour"] < 18 else "late_evening",
        time_of_day="day" if cfg["hour"] < 18 else "night",
        occupancy_state="occupied_quiet",
    )
    brief = build_piece_brief(
        world=world,
        commission=commission,
        family="drift",
        cadence_state=cfg["cadence_state"],
        progression_profile="settling",
    )
    form = plan_form(commission=commission, brief=brief, family="drift")
    tree = compose_score_tree(
        commission=commission,
        brief=brief,
        form=form,
        family="drift",
        cadence_state=cfg["cadence_state"],
        progression_profile="settling",
        song_num=5,
        mood={"energy": 0.3, "valence": 0.4, "arousal": 0.25},
    )
    return tree


def _commission_and_brief_for_forms():
    commission = commission_piece(
        cadence_state="occupied_day",
        day_phase="day",
        weekly_phase="midweek",
        attention_score=0.48,
        narrative_pressure=0.35,
        song_num=5,
        hour=14,
    )
    world = WorldModel(
        observer_description="quiet room, lamp, long hallway",
        cadence_state="occupied_day",
        day_phase="day",
        time_of_day="day",
        occupancy_state="occupied_quiet",
    )
    brief = build_piece_brief(
        world=world,
        commission=commission,
        family="drift",
        cadence_state="occupied_day",
        progression_profile="settling",
    )
    return commission, brief


# --- phrase_family_slots grammar tests ---


def test_phrase_family_slots_returns_exact_count() -> None:
    for count in (1, 2, 3, 4):
        slots = phrase_family_slots("development", count)
        assert len(slots) == count


def test_phrase_family_slots_first_is_seed() -> None:
    for function in ("statement", "development", "turn", "arrival", "coda"):
        slots = phrase_family_slots(function, 2)
        assert slots[0].is_seed is True
        assert slots[0].family == "seed"


def test_phrase_family_slots_non_seed_differ_from_seed() -> None:
    """Non-seed slots must have different transform_ops or family than the seed."""
    for function in ("development", "turn", "arrival"):
        slots = phrase_family_slots(function, 3)
        seed = slots[0]
        for slot in slots[1:]:
            differs = (
                slot.family != seed.family
                or slot.transform_ops != seed.transform_ops
            )
            assert differs, f"{function}: non-seed slot is identical to seed"


def test_phrase_family_slots_padded_beyond_template() -> None:
    slots = phrase_family_slots("statement", 5)
    assert len(slots) == 5
    assert slots[0].is_seed is True
    # Padded slots should not all be identical.
    padded_families = {s.family for s in slots[2:]}
    assert len(padded_families) >= 1


def test_form_library_exposes_recognizable_section_families() -> None:
    commission, brief = _commission_and_brief_for_forms()
    expected_functions = {
        "verse",
        "chorus",
        "bridge",
        "afterglow",
        "build",
        "drop",
        "ambient",
        "return",
        "through_line",
    }
    seen_functions: set[str] = set()

    for form_family in (
        "verse_chorus",
        "aaba",
        "build_drop",
        "ambient_arc",
        "rondo_return",
        "bridge",
        "afterglow",
        "through_composed",
    ):
        plan = plan_form(commission=commission, brief=brief, family="bloom", form_family_hint=form_family)
        seen_functions.update(plan.section_functions)

    assert expected_functions <= seen_functions


def test_form_selection_avoids_recent_repertoire_fatigue() -> None:
    commission, brief = _commission_and_brief_for_forms()
    first_plan = plan_form(commission=commission, brief=brief, family="bloom")
    recent_repertoire = [
        {
            "form_family": first_plan.form_family,
            "score_tree_summary": {
                "section_functions": list(first_plan.section_functions),
            },
        }
        for _ in range(4)
    ]

    next_plan = plan_form(
        commission=commission,
        brief=brief,
        family="bloom",
        repertoire_entries=recent_repertoire,
    )

    assert next_plan.section_functions != first_plan.section_functions


def test_form_complexity_is_valid_for_all_form_classes() -> None:
    base_commission, brief = _commission_and_brief_for_forms()
    durations = {
        "micro": 48.0,
        "song": 180.0,
        "extended": 330.0,
        "suite": 540.0,
    }

    for form_class, duration in durations.items():
        commission = replace(
            base_commission,
            form_class=form_class,
            duration_target_s=duration,
            composition_mode="through_composed" if form_class == "suite" else base_commission.composition_mode,
        )
        plan = plan_form(commission=commission, brief=brief, family="ember")

        assert len(plan.sections) >= minimum_function_count(form_class)
        assert len({section.scene_name for section in plan.sections}) == len(plan.sections)
        assert all(section.target_duration_s > 0.0 for section in plan.sections)
        assert len(plan.section_functions) == len(plan.sections)


# --- Score-tree integration tests ---


def test_song_tree_has_phrase_family_metadata() -> None:
    tree = _build_tree(form_class="song")
    for section in tree.sections:
        for phrase in section.phrases:
            assert phrase.phrase_family in {
                "seed", "variant", "development", "response", "liquidation",
            }, f"unexpected phrase_family: {phrase.phrase_family}"


def test_extended_tree_has_phrase_family_metadata() -> None:
    tree = _build_tree(form_class="extended")
    for section in tree.sections:
        for phrase in section.phrases:
            assert phrase.phrase_family in {
                "seed", "variant", "development", "response", "liquidation",
            }


def test_suite_tree_has_phrase_family_metadata() -> None:
    tree = _build_tree(form_class="suite")
    for section in tree.sections:
        for phrase in section.phrases:
            assert phrase.phrase_family in {
                "seed", "variant", "development", "response", "liquidation",
            }


def test_non_seed_phrases_reference_seed() -> None:
    """Every non-seed phrase must have seed_phrase_id pointing to the section's seed."""
    tree = _build_tree(form_class="extended")
    for section in tree.sections:
        seed_ids = [p.phrase_id for p in section.phrases if p.phrase_family == "seed"]
        for phrase in section.phrases:
            if phrase.phrase_family != "seed":
                assert phrase.seed_phrase_id is not None
                assert phrase.seed_phrase_id in seed_ids, (
                    f"phrase {phrase.phrase_id} references unknown seed {phrase.seed_phrase_id}"
                )
            else:
                assert phrase.seed_phrase_id is None


def test_multi_phrase_sections_have_distinct_transform_ops() -> None:
    """Sections with >1 phrase must not have all phrases sharing identical transform_ops."""
    tree = _build_tree(form_class="extended")
    for section in tree.sections:
        if len(section.phrases) <= 1:
            continue
        ops_sets = [frozenset(p.transform_ops) for p in section.phrases]
        assert len(set(ops_sets)) > 1, (
            f"section {section.scene_name}: all {len(section.phrases)} phrases "
            f"share identical transform_ops {ops_sets[0]}"
        )


def test_long_development_sections_prevent_literal_looping() -> None:
    """Development/turn sections must have >=2 distinct phrase families."""
    tree = _build_tree(form_class="suite")
    for section in tree.sections:
        if section.function not in {"development", "turn"}:
            continue
        families = {p.phrase_family for p in section.phrases}
        assert len(families) >= 2, (
            f"section {section.scene_name} ({section.function}) has only one "
            f"phrase family: {families}"
        )


def test_macro_section_phrase_motif_hierarchy() -> None:
    """Verify the full fractal hierarchy: tree → sections → phrases → motif_refs."""
    tree = _build_tree(form_class="suite")
    motif_ids = {m.motif_id for m in tree.motifs}
    assert len(tree.sections) >= 5, "suite should have >=5 sections"
    for section in tree.sections:
        assert len(section.phrases) >= 1
        for phrase in section.phrases:
            assert phrase.motif_refs, f"phrase {phrase.phrase_id} has no motif_refs"
            for ref in phrase.motif_refs:
                assert ref in motif_ids, f"phrase references unknown motif {ref}"


def test_score_tree_round_trips_phrase_family_fields() -> None:
    """phrase_family and seed_phrase_id survive JSON round-trip."""
    import json
    from senseweave.score_tree import ScoreTree

    tree = _build_tree(form_class="song")
    serialized = tree.to_json()
    restored = ScoreTree.from_dict(json.loads(serialized))
    for orig_section, rest_section in zip(tree.sections, restored.sections):
        for orig_phrase, rest_phrase in zip(orig_section.phrases, rest_section.phrases):
            assert rest_phrase.phrase_family == orig_phrase.phrase_family
            assert rest_phrase.seed_phrase_id == orig_phrase.seed_phrase_id
