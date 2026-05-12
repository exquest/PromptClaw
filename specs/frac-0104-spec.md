# Task frac-0104 Specification: test_render_events Depth 2

## Problem Statement

`tests/test_render_events.py` covers the focused behavior of
`src/cypherclaw/render/events.py`: the `IntentTag` enum, the `Event`
dataclass field contract / score-field locking / JSON + OSC round-trip,
the `PerformanceIntent` defaults and validation envelope, and the
`SectionEnvelope` linear/spline interpolation and parameter validation.
Each existing test exercises a single helper-level concern in isolation
and the production module already implements the simple one-path
behavior required by the render contract.

The missing frac-0104 work is to deepen the test module itself from
helper-level coverage to an explicit depth-2 contract. The test file
needs a deterministic depth gate plus one named end-to-end class that
drives a realistic render-events lifecycle end to end across the public
surface (envelope sampling → intent definition → event population →
score-field locking → JSON / OSC round-trip → JSON-safe combined
diagnostic) without modifying any locked existing assertions.

The generated startup identity hardening bullets target the existing
identity startup subsystem, not this pure render-events data-contract
module. Current regression tests already cover `bootstrap_identity()`
before `FirstBootAnnouncer`, CLI and narrative ASGI startup, and
standalone/federated identity persistence. This task keeps those tests
as mandatory hardening anchors rather than changing unrelated startup
code without a discovered gap.

## Technical Approach

- Add `tests/test_test_render_events_depth.py` with a deterministic
  depth gate requiring `tests/test_render_events.py` to contain
  `RenderEventsEndToEndTests` and the method
  `test_full_render_events_lifecycle_is_json_and_osc_round_trip_safe`.
- Confirm the red phase by running the new depth gate before the
  end-to-end class exists.
- Append `RenderEventsEndToEndTests` to `tests/test_render_events.py`
  without modifying existing assertions, and drive one meaningful
  public path through the existing `IntentTag`, `PerformanceIntent`,
  `SectionEnvelope`, `SectionEnvelopeSample`, and `Event` surface:
  - construct a `SectionEnvelope` with non-trivial breakpoints across
    every `SECTION_ENVELOPE_PARAMETERS` channel and assert that
    `sample(...)` and per-parameter `value_at(...)` agree on a
    deterministic mid-section position;
  - construct a `PerformanceIntent` with non-default arc + tension +
    call-response values and assert each declared field round-trips
    on the dataclass;
  - construct two `Event` instances (one phrase start, one phrase
    end / cadential) populated with realistic `IntentTag` values,
    `seed_path` tuple, `rule_stack`, `section_envelope`, and
    sensor-driven score fields;
  - exercise `lock_score_fields()` and assert all
    `Event.SCORE_LEVEL_FIELDS` are now frozen while non-score fields
    (`onset_sec`, `timing_deviation_ms`, `sensor_brightness`,
    `rule_stack`) remain mutable and accept new values;
  - round-trip both events through `to_json_dict()` /
    `from_json_dict()`, `to_json()` / `from_json()`, and
    `to_osc_bundle()` / `from_osc_bundle()` and assert structural
    equality (preserving `seed_path` tuple identity);
  - build a JSON-safe combined diagnostic that includes
    `IntentTag` membership, `VALID_ARC_SHAPES`,
    `SECTION_ENVELOPE_PARAMETERS`, the sampled envelope values, the
    `PerformanceIntent` snapshot, and both event JSON dicts, then
    round-trip through `json.dumps(..., sort_keys=True)`.
- Preserve existing production behavior unless the red tests expose a
  concrete gap.
- Introduce no new dependencies, migrations, provider secrets, database
  columns, runtime state directories, HTTP routes, or auth behavior.

## Edge Cases

- The end-to-end path covers one realistic mixed-intent two-event piece,
  not every interpolation branch or every `PerformanceIntent` validation
  bound. Existing focused tests continue to own per-field validation,
  spline vs. linear interpolation parity, and individual frozen-field
  rejection.
- The depth gate checks class and method names in addition to
  `sdp.fractal.classify_depth(...)`, so it remains meaningful even in
  checkouts where the fractal classifier is test-doubled.
- The combined diagnostic uses only JSON primitives so render
  diagnostics can be consumed by metrics gates and operator tooling
  without custom encoding; `IntentTag` values, `frozenset` constants,
  and tuple `seed_path` values are explicitly converted to sorted
  lists / tuples before serialization.
- Startup identity hardening remains covered by existing startup tests;
  no startup source changes are expected for this render-events task.

## Acceptance Criteria

1. Existing render-events assertions remain green.
   VERIFY: `pytest tests/test_render_events.py -q`

2. The depth gate confirms `tests/test_render_events.py` reaches depth
   >= 2 and contains the named end-to-end class/method.
   VERIFY: `pytest tests/test_test_render_events_depth.py -q`

3. `RenderEventsEndToEndTests` drives the full public render-events
   lifecycle and JSON-safe diagnostics.
   VERIFY: `pytest tests/test_render_events.py::RenderEventsEndToEndTests -q`

4. Startup identity hardening remains covered for CLI startup, daemon
   startup ordering, standalone/federated identity persistence, and
   narrative ASGI import persistence.
   VERIFY: `pytest tests/test_cli_identity_hardening.py tests/test_first_boot.py::TestStartupIdentityPersistence tests/test_first_boot.py::TestStartupIdentityModePersistence tests/test_governor_integration.py::TestStartupIdentityWiring tests/test_narrative_api_main.py::test_asgi_module_startup_bootstraps_identity_persistence_between_imports -q`

5. Product-facing task notes mention the frac-0104 render-events test
   deepening.
   VERIFY: `grep -n "frac-0104" CHANGELOG.md progress.md`

6. Full project validation remains clean.
   VERIFY: `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/`
