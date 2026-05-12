"""Executable curriculum coverage for production-course exercises."""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw"))

from curriculum.bootstrap import materialize_curriculum
from curriculum.catalog import COURSE_CATALOG, ExerciseSpec, course_by_code
from curriculum.verify import verify_exercise


REQUIRED_PRODUCTION_EXERCISES = {
    "intervals_scales": ("EMSD-110", "ex01", "intervals"),
    "chord_voicings": ("EMSD-210", "ex01", "voicings"),
    "progressions": ("EMSD-302", "ex01", "progressions"),
    "rhythm_groove": ("EMSD-220", "ex01", "groove_grid"),
    "counterpoint": ("EMSD-302", "ex02", "counterpoint_relation"),
    "synthesis_architecture": ("EMSD-201", "ex01", "architecture"),
    "mix_master": ("EMSD-301", "ex01", "master_chain"),
    "senseweave_mapping": ("EMSD-257", "ex01", "senseweave_mapping"),
    "theramini_ensemble": ("EMSD-251", "ex01", "theramini_roles"),
    "genre_strategy": ("EMSD-253", "ex01", "genre_strategy"),
    "full_arc_production": ("EMSD-499", "ex01", "phase_profiles"),
}


def _exercise_by_id(course_code: str, exercise_id: str) -> ExerciseSpec:
    course = course_by_code(course_code)
    for exercise in course.exercises:
        if exercise.id == exercise_id:
            return exercise
    raise AssertionError(f"Missing exercise {course_code}/{exercise_id}")


def test_production_course_exercise_topics_are_covered() -> None:
    """Required production-course topics have concrete exercise specs."""
    for topic, (course_code, exercise_id, feature) in REQUIRED_PRODUCTION_EXERCISES.items():
        exercise = _exercise_by_id(course_code, exercise_id)
        assert exercise.objective, f"{topic} missing objective"
        assert feature in exercise.expected_features, (
            f"{topic} exercise {course_code}/{exercise_id} missing expected feature {feature}"
        )


def test_exercise_metadata_includes_templates_and_expected_features(tmp_path) -> None:
    """Catalog and generated spec.json files expose executable metadata."""
    materialize_curriculum(tmp_path)

    for course in COURSE_CATALOG:
        for exercise in course.exercises:
            assert exercise.objective, f"{course.code}/{exercise.id} missing objective"
            assert exercise.template, f"{course.code}/{exercise.id} missing template"
            assert exercise.verifier in {"structural", "constraint", "spectral", "temporal"}
            assert exercise.expected_features, (
                f"{course.code}/{exercise.id} missing expected_features"
            )
            assert exercise.expected == exercise.expected_features

            spec_path = tmp_path / course.code / "exercises" / exercise.id / "spec.json"
            spec = json.loads(spec_path.read_text(encoding="utf-8"))
            assert spec["objective"] == exercise.objective
            assert spec["template"] == exercise.template
            assert spec["verifier"] == exercise.verifier
            assert spec["expected_features"] == list(exercise.expected_features)
            assert spec["expected"] == spec["expected_features"]


def test_every_exercise_template_passes_its_verifier_stub(tmp_path) -> None:
    """All exercise templates are runnable through their declared verifier."""
    materialize_curriculum(tmp_path)

    exercises_seen = 0
    for course in COURSE_CATALOG:
        for exercise in course.exercises:
            exercises_seen += 1
            exercise_dir = tmp_path / course.code / "exercises" / exercise.id
            result = verify_exercise(course, exercise, exercise_dir, exercise.template)
            assert result.passed, (
                f"{course.code}/{exercise.id} verifier failed: {result.message}"
            )
            assert set(result.checks_passed) == set(exercise.expected_features)
            assert result.checks_failed == ()

    assert exercises_seen >= len(REQUIRED_PRODUCTION_EXERCISES)
