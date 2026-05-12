"""Tests for the core SenseWeave render ablation engine."""
from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools"))

from senseweave.render.ablation import (
    AblationCase,
    ablate,
    build_ablation_cases,
    filter_active_rules,
    rule_identifiers,
    run_ablation_suite,
    summarize_ablation_suite,
)


@dataclass(frozen=True)
class DummyRule:
    rule_id: str


def _render_trace(
    score: str,
    *,
    seeds: Mapping[str, int] | None,
    rules: Sequence[DummyRule],
) -> dict[str, Any]:
    rule_ids = tuple(rule.rule_id for rule in rules)
    return {
        "score": score,
        "seeds": dict(seeds or {}),
        "rule_ids": rule_ids,
        "events": tuple(f"{score}:{rule_id}" for rule_id in rule_ids) or (f"{score}:baseline",),
    }


class TestAblate:
    def test_single_rule_ablation_filters_rule_and_rerenders(self) -> None:
        rules = (
            DummyRule("metric_accent"),
            DummyRule("phrase_arch"),
            DummyRule("microtiming"),
        )

        rendered = ablate(
            "score-a",
            {"composition": 11, "interpretation": 23},
            disabled_rules={"phrase_arch"},
            active_rules=rules,
            renderer=_render_trace,
        )

        assert rendered == {
            "score": "score-a",
            "seeds": {"composition": 11, "interpretation": 23},
            "rule_ids": ("metric_accent", "microtiming"),
            "events": ("score-a:metric_accent", "score-a:microtiming"),
        }

    def test_pair_ablation_preserves_remaining_rule_order(self) -> None:
        rules = (
            DummyRule("metric_accent"),
            DummyRule("phrase_arch"),
            DummyRule("agogic"),
            DummyRule("duration_contrast"),
        )

        rendered = ablate(
            "score-b",
            {"interpretation": 99},
            disabled_rules={"phrase_arch", "duration_contrast"},
            active_rules=rules,
            renderer=_render_trace,
        )

        assert rendered["rule_ids"] == ("metric_accent", "agogic")
        assert rendered["events"] == ("score-b:metric_accent", "score-b:agogic")

    def test_all_rules_off_matches_baseline_render(self) -> None:
        rules = (
            DummyRule("metric_accent"),
            DummyRule("phrase_arch"),
            DummyRule("microtiming"),
        )

        baseline = _render_trace("score-c", seeds={"interpretation": 7}, rules=())
        rendered = ablate(
            "score-c",
            {"interpretation": 7},
            disabled_rules={rule.rule_id for rule in rules},
            active_rules=rules,
            renderer=_render_trace,
        )

        assert rendered == baseline

    def test_unknown_disabled_rule_id_raises(self) -> None:
        rules = (DummyRule("metric_accent"), DummyRule("phrase_arch"))

        with pytest.raises(ValueError, match="unknown disabled rule id"):
            ablate(
                "score-d",
                {"interpretation": 3},
                disabled_rules={"missing_rule"},
                active_rules=rules,
                renderer=_render_trace,
            )


class TestAblationSuite:
    def test_build_ablation_cases_defaults_to_single_rule_plan(self) -> None:
        rules = (
            DummyRule("metric_accent"),
            DummyRule("phrase_arch"),
            DummyRule("microtiming"),
        )

        cases = build_ablation_cases(rules)

        assert cases == (
            AblationCase(
                disabled_rules=("metric_accent",),
                remaining_rule_ids=("phrase_arch", "microtiming"),
                removed_rule_ids=("metric_accent",),
            ),
            AblationCase(
                disabled_rules=("phrase_arch",),
                remaining_rule_ids=("metric_accent", "microtiming"),
                removed_rule_ids=("phrase_arch",),
            ),
            AblationCase(
                disabled_rules=("microtiming",),
                remaining_rule_ids=("metric_accent", "phrase_arch"),
                removed_rule_ids=("microtiming",),
            ),
        )

    def test_build_ablation_cases_accepts_custom_pairs(self) -> None:
        rules = (
            DummyRule("metric_accent"),
            DummyRule("phrase_arch"),
            DummyRule("agogic"),
            DummyRule("duration_contrast"),
        )

        cases = build_ablation_cases(
            rules,
            disabled_rule_sets=(
                ("phrase_arch", "duration_contrast"),
                ("metric_accent",),
            ),
        )

        assert cases == (
            AblationCase(
                disabled_rules=("phrase_arch", "duration_contrast"),
                remaining_rule_ids=("metric_accent", "agogic"),
                removed_rule_ids=("phrase_arch", "duration_contrast"),
            ),
            AblationCase(
                disabled_rules=("metric_accent",),
                remaining_rule_ids=("phrase_arch", "agogic", "duration_contrast"),
                removed_rule_ids=("metric_accent",),
            ),
        )

    def test_build_ablation_cases_rejects_unknown_rule(self) -> None:
        rules = (DummyRule("metric_accent"), DummyRule("phrase_arch"))

        with pytest.raises(ValueError, match="unknown disabled rule id"):
            build_ablation_cases(rules, disabled_rule_sets=(("missing_rule",),))

    def test_run_ablation_suite_returns_baseline_and_results(self) -> None:
        rules = (
            DummyRule("metric_accent"),
            DummyRule("phrase_arch"),
            DummyRule("microtiming"),
        )

        suite = run_ablation_suite(
            "score-e",
            {"interpretation": 5},
            active_rules=rules,
            renderer=_render_trace,
            disabled_rule_sets=(("phrase_arch",), ("microtiming",)),
        )

        assert suite.rule_ids == ("metric_accent", "phrase_arch", "microtiming")
        assert suite.baseline["rule_ids"] == (
            "metric_accent",
            "phrase_arch",
            "microtiming",
        )
        assert tuple(result.disabled_rules for result in suite.results) == (
            ("phrase_arch",),
            ("microtiming",),
        )
        assert suite.results[0].remaining_rule_ids == (
            "metric_accent",
            "microtiming",
        )
        assert suite.results[0].rendered["events"] == (
            "score-e:metric_accent",
            "score-e:microtiming",
        )
        assert suite.results[0].changed is True
        assert (
            suite.results[0].summary
            == "disabled phrase_arch; remaining metric_accent,microtiming; changed"
        )

    def test_summarize_ablation_suite_returns_json_safe_counts(self) -> None:
        rules = (DummyRule("metric_accent"), DummyRule("phrase_arch"))
        suite = run_ablation_suite(
            "score-f",
            {"composition": 13},
            active_rules=rules,
            renderer=_render_trace,
        )

        summary = summarize_ablation_suite(suite)

        assert summary == {
            "rule_ids": ["metric_accent", "phrase_arch"],
            "case_count": 2,
            "changed_count": 2,
            "unchanged_count": 0,
            "cases": [
                {
                    "disabled_rules": ["metric_accent"],
                    "remaining_rule_ids": ["phrase_arch"],
                    "removed_rule_ids": ["metric_accent"],
                    "changed": True,
                    "summary": "disabled metric_accent; remaining phrase_arch; changed",
                },
                {
                    "disabled_rules": ["phrase_arch"],
                    "remaining_rule_ids": ["metric_accent"],
                    "removed_rule_ids": ["phrase_arch"],
                    "changed": True,
                    "summary": "disabled phrase_arch; remaining metric_accent; changed",
                },
            ],
        }


def test_render_ablation_reaches_depth_two() -> None:
    from sdp.fractal import classify_depth

    result = classify_depth("my-claw/tools/senseweave/render/ablation.py")
    assert result.depth >= 2, result.reason


class RenderAblationEndToEndTests:
    """End-to-end render-ablation lifecycle across the public surface."""

    __test__ = True

    def test_baseline_to_summary_lifecycle_is_json_safe(self) -> None:
        rules = (
            DummyRule("metric_accent"),
            DummyRule("phrase_arch"),
            DummyRule("microtiming"),
        )
        score = "score-e2e"
        seeds = {"composition": 17, "interpretation": 41}

        rule_ids = rule_identifiers(rules)
        filtered = filter_active_rules(rules, ("phrase_arch",))
        single_disabled = ablate(
            score,
            seeds,
            disabled_rules={"phrase_arch"},
            active_rules=rules,
            renderer=_render_trace,
        )

        default_cases = build_ablation_cases(rules)
        custom_cases = build_ablation_cases(
            rules,
            disabled_rule_sets=(
                ("phrase_arch",),
                ("metric_accent", "microtiming"),
            ),
        )

        suite = run_ablation_suite(
            score,
            seeds,
            active_rules=rules,
            renderer=_render_trace,
            disabled_rule_sets=(
                ("phrase_arch",),
                ("metric_accent", "microtiming"),
            ),
        )
        summary = summarize_ablation_suite(suite)

        diagnostic = {
            "rule_ids": list(rule_ids),
            "filtered_rule_ids": [rule.rule_id for rule in filtered],
            "single_disabled_events": list(single_disabled["events"]),
            "default_cases": [
                {
                    "disabled_rules": list(case.disabled_rules),
                    "remaining_rule_ids": list(case.remaining_rule_ids),
                    "removed_rule_ids": list(case.removed_rule_ids),
                }
                for case in default_cases
            ],
            "custom_cases": [
                {
                    "disabled_rules": list(case.disabled_rules),
                    "remaining_rule_ids": list(case.remaining_rule_ids),
                    "removed_rule_ids": list(case.removed_rule_ids),
                }
                for case in custom_cases
            ],
            "baseline_events": list(suite.baseline["events"]),
            "summary": summary,
        }
        restored = json.loads(json.dumps(diagnostic, sort_keys=True))

        assert rule_ids == ("metric_accent", "phrase_arch", "microtiming")
        assert tuple(rule.rule_id for rule in filtered) == (
            "metric_accent",
            "microtiming",
        )
        assert single_disabled["events"] == (
            "score-e2e:metric_accent",
            "score-e2e:microtiming",
        )
        assert tuple(case.disabled_rules for case in default_cases) == (
            ("metric_accent",),
            ("phrase_arch",),
            ("microtiming",),
        )
        assert custom_cases[0].remaining_rule_ids == (
            "metric_accent",
            "microtiming",
        )
        assert custom_cases[1].remaining_rule_ids == ("phrase_arch",)
        assert suite.rule_ids == rule_ids
        assert suite.baseline["events"] == (
            "score-e2e:metric_accent",
            "score-e2e:phrase_arch",
            "score-e2e:microtiming",
        )
        assert suite.results[0].changed is True
        assert suite.results[0].summary == (
            "disabled phrase_arch; remaining metric_accent,microtiming; changed"
        )
        assert suite.results[1].rendered["events"] == ("score-e2e:phrase_arch",)
        assert suite.results[1].summary == (
            "disabled metric_accent,microtiming; remaining phrase_arch; changed"
        )
        assert summary["rule_ids"] == [
            "metric_accent",
            "phrase_arch",
            "microtiming",
        ]
        assert summary["case_count"] == 2
        assert summary["changed_count"] == 2
        assert summary["unchanged_count"] == 0
        assert restored["summary"] == summary
        assert restored["baseline_events"] == [
            "score-e2e:metric_accent",
            "score-e2e:phrase_arch",
            "score-e2e:microtiming",
        ]
        assert restored["default_cases"][1] == {
            "disabled_rules": ["phrase_arch"],
            "remaining_rule_ids": ["metric_accent", "microtiming"],
            "removed_rule_ids": ["phrase_arch"],
        }

    def test_full_pipeline_final_rendered_artifact_shape_and_content(self) -> None:
        rules = (
            DummyRule("metric_accent"),
            DummyRule("phrase_arch"),
            DummyRule("microtiming"),
        )
        score = {"score_id": "score-artifact", "title": "Artifact check"}
        seeds = {"composition": 17, "interpretation": 41}

        def artifact_renderer(
            score: Mapping[str, object],
            *,
            seeds: Mapping[str, int] | None,
            rules: Sequence[DummyRule],
        ) -> dict[str, Any]:
            active_rule_ids = [rule.rule_id for rule in rules]
            active_rules = set(active_rule_ids)
            score_id = str(score["score_id"])
            seed_signature = "|".join(
                f"{name}={value}"
                for name, value in sorted((seeds or {}).items())
            )
            section_count = 2 if "phrase_arch" in active_rules else 1
            section_ids = ["A", "B"][:section_count]
            duration_beats = 1.0 if "phrase_arch" in active_rules else 4.0
            offset_pattern = (-8, 6) if "microtiming" in active_rules else (0, 0)

            sections = [
                {
                    "section_id": section_id,
                    "duration_beats": 4.0,
                    "rule_ids": active_rule_ids,
                }
                for section_id in section_ids
            ]
            events = [
                {
                    "event_id": f"{score_id}:lead:{index}",
                    "section_id": section_id,
                    "beat": float(index * 2),
                    "duration_beats": duration_beats,
                    "accent": (
                        "strong" if "metric_accent" in active_rules else "plain"
                    ),
                    "timing_offset_ms": offset_pattern[index % len(offset_pattern)],
                    "rule_ids": active_rule_ids,
                }
                for index, section_id in enumerate(section_ids)
            ]
            return {
                "schema_version": "render-artifact/v1",
                "score_id": score_id,
                "seed_signature": seed_signature,
                "active_rule_ids": active_rule_ids,
                "sections": sections,
                "events": events,
                "metadata": {
                    "rule_count": len(active_rule_ids),
                    "has_metric_accent": "metric_accent" in active_rules,
                    "has_phrase_arch": "phrase_arch" in active_rules,
                    "has_microtiming": "microtiming" in active_rules,
                },
            }

        assert rule_identifiers(rules) == (
            "metric_accent",
            "phrase_arch",
            "microtiming",
        )
        filtered = filter_active_rules(rules, ("phrase_arch", "microtiming"))
        assert tuple(rule.rule_id for rule in filtered) == ("metric_accent",)

        expected_final_artifact = {
            "schema_version": "render-artifact/v1",
            "score_id": "score-artifact",
            "seed_signature": "composition=17|interpretation=41",
            "active_rule_ids": ["metric_accent"],
            "sections": [
                {
                    "section_id": "A",
                    "duration_beats": 4.0,
                    "rule_ids": ["metric_accent"],
                }
            ],
            "events": [
                {
                    "event_id": "score-artifact:lead:0",
                    "section_id": "A",
                    "beat": 0.0,
                    "duration_beats": 4.0,
                    "accent": "strong",
                    "timing_offset_ms": 0,
                    "rule_ids": ["metric_accent"],
                }
            ],
            "metadata": {
                "rule_count": 1,
                "has_metric_accent": True,
                "has_phrase_arch": False,
                "has_microtiming": False,
            },
        }
        direct_artifact = ablate(
            score,
            seeds,
            disabled_rules=("phrase_arch", "microtiming"),
            active_rules=rules,
            renderer=artifact_renderer,
        )
        assert direct_artifact == expected_final_artifact

        cases = build_ablation_cases(
            rules,
            disabled_rule_sets=(
                ("phrase_arch",),
                ("phrase_arch", "microtiming"),
            ),
        )
        suite = run_ablation_suite(
            score,
            seeds,
            active_rules=rules,
            renderer=artifact_renderer,
            disabled_rule_sets=tuple(case.disabled_rules for case in cases),
        )
        summary = summarize_ablation_suite(suite)

        final_result = suite.results[-1]
        assert suite.baseline["active_rule_ids"] == [
            "metric_accent",
            "phrase_arch",
            "microtiming",
        ]
        assert suite.baseline["sections"] == [
            {
                "section_id": "A",
                "duration_beats": 4.0,
                "rule_ids": ["metric_accent", "phrase_arch", "microtiming"],
            },
            {
                "section_id": "B",
                "duration_beats": 4.0,
                "rule_ids": ["metric_accent", "phrase_arch", "microtiming"],
            },
        ]
        assert final_result.disabled_rules == ("phrase_arch", "microtiming")
        assert final_result.remaining_rule_ids == ("metric_accent",)
        assert final_result.removed_rule_ids == ("phrase_arch", "microtiming")
        assert final_result.changed is True
        assert final_result.summary == (
            "disabled phrase_arch,microtiming; remaining metric_accent; changed"
        )
        assert final_result.rendered == expected_final_artifact
        assert summary["cases"][-1] == {
            "disabled_rules": ["phrase_arch", "microtiming"],
            "remaining_rule_ids": ["metric_accent"],
            "removed_rule_ids": ["phrase_arch", "microtiming"],
            "changed": True,
            "summary": (
                "disabled phrase_arch,microtiming; remaining metric_accent; changed"
            ),
        }

        restored_artifact = json.loads(
            json.dumps(final_result.rendered, sort_keys=True)
        )
        assert restored_artifact == expected_final_artifact

    def test_default_cases_remove_each_rule_exactly_once(self) -> None:
        rules = (
            DummyRule("metric_accent"),
            DummyRule("phrase_arch"),
            DummyRule("microtiming"),
            DummyRule("agogic"),
        )
        cases = build_ablation_cases(rules)
        seen_disabled: list[str] = []
        for case in cases:
            assert len(case.disabled_rules) == 1
            disabled_id = case.disabled_rules[0]
            seen_disabled.append(disabled_id)
            assert disabled_id not in case.remaining_rule_ids
            assert case.removed_rule_ids == (disabled_id,)
            for rule in rules:
                if rule.rule_id != disabled_id:
                    assert rule.rule_id in case.remaining_rule_ids
        assert sorted(seen_disabled) == sorted(rule.rule_id for rule in rules)

    def test_each_single_rule_ablation_drops_only_that_rule_event(self) -> None:
        rules = (
            DummyRule("metric_accent"),
            DummyRule("phrase_arch"),
            DummyRule("microtiming"),
        )
        score = "score-loop"
        seeds = {"interpretation": 31}
        baseline = _render_trace(score, seeds=seeds, rules=rules)
        for rule in rules:
            rendered = ablate(
                score,
                seeds,
                disabled_rules={rule.rule_id},
                active_rules=rules,
                renderer=_render_trace,
            )
            expected_events = tuple(
                event for event in baseline["events"] if not event.endswith(f":{rule.rule_id}")
            )
            assert rendered["events"] == expected_events
            assert rule.rule_id not in rendered["rule_ids"]
            for other in rules:
                if other.rule_id != rule.rule_id:
                    assert other.rule_id in rendered["rule_ids"]

    def test_summarize_counts_changed_versus_unchanged_cases(self) -> None:
        rules = (DummyRule("metric_accent"), DummyRule("phrase_arch"))

        def stable_renderer(
            score: str,
            *,
            seeds: Mapping[str, int] | None,
            rules: Sequence[DummyRule],
        ) -> dict[str, Any]:
            return {"score": score, "seeds": dict(seeds or {}), "rule_ids": ()}

        suite = run_ablation_suite(
            "score-stable",
            {"composition": 2},
            active_rules=rules,
            renderer=stable_renderer,
        )
        summary = summarize_ablation_suite(suite)
        unchanged_count = 0
        for case in summary["cases"]:
            if not case["changed"]:
                unchanged_count += 1
        assert unchanged_count == summary["unchanged_count"]
        assert summary["changed_count"] + summary["unchanged_count"] == summary["case_count"]
        assert summary["unchanged_count"] == len(rules)
