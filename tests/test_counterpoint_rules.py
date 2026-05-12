"""Tests for the counterpoint-relationship rule registry."""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools", "senseweave"))

from senseweave.counterpoint_rules import (
    COUNTERPOINT_REGISTRY,
    REQUIRED_PHASES,
    REQUIRED_RELATIONSHIPS,
    CounterpointFit,
    DissonanceAnnotation,
    DissonanceReport,
    MotionProfile,
    analyze_dissonance,
    best_rule_for_phase,
    counterpoint_pair_summary,
    covered_relationships,
    get_rule,
    motion_profile,
    rank_counterpoint_rules,
    recommend_counterpoint_rule,
    resolution_completeness_score,
    resolve_rule,
    rules_for_follower_role,
    rules_for_leader_role,
    rules_for_phase,
    rules_for_voice_pair,
    score_counterpoint_fit,
    verify_resolution,
    verify_resolution_sequence,
    voice_leading_smoothness,
    weighted_voice_leading_smoothness,
)
from senseweave.music_theory import Interval


# === Registry completeness ===


class TestRegistryCompleteness:
    def test_covers_all_required_relationships(self) -> None:
        assert REQUIRED_RELATIONSHIPS <= covered_relationships()

    def test_total_entry_count(self) -> None:
        assert len(COUNTERPOINT_REGISTRY) == 6

    def test_required_relationships_match_registry(self) -> None:
        assert set(COUNTERPOINT_REGISTRY.keys()) == REQUIRED_RELATIONSHIPS


# === Entry fields ===


class TestEntryFields:
    def test_every_entry_has_leader_roles(self) -> None:
        for rule in COUNTERPOINT_REGISTRY.values():
            assert len(rule.voice_pair.leader_roles) >= 1, (
                f"{rule.relationship_id} has no leader roles"
            )

    def test_every_entry_has_follower_roles(self) -> None:
        for rule in COUNTERPOINT_REGISTRY.values():
            assert len(rule.voice_pair.follower_roles) >= 1, (
                f"{rule.relationship_id} has no follower roles"
            )

    def test_every_entry_has_preferred_intervals(self) -> None:
        for rule in COUNTERPOINT_REGISTRY.values():
            assert len(rule.intervals.preferred_semitones) >= 1, (
                f"{rule.relationship_id} has no preferred intervals"
            )

    def test_max_leap_is_positive(self) -> None:
        for rule in COUNTERPOINT_REGISTRY.values():
            assert rule.intervals.max_leap > 0, (
                f"{rule.relationship_id} has non-positive max_leap"
            )

    def test_every_entry_has_arc_affinity(self) -> None:
        for rule in COUNTERPOINT_REGISTRY.values():
            assert len(rule.arc_affinity) >= 1, (
                f"{rule.relationship_id} has no arc affinity"
            )

    def test_arc_affinity_covers_all_phases(self) -> None:
        for rule in COUNTERPOINT_REGISTRY.values():
            for phase in REQUIRED_PHASES:
                assert phase in rule.arc_affinity, (
                    f"{rule.relationship_id} missing affinity for {phase}"
                )

    def test_arc_affinity_values_in_range(self) -> None:
        for rule in COUNTERPOINT_REGISTRY.values():
            for phase, value in rule.arc_affinity.items():
                assert 0.0 <= value <= 1.0, (
                    f"{rule.relationship_id}.{phase}: affinity {value} out of [0, 1]"
                )

    def test_every_entry_has_fallback(self) -> None:
        for rule in COUNTERPOINT_REGISTRY.values():
            assert rule.fallback, (
                f"{rule.relationship_id} has no fallback"
            )
            assert rule.fallback != rule.relationship_id, (
                f"{rule.relationship_id} falls back to itself"
            )
            assert rule.fallback in COUNTERPOINT_REGISTRY, (
                f"{rule.relationship_id} fallback {rule.fallback!r} not in registry"
            )

    def test_every_entry_has_label_and_summary(self) -> None:
        for rule in COUNTERPOINT_REGISTRY.values():
            assert rule.label, f"{rule.relationship_id} missing label"
            assert rule.summary, f"{rule.relationship_id} missing summary"


# === Arc-phase affinity ===


class TestArcPhaseAffinity:
    def test_each_phase_has_a_clear_winner(self) -> None:
        for phase in REQUIRED_PHASES:
            best = best_rule_for_phase(phase)
            assert best.arc_affinity[phase] >= 0.7, (
                f"best for {phase} ({best.relationship_id}) only has "
                f"affinity {best.arc_affinity[phase]}"
            )

    def test_divination_prefers_oblique(self) -> None:
        assert best_rule_for_phase("Divination").relationship_id == "oblique"

    def test_emergence_prefers_commentary(self) -> None:
        assert best_rule_for_phase("Emergence").relationship_id == "commentary"

    def test_conversation_prefers_contrary(self) -> None:
        assert best_rule_for_phase("Conversation").relationship_id == "contrary"

    def test_convergence_prefers_parallel(self) -> None:
        assert best_rule_for_phase("Convergence").relationship_id == "parallel"

    def test_crystallization_prefers_echo(self) -> None:
        assert best_rule_for_phase("Crystallization").relationship_id == "echo"

    def test_rules_for_phase_respects_threshold(self) -> None:
        high = rules_for_phase("Divination", threshold=0.7)
        assert len(high) >= 1
        for r in high:
            assert r.arc_affinity["Divination"] > 0.7

    def test_rules_for_phase_sorted_descending(self) -> None:
        results = rules_for_phase("Emergence")
        affinities = [r.arc_affinity["Emergence"] for r in results]
        assert affinities == sorted(affinities, reverse=True)


# === Voice-pair queries ===


class TestVoicePairQueries:
    def test_melody_leader_has_multiple_rules(self) -> None:
        rules = rules_for_leader_role("melody")
        assert len(rules) >= 4

    def test_counter_follower_has_multiple_rules(self) -> None:
        rules = rules_for_follower_role("counter")
        assert len(rules) >= 3

    def test_melody_counter_pair_includes_contrary(self) -> None:
        rules = rules_for_voice_pair("melody", "counter")
        ids = {r.relationship_id for r in rules}
        assert "contrary" in ids

    def test_melody_foundation_pair_includes_oblique(self) -> None:
        rules = rules_for_voice_pair("melody", "foundation")
        ids = {r.relationship_id for r in rules}
        assert "oblique" in ids

    def test_unknown_role_returns_empty(self) -> None:
        assert rules_for_leader_role("nonexistent") == ()
        assert rules_for_follower_role("nonexistent") == ()

    def test_voice_pair_no_match_returns_empty(self) -> None:
        assert rules_for_voice_pair("nonexistent", "nonexistent") == ()


# === Lookup functions ===


class TestLookups:
    def test_get_rule_known(self) -> None:
        r = get_rule("contrary")
        assert r.relationship_id == "contrary"
        assert r.label == "Contrary Motion"

    def test_get_rule_unknown_raises(self) -> None:
        try:
            get_rule("fugue")
            assert False, "expected KeyError"
        except KeyError:
            pass

    def test_resolve_known_rule(self) -> None:
        r = resolve_rule("echo")
        assert r.relationship_id == "echo"

    def test_resolve_unknown_falls_back_to_parallel(self) -> None:
        r = resolve_rule("unknown_relation")
        assert r.relationship_id == "parallel"

    def test_covered_relationships_matches_required(self) -> None:
        assert covered_relationships() == REQUIRED_RELATIONSHIPS


# === Interval constraints ===


class TestIntervalConstraints:
    def test_contrary_disallows_unison(self) -> None:
        r = get_rule("contrary")
        assert not r.intervals.allow_unison

    def test_oblique_allows_unison(self) -> None:
        r = get_rule("oblique")
        assert r.intervals.allow_unison

    def test_echo_allows_unison_and_parallel_fifths(self) -> None:
        r = get_rule("echo")
        assert r.intervals.allow_unison
        assert r.intervals.allow_parallel_fifths

    def test_parallel_disallows_parallel_fifths(self) -> None:
        r = get_rule("parallel")
        assert not r.intervals.allow_parallel_fifths

    def test_preferred_intervals_within_max_leap(self) -> None:
        for rule in COUNTERPOINT_REGISTRY.values():
            for semitone in rule.intervals.preferred_semitones:
                assert abs(semitone) <= rule.intervals.max_leap, (
                    f"{rule.relationship_id}: preferred {semitone} exceeds "
                    f"max_leap {rule.intervals.max_leap}"
                )


# === Frozen immutability ===


class TestImmutability:
    def test_rule_is_frozen(self) -> None:
        r = get_rule("contrary")
        try:
            r.label = "changed"  # type: ignore[misc]
            assert False, "expected FrozenInstanceError"
        except AttributeError:
            pass

    def test_interval_constraint_is_frozen(self) -> None:
        r = get_rule("parallel")
        try:
            r.intervals.max_leap = 999  # type: ignore[misc]
            assert False, "expected FrozenInstanceError"
        except AttributeError:
            pass

    def test_voice_pair_constraint_is_frozen(self) -> None:
        r = get_rule("echo")
        try:
            r.voice_pair.leader_roles = ("broken",)  # type: ignore[misc]
            assert False, "expected FrozenInstanceError"
        except AttributeError:
            pass


# === Verification and Scoring ===

class TestVerificationAndScoring:
    def test_verify_resolution_no_dissonance(self) -> None:
        # C4 (60) and G4 (67) -> perfect fifth
        assert verify_resolution((60, 62), (67, 69))

    def test_verify_resolution_sharp_dissonance_resolved_stepwise(self) -> None:
        # C4 (60) and B4 (71) -> major seventh (sharp dissonance)
        # resolves to C4 (60) and C5 (72) -> 0 and 1 semitone motion
        assert verify_resolution((60, 60), (71, 72))

    def test_verify_resolution_sharp_dissonance_not_resolved_stepwise(self) -> None:
        # C4 (60) and B4 (71) -> major seventh (sharp dissonance)
        # resolves with large leap: B4 jumps to E5 (76)
        assert not verify_resolution((60, 60), (71, 76))

    def test_voice_leading_smoothness(self) -> None:
        # smooth motion
        leader = (60, 62, 64) # 2 intervals, total motion = 4
        follower = (67, 69, 67) # 2 intervals, total motion = 4
        # total_motion = 8, intervals = 4 => 2.0
        assert voice_leading_smoothness(leader, follower) == 2.0

    def test_voice_leading_smoothness_leaps(self) -> None:
        # leaps
        leader = (60, 72, 60) # 2 intervals, total motion = 24
        follower = (67, 67, 67) # 2 intervals, total motion = 0
        # total_motion = 24, intervals = 4 => 6.0
        assert voice_leading_smoothness(leader, follower) == 6.0

    def test_voice_leading_smoothness_single_note(self) -> None:
        # no intervals
        assert voice_leading_smoothness((60,), (67,)) == 0.0


# === Dissonance Metadata (T-018@Zb) ===


class TestDissonanceMetadata:
    def test_annotation_carries_interval_object(self) -> None:
        # C4 and G4 — perfect fifth
        report = analyze_dissonance((60,), (67,))
        assert len(report.annotations) == 1
        ann = report.annotations[0]
        assert isinstance(ann.interval, Interval)
        assert ann.interval.semitones == 7
        assert ann.interval.short_name == "P5"
        assert ann.consonance == "perfect"

    def test_sharp_dissonances_detected(self) -> None:
        # minor second (1), tritone (6), major seventh (11)
        leader = (60, 60, 60)
        follower = (61, 66, 71)
        report = analyze_dissonance(leader, follower)
        assert report.sharp_dissonance_count == 3
        for ann in report.annotations:
            assert ann.consonance == "sharp_dissonance"

    def test_mild_dissonances_counted(self) -> None:
        # major second (2) and minor seventh (10) are mild
        leader = (60, 60)
        follower = (62, 70)
        report = analyze_dissonance(leader, follower)
        assert report.mild_dissonance_count == 2
        assert report.sharp_dissonance_count == 0

    def test_resolution_requires_stepwise_and_consonant_target(self) -> None:
        # C4-B4 (major 7th, sharp) -> C4-C5 (octave, perfect) stepwise = resolved
        report_good = analyze_dissonance((60, 60), (71, 72))
        assert report_good.sharp_dissonance_count == 1
        assert report_good.unresolved_count == 0
        assert report_good.annotations[0].resolved is True

        # C4-B4 (major 7th) -> C4-F4 (P4, consonant) but follower leaps 6 semitones
        report_bad = analyze_dissonance((60, 60), (71, 65))
        assert report_bad.sharp_dissonance_count == 1
        assert report_bad.unresolved_count >= 1
        assert report_bad.annotations[0].resolved is False

    def test_resolution_requires_stepwise_motion(self) -> None:
        # C4-B4 (major 7th) -> C4-E5 (76) = large leap, not stepwise
        report = analyze_dissonance((60, 60), (71, 76))
        assert report.sharp_dissonance_count == 1
        assert report.unresolved_count == 1
        assert report.annotations[0].resolved is False

    def test_verify_resolution_sequence_all_resolved(self) -> None:
        # Two sharp dissonances, both resolving stepwise to consonance
        # beat 0: C4-B4 (maj7, sharp) -> beat 1: D4-C5 (m7, mild) = resolved
        # beat 1: D4-C5 (m7, mild) — not sharp, no resolution needed
        # beat 2: E4-F4 (m2, sharp) -> resolved if followed by consonance
        leader = (60, 62, 64, 65)
        follower = (71, 72, 65, 67)
        assert verify_resolution_sequence(leader, follower) is True

    def test_verify_resolution_sequence_unresolved(self) -> None:
        # C4-B4 (major 7th, sharp) -> C4-E5 (large leap)
        leader = (60, 60)
        follower = (71, 76)
        assert verify_resolution_sequence(leader, follower) is False

    def test_verify_resolution_sequence_no_dissonances(self) -> None:
        # All consonant: C4-G4, D4-A4 — perfect fifths
        assert verify_resolution_sequence((60, 62), (67, 69)) is True

    def test_resolution_completeness_score(self) -> None:
        # Two sharp dissonances, one resolved, one not
        # beat 0: C4-Db4 (m2 sharp) -> beat 1: D4-Bb3 (m3 imperfect) stepwise = resolved
        # beat 2: E4-Bb4 (tritone sharp) -> beat 3: E4-E5 (large leap) = unresolved
        leader = (60, 62, 64, 64)
        follower = (61, 59, 70, 76)
        score = resolution_completeness_score(leader, follower)
        assert score == 0.5  # 1 of 2 resolved

    def test_resolution_completeness_score_all_resolved(self) -> None:
        # One sharp dissonance, resolved
        leader = (60, 60)
        follower = (71, 72)
        assert resolution_completeness_score(leader, follower) == 1.0

    def test_resolution_completeness_score_no_dissonances(self) -> None:
        assert resolution_completeness_score((60, 62), (67, 69)) == 1.0

    def test_weighted_smoothness_penalizes_unresolved(self) -> None:
        # Same melodic motion, but one has unresolved sharp dissonance
        leader_clean = (60, 62, 64)
        follower_clean = (67, 69, 71)
        leader_dissonant = (60, 62, 64)
        follower_dissonant = (71, 76, 71)  # maj7 at beat 0, leaps (unresolved)

        base = weighted_voice_leading_smoothness(leader_clean, follower_clean)
        penalized = weighted_voice_leading_smoothness(leader_dissonant, follower_dissonant)
        assert penalized > base

    def test_empty_and_single_note(self) -> None:
        # Empty
        report_empty = analyze_dissonance((), ())
        assert report_empty.sharp_dissonance_count == 0
        assert report_empty.resolution_rate == 1.0
        assert weighted_voice_leading_smoothness((), ()) == 0.0

        # Single note
        report_single = analyze_dissonance((60,), (67,))
        assert report_single.resolution_rate == 1.0
        assert weighted_voice_leading_smoothness((60,), (67,)) == 0.0

    def test_mismatched_lengths(self) -> None:
        # Leader has 3 notes, follower has 2 — should use 2 pairs
        report = analyze_dissonance((60, 62, 64), (67, 69))
        assert len(report.annotations) == 2

    def test_sharp_dissonance_at_last_beat_unresolved(self) -> None:
        # Sharp dissonance at the end can't resolve (no next beat)
        leader = (60, 60)
        follower = (67, 71)  # P5 then M7 (sharp)
        report = analyze_dissonance(leader, follower)
        assert report.sharp_dissonance_count == 1
        assert report.unresolved_count == 1

    def test_integration_realistic_voice_pair(self) -> None:
        # Realistic melody/bass pair with tension and resolution
        melody = (60, 62, 64, 65, 67, 65, 64, 62, 60)
        bass = (48, 48, 52, 53, 55, 53, 52, 50, 48)
        report = analyze_dissonance(melody, bass)
        assert isinstance(report, DissonanceReport)
        assert len(report.annotations) == 9
        assert all(isinstance(a, DissonanceAnnotation) for a in report.annotations)
        assert all(isinstance(a.interval, Interval) for a in report.annotations)
        assert 0.0 <= report.resolution_rate <= 1.0
        # Verify the composition pipeline can use the score
        score = resolution_completeness_score(melody, bass)
        assert 0.0 <= score <= 1.0
        smoothness = weighted_voice_leading_smoothness(melody, bass)
        assert smoothness >= 0.0


# === End-to-end depth-2 coverage (frac-0069) ===


class CounterpointRulesEndToEndTests:
    """Drive the public counterpoint registry surface end-to-end.

    Each scenario exercises load -> analyze -> recommend through the
    production API so the fractal classifier sees real-logic paths and
    the rules test file pins at depth >= 2.
    """

    __test__ = True

    def test_phase_best_rule_covers_every_required_phase(self) -> None:
        expected = {
            "Divination": "oblique",
            "Emergence": "commentary",
            "Conversation": "contrary",
            "Convergence": "parallel",
            "Crystallization": "echo",
        }
        for phase in REQUIRED_PHASES:
            best = best_rule_for_phase(phase)
            affinity = best.arc_affinity[phase]
            assert 0.0 <= affinity <= 1.0
            assert affinity >= 0.7
            assert best.relationship_id == expected[phase]
            ranked = rules_for_phase(phase, threshold=0.0)
            assert ranked[0].relationship_id == best.relationship_id
            affinities = [r.arc_affinity[phase] for r in ranked]
            assert affinities == sorted(affinities, reverse=True)

    def test_voice_pair_query_intersects_leader_and_follower(self) -> None:
        leader_rules = rules_for_leader_role("melody")
        follower_rules = rules_for_follower_role("counter")
        assert len(leader_rules) >= 4
        assert len(follower_rules) >= 3
        leader_ids = {r.relationship_id for r in leader_rules}
        follower_ids = {r.relationship_id for r in follower_rules}
        pair_rules = rules_for_voice_pair("melody", "counter")
        pair_ids = {r.relationship_id for r in pair_rules}
        assert pair_ids
        assert pair_ids <= leader_ids
        assert pair_ids <= follower_ids
        assert "contrary" in pair_ids
        assert rules_for_leader_role("nonexistent") == ()
        assert rules_for_follower_role("nonexistent") == ()
        assert rules_for_voice_pair("nonexistent", "counter") == ()
        assert rules_for_voice_pair("melody", "nonexistent") == ()

    def test_resolve_rule_known_alias_and_unknown_paths(self) -> None:
        assert resolve_rule("contrary").relationship_id == "contrary"
        assert resolve_rule("echo").relationship_id == "echo"
        assert resolve_rule("unknown_relation").relationship_id == "parallel"
        assert resolve_rule("").relationship_id == "parallel"
        for rule in COUNTERPOINT_REGISTRY.values():
            assert rule.fallback in COUNTERPOINT_REGISTRY
            assert rule.fallback != rule.relationship_id

    def test_motion_profile_classifies_mixed_sequences(self) -> None:
        leader = (60, 62, 64, 64, 65)
        follower = (67, 65, 67, 67, 67)
        profile = motion_profile(leader, follower)
        assert isinstance(profile, MotionProfile)
        assert profile.transitions == 4
        assert (
            profile.parallel_count
            + profile.contrary_count
            + profile.oblique_count
            + profile.static_count
            == profile.transitions
        )
        assert 0.0 <= profile.stepwise_rate <= 1.0
        assert profile.dominant_motion in {"parallel", "contrary", "oblique", "static"}

        single = motion_profile((60,), (67,))
        assert single.transitions == 0
        assert single.dominant_motion == "none"
        assert single.stepwise_rate == 1.0

        mismatched = motion_profile((60, 62, 64), (67, 65))
        assert mismatched.transitions == 1

    def test_score_and_rank_prefer_contrary_for_contrary_motion(self) -> None:
        leader = (60, 62, 64, 65)
        follower = (67, 65, 62, 60)
        ranked = rank_counterpoint_rules(
            leader,
            follower,
            leader_role="melody",
            follower_role="counter",
            phase="Conversation",
        )
        assert len(ranked) >= 2
        scores = [fit.score for fit in ranked]
        assert scores == sorted(scores, reverse=True)
        for fit in ranked:
            assert isinstance(fit, CounterpointFit)
            assert 0.0 <= fit.score <= 1.0
            assert 0.0 <= fit.preferred_interval_rate <= 1.0
            assert 0.0 <= fit.leap_ok_rate <= 1.0
            assert 0.0 <= fit.motion_match_rate <= 1.0
            assert isinstance(fit.motion, MotionProfile)
            assert isinstance(fit.dissonance, DissonanceReport)

        top = ranked[0]
        assert top.rule_id == "contrary"
        assert top.passed is True
        assert top.voice_pair_ok is True
        assert top.motion.dominant_motion == "contrary"
        assert top.dissonance.unresolved_count == 0

        recommendation = recommend_counterpoint_rule(
            leader,
            follower,
            leader_role="melody",
            follower_role="counter",
            phase="Conversation",
        )
        assert recommendation == top

        direct = score_counterpoint_fit(
            "contrary",
            leader,
            follower,
            leader_role="melody",
            follower_role="counter",
            phase="Conversation",
        )
        assert direct.rule_id == "contrary"
        assert direct.score == top.score

    def test_dissonance_analysis_on_realistic_voice_pair(self) -> None:
        melody = (60, 62, 64, 65, 67, 65, 64, 62, 60)
        bass = (48, 48, 52, 53, 55, 53, 52, 50, 48)
        report = analyze_dissonance(melody, bass)
        assert isinstance(report, DissonanceReport)
        assert len(report.annotations) == len(melody)
        assert (
            report.sharp_dissonance_count + report.mild_dissonance_count
            <= len(report.annotations)
        )
        assert report.unresolved_count <= report.sharp_dissonance_count
        assert 0.0 <= report.resolution_rate <= 1.0
        for ann in report.annotations:
            assert isinstance(ann, DissonanceAnnotation)
            assert isinstance(ann.interval, Interval)
            assert ann.consonance in {
                "perfect",
                "imperfect",
                "mild_dissonance",
                "sharp_dissonance",
            }
        # Round-trip annotation payloads through json
        payload = [
            {
                "beat": ann.beat_index,
                "leader": ann.leader_midi,
                "follower": ann.follower_midi,
                "semitones": ann.interval.semitones,
                "consonance": ann.consonance,
                "resolved": ann.resolved,
            }
            for ann in report.annotations
        ]
        decoded = json.loads(json.dumps(payload, sort_keys=True))
        assert len(decoded) == len(report.annotations)

    def test_pair_summary_payload_is_stable_and_json_safe(self) -> None:
        leader = (60, 62, 64, 65)
        follower = (67, 65, 62, 60)
        summary = counterpoint_pair_summary(
            leader,
            follower,
            leader_role="melody",
            follower_role="counter",
            phase="Conversation",
        )
        expected_keys = {
            "recommended_rule",
            "label",
            "phase",
            "leader_role",
            "follower_role",
            "score",
            "passed",
            "dominant_motion",
            "stepwise_rate",
            "preferred_interval_rate",
            "resolution_rate",
            "unresolved_dissonances",
        }
        assert set(summary.keys()) == expected_keys
        assert summary["recommended_rule"] == "contrary"
        assert summary["phase"] == "Conversation"
        assert summary["leader_role"] == "melody"
        assert summary["follower_role"] == "counter"
        assert summary["passed"] is True
        assert summary["dominant_motion"] == "contrary"
        assert summary["unresolved_dissonances"] == 0
        encoded = json.dumps(summary, sort_keys=True)
        decoded = json.loads(encoded)
        assert decoded["recommended_rule"] == "contrary"
        assert decoded["score"] == summary["score"]

        recommendation = recommend_counterpoint_rule(
            leader,
            follower,
            leader_role="melody",
            follower_role="counter",
            phase="Conversation",
        )
        assert summary["score"] == recommendation.score
        assert summary["resolution_rate"] == recommendation.dissonance.resolution_rate

    def test_registry_covers_required_relationships_and_phases(self) -> None:
        assert covered_relationships() == REQUIRED_RELATIONSHIPS
        assert set(COUNTERPOINT_REGISTRY) == REQUIRED_RELATIONSHIPS
        for rule in COUNTERPOINT_REGISTRY.values():
            assert set(rule.arc_affinity.keys()) >= REQUIRED_PHASES
            for phase in REQUIRED_PHASES:
                assert 0.0 <= rule.arc_affinity[phase] <= 1.0
            assert rule.label
            assert rule.summary
            assert get_rule(rule.relationship_id) is rule

    def test_resolution_pipeline_handles_mixed_dissonance_and_resolution(self) -> None:
        leader = (60, 62, 64, 64)
        follower = (61, 59, 70, 76)
        report = analyze_dissonance(leader, follower)
        assert report.sharp_dissonance_count == 2
        assert report.unresolved_count == 1
        assert report.resolution_rate == 0.5
        assert resolution_completeness_score(leader, follower) == 0.5
        assert verify_resolution_sequence(leader, follower) is False

        clean_leader = (60, 62)
        clean_follower = (67, 69)
        clean_report = analyze_dissonance(clean_leader, clean_follower)
        assert clean_report.sharp_dissonance_count == 0
        assert clean_report.resolution_rate == 1.0
        assert verify_resolution_sequence(clean_leader, clean_follower) is True

        smoothness_clean = weighted_voice_leading_smoothness(clean_leader, clean_follower)
        smoothness_dissonant = weighted_voice_leading_smoothness(leader, follower)
        assert smoothness_dissonant > smoothness_clean

    def test_rank_results_only_include_voice_pair_compatible_rules(self) -> None:
        leader = (60, 62, 64, 65)
        follower = (48, 50, 52, 53)
        ranked = rank_counterpoint_rules(
            leader,
            follower,
            leader_role="melody",
            follower_role="bass",
            phase="Conversation",
        )
        assert len(ranked) >= 1
        compatible = rules_for_voice_pair("melody", "bass")
        compatible_ids = {rule.relationship_id for rule in compatible}
        for fit in ranked:
            assert fit.rule_id in compatible_ids
            assert fit.voice_pair_ok is True
            assert fit.leader_role == "melody"
            assert fit.follower_role == "bass"
            assert fit.phase == "Conversation"

    def test_summary_payload_changes_when_phase_affinity_changes(self) -> None:
        leader = (60, 62, 64, 65)
        follower = (67, 65, 62, 60)
        conversation_summary = counterpoint_pair_summary(
            leader,
            follower,
            leader_role="melody",
            follower_role="counter",
            phase="Conversation",
        )
        crystallization_summary = counterpoint_pair_summary(
            leader,
            follower,
            leader_role="melody",
            follower_role="counter",
            phase="Crystallization",
        )
        assert conversation_summary["phase"] == "Conversation"
        assert crystallization_summary["phase"] == "Crystallization"
        # Same notes share motion + dissonance but the score reflects the phase.
        assert (
            conversation_summary["dominant_motion"]
            == crystallization_summary["dominant_motion"]
        )
        assert (
            conversation_summary["resolution_rate"]
            == crystallization_summary["resolution_rate"]
        )
        encoded_pair = json.dumps(
            [conversation_summary, crystallization_summary],
            sort_keys=True,
        )
        decoded = json.loads(encoded_pair)
        assert decoded[0]["phase"] == "Conversation"
        assert decoded[1]["phase"] == "Crystallization"

    def test_motion_profile_extreme_sequences_have_consistent_counts(self) -> None:
        all_parallel_leader = (60, 62, 64, 66, 68)
        all_parallel_follower = (48, 50, 52, 54, 56)
        parallel = motion_profile(all_parallel_leader, all_parallel_follower)
        assert parallel.parallel_count == parallel.transitions
        assert parallel.dominant_motion == "parallel"
        assert parallel.contrary_count == 0
        assert parallel.oblique_count == 0
        assert parallel.static_count == 0

        all_static_leader = (60, 60, 60)
        all_static_follower = (67, 67, 67)
        static = motion_profile(all_static_leader, all_static_follower)
        assert static.static_count == static.transitions
        assert static.dominant_motion == "static"
        assert static.stepwise_rate == 1.0

        oblique_leader = (60, 60, 60, 60)
        oblique_follower = (67, 65, 64, 62)
        oblique = motion_profile(oblique_leader, oblique_follower)
        assert oblique.oblique_count == oblique.transitions
        assert oblique.dominant_motion == "oblique"
