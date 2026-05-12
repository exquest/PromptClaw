"""Exercise verification for EMSD curriculum courses."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .catalog import Course, ExerciseSpec


@dataclass
class VerifyResult:
    """Result of an exercise verification run."""

    passed: bool
    exercise_id: str
    course_code: str
    message: str
    checks_passed: tuple[str, ...] = ()
    checks_failed: tuple[str, ...] = ()


def load_exercise_spec(exercise_dir: Path) -> dict:
    """Load spec.json from an exercise directory."""
    spec_path = exercise_dir / "spec.json"
    if not spec_path.exists():
        raise FileNotFoundError(f"No spec.json in {exercise_dir}")
    return json.loads(spec_path.read_text(encoding="utf-8"))


def verify_exercise(
    course: Course,
    spec: ExerciseSpec,
    exercise_dir: Path,
    submission: dict | None = None,
) -> VerifyResult:
    """Verify an exercise submission against its spec.

    If *submission* is ``None``, only the exercise directory structure is
    checked (spec.json exists).  When a *submission* dict is provided the
    appropriate verifier is run against it.
    """
    if not exercise_dir.exists():
        return VerifyResult(
            passed=False,
            exercise_id=spec.id,
            course_code=course.code,
            message=f"Exercise directory does not exist: {exercise_dir}",
        )

    if submission is None:
        return _verify_scaffold(course, spec, exercise_dir)

    verifiers = {
        "constraint": _verify_constraint,
        "structural": _verify_structural,
        "spectral": _verify_spectral,
        "temporal": _verify_temporal,
    }
    fn = verifiers.get(spec.verifier, _verify_structural)
    return fn(course, spec, submission)


# ------------------------------------------------------------------
# Internal verifiers
# ------------------------------------------------------------------

def _verify_scaffold(
    course: Course, spec: ExerciseSpec, exercise_dir: Path,
) -> VerifyResult:
    """Ensure the exercise directory has the required scaffold files."""
    passed: list[str] = []
    failed: list[str] = []

    if (exercise_dir / "spec.json").exists():
        passed.append("spec_exists")
    else:
        failed.append("spec_exists")

    return VerifyResult(
        passed=not failed,
        exercise_id=spec.id,
        course_code=course.code,
        message="Structure valid" if not failed else "Missing required files",
        checks_passed=tuple(passed),
        checks_failed=tuple(failed),
    )


def _verify_constraint(
    course: Course, spec: ExerciseSpec, submission: dict,
) -> VerifyResult:
    """Check that every expected key is present and truthy."""
    passed: list[str] = []
    failed: list[str] = []

    for key in spec.expected:
        val = submission.get(key)
        if val is not None and val is not False:
            passed.append(key)
        else:
            failed.append(key)

    return VerifyResult(
        passed=not failed,
        exercise_id=spec.id,
        course_code=course.code,
        message="All constraints satisfied" if not failed else f"Failed: {', '.join(failed)}",
        checks_passed=tuple(passed),
        checks_failed=tuple(failed),
    )


def _verify_structural(
    course: Course, spec: ExerciseSpec, submission: dict,
) -> VerifyResult:
    """Check that every expected key is present in the submission."""
    passed: list[str] = []
    failed: list[str] = []

    for key in spec.expected:
        if key in submission:
            passed.append(key)
        else:
            failed.append(key)

    return VerifyResult(
        passed=not failed,
        exercise_id=spec.id,
        course_code=course.code,
        message="Structure complete" if not failed else f"Missing: {', '.join(failed)}",
        checks_passed=tuple(passed),
        checks_failed=tuple(failed),
    )


def _verify_spectral(
    course: Course, spec: ExerciseSpec, submission: dict,
) -> VerifyResult:
    """Verify spectral analysis properties (delegates to constraint check)."""
    return _verify_constraint(course, spec, submission)


def _verify_temporal(
    course: Course, spec: ExerciseSpec, submission: dict,
) -> VerifyResult:
    """Verify temporal/rhythmic properties (delegates to constraint check)."""
    return _verify_constraint(course, spec, submission)
