"""Tests for self_critique.py — pre-performance self-critique and revision passes."""
from __future__ import annotations

import os
import sys
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools", "senseweave"))

from senseweave.self_critique import (
    CritiqueReport,
    RevisionResult,
    critique_score,
    preview_score,
    revise_score,
)
from senseweave.generative_scores import (
    Note,
    Phrase,
    Score,
    score_from_mood,
)


# === preview_score ===


class TestPreviewScore:
    def test_returns_metric_dict(self):
        score = score_from_mood({"energy": 0.6, "valence": 0.7, "arousal": 0.5})
        metrics = preview_score(score)
        assert isinstance(metrics, dict)
        assert len(metrics) > 0

    def test_contains_core_ear_metrics(self):
        score = score_from_mood({"energy": 0.6, "valence": 0.7, "arousal": 0.5})
        metrics = preview_score(score)
        for key in (
            "interval_variety",
            "development_score",
            "hook_clarity",
            "cadence_strength",
            "onset_density",
            "repetition_score",
        ):
            assert key in metrics, f"missing metric: {key}"

    def test_contains_feedback_scores(self):
        score = score_from_mood({"energy": 0.6, "valence": 0.7, "arousal": 0.5})
        metrics = preview_score(score)
        for key in ("static_score", "harsh_score", "muddy_score", "underdeveloped_score"):
            assert key in metrics, f"missing feedback score: {key}"

    def test_metrics_are_numeric(self):
        score = score_from_mood({"energy": 0.5, "valence": 0.5, "arousal": 0.5})
        metrics = preview_score(score)
        for key, value in metrics.items():
            assert isinstance(value, (int, float)), f"{key} is not numeric: {value}"

    def test_minimal_sleeping_score_produces_metrics(self):
        score = score_from_mood({"energy": 0.1, "valence": 0.3, "arousal": 0.1})
        metrics = preview_score(score)
        assert isinstance(metrics, dict)
        assert "development_score" in metrics

    def test_manual_score_produces_valid_metrics(self):
        """A hand-built Score can be previewed without score_from_mood."""
        manual = Score(
            phrases=[
                Phrase(
                    notes=[
                        Note(1, 1.0, True),
                        Note(3, 0.5, False),
                        Note(5, 1.0, True),
                        Note(3, 0.5, False),
                        Note(1, 1.5, False),
                    ],
                    voice="pluck",
                    dynamic="mf",
                    role="melody",
                )
            ],
            key="C",
            tempo_bpm=100.0,
            mood="calm",
            created_at=0.0,
        )
        metrics = preview_score(manual)
        assert metrics["pitch_range_semitones"] > 0


# === critique_score ===


class TestCritiqueScore:
    def test_returns_critique_report(self):
        score = score_from_mood({"energy": 0.6, "valence": 0.7, "arousal": 0.5})
        report = critique_score(score)
        assert isinstance(report, CritiqueReport)

    def test_report_has_metrics(self):
        score = score_from_mood({"energy": 0.6, "valence": 0.7, "arousal": 0.5})
        report = critique_score(score)
        assert isinstance(report.metrics, dict)
        assert len(report.metrics) > 0

    def test_report_passed_is_bool(self):
        score = score_from_mood({"energy": 0.6, "valence": 0.7, "arousal": 0.5})
        report = critique_score(score)
        assert isinstance(report.passed, bool)

    def test_report_failed_metrics_is_tuple(self):
        score = score_from_mood({"energy": 0.6, "valence": 0.7, "arousal": 0.5})
        report = critique_score(score)
        assert isinstance(report.failed_metrics, tuple)

    def test_passing_score_has_no_failures(self):
        score = score_from_mood({"energy": 0.6, "valence": 0.7, "arousal": 0.5})
        # Use very lenient thresholds that anything should pass
        report = critique_score(score, thresholds={
            "underdeveloped_score": ("max", 0.99),
            "static_score": ("max", 0.99),
            "development_score": ("min", 0.01),
            "hook_clarity": ("min", 0.01),
        })
        assert report.passed is True
        assert report.failed_metrics == ()

    def test_strict_thresholds_cause_failure(self):
        score = score_from_mood({"energy": 0.3, "valence": 0.5, "arousal": 0.3})
        # Use impossibly strict thresholds
        report = critique_score(score, thresholds={
            "development_score": ("min", 0.99),
        })
        assert report.passed is False
        assert "development_score" in report.failed_metrics

    def test_custom_thresholds_override_defaults(self):
        score = score_from_mood({"energy": 0.5, "valence": 0.5, "arousal": 0.5})
        # Only check one metric with a custom threshold
        report = critique_score(score, thresholds={
            "hook_clarity": ("min", 0.01),
        })
        # With such a lenient threshold, it should pass
        assert report.passed is True


# === revise_score ===


class TestReviseScore:
    def test_returns_revision_result(self):
        mood = {"energy": 0.6, "valence": 0.7, "arousal": 0.5}
        result = revise_score(mood, song_num=1, family="ember", cadence_state="wake_ramp")
        assert isinstance(result, RevisionResult)

    def test_has_original_score_and_metrics(self):
        mood = {"energy": 0.6, "valence": 0.7, "arousal": 0.5}
        result = revise_score(mood, song_num=1, family="ember", cadence_state="wake_ramp")
        assert isinstance(result.original_score, Score)
        assert isinstance(result.original_metrics, dict)

    def test_no_revision_when_passing(self):
        mood = {"energy": 0.6, "valence": 0.7, "arousal": 0.5}
        # Lenient thresholds — should pass on first attempt
        result = revise_score(
            mood,
            song_num=1,
            family="ember",
            cadence_state="wake_ramp",
            thresholds={
                "underdeveloped_score": ("max", 0.99),
                "static_score": ("max", 0.99),
                "development_score": ("min", 0.01),
                "hook_clarity": ("min", 0.01),
            },
        )
        assert result.revision_used is False
        assert result.revised_score is None
        assert result.revised_metrics is None

    def test_revision_requested_for_failed_metrics(self):
        mood = {"energy": 0.5, "valence": 0.5, "arousal": 0.5}
        # Strict thresholds to force a revision attempt
        result = revise_score(
            mood,
            song_num=5,
            family="drift",
            cadence_state="occupied_day",
            thresholds={
                "development_score": ("min", 0.99),
            },
        )
        # A revision was attempted (even if it didn't help)
        assert result.revised_metrics is not None

    def test_revision_improves_at_least_one_metric(self):
        """When revision is used, at least one failed metric must improve."""
        mood = {"energy": 0.5, "valence": 0.5, "arousal": 0.5}
        result = revise_score(
            mood,
            song_num=5,
            family="drift",
            cadence_state="occupied_day",
            thresholds={
                "development_score": ("min", 0.99),
                "hook_clarity": ("min", 0.99),
            },
        )
        if result.revision_used:
            assert len(result.improved_metrics) >= 1

    def test_identity_preserved_after_revision(self):
        mood = {"energy": 0.5, "valence": 0.5, "arousal": 0.5}
        result = revise_score(
            mood,
            song_num=5,
            family="drift",
            cadence_state="occupied_day",
            thresholds={
                "development_score": ("min", 0.99),
            },
        )
        assert result.identity_preserved is True
        # The final score always preserves the original concept's identity
        final = result.final_score
        assert final.key == result.original_score.key
        assert final.mood == result.original_score.mood
        assert final.tempo_bpm == result.original_score.tempo_bpm
        # If revision was used, the revised score must match the original's identity
        if result.revision_used and result.revised_score is not None:
            assert result.revised_score.key == result.original_score.key
            assert result.revised_score.mood == result.original_score.mood
            assert result.revised_score.tempo_bpm == result.original_score.tempo_bpm

    def test_keeps_original_when_revision_worse(self):
        """If revision does not improve any failed metric, keep original."""
        mood = {"energy": 0.6, "valence": 0.7, "arousal": 0.5}
        result = revise_score(
            mood,
            song_num=1,
            family="ember",
            cadence_state="wake_ramp",
            thresholds={
                "development_score": ("min", 0.99),
            },
        )
        # Whether revision_used is True or False, identity must be preserved
        assert result.identity_preserved is True
        # If not used, original is the final score
        if not result.revision_used:
            assert result.improved_metrics == ()

    def test_max_one_rewrite_pass(self):
        """Only one revision attempt is made, never more."""
        mood = {"energy": 0.5, "valence": 0.5, "arousal": 0.5}
        # Even with very strict thresholds, only one revision is attempted
        result = revise_score(
            mood,
            song_num=5,
            family="drift",
            cadence_state="occupied_day",
            thresholds={
                "development_score": ("min", 0.99),
                "hook_clarity": ("min", 0.99),
                "static_score": ("max", 0.01),
                "underdeveloped_score": ("max", 0.01),
            },
        )
        # The result should have exactly one revision attempt
        assert result.revised_metrics is not None
        # The final score is either original or revised — not a third attempt
        final = result.revised_score if result.revision_used else result.original_score
        assert isinstance(final, Score)

    def test_final_score_is_accessible(self):
        mood = {"energy": 0.6, "valence": 0.7, "arousal": 0.5}
        result = revise_score(mood, song_num=1, family="ember", cadence_state="wake_ramp")
        final = result.final_score
        assert isinstance(final, Score)
        assert len(final.phrases) >= 1


# === Pipeline integration: revise_score is wired into composition flow ===


class TestPipelineIntegration:
    """Verify that revise_score is called by the composition pipeline, not
    raw score_from_mood, so every piece goes through critique/revision
    before being finalized for playback."""

    def test_tracker_compiler_uses_revise_score(self):
        """compile_score_tree_to_tracker routes through revise_score."""
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
            piece_id="test-piece-1",
            title="Integration Test",
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
            compiled = compile_score_tree_to_tracker(
                tree,
                mood=mood,
                family_name="ember",
                patch_name="default",
                cadence_state="wake_ramp",
            )

        assert len(calls) >= 1, "revise_score was not called by compile_score_tree_to_tracker"
        assert isinstance(compiled.source_score, Score)
        assert len(compiled.source_score.phrases) >= 1

    def test_fallback_path_uses_revise_score(self):
        """The duet_composer fallback (gate-failed) path calls revise_score
        instead of raw score_from_mood, so the piece is critiqued before playback."""
        # We can't run the full duet_composer without OSC/audio, so we verify
        # the import wiring: revise_score is importable from the composer module
        # and the fallback code path references it.
        import importlib

        spec = importlib.util.find_spec("duet_composer")
        if spec is None:
            # Try the tools path
            sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools"))
            spec = importlib.util.find_spec("duet_composer")

        assert spec is not None, "duet_composer module not found"
        source_path = spec.origin
        assert source_path is not None

        with open(source_path) as f:
            source = f.read()

        # Verify revise_score is imported (standalone or alongside other imports)
        assert "from senseweave.self_critique import revise_score" in source, (
            "duet_composer does not import revise_score from self_critique"
        )
        # Verify the fallback path uses revise_score, not bare score_from_mood
        # The fallback block (gate not approved) should call revise_score
        assert "revision = revise_score(" in source, (
            "duet_composer fallback path does not call revise_score"
        )
        assert "score = revision.final_score" in source, (
            "duet_composer fallback path does not use revision.final_score"
        )

    def test_revision_result_selected_from_two_pass(self):
        """With strict thresholds, a revision attempt is made and the final
        score is selected from the two-pass result (original or revised)."""
        mood = {"energy": 0.5, "valence": 0.5, "arousal": 0.5}
        # Force a revision by using impossibly strict thresholds
        result = revise_score(
            mood,
            song_num=3,
            family="drift",
            cadence_state="occupied_day",
            thresholds={
                "development_score": ("min", 0.99),
            },
        )
        # A revision was attempted
        assert result.revised_score is not None, "No revision was attempted for failing metrics"
        assert result.revised_metrics is not None
        # The final score is one of the two candidates
        final = result.final_score
        assert final is result.original_score or final is result.revised_score
        # If revision was used, at least one metric improved
        if result.revision_used:
            assert len(result.improved_metrics) >= 1
            assert final is result.revised_score
        else:
            assert final is result.original_score
