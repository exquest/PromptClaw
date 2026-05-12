# Verification Report — frac-0107

**Verify Agent:** Claude Sonnet 4.6 (VERIFY)
**Date:** 2026-05-02
**Artifacts Reviewed:**
- `tests/test_research_runtime.py` (diff HEAD~3)
- `tests/test_test_research_runtime_depth.py` (new file)
- `specs/frac-0107-spec.md`
- `ESCALATIONS.md` (frac-0107 entry)
- `CHANGELOG.md` (frac-0107 entry)
- `progress.md` (frac-0107 entry)

## Correctness

All six acceptance criteria are met:

1. Existing research-runtime tests remain green — `pytest tests/test_research_runtime.py -q` → **5 passed**.
2. Depth gate confirms `tests/test_research_runtime.py` reaches depth >= 2 and contains the named class/method — `pytest tests/test_test_research_runtime_depth.py -q` → **1 passed**.
3. `ResearchRuntimeEndToEndTests::test_auto_deep_research_persists_verified_report_and_json_diagnostic` drives the full auto-deep lifecycle (scope auto→deep, five monkeypatched agents, Observatory events, progress messages, `tmp_path` persisted report, confidence breakdown, JSON round-trip) — **1 passed**.
4. Startup identity hardening regression anchors (`test_cli_identity_hardening`, `TestStartupIdentityPersistence`, `TestStartupIdentityModePersistence`, `TestStartupIdentityWiring`, `test_asgi_module_startup_bootstraps_identity_persistence_between_imports`) → **11 passed**.
5. `grep -n "frac-0107" CHANGELOG.md progress.md` returns entries in both files with correct no-new-dependencies/migrations language.
6. Full project validation previously recorded as `4651 passed, 3 skipped`, Ruff clean, mypy clean (per ESCALATIONS.md red-phase/validation entry).

The end-to-end test verifies: `scope == "deep"`, `verified is True`, `sources_count == 3`, confidence breakdown `{"high": 2, "medium": 1, "low": 0}`, ordered source types `[web, academic, codebase]`, lifecycle events `[research_started, research_completed]`, user-facing messages, agent call counts per provider, timeout set `{60, 90, 120}`, one persisted markdown report with expected sections/URLs, and a full JSON diagnostic round-trip. All assertions are exercised by the deterministic fake agent/tools doubles.

## Completeness

The spec's single happy-path requirement is fully covered. The depth gate enforces structural presence of the class and named method via AST. Red-phase confirmation is documented in ESCALATIONS.md. No edge-case scope is missing per spec design: existing focused tests own quick/medium routing, HTML cleanup, experiment execution, and benchmark ordering. The startup identity surface is covered by regression anchors rather than new code.

Candidate hardening items:
- *Runtime does not invoke `bootstrap_identity` on startup* — addressed: spec and ESCALATIONS.md note that daemon poll loops already call `bootstrap_identity()` before `FirstBootAnnouncer`; 11 existing identity tests confirmed green as regression anchors.
- *`bootstrap_identity()` in startup flow* — confirmed covered by existing tests, no change needed.
- *Standalone and federated modes* — `TestStartupIdentityModePersistence` covers both; confirmed green.
- *Integration test for identity persistence between boots* — `test_asgi_module_startup_bootstraps_identity_persistence_between_imports` and `TestStartupIdentityPersistence` serve this role; both green.

## Consistency

The new `ResearchRuntimeEndToEndTests` class follows the established depth-2 pattern: `__test__ = True` on the class, one long deterministic method name matching the spec, `monkeypatch` + `tmp_path` fixtures, `FakeTools`/`FakeObservatory` test doubles already defined in the file. The depth gate file mirrors the pattern used in `frac-0091`, `frac-0093`, `frac-0106`, etc. No existing locked assertions were modified.

## Security

No secrets, credentials, provider tokens, or external network calls are introduced. The fake agent runner keeps tests fully hermetic. The `tmp_path` fixture scopes all file writes to pytest's temporary directory. No new dependencies, HTTP routes, or auth behavior introduced. No injectable strings pass through unsafe shell invocations.

## Quality

- Test is deterministic and hermetic (fake agent, fake tools, `tmp_path`).
- All assertions are specific and meaningful — no placeholder or trivially-true checks.
- JSON round-trip assertion validates operator diagnostic serializability end-to-end.
- `ThreadPoolExecutor` ordering sensitivity is avoided by counting calls per-provider rather than by call order.
- Ruff and mypy clean per ESCALATIONS.md validation record.
- CHANGELOG and progress.md updated.

## Issues Found

None.

## Verdict: PASS

## Notes for Lead Agent

Work is clean. No items to address.
