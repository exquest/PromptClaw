"""Depth-2 production_course helpers - locked test surface for frac-0014."""
from __future__ import annotations

import dataclasses
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools"))
sys.path.insert(
    0,
    os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools", "senseweave"),
)

from senseweave.production_course import (  # noqa: E402
    REQUIRED_CHAPTER_IDS,
    REQUIRED_PHASE_NAMES,
    ArcPhaseSnapshot,
    ChapterDigest,
    CourseArcPlan,
    CourseSummary,
    arc_phase_snapshot,
    catalog_digest,
    chapter_digest,
    course_for_section,
    plan_course_arc,
    summarize_course,
    validate_course,
)


def _default_course() -> dict[str, str]:
    return course_for_section(
        function="statement",
        harmonic_role="tonic",
        arc_metadata={
            "arc_phase": "Emergence",
            "arc_harmonic": "modal",
            "arc_rhythm": "pulse",
            "arc_synthesis": "fm",
            "arc_spatial": "clear",
        },
        groove_identity="pulse",
        next_function=None,
        next_harmonic_role=None,
    )


def test_summarize_course_returns_titles_for_a_built_course() -> None:
    course = _default_course()

    summary = summarize_course(course)

    assert isinstance(summary, CourseSummary)
    assert dataclasses.is_dataclass(summary)
    assert getattr(summary, "__dataclass_params__").frozen
    assert summary.chapter_count == len(REQUIRED_CHAPTER_IDS)
    assert summary.transition_type == "terminal"
    assert summary.mix_role == "lead"
    assert summary.summary_titles == (
        "Modal",
        "Tonic",
        "Pulse",
        "Unison Shadow",
        "FM",
        "Lead",
        "Clear",
        "Minimalist Process",
        "Emergence",
        "Terminal",
    )


def test_chapter_digest_returns_concept_metadata() -> None:
    digest = chapter_digest("mode_scale")

    assert isinstance(digest, ChapterDigest)
    assert digest.chapter_id == "mode_scale"
    assert digest.title == "Mode and Scale"
    assert digest.concept_count == 5
    assert digest.sample_values == ("open", "modal", "functional")


def test_chapter_digest_raises_for_unknown_chapter() -> None:
    with pytest.raises(KeyError):
        chapter_digest("not_a_chapter")


def test_catalog_digest_covers_required_chapters() -> None:
    digests = catalog_digest()

    assert tuple(d.chapter_id for d in digests) == REQUIRED_CHAPTER_IDS
    for digest in digests:
        assert isinstance(digest, ChapterDigest)
        assert digest.title
        assert digest.concept_count >= len(digest.sample_values)
        assert len(digest.sample_values) <= 3


def test_arc_phase_snapshot_classifies_density_buckets() -> None:
    sparse = arc_phase_snapshot("Divination")
    balanced = arc_phase_snapshot("Emergence")
    dense = arc_phase_snapshot("Conversation")

    assert isinstance(sparse, ArcPhaseSnapshot)
    assert sparse.dominant_quality == "sparse"
    assert balanced.dominant_quality == "balanced"
    assert dense.dominant_quality == "dense"
    assert sparse.phase_name == "Divination"
    assert sparse.density == pytest.approx(0.24)
    assert sparse.transition_intent == "listen before speaking"

    # Every required phase resolves without raising.
    for phase_name in REQUIRED_PHASE_NAMES:
        snapshot = arc_phase_snapshot(phase_name)
        assert snapshot.phase_name == phase_name
        assert snapshot.dominant_quality in {"sparse", "balanced", "dense"}


def test_arc_phase_snapshot_raises_for_unknown_phase() -> None:
    with pytest.raises(KeyError):
        arc_phase_snapshot("Not a Phase")


def test_plan_course_arc_walks_sections_and_terminates() -> None:
    sections = [
        {
            "function": "statement",
            "harmonic_role": "tonic",
            "groove_identity": "pulse",
            "arc_metadata": {
                "arc_phase": "Emergence",
                "arc_harmonic": "modal",
                "arc_rhythm": "pulse",
                "arc_synthesis": "fm",
                "arc_spatial": "clear",
            },
        },
        {
            "function": "coda",
            "harmonic_role": "authentic",
            "groove_identity": "drift",
            "arc_metadata": {
                "arc_phase": "Crystallization",
                "arc_harmonic": "static",
                "arc_rhythm": "drone",
                "arc_synthesis": "granular",
                "arc_spatial": "expansive",
            },
        },
    ]

    plan = plan_course_arc(sections)

    assert isinstance(plan, CourseArcPlan)
    assert len(plan.courses) == len(sections)
    assert plan.transition_types == ("modulation", "terminal")
    assert plan.courses[-1]["transition_type"] == "terminal"
    assert plan.courses[0]["mix_role"] == "lead"
    for course in plan.courses:
        assert tuple(course) == REQUIRED_CHAPTER_IDS


def test_plan_course_arc_short_circuits_on_empty() -> None:
    plan = plan_course_arc(())

    assert isinstance(plan, CourseArcPlan)
    assert plan.courses == ()
    assert plan.transition_types == ()


def test_validate_course_reports_unknown_values() -> None:
    course = dict(_default_course())
    assert validate_course(course) == ()

    course["mix_role"] = "not_a_role"
    course["mode_scale"] = "wobble"

    issues = validate_course(course)
    assert issues == ("mix_role", "mode_scale") or issues == tuple(
        sorted(("mix_role", "mode_scale"))
    )
    assert set(issues) == {"mix_role", "mode_scale"}


def test_production_course_reaches_depth_two() -> None:
    sdp_src = "/Users/anthony/Programming/sdp-cli/src"
    if sdp_src not in sys.path:
        sys.path.insert(0, sdp_src)
    from sdp.fractal import classify_depth

    result = classify_depth("my-claw/tools/senseweave/production_course.py")
    assert result.depth >= 2, result.reason
