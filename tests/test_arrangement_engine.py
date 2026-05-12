"""Tests for arrangement_engine.py -- section arrangement plans."""
from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools", "senseweave"))

from senseweave.arrangement_engine import (
    AutomationCurve,
    RegisterBand,
    active_voices_at,
    build_arrangement_plan,
    build_scene_timeline,
    climaxes_staggered,
    contours_independent,
    interpolate_automation,
    register_crowding_detected,
    registers_safe,
    thin_events,
)
from senseweave.music_tracker import tracker_form_for_family


def test_arrangement_plan_builds_scene_entries_for_form() -> None:
    form = tracker_form_for_family("bloom", song_num=2)
    plan = build_arrangement_plan(
        patch_name="house_garden",
        family_name="bloom",
        cadence_state="occupied_day",
        progression_profile="open_day",
        form_templates=form,
    )

    assert plan.groove_family in {"rolling", "lyric", "suspended", "procession", "study"}
    assert set(plan.scenes) == {scene.name for scene in form}
    assert plan.scenes["Theme"].entry_intent
    assert "density" in plan.scenes["Development"].automation_overrides


def test_sleep_arrangement_is_quieter_than_occupied_day() -> None:
    sleep = build_arrangement_plan(
        patch_name="house_monastery",
        family_name="nocturne",
        cadence_state="sleep",
        progression_profile="stillness",
        form_templates=tracker_form_for_family("nocturne", song_num=1),
    )
    day = build_arrangement_plan(
        patch_name="house_garden",
        family_name="bloom",
        cadence_state="occupied_day",
        progression_profile="open_day",
        form_templates=tracker_form_for_family("bloom", song_num=1),
    )

    assert sleep.scenes["Theme"].automation_overrides["density"] < day.scenes["Theme"].automation_overrides["density"]


def test_repertoire_density_bias_shapes_scene_density() -> None:
    base = build_arrangement_plan(
        patch_name="house_garden",
        family_name="bloom",
        cadence_state="occupied_day",
        progression_profile="open_day",
        form_templates=tracker_form_for_family("bloom", song_num=1),
    )
    biased = build_arrangement_plan(
        patch_name="house_garden",
        family_name="bloom",
        cadence_state="occupied_day",
        progression_profile="open_day",
        form_templates=tracker_form_for_family("bloom", song_num=1),
        density_bias=0.12,
    )

    assert biased.scenes["Theme"].automation_overrides["density"] > base.scenes["Theme"].automation_overrides["density"]


def test_payoff_scene_bias_pushes_target_scene_forward() -> None:
    base = build_arrangement_plan(
        patch_name="house_garden",
        family_name="bloom",
        cadence_state="occupied_day",
        progression_profile="open_day",
        form_templates=tracker_form_for_family("bloom", song_num=1),
    )
    biased = build_arrangement_plan(
        patch_name="house_garden",
        family_name="bloom",
        cadence_state="occupied_day",
        progression_profile="open_day",
        form_templates=tracker_form_for_family("bloom", song_num=1),
        payoff_scene="Recap",
        payoff_bias=0.14,
    )

    assert biased.scenes["Recap"].automation_overrides["master_amp"] > base.scenes["Recap"].automation_overrides["master_amp"]
    assert biased.scenes["Recap"].entry_intent != base.scenes["Recap"].entry_intent


# ── Staged ensemble growth ────────────────────────────────────────


class TestStagedEnsembleGrowth:
    def test_sparse_has_two_voices(self) -> None:
        tl = build_scene_timeline("Emergence", max_polyphony=2, base_density=0.2, base_amp=0.52)
        entries = [e for e in tl.lane_events if e.action == "enter"]
        assert len(entries) == 2

    def test_medium_has_four_voices(self) -> None:
        tl = build_scene_timeline("Theme", max_polyphony=3, base_density=0.45, base_amp=0.65)
        entries = [e for e in tl.lane_events if e.action == "enter"]
        assert len(entries) == 4

    def test_full_has_seven_voices(self) -> None:
        tl = build_scene_timeline("Development", max_polyphony=5, base_density=0.78, base_amp=0.72)
        entries = [e for e in tl.lane_events if e.action == "enter"]
        assert len(entries) == 7

    def test_staged_entry_not_simultaneous(self) -> None:
        """Voices enter over time, not all at t=0."""
        tl = build_scene_timeline("Development", max_polyphony=5, base_density=0.78, base_amp=0.72)
        entries = [e for e in tl.lane_events if e.action == "enter"]
        entry_times = [e.t for e in entries]
        assert entry_times[0] == 0.0
        assert entry_times[-1] > 0.0

    def test_support_dropout_and_return(self) -> None:
        tl = build_scene_timeline("Theme", max_polyphony=3, base_density=0.45, base_amp=0.65)
        dropouts = [e for e in tl.lane_events if e.action == "dropout"]
        returns = [e for e in tl.lane_events if e.action == "return"]
        assert len(dropouts) >= 1
        assert len(returns) >= 1
        assert dropouts[0].role == "support"

    def test_full_variant_has_double(self) -> None:
        tl = build_scene_timeline("Development", max_polyphony=5, base_density=0.78, base_amp=0.72)
        doubles = [e for e in tl.lane_events if e.action == "double"]
        assert len(doubles) >= 1

    def test_sparse_no_dropout(self) -> None:
        tl = build_scene_timeline("Emergence", max_polyphony=2, base_density=0.2, base_amp=0.52)
        dropouts = [e for e in tl.lane_events if e.action == "dropout"]
        assert len(dropouts) == 0

    def test_plan_sparse_fewer_entries_than_full(self) -> None:
        form = tracker_form_for_family("bloom", song_num=1)
        plan = build_arrangement_plan(
            patch_name="house_garden",
            family_name="bloom",
            cadence_state="occupied_day",
            progression_profile="open_day",
            form_templates=form,
        )
        res_entries = [e for e in plan.scenes["Resolution"].timeline.lane_events if e.action == "enter"]
        dev_entries = [e for e in plan.scenes["Development"].timeline.lane_events if e.action == "enter"]
        assert len(res_entries) < len(dev_entries)


# ── Active voices at time ─────────────────────────────────────────


class TestActiveVoicesAt:
    def test_at_least_one_at_start(self) -> None:
        tl = build_scene_timeline("Development", max_polyphony=5, base_density=0.78, base_amp=0.72)
        assert len(active_voices_at(tl, 0.0)) >= 1

    def test_voices_grow_over_time(self) -> None:
        tl = build_scene_timeline("Development", max_polyphony=5, base_density=0.78, base_amp=0.72)
        early = active_voices_at(tl, 0.05)
        late = active_voices_at(tl, 0.55)
        assert len(late) >= len(early)

    def test_dropout_reduces_voices(self) -> None:
        tl = build_scene_timeline("Theme", max_polyphony=3, base_density=0.45, base_amp=0.65)
        before = active_voices_at(tl, 0.64)
        after = active_voices_at(tl, 0.66)
        assert len(after) < len(before)

    def test_return_restores_voice(self) -> None:
        tl = build_scene_timeline("Theme", max_polyphony=3, base_density=0.45, base_amp=0.65)
        during_dropout = active_voices_at(tl, 0.7)
        after_return = active_voices_at(tl, 0.85)
        assert len(after_return) > len(during_dropout)


# ── Thinning preserves primary continuity ─────────────────────────


class TestThinEvents:
    def test_thin_preserves_primary(self) -> None:
        tl = build_scene_timeline("Development", max_polyphony=5, base_density=0.78, base_amp=0.72)
        thinned = thin_events(tl)
        voices = {e.voice for e in thinned.lane_events}
        assert "bowed" in voices
        assert "choir" in voices

    def test_thin_removes_support(self) -> None:
        tl = build_scene_timeline("Development", max_polyphony=5, base_density=0.78, base_amp=0.72)
        thinned = thin_events(tl)
        voices = {e.voice for e in thinned.lane_events}
        assert "pluck" not in voices
        assert "kotekan" not in voices

    def test_thin_keeps_density_gates(self) -> None:
        tl = build_scene_timeline("Development", max_polyphony=5, base_density=0.78, base_amp=0.72)
        thinned = thin_events(tl)
        assert thinned.density_gates == tl.density_gates

    def test_thin_with_explicit_keep(self) -> None:
        tl = build_scene_timeline("Development", max_polyphony=5, base_density=0.78, base_amp=0.72)
        thinned = thin_events(tl, voices_to_keep=["bowed", "pluck"])
        voices = {e.voice for e in thinned.lane_events}
        assert voices == {"bowed", "pluck"}


# ── Register safety ───────────────────────────────────────────────


class TestRegisterSafety:
    def test_default_bands_are_safe(self) -> None:
        tl = build_scene_timeline("Development", max_polyphony=5, base_density=0.78, base_amp=0.72)
        assert registers_safe(tl.register_bands)

    def test_degenerate_band_is_unsafe(self) -> None:
        assert not registers_safe([RegisterBand(voice="x", low_midi=60, high_midi=60)])

    def test_narrow_band_is_unsafe(self) -> None:
        assert not registers_safe([RegisterBand(voice="x", low_midi=60, high_midi=66)])

    def test_out_of_range_is_unsafe(self) -> None:
        assert not registers_safe([RegisterBand(voice="x", low_midi=10, high_midi=40)])

    def test_all_variants_safe(self) -> None:
        for poly in (2, 3, 5):
            tl = build_scene_timeline("Test", max_polyphony=poly, base_density=0.5, base_amp=0.6)
            assert registers_safe(tl.register_bands), f"Unsafe at polyphony={poly}"


# ── Lane analysis helpers ────────────────────────────────────────


class TestLaneAnalysis:
    def test_independent_contours_accept_different_shapes(self) -> None:
        contours = {
            "bowed": [60, 62, 65, 64, 67],
            "choir": [67, 67, 69, 71, 70],
            "bell": [76, 74, 72, 74, 77],
        }
        assert contours_independent(contours)

    def test_independent_contours_reject_locked_shapes(self) -> None:
        contours = {
            "bowed": [60, 62, 65, 64],
            "choir": [72, 74, 77, 76],
        }
        assert not contours_independent(contours)

    def test_staggered_climaxes_accept_separated_lane_peaks(self) -> None:
        activity = {
            "bowed": [(0.0, 0.2), (0.35, 0.9), (1.0, 0.4)],
            "choir": [(0.0, 0.3), (0.65, 0.85), (1.0, 0.5)],
            "bell": [(0.0, 0.1), (0.85, 0.7), (1.0, 0.3)],
        }
        assert climaxes_staggered(activity, min_separation=0.12)

    def test_staggered_climaxes_reject_same_peak_time(self) -> None:
        activity = {
            "bowed": [(0.0, 0.2), (0.5, 0.9), (1.0, 0.4)],
            "choir": [(0.0, 0.3), (0.5, 0.85), (1.0, 0.5)],
        }
        assert not climaxes_staggered(activity)

    def test_register_crowding_detects_unison_doubling(self) -> None:
        bands = [
            RegisterBand(voice="bowed", low_midi=60, high_midi=76),
            RegisterBand(voice="choir", low_midi=60, high_midi=76),
        ]
        assert register_crowding_detected(bands)

    def test_register_crowding_detects_masking_overlap(self) -> None:
        bands = [
            RegisterBand(voice="bowed", low_midi=60, high_midi=76),
            RegisterBand(voice="choir", low_midi=66, high_midi=82),
        ]
        assert register_crowding_detected(bands)

    def test_register_crowding_accepts_separated_bands(self) -> None:
        bands = [
            RegisterBand(voice="gong", low_midi=36, high_midi=52),
            RegisterBand(voice="bowed", low_midi=56, high_midi=72),
            RegisterBand(voice="bell", low_midi=76, high_midi=96),
        ]
        assert not register_crowding_detected(bands)


# ── Non-flat automation ───────────────────────────────────────────


class TestNonFlatAutomation:
    def test_density_gates_not_flat(self) -> None:
        tl = build_scene_timeline("Development", max_polyphony=5, base_density=0.78, base_amp=0.72)
        densities = [g.density for g in tl.density_gates]
        assert len(set(densities)) > 1

    def test_master_amp_curve_not_flat(self) -> None:
        tl = build_scene_timeline("Development", max_polyphony=5, base_density=0.78, base_amp=0.72)
        amp_curve = next(c for c in tl.automation_curves if c.name == "master_amp")
        values = [p[1] for p in amp_curve.points]
        assert len(set(values)) > 1

    def test_interpolation_at_boundaries(self) -> None:
        curve = AutomationCurve(name="test", points=((0.0, 0.5), (0.5, 1.0), (1.0, 0.7)))
        assert interpolate_automation(curve, 0.0) == 0.5
        assert interpolate_automation(curve, 1.0) == 0.7

    def test_interpolation_midpoint(self) -> None:
        curve = AutomationCurve(name="test", points=((0.0, 0.0), (1.0, 1.0)))
        assert interpolate_automation(curve, 0.5) == 0.5

    def test_interpolation_beyond_range(self) -> None:
        curve = AutomationCurve(name="test", points=((0.2, 0.5), (0.8, 0.9)))
        assert interpolate_automation(curve, 0.0) == 0.5
        assert interpolate_automation(curve, 1.0) == 0.9

    def test_automation_curves_present(self) -> None:
        tl = build_scene_timeline("Theme", max_polyphony=3, base_density=0.45, base_amp=0.65)
        curve_names = {c.name for c in tl.automation_curves}
        assert "master_amp" in curve_names
        assert "density" in curve_names


# ── Plan integration ──────────────────────────────────────────────


class TestArrangementPlanTimeline:
    def test_all_scenes_have_timelines(self) -> None:
        form = tracker_form_for_family("bloom", song_num=1)
        plan = build_arrangement_plan(
            patch_name="house_garden",
            family_name="bloom",
            cadence_state="occupied_day",
            progression_profile="open_day",
            form_templates=form,
        )
        for name, scene in plan.scenes.items():
            assert scene.timeline is not None, f"Scene {name} missing timeline"


# ── End-to-end arrangement contracts ──────────────────────────────


class TestArrangementEngineEndToEnd:
    def test_complete_form_builds_meaningful_scene_contracts(self) -> None:
        form = tracker_form_for_family("bloom", song_num=1)
        plan = build_arrangement_plan(
            patch_name="house_garden",
            family_name="bloom",
            cadence_state="occupied_day",
            progression_profile="open_day",
            form_templates=form,
        )

        assert plan.groove_family == "rolling"
        for template in form:
            scene = plan.scenes[template.name]
            assert scene.entry_intent
            assert {"density", "master_amp", "reverb_send"} <= set(scene.automation_overrides)
            assert 0.05 <= scene.automation_overrides["density"] <= 1.0
            assert scene.timeline is not None
            assert any(event.action == "enter" for event in scene.timeline.lane_events)

    def test_scene_entry_counts_follow_polyphony_variants(self) -> None:
        form = tracker_form_for_family("bloom", song_num=1)
        plan = build_arrangement_plan(
            patch_name="house_garden",
            family_name="bloom",
            cadence_state="occupied_day",
            progression_profile="open_day",
            form_templates=form,
        )

        for template in form:
            scene = plan.scenes[template.name]
            assert scene.timeline is not None
            entries = [event for event in scene.timeline.lane_events if event.action == "enter"]
            expected = 2 if template.max_polyphony <= 2 else 4 if template.max_polyphony <= 4 else 7
            entry_times = [event.t for event in entries]
            assert len(entries) == expected
            assert entry_times == sorted(entry_times)
            assert entry_times[0] == 0.0
            assert entry_times[-1] <= 0.6

    def test_active_voice_curve_grows_and_breathes_inside_scenes(self) -> None:
        plan = build_arrangement_plan(
            patch_name="house_garden",
            family_name="bloom",
            cadence_state="occupied_day",
            progression_profile="open_day",
            form_templates=tracker_form_for_family("bloom", song_num=1),
        )

        for scene_name in ("Theme", "Development"):
            timeline = plan.scenes[scene_name].timeline
            assert timeline is not None
            counts = [len(active_voices_at(timeline, point)) for point in (0.0, 0.35, 0.55)]
            assert counts[0] < counts[-1]
            before_dropout = active_voices_at(timeline, 0.64)
            during_dropout = active_voices_at(timeline, 0.66)
            after_return = active_voices_at(timeline, 0.85)
            assert len(during_dropout) < len(before_dropout)
            assert len(after_return) > len(during_dropout)

    def test_support_thinning_keeps_primary_voices_and_curves(self) -> None:
        plan = build_arrangement_plan(
            patch_name="house_garden",
            family_name="bloom",
            cadence_state="occupied_day",
            progression_profile="open_day",
            form_templates=tracker_form_for_family("bloom", song_num=1),
        )

        for scene_name, scene in plan.scenes.items():
            assert scene.timeline is not None
            thinned = thin_events(scene.timeline)
            roles = {event.voice: event.role for event in scene.timeline.lane_events}
            kept_roles = {roles[event.voice] for event in thinned.lane_events}
            assert kept_roles == {"primary"}, scene_name
            assert {"bowed", "choir"} <= {event.voice for event in thinned.lane_events}
            assert thinned.density_gates == scene.timeline.density_gates
            assert thinned.automation_curves == scene.timeline.automation_curves

    def test_register_bands_are_valid_unique_and_voice_matched(self) -> None:
        plan = build_arrangement_plan(
            patch_name="house_garden",
            family_name="bloom",
            cadence_state="occupied_day",
            progression_profile="open_day",
            form_templates=tracker_form_for_family("bloom", song_num=1),
        )

        for scene in plan.scenes.values():
            assert scene.timeline is not None
            voices = {event.voice for event in scene.timeline.lane_events if event.action == "enter"}
            band_voices = [band.voice for band in scene.timeline.register_bands]
            assert registers_safe(scene.timeline.register_bands)
            assert set(band_voices) == voices
            assert len(band_voices) == len(set(band_voices))
            for band in scene.timeline.register_bands:
                assert band.low_midi < band.high_midi

    def test_automation_curves_interpolate_within_declared_ranges(self) -> None:
        plan = build_arrangement_plan(
            patch_name="house_garden",
            family_name="bloom",
            cadence_state="occupied_day",
            progression_profile="open_day",
            form_templates=tracker_form_for_family("bloom", song_num=1),
        )

        for scene in plan.scenes.values():
            assert scene.timeline is not None
            for curve in scene.timeline.automation_curves:
                values = [value for _point, value in curve.points]
                samples = [interpolate_automation(curve, point) for point in (0.0, 0.25, 0.5, 0.75, 1.0)]
                assert len(set(values)) > 1
                assert min(values) <= min(samples) <= max(values)
                assert min(values) <= max(samples) <= max(values)
                if curve.name == "density":
                    gates = tuple((gate.t, gate.density) for gate in scene.timeline.density_gates)
                    assert curve.points == gates

    def test_payoff_bias_targets_one_scene_without_rewriting_form(self) -> None:
        form = tracker_form_for_family("bloom", song_num=1)
        base = build_arrangement_plan(
            patch_name="house_garden",
            family_name="bloom",
            cadence_state="occupied_day",
            progression_profile="open_day",
            form_templates=form,
        )
        biased = build_arrangement_plan(
            patch_name="house_garden",
            family_name="bloom",
            cadence_state="occupied_day",
            progression_profile="open_day",
            form_templates=form,
            payoff_scene="Recap",
            payoff_bias=0.14,
        )

        assert set(base.scenes) == set(biased.scenes)
        for name in base.scenes:
            base_scene = base.scenes[name]
            biased_scene = biased.scenes[name]
            if name == "Recap":
                assert biased_scene.automation_overrides["density"] > base_scene.automation_overrides["density"]
                assert biased_scene.automation_overrides["master_amp"] > base_scene.automation_overrides["master_amp"]
                assert biased_scene.entry_intent.endswith("and arrive")
            else:
                assert biased_scene.automation_overrides["density"] == base_scene.automation_overrides["density"]
                assert biased_scene.entry_intent == base_scene.entry_intent

    def test_cadence_state_quieting_and_practice_lift_are_consistent(self) -> None:
        form = tracker_form_for_family("bloom", song_num=1)
        plans = {
            cadence: build_arrangement_plan(
                patch_name="house_garden",
                family_name="bloom",
                cadence_state=cadence,
                progression_profile="open_day",
                form_templates=form,
            )
            for cadence in ("sleep", "wind_down", "occupied_day", "away_practice")
        }

        for scene_name in plans["occupied_day"].scenes:
            sleep_scene = plans["sleep"].scenes[scene_name]
            wind_scene = plans["wind_down"].scenes[scene_name]
            day_scene = plans["occupied_day"].scenes[scene_name]
            practice_scene = plans["away_practice"].scenes[scene_name]
            assert sleep_scene.automation_overrides["density"] < wind_scene.automation_overrides["density"]
            assert wind_scene.automation_overrides["density"] < day_scene.automation_overrides["density"]
            assert practice_scene.automation_overrides["density"] >= day_scene.automation_overrides["density"]
            assert sleep_scene.automation_overrides["master_amp"] < day_scene.automation_overrides["master_amp"]

    def test_public_dataclasses_render_json_safe_plan_output(self) -> None:
        plan = build_arrangement_plan(
            patch_name="house_garden",
            family_name="bloom",
            cadence_state="occupied_day",
            progression_profile="open_day",
            form_templates=tracker_form_for_family("bloom", song_num=1),
        )

        payload = asdict(plan)
        rendered = json.dumps(payload, sort_keys=True)
        decoded = json.loads(rendered)
        for scene_name, scene_payload in decoded["scenes"].items():
            timeline = scene_payload["timeline"]
            assert scene_payload["entry_intent"], scene_name
            assert isinstance(timeline["lane_events"], list)
            assert isinstance(timeline["register_bands"], list)
            assert isinstance(timeline["density_gates"], list)
            assert isinstance(timeline["automation_curves"], list)

    def test_multiple_families_stay_end_to_end_shape_compatible(self) -> None:
        scenarios = [
            ("bloom", "house_garden", "occupied_day", "open_day", "rolling"),
            ("nocturne", "house_monastery", "sleep", "stillness", "suspended"),
            ("drift", "unknown_patch", "wind_down", "experiment", "study"),
        ]

        for family, patch, cadence, profile, expected_groove in scenarios:
            form = tracker_form_for_family(family, song_num=2)
            plan = build_arrangement_plan(
                patch_name=patch,
                family_name=family,
                cadence_state=cadence,
                progression_profile=profile,
                form_templates=form,
            )
            assert plan.groove_family == expected_groove
            assert set(plan.scenes) == {template.name for template in form}
            for scene in plan.scenes.values():
                assert scene.timeline is not None
                assert registers_safe(scene.timeline.register_bands)
                assert any(curve.name == "density" for curve in scene.timeline.automation_curves)
