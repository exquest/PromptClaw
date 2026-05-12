# Task frac-0024 Specification: Score Tree Depth 2

## Problem Statement

`my-claw/tools/senseweave/score_tree.py` owns the canonical score-tree data
model used by the CypherClaw composition pipeline. It exports
`MOTIF_LIFECYCLE_STATES`, `PRODUCTION_COURSE_KEYS`, the `MotifNode`,
`PhraseNode`, `SectionNode`, and `ScoreTree` dataclasses, plus the
`ScoreTree.to_dict`, `ScoreTree.to_json`, `ScoreTree.from_dict`, and
`ScoreTree.minimal` helpers. Downstream callers in
`composer_runtime.py`, `tracker_compiler.py`, `gallery_status.py`, and
`duet_composer.py` consume those structures directly.

The module currently classifies at fractal depth 1
(`5/8 trivial, 3 real`) because the public surface is dominated by the
`to_dict`/`to_json`/`minimal` constructors and the two dataclass
`__post_init__` envelope coercions, which outnumber the real
`from_dict`/`_coerce_*` parsing helpers. This task deepens the module to a
simple depth-2 implementation by adding one typed report path that turns a
concrete `ScoreTree` into stable operator-readable shape diagnostics
without changing any existing dataclass field, JSON contract, or
`from_dict`/`minimal` behavior.

## Technical Approach

Extend `senseweave.score_tree` in place with stdlib-only, typed helpers.
No new dependencies, migrations, runtime state files, provider secrets,
database columns, or agent command strings are introduced.

- Add frozen dataclass `ScoreTreeSectionReport` containing one section's
  resolved view: `section_id`, `scene_name`, `function`,
  `harmonic_role`, `harmonic_function`, `cadence_type`, `groove_state`,
  `transition_intent`, `transform_strength`, `target_duration_s`,
  `phrase_count`, `phrase_load_band`, `motif_refs` (ordered, de-duplicated
  motif ids referenced by the section's phrases), and
  `production_course_complete` (whether `production_course` covers every
  `PRODUCTION_COURSE_KEYS` entry).
- Add frozen dataclass `ScoreTreeReport` containing the tree-level view:
  `piece_id`, `title`, `form_family`, `form_class`, `composition_mode`,
  `ending_family`, `planned_duration_s`, `section_count`, `motif_count`,
  `phrase_count`, `motif_lifecycle_counts` (ordered mapping of every
  `MOTIF_LIFECYCLE_STATES` entry to its motif count, including zeros),
  `unreferenced_motif_ids` (ordered tuple of motif ids that no section's
  phrase references), and `sections` (ordered tuple of
  `ScoreTreeSectionReport` entries, one per `tree.sections`).
- Add `motif_lifecycle_band(state)`:
  - Map a motif lifecycle state to one of `"introduction"`,
    `"development"`, or `"resolution"` using the canonical
    `MOTIF_LIFECYCLE_STATES` ordering. `"statement"` and `"variation"`
    map to `"introduction"`; `"contrast"`, `"recall"`, and `"answer"`
    map to `"development"`; `"liquidation"` and `"residue"` map to
    `"resolution"`. Unknown states return `"unclassified"`.
- Add `section_phrase_load_band(count)`:
  - Map a phrase count to one of `"spare"` (0–1), `"compact"` (2–3),
    `"developed"` (4–5), or `"saturated"` (6+).
- Add `count_motif_lifecycle_states(tree)`:
  - Walk `tree.motifs` and return a `dict[str, int]` keyed by every
    `MOTIF_LIFECYCLE_STATES` value with that state's motif count.
    Unknown states are not returned.
- Add `build_score_tree_section_report(section)`:
  - Resolve `phrase_count` from `section.phrases`, classify it through
    `section_phrase_load_band`, collect ordered de-duplicated
    `motif_refs` from each phrase's `motif_refs`, and report
    `production_course_complete` against `PRODUCTION_COURSE_KEYS`.
- Add `build_score_tree_report(tree)`:
  - Build one `ScoreTreeSectionReport` per section (in `tree.sections`
    order) through `build_score_tree_section_report`, populate
    `motif_lifecycle_counts` through `count_motif_lifecycle_states`
    (ensuring every canonical state appears, with zero counts for
    missing states), compute `unreferenced_motif_ids` as the ordered
    tuple of `motif.motif_id` values that no section's phrase
    references, and aggregate `section_count`, `motif_count`, and
    `phrase_count` directly from the tree.
- Add `summarize_score_tree_report(report)`:
  - Return a JSON-safe dictionary covering the tree-level identity,
    form/duration shape, counts, lifecycle counts, unreferenced motif
    ids, and a `sections` list whose entries mirror each section
    report's fields. All values must be primitives, lists, or
    dictionaries of primitives.
- Keep `MOTIF_LIFECYCLE_STATES`, `PRODUCTION_COURSE_KEYS`, `MotifNode`,
  `PhraseNode`, `SectionNode`, and the existing `ScoreTree.to_dict`,
  `ScoreTree.to_json`, `ScoreTree.from_dict`, and `ScoreTree.minimal`
  semantics unchanged so the existing JSON round-trip and minimal-tree
  tests continue to pass.

## Edge Cases

- Phrase counts of 0 or 1 report `"spare"`; 2 or 3 report `"compact"`;
  4 or 5 report `"developed"`; 6 or more report `"saturated"`.
- `motif_lifecycle_band` returns `"unclassified"` for any string that is
  not in `MOTIF_LIFECYCLE_STATES`.
- `count_motif_lifecycle_states` ignores motifs whose `lifecycle_state`
  is not in `MOTIF_LIFECYCLE_STATES`; `build_score_tree_report` still
  fills every canonical state in `motif_lifecycle_counts` (zero when
  absent).
- `build_score_tree_section_report` de-duplicates motif refs while
  preserving first-seen order across the section's phrases.
- `production_course_complete` is `True` only when `section.production_course`
  has a non-empty value for every key in `PRODUCTION_COURSE_KEYS`.
- `build_score_tree_report` reports `unreferenced_motif_ids` in the
  declaration order of `tree.motifs`; motifs referenced by any phrase
  in any section are excluded.
- A `ScoreTree.minimal(...)` instance reports `section_count=0`,
  `motif_count=0`, `phrase_count=0`, every lifecycle count zero, no
  unreferenced motif ids, and an empty `sections` tuple.
- The hardening checks for narrative HTTP endpoints
  (`/healthz`, `/readyz`, bearer-token auth header) target
  `narrative/` HTTP services, not the score-tree data model. The
  current narrative service already exposes `/healthz` and `/readyz`
  with a bearer token header and is covered by
  `tests/test_smoke_narrative_script.py`; this task keeps that smoke
  test as a mandatory regression anchor.

## Acceptance Criteria

1. Existing score-tree dataclass round-trip and minimal-tree behavior
   remains unchanged.
   VERIFY: `pytest tests/test_score_tree.py -q`

2. `motif_lifecycle_band` maps canonical states to bands and falls back
   to `"unclassified"` for unknown inputs.
   VERIFY: `pytest tests/test_score_tree_depth.py::test_motif_lifecycle_band_maps_states_to_bands -q`

3. `section_phrase_load_band` maps phrase counts to stable named bands
   at the documented cutpoints.
   VERIFY: `pytest tests/test_score_tree_depth.py::test_section_phrase_load_band_maps_counts_to_bands -q`

4. `count_motif_lifecycle_states` returns the per-lifecycle motif counts
   restricted to canonical states.
   VERIFY: `pytest tests/test_score_tree_depth.py::test_count_motif_lifecycle_states_counts_canonical_states -q`

5. `build_score_tree_section_report` returns a frozen
   `ScoreTreeSectionReport` with phrase-load band, ordered motif refs,
   and production-course completeness for one section.
   VERIFY: `pytest tests/test_score_tree_depth.py::test_build_score_tree_section_report_resolves_section_shape -q`

6. `build_score_tree_report` returns a frozen `ScoreTreeReport` with
   per-section reports, lifecycle counts (including zeros for absent
   canonical states), and ordered unreferenced motif ids for a
   populated tree.
   VERIFY: `pytest tests/test_score_tree_depth.py::test_build_score_tree_report_resolves_populated_tree -q`

7. `summarize_score_tree_report` returns a stable JSON-safe operator
   summary that round-trips through `json.dumps`.
   VERIFY: `pytest tests/test_score_tree_depth.py::test_summarize_score_tree_report_returns_json_safe_summary -q`

8. The report path drives the existing `ScoreTree.minimal` constructor:
   a minimal tree reports zero sections, zero motifs, zero phrases, and
   zero counts across every canonical lifecycle state.
   VERIFY: `pytest tests/test_score_tree_depth.py::test_score_tree_report_handles_minimal_tree -q`

9. Fractal depth for `my-claw/tools/senseweave/score_tree.py` reaches at
   least depth 2.
   VERIFY: `pytest tests/test_score_tree_depth.py::test_score_tree_reaches_depth_two -q`

10. Narrative HTTP service smoke regression remains covered (hardening
    anchor for `/healthz`, `/readyz`, and the bearer-token auth header).
    VERIFY: `pytest tests/test_smoke_narrative_script.py -q`

11. Full project validation remains clean.
    VERIFY: `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/`
