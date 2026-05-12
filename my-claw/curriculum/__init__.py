"""Curriculum helpers for CypherClaw's formal music study tracks."""

from .bootstrap import materialize_curriculum
from .catalog import (
    COURSE_CATALOG,
    Course,
    ExerciseSpec,
    catalog_summary,
    course_by_code,
    courses_by_category,
    courses_for_semester,
    curriculum_totals,
    exercise_index,
    prerequisite_graph,
    validate_catalog,
)
from .verify import VerifyResult, verify_exercise

__all__ = [
    "COURSE_CATALOG",
    "Course",
    "ExerciseSpec",
    "VerifyResult",
    "catalog_summary",
    "course_by_code",
    "courses_by_category",
    "courses_for_semester",
    "curriculum_totals",
    "exercise_index",
    "materialize_curriculum",
    "prerequisite_graph",
    "validate_catalog",
    "verify_exercise",
]
