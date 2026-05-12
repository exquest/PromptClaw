"""Materialize EMSD course scaffolds into a curriculum tree."""
from __future__ import annotations

import json
from pathlib import Path

from .catalog import COURSE_CATALOG, Course


def _course_readme(course: Course) -> str:
    prereq = ", ".join(course.prerequisites) if course.prerequisites else "None"
    modules = "\n".join(f"- `{module}`" for module in course.live_modules) or "- `TBD`"

    parts = [
        f"# {course.code}: {course.title}\n\n"
        f"- Credits: `{course.credits}`\n"
        f"- Semester: `{course.semester}`\n"
        f"- Category: `{course.category}`\n"
        f"- Prerequisites: `{prereq}`\n",
    ]

    if course.description:
        parts.append(f"\n{course.description}\n")

    if course.learning_objectives:
        lo_lines = "\n".join(f"- {lo}" for lo in course.learning_objectives)
        parts.append(f"\n## Learning Objectives\n\n{lo_lines}\n")

    if course.topics:
        topic_lines = "\n".join(f"- {t}" for t in course.topics)
        parts.append(f"\n## Topics\n\n{topic_lines}\n")

    parts.append(
        "\n## Runtime Mapping\n\n"
        f"{modules}\n"
    )

    return "".join(parts)


def _overview_doc(course: Course) -> str:
    parts = [
        f"# {course.code} Overview\n\n"
        f"This reference note anchors `{course.title}` inside CypherClaw.\n\n",
    ]

    if course.description:
        parts.append(f"{course.description}\n\n")

    parts.append("## Key Questions\n\n")

    if course.topics:
        for topic in course.topics:
            parts.append(f"- How does **{topic}** improve CypherClaw's runtime behavior?\n")
    else:
        parts.append(
            "- What runtime behaviors should this course improve?\n"
            "- What should be measurable in tests or audio analysis?\n"
            "- Which current modules need to become more literate because of this course?\n"
        )

    if course.learning_objectives:
        parts.append("\n## Measurable Outcomes\n\n")
        for lo in course.learning_objectives:
            parts.append(f"- [ ] {lo}\n")

    return "".join(parts)


def _composition_prompt(course: Course) -> str:
    parts = [
        f"# Composition Prompt — {course.code}: {course.title}\n\n"
        "You are CypherClaw studying this course. Compose or design one exercise-sized\n"
        "artifact that demonstrates the musical or technical competency targeted by\n"
        "the course.\n\n",
    ]

    if course.learning_objectives:
        parts.append("## Target Competencies\n\n")
        for lo in course.learning_objectives:
            parts.append(f"- {lo}\n")
        parts.append("\n")

    if course.topics:
        parts.append("## Relevant Topics\n\n")
        parts.append(f"Draw from: {', '.join(course.topics).lower()}.\n\n")

    parts.append(
        "## Requirements\n\n"
        "- Stay inside measurable constraints.\n"
        "- Explain the signal path or formal logic.\n"
        "- Leave a clear verification target.\n"
    )

    return "".join(parts)


def _analysis_prompt(course: Course) -> str:
    parts = [
        f"# Analysis Prompt — {course.code}: {course.title}\n\n"
        "You are reviewing a CypherClaw output against this course's learning goals.\n\n",
    ]

    if course.learning_objectives:
        parts.append("## Evaluation Criteria\n\n")
        for lo in course.learning_objectives:
            parts.append(f"- Does the output demonstrate: *{lo}*?\n")
        parts.append("\n")

    parts.append(
        "## Review Structure\n\n"
        "1. Identify what is musically successful.\n"
        "2. Identify what is technically weak.\n"
        "3. Name the specific change that would move the piece toward the course standard.\n"
    )

    return "".join(parts)


def _exercise_readme(course: Course) -> str:
    parts = [f"# {course.code} Exercises\n\n"]

    if not course.exercises:
        parts.append(
            "No exercises defined yet.\n\n"
            "- Add coding tasks under `exercises/exNN/`.\n"
            "- Each exercise should include a machine-verifiable target.\n"
            "- Prefer spectral, temporal, structural, or constraint-based verification.\n"
        )
        return "".join(parts)

    for ex in course.exercises:
        parts.append(f"## {ex.id}: {ex.title}\n\n")
        parts.append(f"**Objective:** {ex.objective}\n\n")
        parts.append(f"**Verifier:** `{ex.verifier}`\n\n")
        parts.append("**Template:**\n\n")
        parts.append("```json\n")
        parts.append(json.dumps(ex.template, indent=2))
        parts.append("\n```\n\n")
        parts.append("**Expected features:**\n\n")
        for feat in ex.expected_features:
            parts.append(f"- `{feat}`\n")
        parts.append("\n")

    return "".join(parts)


def _completion_doc(course: Course) -> str:
    parts = [f"# {course.code} Completion — {course.title}\n\n"]

    parts.append("## Reference\n\n")
    if course.topics:
        for topic in course.topics:
            parts.append(f"- [ ] Reference note covers: {topic}\n")
    else:
        parts.append("- [ ] Reference notes drafted\n")

    parts.append("\n## Prompts\n\n")
    parts.append("- [ ] Composition prompt tailored to course objectives\n")
    parts.append("- [ ] Analysis prompt includes course-specific evaluation criteria\n")

    parts.append("\n## Exercises\n\n")
    if course.exercises:
        for ex in course.exercises:
            parts.append(f"- [ ] `{ex.id}`: {ex.title} — verifier passing\n")
    else:
        parts.append("- [ ] At least one exercise implemented\n")

    parts.append("\n## Integration\n\n")
    parts.append("- [ ] Verification passing\n")
    parts.append("- [ ] Runtime integration reviewed\n")

    return "".join(parts)


def materialize_curriculum(root: str | Path) -> None:
    target_root = Path(root)
    target_root.mkdir(parents=True, exist_ok=True)
    for course in COURSE_CATALOG:
        course_dir = target_root / course.code
        (course_dir / "reference").mkdir(parents=True, exist_ok=True)
        (course_dir / "prompts").mkdir(parents=True, exist_ok=True)
        (course_dir / "exercises").mkdir(parents=True, exist_ok=True)
        (course_dir / "README.md").write_text(_course_readme(course), encoding="utf-8")
        (course_dir / "reference" / "01-overview.md").write_text(_overview_doc(course), encoding="utf-8")
        (course_dir / "prompts" / "composition.md").write_text(_composition_prompt(course), encoding="utf-8")
        (course_dir / "prompts" / "analysis.md").write_text(_analysis_prompt(course), encoding="utf-8")
        (course_dir / "exercises" / "README.md").write_text(_exercise_readme(course), encoding="utf-8")
        (course_dir / "COMPLETION.md").write_text(_completion_doc(course), encoding="utf-8")

        for ex in course.exercises:
            ex_dir = course_dir / "exercises" / ex.id
            ex_dir.mkdir(parents=True, exist_ok=True)
            spec = {
                "id": ex.id,
                "title": ex.title,
                "objective": ex.objective,
                "template": ex.template,
                "verifier": ex.verifier,
                "expected_features": list(ex.expected_features),
                "expected": list(ex.expected_features),
            }
            (ex_dir / "spec.json").write_text(
                json.dumps(spec, indent=2) + "\n", encoding="utf-8",
            )
