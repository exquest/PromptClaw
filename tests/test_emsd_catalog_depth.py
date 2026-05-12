"""Depth-2 catalog behavior tests for EMSD curriculum helpers."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw"))

from curriculum.catalog import (  # noqa: E402
    COURSE_CATALOG,
    Course,
    ExerciseSpec,
    catalog_summary,
    courses_by_category,
    courses_for_semester,
    exercise_index,
    prerequisite_graph,
    validate_catalog,
)


def test_catalog_depth_helpers_return_meaningful_output() -> None:
    """Catalog helpers expose grouped, filtered, indexed, and summary data."""
    grouped = courses_by_category()

    assert set(grouped) == {
        "core_concentrate",
        "musicianship",
        "concentrate_elective",
        "specialization",
        "foundations",
    }
    assert [course.code for course in grouped["core_concentrate"][:3]] == [
        "EMSD-101",
        "EMSD-102",
        "EMSD-201",
    ]
    assert courses_by_category("core_concentrate") == grouped["core_concentrate"]
    assert courses_by_category("missing") == ()

    semester_one = courses_for_semester(1)
    assert {course.code for course in semester_one} == {
        "EMSD-101",
        "EMSD-102",
        "EMSD-110",
        "EMSD-L101",
    }
    assert courses_for_semester(99) == ()

    graph = prerequisite_graph()
    assert graph["EMSD-201"] == ("EMSD-102",)
    assert graph["EMSD-499"] == ("EMSD-401", "EMSD-304", "EMSD-303")

    exercises = exercise_index()
    assert len(exercises) == 17
    assert exercises["EMSD-302/ex02"].title == "Counterpoint Relation Study"
    assert "counterpoint_relation" in exercises["EMSD-302/ex02"].expected_features

    summary = catalog_summary()
    assert summary == {
        "course_count": 40,
        "credit_count": 120,
        "exercise_count": 17,
        "semester_count": 8,
        "category_counts": {
            "concentrate_elective": 2,
            "core_concentrate": 10,
            "foundations": 14,
            "musicianship": 3,
            "specialization": 11,
        },
    }


def test_catalog_validation_reports_inconsistencies() -> None:
    """Catalog validation passes cleanly now and reports bad catalog metadata."""
    assert validate_catalog() == ()

    broken_exercise = ExerciseSpec(
        id="ex01",
        title="Broken Exercise",
        objective="Missing expected features and invalid verifier.",
        template={},
        verifier="manual",
        expected_features=(),
    )
    duplicate_exercise = ExerciseSpec(
        id="ex01",
        title="Duplicate Exercise",
        objective="Duplicate exercise id.",
        template={"ok": True},
        verifier="structural",
        expected_features=("ok",),
    )
    broken_course = Course(
        code="EMSD-101",
        title="Broken Course",
        credits=3,
        semester=1,
        category="unknown",
        prerequisites=("EMSD-MISSING",),
        exercises=(broken_exercise, duplicate_exercise),
    )

    errors = validate_catalog((COURSE_CATALOG[0], broken_course))

    assert "duplicate course code: EMSD-101" in errors
    assert "EMSD-101 has invalid category: unknown" in errors
    assert "EMSD-101 references missing prerequisite: EMSD-MISSING" in errors
    assert "EMSD-101/ex01 has invalid verifier: manual" in errors
    assert "EMSD-101/ex01 has no expected features" in errors
    assert "EMSD-101 has duplicate exercise id: ex01" in errors
