# Task T-048d: Morph Phrase Test Coverage Hardening

## Problem Statement

T-048a added composer API schema validation for morph phrase requests, T-048b
added composer-side `linear`, `exponential`, and `sigmoid` interpolation
helpers, and T-048c wired endpoint-inclusive single-line phrase generation when
callers provide `phrase_curve`. The existing coverage proves one generated
`sigmoid` / `equal-power` path, but it does not explicitly enumerate every
phrase curve, every SynthDef gain-law curve, or the validation boundary around
generation-only fields.

T-048d hardens tests for the completed T-048 surface and closes one schema gap:
`phrase_frame_count` must not be silently accepted when `phrase_curve` is
omitted, because the route would otherwise ignore a generation-specific field
and return a validation-only response.

## Technical Approach

- Extend `tests/test_composer_api.py` with locked regression tests that:
  - assert each `MorphInterpolationCurve` value can drive end-to-end endpoint
    phrase generation;
  - assert each `MorphCurveType` value is carried into generated frame
    `control_args` as the numeric SuperCollider `morph_curve` value;
  - reject `phrase_frame_count` unless `phrase_curve` is present;
  - expose `SUPPORTED_PHRASE_CURVES` in the schema vocabulary diagnostic.
- Keep the two curve layers distinct:
  - `morph_curve_type` is the SynthDef gain-law selector
    (`linear` / `equal-power`);
  - `phrase_curve` is the composer-side progression curve
    (`linear` / `exponential` / `sigmoid`) used to compute `morph_x`.
- Implement the minimum production change in
  `cypherclaw.composer_api.schemas.MorphPhraseRequest`: if a caller explicitly
  supplies `phrase_frame_count` while omitting `phrase_curve`, validation fails.
- Do not change SuperCollider sources, route paths, database schema, runtime
  state, or startup flow.
- Treat the generated startup-identity hardening bullets as mandatory
  regression anchors. Current code already calls `bootstrap_identity()` in CLI,
  narrative ASGI/import paths, and daemon startup before `FirstBootAnnouncer`;
  T-048d re-runs those tests rather than adding unrelated startup behavior.

## Edge Cases

- Requests without `phrase_curve` and without an explicit `phrase_frame_count`
  keep the T-048a validation-only response shape.
- Requests with `phrase_curve` use default `phrase_frame_count=5` unless the
  caller supplies a valid count.
- `phrase_frame_count < 2` still fails through the existing Pydantic field
  constraint.
- All generated phrase curves preserve exact `morph_x` endpoints of `0.0` and
  `1.0`.
- The `linear` SynthDef gain law must emit `morph_curve=0` in every generated
  frame's `control_args`; `equal-power` must emit `morph_curve=1`.
- No new dependencies, provider secrets, database columns, migrations, runtime
  state directories, agent commands, startup-flow rewiring, or SuperCollider
  source changes are required.

## Acceptance Criteria

1. The schema rejects generation-only `phrase_frame_count` when `phrase_curve`
   is omitted while preserving validation-only requests that omit both fields.
   VERIFY: `pytest tests/test_composer_api.py::test_morph_phrase_endpoint_rejects_frame_count_without_phrase_curve -q`

2. The endpoint generates endpoint-inclusive phrases for every composer-side
   phrase curve (`linear`, `exponential`, `sigmoid`) and each response's
   `morph_x` values match the shared interpolation helper.
   VERIFY: `pytest tests/test_composer_api.py::test_morph_phrase_endpoint_generates_each_phrase_curve_type -q`

3. The endpoint carries every SynthDef gain-law curve (`linear`,
   `equal-power`) into generated frame control args using the numeric
   SuperCollider values.
   VERIFY: `pytest tests/test_composer_api.py::test_morph_phrase_endpoint_generates_each_synth_gain_law_curve_type -q`

4. Schema diagnostics export canonical supported voices, SynthDef gain-law
   curve types, phrase curves, and numeric gain-law mappings.
   VERIFY: `pytest tests/test_composer_api.py::test_morph_phrase_schema_exports_supported_vocabularies -q`

5. Existing T-048 interpolation and generation tests remain compatible with the
   hardened schema.
   VERIFY: `pytest tests/test_composer_api.py tests/test_instrument_morph_curves.py -q`

6. Startup identity hardening remains covered for CLI startup,
   bootstrap-before-`FirstBootAnnouncer` ordering, standalone/federated
   persistence, and narrative ASGI import persistence.
   VERIFY: `pytest tests/test_cli_identity_hardening.py tests/test_first_boot.py::TestStartupIdentityPersistence tests/test_first_boot.py::TestStartupIdentityModePersistence tests/test_governor_integration.py::TestStartupIdentityWiring tests/test_narrative_api_main.py::test_asgi_module_startup_bootstraps_identity_persistence_between_imports -q`

7. Task documentation and status mention T-048d, schema validation, every curve
   type, end-to-end morph phrase generation, no migration, no new dependencies,
   and startup identity hardening.
   VERIFY: `rg -n "T-048d|schema validation|every curve|end-to-end morph phrase|No new dependencies|No database|startup identity" specs/t-048d-spec.md CHANGELOG.md progress.md ESCALATIONS.md`

8. Required final validation passes.
   VERIFY: `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/`
