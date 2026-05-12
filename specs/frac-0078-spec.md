# Task frac-0078 Specification: test_generation_health Depth 2

## Problem Statement

`tests/test_generation_health.py` covers the IDyOM KL-divergence audit helpers
and core signal rules, but it does not yet prove the generation-health surface
works end-to-end as one deterministic operator path. The production module
`my-claw/tools/senseweave/generation/health.py` already exposes the needed
surface:

- `idyom_kl_divergence_audit`
- `AuditEntry`
- `AuditReport`
- rolling history persistence
- collapse alert JSON output
- `_main()` config-driven entry point

The missing depth-2 work is a locked end-to-end test class plus a depth gate.
The one-path scenario should create current and week-0 LTM files, drive several
weekly audit runs through the real public function, persist history, produce a
JSON-safe `AuditReport`, write the alert only when all three collapse signals
align, and verify the config-driven CLI entry point prints the same meaningful
diagnostic shape without modifying the LTM files.

## Technical Approach

- Preserve the existing helper assertions in `tests/test_generation_health.py`.
- Add a depth gate in `tests/test_test_generation_health_depth.py` requiring
  `tests/test_generation_health.py` to contain `GenerationHealthEndToEndTests`
  and classify at depth >= 2 via the repo-local `sdp.fractal.classify_depth`.
- Append `GenerationHealthEndToEndTests` to `tests/test_generation_health.py`.
- Drive the existing public audit API through deterministic temp files:
  - write a seed snapshot and weekly current LTM files;
  - run three weekly audits with increasing KL, high generated ratio, and
    decreasing CLAP centroid variance;
  - assert persisted history shape, week indexes, timestamps, flag reason,
    alert payload, and JSON-safe report round-trip;
  - assert current and snapshot LTM hashes are unchanged after the audit;
  - run `_main()` with `IDYOM_KL_AUDIT_CONFIG` and capture printed JSON.
- Keep production behavior unchanged unless the tests expose a real gap.
- Treat the generated startup identity hardening checks as regression anchors.
  Existing CLI, daemon, first-boot, and narrative ASGI tests already cover
  `bootstrap_identity()` before `FirstBootAnnouncer` and standalone/federated
  identity persistence, so this task re-runs those anchors rather than changing
  unrelated startup code.

## Edge Cases

- This depth-2 pass intentionally exercises one deterministic operator path
  rather than every malformed LTM or config shape.
- Collapse should not flag before the minimum trend window; the end-to-end
  path uses three observations so the final report can flag.
- The alert file should be absent before the final collapse-aligned run and
  present afterward.
- The audit must never mutate the snapshot or current LTM files.
- The CLI path must read its JSON config from `IDYOM_KL_AUDIT_CONFIG` and
  print JSON-safe diagnostics.
- No new dependencies, migrations, provider secrets, database columns, runtime
  state directories, HTTP routes, or auth behavior are introduced.

## Acceptance Criteria

1. Existing generation-health helper assertions remain green.
   VERIFY: `pytest tests/test_generation_health.py -q`

2. The new depth gate confirms `tests/test_generation_health.py` reaches
   depth >= 2 and contains `GenerationHealthEndToEndTests`.
   VERIFY: `pytest tests/test_test_generation_health_depth.py -q`

3. `GenerationHealthEndToEndTests` drives the full LTM snapshot -> weekly
   audit -> rolling history -> alert -> JSON diagnostic -> CLI config path
   through the public API.
   VERIFY: `pytest tests/test_generation_health.py::GenerationHealthEndToEndTests -q`

4. Startup identity hardening remains covered for CLI startup, standalone and
   federated identity persistence, daemon bootstrap-before-announcer ordering,
   and narrative ASGI import persistence.
   VERIFY: `pytest tests/test_cli_identity_hardening.py tests/test_first_boot.py::TestStartupIdentityPersistence tests/test_governor_integration.py::TestStartupIdentityWiring tests/test_narrative_api_main.py::test_asgi_module_startup_bootstraps_identity_persistence_between_imports -q`

5. Product-facing notes mention the frac-0078 generation-health depth-2 work.
   VERIFY: `grep -n "frac-0078" CHANGELOG.md progress.md`

6. Full project validation remains clean.
   VERIFY: `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/`
