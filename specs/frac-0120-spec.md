# Task frac-0120 Specification: test_voice_aliases Depth 2

## Problem Statement

`tests/test_voice_aliases.py` currently verifies the runtime-safe voice alias
lookup surface at focused helper depth: each assertion calls
`resolve_runtime_voice_name(...)` for one alias or passthrough voice. That keeps
the legacy lookup behavior protected, but it does not exercise the complete
diagnostic path added to `my-claw/tools/senseweave/voice_aliases.py` in
frac-0032: alias-table iteration, report construction, JSON-safe summary
generation, and agreement between the report and runtime lookup behavior.

The production module already implements a simple one-path solution:
`RUNTIME_VOICE_ALIAS` drives `resolve_runtime_voice_name(...)`,
`build_voice_alias_report()`, `summarize_voice_alias_report(...)`, and the
supporting alias-chain/target helpers. This task therefore deepens the base
test file rather than changing production code unless the red tests expose a
concrete gap.

The generated startup identity hardening bullets target the existing identity
startup subsystem. Current CLI, first-boot, daemon-ordering, standalone /
federated persistence, and narrative ASGI tests already cover
`bootstrap_identity()` being invoked before `FirstBootAnnouncer` and identity
persistence between boots. This task keeps those tests as mandatory regression
anchors instead of changing unrelated startup flow.

The active ADP process is the task prompt's Explore -> Specify -> Test ->
Implement -> Verify -> Document workflow, as mirrored in
`sdp/templates/candidates/lead_t2/v006.md`.

## Technical Approach

- Add `tests/test_test_voice_aliases_depth.py` using the recent depth-gate
  pattern from `tests/test_test_synthesis_architecture_registry_depth.py` and
  `tests/test_test_theramini_duet_depth.py`. The gate requires:
  - `VoiceAliasesEndToEndTests` exists in `tests/test_voice_aliases.py`;
  - the named method
    `test_runtime_alias_report_round_trips_json_diagnostic` exists;
  - `classify_depth("tests/test_voice_aliases.py").depth >= 2`;
  - the test module declares a machine-readable depth-2 marker either in the
    module docstring (`depth: 2`) or as a top-level `DEPTH = 2` constant.
- Confirm the red phase by running the new depth gate before the end-to-end
  class and marker exist.
- Extend `tests/test_voice_aliases.py` without modifying existing lookup
  assertions:
  - add a module docstring with `depth: 2`;
  - import `json` and the existing report/chain helpers from
    `senseweave.voice_aliases`;
  - append `VoiceAliasesEndToEndTests` with one deterministic end-to-end
    diagnostic test.
- The end-to-end test will:
  - resolve a representative requested voice path (`gong`, `sw_grain`,
    `tabla_ge`, and unaliased `bowed`) through `resolve_runtime_voice_name`;
  - build the full `VoiceAliasReport`;
  - summarize it with `summarize_voice_alias_report(...)`;
  - assert the summary contains meaningful alias-table output: total aliases,
    namespace counts, family counts, target-to-sources mapping, and per-entry
    source-to-target data;
  - assert the report agrees with `alias_chain(...)` and
    `aliases_for_target(...)` for representative core and SenseWeave aliases;
  - round-trip a primitive operator diagnostic through
    `json.dumps(..., sort_keys=True)` and `json.loads(...)`.
- Preserve production behavior unless the red tests reveal a source gap.
- Introduce no new dependencies, migrations, provider secrets, database
  columns, runtime state directories, HTTP routes, auth behavior, or agent
  command strings.

## Edge Cases

- This is intentionally one happy-path diagnostic test. Existing focused tests
  remain responsible for individual alias pairs and passthrough lookup behavior.
- Unknown voice passthrough is still covered by
  `test_resolve_runtime_voice_name_preserves_normal_voice`; the end-to-end test
  includes `bowed` as a normal runtime voice to prove mixed alias/passthrough
  diagnostics do not require a second code path.
- JSON diagnostics only include strings, ints, booleans, lists, and nested
  dictionaries, so serialization remains deterministic and hermetic.
- No database schema changes are introduced, so no migration or index work is
  required.
- Startup identity hardening remains a regression anchor and is not widened
  inside the voice-alias tests.

## Acceptance Criteria

1. Existing voice-alias lookup assertions remain green.
   VERIFY: `pytest tests/test_voice_aliases.py -q`

2. The depth gate confirms `tests/test_voice_aliases.py` reaches depth >= 2
   and contains the named end-to-end class/method plus the machine-readable
   depth-2 marker.
   VERIFY: `pytest tests/test_test_voice_aliases_depth.py -q`

3. `VoiceAliasesEndToEndTests` drives lookup resolution, report generation,
   JSON-safe summary construction, alias-chain/target helper agreement, and
   diagnostic JSON round-trip through one meaningful path.
   VERIFY: `pytest tests/test_voice_aliases.py::VoiceAliasesEndToEndTests -q`

4. The existing production helper depth tests remain green.
   VERIFY: `pytest tests/test_voice_aliases_depth.py -q`

5. Startup identity hardening remains covered for CLI startup, daemon startup
   ordering, standalone/federated identity persistence, and narrative ASGI
   import persistence.
   VERIFY: `pytest tests/test_cli_identity_hardening.py tests/test_first_boot.py::TestStartupIdentityPersistence tests/test_first_boot.py::TestStartupIdentityModePersistence tests/test_governor_integration.py::TestStartupIdentityWiring tests/test_narrative_api_main.py::test_asgi_module_startup_bootstraps_identity_persistence_between_imports -q`

6. Product-facing task notes mention the frac-0120 voice-alias test deepening
   with no new dependencies or migrations.
   VERIFY: `grep -n "frac-0120" CHANGELOG.md progress.md ESCALATIONS.md`

7. Full project validation remains clean.
   VERIFY: `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/`
