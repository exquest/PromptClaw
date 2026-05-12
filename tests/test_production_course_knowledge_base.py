"""Tests for the runtime production-course knowledge base."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools"))
sys.path.insert(
    0,
    os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools", "senseweave"),
)

from senseweave.production_course import (
    REQUIRED_CHAPTER_IDS,
    REQUIRED_PHASE_NAMES,
    arc_phase_profile,
    course_concept,
    course_for_section,
    load_arc_phase_profiles,
    load_course_chapters,
)
from senseweave.score_tree import PRODUCTION_COURSE_KEYS


def test_required_production_course_chapters_are_present_and_loadable() -> None:
    chapters = {chapter.chapter_id: chapter for chapter in load_course_chapters()}

    assert REQUIRED_CHAPTER_IDS == PRODUCTION_COURSE_KEYS
    assert tuple(chapters) == REQUIRED_CHAPTER_IDS

    for chapter_id in REQUIRED_CHAPTER_IDS:
        chapter = chapters[chapter_id]
        assert chapter.stable_id == f"production-course.chapter.{chapter_id}"
        assert chapter.title
        assert chapter.summary
        assert chapter.concepts
        for concept in chapter.concepts:
            assert concept.stable_id.startswith(
                f"production-course.{chapter_id}."
            )
            assert concept.chapter_id == chapter_id
            assert concept.value
            assert concept.title


def test_required_arc_phase_profiles_are_present_and_loadable() -> None:
    profiles = {profile.phase_name: profile for profile in load_arc_phase_profiles()}

    assert tuple(profiles) == REQUIRED_PHASE_NAMES
    for phase_name in REQUIRED_PHASE_NAMES:
        profile = arc_phase_profile(phase_name)
        assert profile is not None
        assert profile == profiles[phase_name]
        assert profile.stable_id == (
            f"production-course.phase.{phase_name.lower()}"
        )
        assert profile.transition_intent
        assert profile.dynamic
        assert profile.harmonic
        assert profile.rhythm
        assert profile.synthesis


def test_runtime_course_builder_uses_loadable_chapter_concepts() -> None:
    course = course_for_section(
        function="development",
        harmonic_role="borrowed",
        groove_identity="ritual_ostinato",
        arc_metadata={
            "arc_phase": "Conversation",
            "arc_harmonic": "functional",
            "arc_rhythm": "groove",
            "arc_synthesis": "subtractive",
            "arc_spatial": "focused",
        },
        next_function="recap",
        next_harmonic_role="authentic",
    )

    assert tuple(course) == REQUIRED_CHAPTER_IDS
    assert course["phase_profile"] == "Conversation"
    assert course["transition_type"] == "modulation"

    for chapter_id, value in course.items():
        assert course_concept(chapter_id, value) is not None
