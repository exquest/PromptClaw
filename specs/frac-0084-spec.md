# Task frac-0084 Specification: test_image_api_spec_parser Depth 2

## Problem Statement

`tests/test_image_api_spec_parser.py` already covers the parser's Shape A,
Shape B, project-slug coherence, malformed-input, and model override behavior
at a helper level. The missing depth-2 work is a named end-to-end parser test
path that proves the existing parser turns representative CT Marketing YAML
payloads into meaningful `InternalSpec` output in one deterministic flow.

The affected production parser already implements the simple one-path surface:

- `parse_spec_yaml`
- `_parse_dimensions`
- `_shape_a_prompt`
- `_shape_b_inferred_prompt`
- `SpecParseError`

This task deepens the test surface without changing existing locked assertions
or production behavior unless the new red tests expose a concrete production
gap.

## Technical Approach

- Preserve existing assertions in `tests/test_image_api_spec_parser.py`.
- Add a depth gate at `tests/test_test_image_api_spec_parser_depth.py` that
  requires `tests/test_image_api_spec_parser.py` to contain
  `TestImageApiSpecParserEndToEnd` and to classify at depth >= 2 through the
  repo-local `sdp.fractal.classify_depth`.
- Append `TestImageApiSpecParserEndToEnd` to
  `tests/test_image_api_spec_parser.py`. The class will drive one deterministic
  public parser path through:
  - explicit prompt YAML normalization,
  - content-derived YAML prompt inference,
  - dimensions, filenames, style, content-piece id, and model override output,
  - JSON-safe `InternalSpec` serialization.
- Use only stdlib test support and existing image API imports.
- Treat the generated startup identity hardening checks as regression anchors.
  Existing CLI, first-boot, daemon-ordering, and narrative ASGI tests already
  cover `bootstrap_identity()` before `FirstBootAnnouncer` and identity
  persistence across standalone/federated boots, so this task re-runs those
  anchors rather than broadening parser code.

## Edge Cases

- This depth-2 pass intentionally exercises one deterministic happy path rather
  than expanding malformed-input matrices.
- Existing helper-level tests remain the authority for invalid YAML,
  non-mapping roots, mismatched project slugs, invalid dimensions, and invalid
  `content_piece_id`.
- The end-to-end parser output must remain JSON-safe through Pydantic's
  `model_dump(mode="json")`.
- No new dependencies, migrations, provider secrets, database columns, runtime
  state files, HTTP routes, or auth behavior are introduced.

## Acceptance Criteria

1. Existing spec-parser assertions remain green.
   VERIFY: `pytest tests/test_image_api_spec_parser.py -q`

2. The new depth gate confirms `tests/test_image_api_spec_parser.py` reaches
   depth >= 2 and contains `TestImageApiSpecParserEndToEnd`.
   VERIFY: `pytest tests/test_test_image_api_spec_parser_depth.py -q`

3. `TestImageApiSpecParserEndToEnd` drives one meaningful public parser path
   through Shape A normalization, Shape B prompt inference, key metadata
   propagation, and JSON-safe `InternalSpec` output.
   VERIFY: `pytest tests/test_image_api_spec_parser.py::TestImageApiSpecParserEndToEnd -q`

4. Startup identity hardening remains covered for CLI startup, standalone and
   federated identity persistence, daemon bootstrap-before-announcer ordering,
   and narrative ASGI import persistence.
   VERIFY: `pytest tests/test_cli_identity_hardening.py tests/test_first_boot.py::TestStartupIdentityPersistence tests/test_governor_integration.py::TestStartupIdentityWiring tests/test_narrative_api_main.py::test_asgi_module_startup_bootstraps_identity_persistence_between_imports -q`

5. Product-facing notes mention the frac-0084 spec-parser depth-2 work.
   VERIFY: `grep -n "frac-0084" CHANGELOG.md progress.md`

6. Full project validation remains clean.
   VERIFY: `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/`
