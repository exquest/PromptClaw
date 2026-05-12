# Task frac-0116c Specification: sw_sampler End-to-End Diagnostic Exhaustive Coverage

## Problem Statement

`SwSamplerEndToEndTests.test_sw_sampler_source_and_runtime_harness_round_trip_json_diagnostic`
in `tests/test_sw_sampler.py` (added by frac-0116) constructs a JSON-safe
diagnostic payload covering the granular SynthDef control surface and the
SC-side runtime harness, and asserts it round-trips through
`json.dumps(..., sort_keys=True)`. Coverage of the round-tripped payload is
currently a spot-check rather than exhaustive:

- `defaults` is asserted on six of fourteen documented controls (`amp`,
  `grain_size_ms`, `density`, `gate`, `out_bus`, `fx_send`); the remaining
  eight (`bufnum`, `position`, `position_rate`,
  `pitch_transpose_semitones`, `pitch_jitter_semitones`, `attack_sec`,
  `release_sec`, `fx_bus`) are constructed but not asserted on the
  round-tripped payload, so a regression that drops a key during
  serialization or constructor-side filtering would not surface.
- `signal_chain` equality is asserted, but not the cardinality of the
  list, so a future refactor that introduces a duplicate label or extra
  stage would still be accepted by the equality check only by coincidence.

This task tightens the end-to-end coverage from spot-check to exhaustive:
the round-tripped diagnostic dict must carry exactly all fourteen
documented argument names in `defaults` and exactly all eight canonical
signal-chain stages.

The active ADP process is the task prompt's Explore -> Specify -> Test ->
Implement -> Verify -> Document workflow.

## Technical Approach

- Add new assertions to the existing
  `test_sw_sampler_source_and_runtime_harness_round_trip_json_diagnostic`
  method. The new assertions are *additive* — existing assertions are
  preserved verbatim so the locked frac-0116 acceptance criteria still
  hold.
- The added assertions:
  - `set(round_tripped["defaults"].keys())` equals the canonical
    fourteen-name set;
  - `len(round_tripped["defaults"]) == 14` so duplicates or extras are
    rejected;
  - `set(round_tripped["signal_chain"])` equals the canonical eight-stage
    set;
  - `len(round_tripped["signal_chain"]) == 8` so duplicates or extras are
    rejected.
- The production source already supplies meaningful values for all
  fourteen controls and the diagnostic constructor already enumerates
  them, so the new assertions pass against the current code on first
  run; this task therefore deepens the test surface without modifying
  runtime code.
- Introduce no new dependencies, migrations, provider secrets, database
  columns, runtime state directories, HTTP routes, or auth behavior.

## Edge Cases

- The new assertions intentionally use set equality plus explicit length
  so a duplicate stage label or duplicate default key is rejected even
  though set equality alone would mask it.
- The existing list-equality assertion on `signal_chain` continues to
  pin the canonical source order; the new set/length pair guards against
  drift in cardinality and content independently of order.
- The existing per-control numeric assertions remain authoritative for
  default values; this task only widens the *key set* coverage, not the
  per-key value coverage.
- The generated startup identity hardening bullets target the existing
  identity startup subsystem and remain covered by the CLI, first-boot,
  daemon-ordering, standalone/federated identity, and narrative ASGI
  import tests; this task does not change that surface.

## Acceptance Criteria

1. Exploration findings and assumptions are recorded for frac-0116c.
   VERIFY: `grep -n "frac-0116c" progress.md ESCALATIONS.md`

2. The specification documents the exhaustive-coverage scope and
   acceptance criteria.
   VERIFY: `test -f specs/frac-0116c-spec.md && grep -n "exhaustive" specs/frac-0116c-spec.md`

3. The end-to-end test asserts the round-tripped `defaults` dict contains
   exactly the fourteen documented argument names (set equality plus
   length).
   VERIFY: `grep -n "len(round_tripped\\[\"defaults\"\\]) == 14" tests/test_sw_sampler.py`

4. The end-to-end test asserts the round-tripped `signal_chain` list
   contains exactly the eight canonical stages (set equality plus
   length).
   VERIFY: `grep -n "len(round_tripped\\[\"signal_chain\"\\]) == 8" tests/test_sw_sampler.py`

5. Existing sw_sampler assertions, the depth gate, and the
   end-to-end class continue to pass.
   VERIFY: `pytest tests/test_sw_sampler.py tests/test_test_sw_sampler_depth.py -q`

6. Startup identity hardening remains covered for CLI startup, daemon
   startup ordering, standalone/federated identity persistence, and
   narrative ASGI import persistence.
   VERIFY: `pytest tests/test_cli_identity_hardening.py tests/test_first_boot.py::TestStartupIdentityPersistence tests/test_first_boot.py::TestStartupIdentityModePersistence tests/test_governor_integration.py::TestStartupIdentityWiring tests/test_narrative_api_main.py::test_asgi_module_startup_bootstraps_identity_persistence_between_imports -q`

7. Product-facing task notes mention frac-0116c tightening end-to-end
   coverage from spot-check to exhaustive without dependencies or
   migrations.
   VERIFY: `grep -n "frac-0116c" CHANGELOG.md progress.md ESCALATIONS.md`

8. Full project validation remains clean.
   VERIFY: `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/`
