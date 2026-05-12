# Task frac-0080 Specification: test_generative_scores Depth 2

## Problem Statement

`tests/test_generative_scores.py` already covers many individual score
generation helpers, but it does not have a named depth-2 gate that proves the
test module contains one coherent end-to-end class. The affected production
module, `my-claw/tools/senseweave/generative_scores.py`, already implements the
simple one-path score surface:

- `generate_melody`
- `generate_bass_line`
- `generate_countermelody`
- `score_from_mood`
- `score_from_narrative_event`
- `score_to_frequencies`

The missing depth-2 work is a deterministic end-to-end test class and a depth
gate that verify those functions produce meaningful output together.

## Technical Approach

- Preserve existing assertions in `tests/test_generative_scores.py`.
- Add `tests/test_test_generative_scores_depth.py` requiring
  `tests/test_generative_scores.py` to contain
  `GenerativeScoresEndToEndTests` and classify at depth >= 2 through the
  repo-local `sdp.fractal.classify_depth`.
- Append `GenerativeScoresEndToEndTests` to `tests/test_generative_scores.py`.
  The class will drive:
  - mood input through `score_from_mood` and `score_to_frequencies`;
  - narrative events through `score_from_narrative_event` and frequency
    conversion;
  - memory fragments and repertoire hints through score metadata, melody
    shaping, JSON-safe hook fields, and frequency output.
- Keep production behavior unchanged unless these tests expose a real gap.
- Treat the generated startup identity hardening checks as regression anchors.
  Existing CLI, first-boot, daemon-ordering, and narrative ASGI tests already
  cover `bootstrap_identity()` before `FirstBootAnnouncer` and identity
  persistence across standalone/federated boots, so this task re-runs those
  anchors instead of changing unrelated startup code.

## Edge Cases

- This depth-2 pass intentionally covers one deterministic happy path rather
  than adding broad malformed-input matrices.
- Existing unit tests remain the authority for individual contour, bass,
  narrative-event, register, and modal-frequency edge cases.
- Score metadata containing hook degrees and section intent must be normal
  JSON strings that round-trip through `json.loads`.
- Frequency conversion must preserve phrase/note counts and produce positive
  frequency/duration pairs.
- No new dependencies, migrations, provider secrets, database columns, runtime
  state files, HTTP routes, or auth behavior are introduced.

## Acceptance Criteria

1. Existing generative-score assertions remain green.
   VERIFY: `pytest tests/test_generative_scores.py -q`

2. The new depth gate confirms `tests/test_generative_scores.py` reaches
   depth >= 2 and contains `GenerativeScoresEndToEndTests`.
   VERIFY: `pytest tests/test_test_generative_scores_depth.py -q`

3. `GenerativeScoresEndToEndTests` drives mood, narrative, memory, metadata,
   JSON-safe diagnostics, and frequency conversion through the public API.
   VERIFY: `pytest tests/test_generative_scores.py::GenerativeScoresEndToEndTests -q`

4. Startup identity hardening remains covered for CLI startup, standalone and
   federated identity persistence, daemon bootstrap-before-announcer ordering,
   and narrative ASGI import persistence.
   VERIFY: `pytest tests/test_cli_identity_hardening.py tests/test_first_boot.py::TestStartupIdentityPersistence tests/test_governor_integration.py::TestStartupIdentityWiring tests/test_narrative_api_main.py::test_asgi_module_startup_bootstraps_identity_persistence_between_imports -q`

5. Product-facing notes mention the frac-0080 generative-score depth-2 work.
   VERIFY: `grep -n "frac-0080" CHANGELOG.md progress.md`

6. Full project validation remains clean.
   VERIFY: `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/`
