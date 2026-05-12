# Task frac-0014 Specification: Production Course Depth 2

## Problem Statement

`my-claw/tools/senseweave/production_course.py` ships the runtime
production-course knowledge base: ten typed chapters, five `ArcPhaseProfile`
records, and the `course_for_section` builder used by the score-tree composer.
Beyond that builder and `transition_type_for_section`, the module's public
surface is mostly trivial registry lookups (`load_course_chapters`,
`load_arc_phase_profiles`, `course_chapter`, `course_concept`,
`arc_phase_profile`). The fractal scanner therefore classifies the file at
depth 1 (`9/11 trivial, 2 real`).

The task is to deepen the module to a simple depth-2 implementation: keep the
existing chapter/phase/course builder behavior unchanged while adding one-path
helpers that turn the knowledge base into meaningful operator-readable output:
a course summary built from a section's course dict, a chapter digest with
sample concept values, an arc phase snapshot that buckets density, a course
arc planner that walks a list of section descriptors and reuses
`course_for_section`, and a course validator that reports unknown chapter
values. This gives runtime diagnostics and tests meaningful end-to-end output
without changing the score-tree composer or its callers.

## Technical Approach

Extend `production_course.py` in place with typed, pure helpers. No new
dependencies, migrations, runtime state files, provider secrets, or agent
commands are introduced.

- Frozen dataclasses:
  - `CourseSummary(chapter_count, transition_type, mix_role,
    summary_titles)` — operator-readable view of one section's course.
  - `ChapterDigest(chapter_id, title, concept_count, sample_values)` — short
    description of one chapter and its first three concept values.
  - `ArcPhaseSnapshot(phase_name, density, mutation_rate, transition_intent,
    dominant_quality)` — phase profile plus a `"sparse" | "balanced" | "dense"`
    bucket.
  - `CourseArcPlan(courses, transition_types)` — the planned course dicts and
    their per-section transition types.

- `summarize_course(course)`:
  - Walks `REQUIRED_CHAPTER_IDS` to look up each value via `course_concept`.
  - Returns a `CourseSummary` whose `summary_titles` are the resolved concept
    titles in chapter order; unknown values are skipped (the validator covers
    that path explicitly).
  - `transition_type` and `mix_role` are read directly from `course`.

- `chapter_digest(chapter_id)`:
  - Resolves the chapter via `course_chapter`.
  - Raises `KeyError(chapter_id)` for unknown ids.
  - Returns a `ChapterDigest` with the chapter title, concept count, and the
    first three concept values as `sample_values`.

- `catalog_digest()`:
  - Iterates `REQUIRED_CHAPTER_IDS` and returns the matching tuple of
    `ChapterDigest` records in declared order.

- `arc_phase_snapshot(phase_name)`:
  - Resolves the profile via `arc_phase_profile`.
  - Raises `KeyError(phase_name)` for unknown names.
  - Buckets `density`: `< 0.4` → `"sparse"`, `>= 0.7` → `"dense"`, else
    `"balanced"`.

- `plan_course_arc(sections)`:
  - Accepts an iterable of section descriptors. Each descriptor is a mapping
    with `function`, `harmonic_role`, `groove_identity`, and `arc_metadata`
    (a `Mapping[str, str]`).
  - For each section, calls `course_for_section` with the next section's
    `function` / `harmonic_role` (or `None` for the last section) so the
    transition type resolves cleanly.
  - Returns a `CourseArcPlan` whose `courses` is the tuple of course dicts and
    whose `transition_types` is the parallel tuple of `transition_type`
    values, ending with `"terminal"`.

- `validate_course(course)`:
  - Walks `REQUIRED_CHAPTER_IDS` and reports any chapter whose value is missing
    or not registered in `_CONCEPTS_BY_CHAPTER_VALUE`.
  - Returns a sorted tuple of offending chapter ids; an empty tuple means the
    course is fully valid.

Existing `REQUIRED_CHAPTER_IDS`, `REQUIRED_PHASE_NAMES`, `COURSE_CHAPTERS`,
`ARC_PHASE_PROFILES`, `load_course_chapters`, `load_arc_phase_profiles`,
`course_chapter`, `course_concept`, `arc_phase_profile`,
`transition_type_for_section`, and `course_for_section` keep their current
signatures and semantics.

## Edge Cases

- `chapter_digest` and `arc_phase_snapshot` raise `KeyError` for unknown ids,
  matching the failure mode used by the locked depth-2 helpers in
  `frac-0012` (`genre_literacy`).
- `summarize_course` skips unregistered values silently so live diagnostics
  never crash on a stale value; `validate_course` is the typed surface that
  surfaces those issues to operators.
- `plan_course_arc(())` returns a `CourseArcPlan` with empty tuples and never
  calls `course_for_section`.
- A single-section plan ends with `"terminal"` because `next_function` is
  `None` for the only section.
- Startup identity hardening targets the daemon startup subsystem, not this
  pure knowledge-base module. Existing startup identity tests
  (`tests/test_first_boot.py::TestStartupIdentityPersistence`,
  `tests/test_governor_integration.py::TestStartupIdentityWiring`) remain
  mandatory regression anchors.

## Acceptance Criteria

1. `summarize_course` returns a stable `CourseSummary` whose titles match the
   resolved concept titles for a fully populated course.
   VERIFY: `pytest tests/test_production_course_depth.py::test_summarize_course_returns_titles_for_a_built_course -q`

2. `chapter_digest` returns chapter metadata with the first three concept
   values and raises `KeyError` for unknown chapter ids.
   VERIFY: `pytest tests/test_production_course_depth.py::test_chapter_digest_returns_concept_metadata tests/test_production_course_depth.py::test_chapter_digest_raises_for_unknown_chapter -q`

3. `catalog_digest` covers every required chapter in declared order.
   VERIFY: `pytest tests/test_production_course_depth.py::test_catalog_digest_covers_required_chapters -q`

4. `arc_phase_snapshot` reports density buckets matching the canonical phase
   data and raises `KeyError` for unknown phase names.
   VERIFY: `pytest tests/test_production_course_depth.py::test_arc_phase_snapshot_classifies_density_buckets tests/test_production_course_depth.py::test_arc_phase_snapshot_raises_for_unknown_phase -q`

5. `plan_course_arc` returns one course per section with the last section's
   `transition_type` equal to `"terminal"`, and short-circuits on empty input.
   VERIFY: `pytest tests/test_production_course_depth.py::test_plan_course_arc_walks_sections_and_terminates tests/test_production_course_depth.py::test_plan_course_arc_short_circuits_on_empty -q`

6. `validate_course` returns the sorted tuple of chapter ids whose values are
   unknown, and an empty tuple for a fully valid course.
   VERIFY: `pytest tests/test_production_course_depth.py::test_validate_course_reports_unknown_values -q`

7. Existing production-course knowledge base and integration tests still
   pass.
   VERIFY: `pytest tests/test_production_course_knowledge_base.py tests/test_production_course_integration.py -q`

8. Fractal depth for `my-claw/tools/senseweave/production_course.py` reaches
   at least depth 2.
   VERIFY: `pytest tests/test_production_course_depth.py::test_production_course_reaches_depth_two -q`

9. Startup identity hardening remains covered for standalone and federated
   startup paths.
   VERIFY: `pytest tests/test_first_boot.py::TestStartupIdentityPersistence tests/test_governor_integration.py::TestStartupIdentityWiring -q`

10. Full project validation remains clean.
    VERIFY: `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/`
