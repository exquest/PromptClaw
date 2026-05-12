"""Tests for the EMSD curriculum catalog and scaffold generator."""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw"))

from curriculum.bootstrap import materialize_curriculum
from curriculum.catalog import COURSE_CATALOG, ExerciseSpec, course_by_code, curriculum_totals, scaffold_relpaths
from curriculum.verify import verify_exercise


# ------------------------------------------------------------------
# Existing catalog shape tests
# ------------------------------------------------------------------

def test_curriculum_catalog_matches_declared_degree_shape() -> None:
    totals = curriculum_totals()

    assert totals == {"courses": 40, "credits": 120}
    assert len(COURSE_CATALOG) == 40


def test_course_lookup_exposes_capstone_and_core_prerequisites() -> None:
    capstone = course_by_code("EMSD-499")
    theory = course_by_code("EMSD-110")

    assert capstone.title.startswith("Capstone")
    assert "EMSD-401" in capstone.prerequisites
    assert theory.prerequisites == ()


def test_scaffold_relpaths_follow_standard_course_layout() -> None:
    paths = scaffold_relpaths(course_by_code("EMSD-201"))

    assert "EMSD-201/README.md" in paths
    assert "EMSD-201/reference/01-overview.md" in paths
    assert "EMSD-201/prompts/composition.md" in paths
    assert "EMSD-201/exercises/README.md" in paths


def test_materialize_curriculum_creates_course_scaffolds(tmp_path) -> None:
    materialize_curriculum(tmp_path)

    assert (tmp_path / "EMSD-101" / "README.md").exists()
    assert (tmp_path / "EMSD-201" / "reference" / "01-overview.md").exists()
    assert (tmp_path / "EMSD-401" / "prompts" / "analysis.md").exists()
    assert (tmp_path / "EMSD-499" / "COMPLETION.md").exists()


# ------------------------------------------------------------------
# Meaningful content tests
# ------------------------------------------------------------------

def test_all_courses_have_meaningful_content() -> None:
    """Every course has a description, learning objectives, and topics."""
    for course in COURSE_CATALOG:
        assert course.description, f"{course.code} missing description"
        assert len(course.learning_objectives) >= 3, (
            f"{course.code} has {len(course.learning_objectives)} learning objectives, need >= 3"
        )
        assert len(course.topics) >= 4, (
            f"{course.code} has {len(course.topics)} topics, need >= 4"
        )


def test_core_courses_have_exercise_specs() -> None:
    """Every core_concentrate course has at least one exercise spec."""
    core_courses = [c for c in COURSE_CATALOG if c.category == "core_concentrate"]
    assert len(core_courses) == 10

    for course in core_courses:
        assert len(course.exercises) >= 1, f"{course.code} has no exercise specs"


def test_exercise_metadata_validity() -> None:
    """Exercise specs have all required fields with valid values."""
    valid_verifiers = {"structural", "constraint", "spectral", "temporal"}
    seen_ids: dict[str, set[str]] = {}

    for course in COURSE_CATALOG:
        seen_ids[course.code] = set()
        for ex in course.exercises:
            assert isinstance(ex, ExerciseSpec)
            assert ex.id, f"{course.code} exercise has empty id"
            assert ex.title, f"{course.code}/{ex.id} has empty title"
            assert ex.objective, f"{course.code}/{ex.id} has empty objective"
            assert ex.verifier in valid_verifiers, (
                f"{course.code}/{ex.id} has invalid verifier: {ex.verifier}"
            )
            assert len(ex.expected) >= 1, (
                f"{course.code}/{ex.id} has no expected features"
            )
            assert ex.id not in seen_ids[course.code], (
                f"{course.code} has duplicate exercise id: {ex.id}"
            )
            seen_ids[course.code].add(ex.id)


# ------------------------------------------------------------------
# Directory completeness tests
# ------------------------------------------------------------------

def test_materialized_directories_complete(tmp_path) -> None:
    """Every scaffold file listed in scaffold_relpaths is created."""
    materialize_curriculum(tmp_path)

    for course in COURSE_CATALOG:
        for relpath in scaffold_relpaths(course):
            full_path = tmp_path / relpath
            assert full_path.exists(), f"Missing: {relpath}"


def test_materialized_exercise_specs_match_catalog(tmp_path) -> None:
    """Generated spec.json files match the catalog ExerciseSpec data."""
    materialize_curriculum(tmp_path)

    for course in COURSE_CATALOG:
        for ex in course.exercises:
            spec_path = tmp_path / course.code / "exercises" / ex.id / "spec.json"
            assert spec_path.exists(), f"Missing spec.json for {course.code}/{ex.id}"

            spec = json.loads(spec_path.read_text(encoding="utf-8"))
            assert spec["id"] == ex.id
            assert spec["title"] == ex.title
            assert spec["objective"] == ex.objective
            assert spec["verifier"] == ex.verifier
            assert spec["expected"] == list(ex.expected)


def test_materialized_readme_contains_learning_objectives(tmp_path) -> None:
    """Generated READMEs include the course learning objectives."""
    materialize_curriculum(tmp_path)

    course = course_by_code("EMSD-101")
    readme = (tmp_path / "EMSD-101" / "README.md").read_text(encoding="utf-8")

    assert "Learning Objectives" in readme
    for lo in course.learning_objectives:
        assert lo in readme, f"Missing LO in README: {lo}"


def test_materialized_completion_has_course_specific_criteria(tmp_path) -> None:
    """COMPLETION.md files include course-specific checklists."""
    materialize_curriculum(tmp_path)

    # Core course with exercises should list exercise titles
    completion = (tmp_path / "EMSD-101" / "COMPLETION.md").read_text(encoding="utf-8")
    assert "MIDI-Frequency Converter" in completion

    # Core course should list topic-specific reference checks
    assert "PCM encoding" in completion


# ------------------------------------------------------------------
# Exercise verifier tests
# ------------------------------------------------------------------

def test_exercise_verifier_scaffold_check(tmp_path) -> None:
    """Structure-only verification passes when spec.json exists."""
    materialize_curriculum(tmp_path)
    core_courses = [c for c in COURSE_CATALOG if c.category == "core_concentrate"]

    for course in core_courses:
        for ex in course.exercises:
            ex_dir = tmp_path / course.code / "exercises" / ex.id
            result = verify_exercise(course, ex, ex_dir)
            assert result.passed, (
                f"{course.code}/{ex.id} scaffold check failed: {result.message}"
            )
            assert result.course_code == course.code
            assert result.exercise_id == ex.id


def test_exercise_verifier_accepts_complete_submission(tmp_path) -> None:
    """A submission with all expected keys passes verification."""
    materialize_curriculum(tmp_path)
    core_courses = [c for c in COURSE_CATALOG if c.category == "core_concentrate"]

    for course in core_courses:
        for ex in course.exercises:
            ex_dir = tmp_path / course.code / "exercises" / ex.id
            submission = {k: True for k in ex.expected}
            result = verify_exercise(course, ex, ex_dir, submission)
            assert result.passed, (
                f"{course.code}/{ex.id} should pass with all keys: {result.message}"
            )
            assert set(result.checks_passed) == set(ex.expected)
            assert result.checks_failed == ()


def test_exercise_verifier_rejects_empty_submission(tmp_path) -> None:
    """An empty submission fails verification."""
    materialize_curriculum(tmp_path)
    core_courses = [c for c in COURSE_CATALOG if c.category == "core_concentrate"]

    for course in core_courses:
        for ex in course.exercises:
            ex_dir = tmp_path / course.code / "exercises" / ex.id
            result = verify_exercise(course, ex, ex_dir, {})
            assert not result.passed, (
                f"{course.code}/{ex.id} should fail with empty submission"
            )
            assert set(result.checks_failed) == set(ex.expected)


def test_exercise_verifier_missing_dir() -> None:
    """Verification fails cleanly when exercise directory is absent."""
    from pathlib import Path

    course = course_by_code("EMSD-101")
    ex = course.exercises[0]
    result = verify_exercise(course, ex, Path("/nonexistent/path"))
    assert not result.passed
    assert "does not exist" in result.message
