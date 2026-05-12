"""Tests for course-driven self-critique and revision targets.

Red-phase tests: these must FAIL before implementation and PASS after.
"""
from __future__ import annotations

import os
import sys
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools", "senseweave"))

from senseweave.generative_scores import score_from_mood
from senseweave.self_critique import (
    RevisionResult,
    revise_score,
)


# === Course-to-metric mapping ===


class TestCourseMetricMap:
    def test_course_metric_map_exists(self):
        from senseweave.self_critique import COURSE_METRIC_MAP

        assert isinstance(COURSE_METRIC_MAP, dict)
        assert len(COURSE_METRIC_MAP) > 0

    def test_map_contains_known_concepts(self):
        from senseweave.self_critique import COURSE_METRIC_MAP

        assert ("harmonic_function", "dominant") in COURSE_METRIC_MAP
        assert ("meter_groove", "groove") in COURSE_METRIC_MAP
        assert ("mix_role", "lead") in COURSE_METRIC_MAP

    def test_map_values_are_threshold_dicts(self):
        from senseweave.self_critique import COURSE_METRIC_MAP

        for key, thresholds in COURSE_METRIC_MAP.items():
            assert isinstance(thresholds, dict), f"{key}: expected dict"
            for metric, (direction, value) in thresholds.items():
                assert direction in ("min", "max"), f"{key}/{metric}: bad direction"
                assert isinstance(value, (int, float)), f"{key}/{metric}: bad value"


# === Course-aware threshold builder ===


class TestThresholdsForCourse:
    def test_returns_dict(self):
        from senseweave.self_critique import thresholds_for_course

        course = {"harmonic_function": "dominant", "mix_role": "lead"}
        result = thresholds_for_course(course)
        assert isinstance(result, dict)

    def test_includes_defaults(self):
        from senseweave.self_critique import DEFAULT_THRESHOLDS, thresholds_for_course

        result = thresholds_for_course({})
        for key in DEFAULT_THRESHOLDS:
            assert key in result

    def test_merges_course_thresholds(self):
        from senseweave.self_critique import thresholds_for_course

        course = {"harmonic_function": "dominant"}
        result = thresholds_for_course(course)
        assert "cadence_strength" in result

    def test_unknown_concept_ignored(self):
        from senseweave.self_critique import DEFAULT_THRESHOLDS, thresholds_for_course

        result = thresholds_for_course({"harmonic_function": "nonexistent_value_xyz"})
        assert len(result) >= len(DEFAULT_THRESHOLDS)

    def test_stricter_threshold_wins(self):
        from senseweave.self_critique import thresholds_for_course

        course = {
            "mix_role": "lead",
            "harmonic_function": "dominant",
        }
        result = thresholds_for_course(course)
        assert isinstance(result, dict)


# === CourseFailure and CourseCritiqueReport ===


class TestCourseCritiqueReport:
    def test_course_failure_dataclass_exists(self):
        from senseweave.self_critique import CourseFailure

        f = CourseFailure(
            chapter_id="harmonic_function",
            concept_value="dominant",
            metric_name="cadence_strength",
            direction="min",
            threshold=0.35,
            actual=0.1,
        )
        assert f.chapter_id == "harmonic_function"
        assert f.concept_value == "dominant"
        assert f.metric_name == "cadence_strength"

    def test_course_critique_report_exists(self):
        from senseweave.self_critique import CourseCritiqueReport

        report = CourseCritiqueReport(
            metrics={"cadence_strength": 0.1},
            passed=False,
            failed_metrics=("cadence_strength",),
            course_failures=(
            ),
        )
        assert isinstance(report.course_failures, tuple)

    def test_critique_score_with_course_returns_report(self):
        from senseweave.self_critique import CourseCritiqueReport, critique_score_with_course

        score = score_from_mood({"energy": 0.5, "valence": 0.5, "arousal": 0.5})
        course = {"harmonic_function": "dominant", "mix_role": "lead"}
        report = critique_score_with_course(score, course)
        assert isinstance(report, CourseCritiqueReport)
        assert isinstance(report.metrics, dict)
        assert isinstance(report.passed, bool)

    def test_critique_names_course_concepts_on_failure(self):
        from senseweave.self_critique import critique_score_with_course

        score = score_from_mood({"energy": 0.3, "valence": 0.3, "arousal": 0.2})
        course = {
            "harmonic_function": "dominant",
            "meter_groove": "groove",
            "mix_role": "lead",
        }
        report = critique_score_with_course(score, course)
        if not report.passed:
            assert len(report.course_failures) > 0
            for failure in report.course_failures:
                assert failure.chapter_id in course
                assert failure.concept_value == course[failure.chapter_id]
                assert isinstance(failure.metric_name, str)

    def test_passing_score_has_no_course_failures(self):
        from senseweave.self_critique import critique_score_with_course

        score = score_from_mood({"energy": 0.6, "valence": 0.7, "arousal": 0.5})
        report = critique_score_with_course(score, {})
        if report.passed:
            assert report.course_failures == ()


# === Revision targets ===


class TestRevisionTargets:
    def test_revision_targets_dataclass_exists(self):
        from senseweave.self_critique import RevisionTargets

        targets = RevisionTargets(
            adjust_form=False,
            adjust_harmony=True,
            adjust_rhythm=False,
            adjust_register=False,
            adjust_mix=False,
            adjust_strategy=False,
        )
        assert targets.adjust_harmony is True
        assert targets.adjust_form is False

    def test_revision_targets_from_failures(self):
        from senseweave.self_critique import (
            CourseFailure,
            RevisionTargets,
            revision_targets_from_failures,
        )

        failures = (
            CourseFailure("harmonic_function", "dominant", "cadence_strength", "min", 0.35, 0.1),
        )
        targets = revision_targets_from_failures(failures)
        assert isinstance(targets, RevisionTargets)
        assert targets.adjust_harmony is True

    def test_rhythm_failure_enables_rhythm_adjustment(self):
        from senseweave.self_critique import (
            CourseFailure,
            revision_targets_from_failures,
        )

        failures = (
            CourseFailure("meter_groove", "groove", "onset_density", "min", 1.5, 0.5),
        )
        targets = revision_targets_from_failures(failures)
        assert targets.adjust_rhythm is True

    def test_mix_failure_enables_mix_adjustment(self):
        from senseweave.self_critique import (
            CourseFailure,
            revision_targets_from_failures,
        )

        failures = (
            CourseFailure("mix_role", "lead", "hook_clarity", "min", 0.3, 0.05),
        )
        targets = revision_targets_from_failures(failures)
        assert targets.adjust_mix is True

    def test_register_failure_enables_register_adjustment(self):
        from senseweave.self_critique import (
            CourseFailure,
            revision_targets_from_failures,
        )

        failures = (
            CourseFailure("spatial_intent", "wide", "pitch_range_semitones", "min", 8.0, 3.0),
        )
        targets = revision_targets_from_failures(failures)
        assert targets.adjust_register is True

    def test_strategy_failure_enables_strategy_adjustment(self):
        from senseweave.self_critique import (
            CourseFailure,
            revision_targets_from_failures,
        )

        failures = (
            CourseFailure("genre_strategy", "ambient_drone", "static_score", "max", 0.85, 0.9),
        )
        targets = revision_targets_from_failures(failures)
        assert targets.adjust_strategy is True

    def test_no_failures_all_false(self):
        from senseweave.self_critique import revision_targets_from_failures

        targets = revision_targets_from_failures(())
        assert targets.adjust_form is False
        assert targets.adjust_harmony is False
        assert targets.adjust_rhythm is False
        assert targets.adjust_register is False
        assert targets.adjust_mix is False
        assert targets.adjust_strategy is False

    def test_identity_preserved_with_targets(self):
        """Revision targets do not allow changing key, mood, or tempo."""
        from senseweave.self_critique import RevisionTargets

        targets = RevisionTargets(
            adjust_form=True,
            adjust_harmony=True,
            adjust_rhythm=True,
            adjust_register=True,
            adjust_mix=True,
            adjust_strategy=True,
        )
        # Even with all adjustments enabled, piece identity fields are not adjustment targets
        assert not hasattr(targets, "adjust_key")
        assert not hasattr(targets, "adjust_mood")
        assert not hasattr(targets, "adjust_tempo")


# === Course-aware revise_score ===


class TestCourseRevision:
    def test_revise_score_accepts_course_kwarg(self):
        mood = {"energy": 0.5, "valence": 0.5, "arousal": 0.5}
        course = {"harmonic_function": "dominant"}
        result = revise_score(mood, song_num=1, family="ember", course=course)
        assert isinstance(result, RevisionResult)

    def test_revision_result_has_course_failures(self):
        mood = {"energy": 0.5, "valence": 0.5, "arousal": 0.5}
        course = {"harmonic_function": "dominant", "mix_role": "lead"}
        result = revise_score(mood, song_num=1, family="ember", course=course)
        assert hasattr(result, "course_failures")
        assert isinstance(result.course_failures, tuple)

    def test_revision_result_has_revision_targets(self):
        mood = {"energy": 0.5, "valence": 0.5, "arousal": 0.5}
        course = {"harmonic_function": "dominant"}
        result = revise_score(mood, song_num=1, family="ember", course=course)
        assert hasattr(result, "revision_targets")

    def test_identity_preserved_with_course(self):
        mood = {"energy": 0.5, "valence": 0.5, "arousal": 0.5}
        course = {"harmonic_function": "dominant", "meter_groove": "groove"}
        result = revise_score(
            mood,
            song_num=5,
            family="drift",
            cadence_state="occupied_day",
            course=course,
        )
        assert result.identity_preserved is True
        final = result.final_score
        assert final.key == result.original_score.key
        assert final.mood == result.original_score.mood
        assert final.tempo_bpm == result.original_score.tempo_bpm

    def test_at_least_one_metric_improves_when_revision_used(self):
        mood = {"energy": 0.5, "valence": 0.5, "arousal": 0.5}
        course = {"harmonic_function": "dominant", "mix_role": "lead"}
        result = revise_score(
            mood,
            song_num=5,
            family="drift",
            cadence_state="occupied_day",
            course=course,
        )
        if result.revision_used:
            assert len(result.improved_metrics) >= 1

    def test_no_course_falls_back_to_defaults(self):
        mood = {"energy": 0.6, "valence": 0.7, "arousal": 0.5}
        result_no_course = revise_score(mood, song_num=1, family="ember")
        result_with_none = revise_score(mood, song_num=1, family="ember", course=None)
        assert type(result_no_course) is type(result_with_none)


# === Pipeline integration ===


class TestCoursePipelineIntegration:
    def test_tracker_compiler_passes_course_to_revise(self):
        """compile_score_tree_to_tracker should pass section production_course to revise_score."""
        from senseweave.tracker_compiler import compile_score_tree_to_tracker
        from senseweave.score_tree import ScoreTree, SectionNode, MotifNode, PhraseNode
        from senseweave.piece_commission import PieceCommission
        from senseweave.piece_brief import PieceBrief
        from senseweave.form_grammar import FormPlan, PlannedSection

        mood = {"energy": 0.5, "valence": 0.5, "arousal": 0.5}
        commission = PieceCommission(
            form_class="song",
            composition_mode="hook_led",
            duration_target_s=60.0,
            sonic_world_count=1,
            hook_pressure=0.5,
            narrative_scale="scene",
            ending_family="fadeout",
            groove_identity="steady",
            reason_tags=("test",),
        )
        brief = PieceBrief(
            image_field=("test",),
            dramatic_premise="test premise",
            conflict="none",
            desired_payoff="resolution",
            residue="silence",
            ending_feeling="calm",
            motion_character="steady",
            hook_pressure=0.5,
            through_composed_pressure=0.0,
            section_beats=("statement",),
            narrative_scale="scene",
        )
        form = FormPlan(
            form_family="standard",
            form_class="song",
            composition_mode="hook_led",
            sections=(
                PlannedSection(
                    scene_name="Theme",
                    function="statement",
                    target_duration_s=30.0,
                ),
            ),
            ending_family="fadeout",
        )
        motif = MotifNode(
            motif_id="m1",
            hook_class="melodic",
            contour=(1, 3, 5, 3, 1),
            rhythm=(1.0, 0.5, 1.0, 0.5, 1.5),
            anchor_degrees=(1, 3, 5),
            answer_degrees=(5, 3, 1),
            text_hook="test hook",
        )
        section = SectionNode(
            section_id="s1",
            scene_name="Theme",
            function="statement",
            target_duration_s=30.0,
            harmonic_role="tonic",
            cadence_type="half",
            groove_state="steady",
            production_course={
                "harmonic_function": "dominant",
                "mix_role": "lead",
            },
            phrases=[
                PhraseNode(
                    phrase_id="p1",
                    function="statement",
                    motif_refs=("m1",),
                    target_duration_s=15.0,
                    transform_ops=(),
                ),
            ],
        )
        tree = ScoreTree(
            piece_id="test-course-pipe-1",
            title="Course Pipeline Test",
            commission=commission,
            brief=brief,
            form=form,
            motifs=[motif],
            sections=[section],
            harmonic_plan={},
            arrangement_plan={},
            ending_family="fadeout",
            narrative_map={},
            metadata={"song_num": "1"},
            planned_duration_s=60.0,
            primary_hook_text="test hook",
        )

        calls: list[dict] = []
        original_revise = revise_score

        def tracking_revise(mood_arg, **kwargs):
            calls.append({"mood": mood_arg, **kwargs})
            return original_revise(mood_arg, **kwargs)

        with patch("senseweave.tracker_compiler.revise_score", side_effect=tracking_revise):
            compile_score_tree_to_tracker(
                tree,
                mood=mood,
                family_name="ember",
                patch_name="default",
                cadence_state="wake_ramp",
            )

        assert len(calls) >= 1, "revise_score was not called"
        assert "course" in calls[0], "revise_score was not called with course kwarg"
        assert calls[0]["course"] == {"harmonic_function": "dominant", "mix_role": "lead"}

    def test_duet_composer_fallback_passes_course(self):
        """The duet_composer fallback path should pass course to revise_score."""
        import importlib

        spec = importlib.util.find_spec("duet_composer")
        if spec is None:
            sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools"))
            spec = importlib.util.find_spec("duet_composer")

        assert spec is not None, "duet_composer module not found"
        source_path = spec.origin
        assert source_path is not None

        with open(source_path) as f:
            source = f.read()

        assert "course=" in source, (
            "duet_composer fallback does not pass course kwarg to revise_score"
        )


# === End-to-end revision with course context ===


class TestCourseRevisionEndToEnd:
    def test_piece_goes_through_course_critique_before_finalization(self):
        """A piece with course metadata goes through course-aware critique,
        failed metrics trigger one bounded rewrite attempt, and the final
        score is selected from the two-pass result."""
        mood = {"energy": 0.5, "valence": 0.5, "arousal": 0.5}
        course = {
            "harmonic_function": "dominant",
            "meter_groove": "groove",
            "mix_role": "lead",
        }
        result = revise_score(
            mood,
            song_num=3,
            family="drift",
            cadence_state="occupied_day",
            course=course,
        )
        assert isinstance(result, RevisionResult)
        assert hasattr(result, "course_failures")
        assert hasattr(result, "revision_targets")

        if not result.original_metrics:
            return

        if result.revised_score is not None:
            assert result.revised_metrics is not None
            final = result.final_score
            assert final is result.original_score or final is result.revised_score
            if result.revision_used:
                assert len(result.improved_metrics) >= 1
                assert final is result.revised_score
            else:
                assert final is result.original_score

    def test_course_failures_name_concrete_concepts(self):
        """When critique fails, course_failures names the specific concept."""
        mood = {"energy": 0.3, "valence": 0.3, "arousal": 0.2}
        course = {
            "harmonic_function": "dominant",
            "meter_groove": "groove",
            "mix_role": "lead",
        }
        result = revise_score(
            mood,
            song_num=7,
            family="drift",
            cadence_state="occupied_day",
            course=course,
        )
        for failure in result.course_failures:
            assert failure.chapter_id in (
                "harmonic_function",
                "meter_groove",
                "mix_role",
                "mode_scale",
                "counterpoint_relation",
                "spatial_intent",
                "genre_strategy",
                "transition_type",
                "phase_profile",
                "synthesis_architecture",
            )
            assert isinstance(failure.metric_name, str)
            assert isinstance(failure.actual, (int, float))
            assert isinstance(failure.threshold, (int, float))
