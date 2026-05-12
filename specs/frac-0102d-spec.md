# Task frac-0102d Specification: Gate Suite Run + Render-Ablation Depth-2 Completion Note

## Problem Statement

The frac-0102 split delivered depth-2 render-ablation coverage across three
predecessor sub-tasks: frac-0102 added the `RenderAblationEndToEndTests` class
covering the public ablation surface end-to-end, frac-0102a captured the
pre-depth-2 baseline and gap list in
`sdp/notes/frac-0102a-render-ablation-depth.md`, and frac-0102c added the
final-artifact assertion `test_full_pipeline_final_rendered_artifact_shape_and_content`
along with the depth-gate test that requires that method by name.

Two loose ends remain for frac-0102d:

1. The full project gate (`pip install -e '.[dev]' && pytest tests/ -x &&
   ruff check src/ tests/ && mypy src/`) needs to be re-run on the current
   tree so that any failures introduced by the frac-0102c assertion landing
   are surfaced and fixed.
2. The render-ablation validation document at
   `sdp/notes/frac-0102a-render-ablation-depth.md` still describes only the
   pre-depth-2 baseline and lists gaps as open. It does not yet record that
   depth-2 coverage is complete, which gap each landed assertion closes, or
   which subsequent task ID delivered the close. Future readers of the notes
   currently cannot see that the depth-2 work shipped.

The generated startup identity hardening bullets target the existing identity
startup subsystem (CLI startup, daemon ordering, narrative ASGI, standalone /
federated identity persistence). They are already covered by anchor tests,
which this task re-runs as regressions. No identity startup wiring is changed.

## Technical Approach

- Run the gate suite up front to confirm the current `HEAD` is clean. The
  recorded result at the start of frac-0102d was `4620 passed, 3 skipped`,
  Ruff clean, mypy clean. If the gate is dirty, fix the regressions before
  any other work and document the fix in `ESCALATIONS.md`.
- Add a red contract test
  (`tests/test_frac_0102d_depth_completion.py`) that asserts
  `sdp/notes/frac-0102a-render-ablation-depth.md` includes a
  `Depth-2 Completion` section with explicit references to:
  - `RenderAblationEndToEndTests`;
  - `test_full_pipeline_final_rendered_artifact_shape_and_content`;
  - the closing task IDs `frac-0102` and `frac-0102c`;
  - the production module `my-claw/tools/senseweave/render/ablation.py`;
  - the public surface symbols `rule_identifiers`, `filter_active_rules`,
    `ablate`, `build_ablation_cases`, `run_ablation_suite`, and
    `summarize_ablation_suite`;
  - at least one `- Closed:` bullet per landed gap noted in the existing
    `Concrete Gaps` section that has actually been delivered.
- Confirm the red phase by running the new contract test before editing the
  notes file.
- Append a `Depth-2 Completion` section to
  `sdp/notes/frac-0102a-render-ablation-depth.md` that:
  - states depth-2 coverage is complete and identifies the locked test class
    and final-artifact method by name;
  - cross-references the task IDs that closed each tracked gap;
  - lists each previously open gap with a `- Closed:` line that names the
    delivering task ID, plus any gaps that remain intentionally open (e.g.,
    duplicate active/disabled IDs, no-rule default-renderer path);
  - does not modify the existing `Pre-Depth-2 Baseline`, `Exercised Paths`,
    `Smoke-Checked Outputs`, or `Concrete Gaps` sections, since those describe
    the pre-depth-2 baseline and are referenced by
    `tests/test_frac_0102a_notes.py`.
- Update `CHANGELOG.md`, `progress.md`, and `ESCALATIONS.md` to mention
  `frac-0102d`.
- Re-run the full gate after the documentation update.
- Introduce no new dependencies, migrations, provider secrets, database
  columns, runtime state directories, HTTP routes, or auth behavior.

## Edge Cases

- The pre-depth-2 baseline sections must remain intact so the existing
  `tests/test_frac_0102a_notes.py` contract continues to pass. The new
  section is appended below them.
- The new contract test reads the file from the repo root, so it must use a
  `Path(...)` resolved relative to the repository, matching the existing
  notes test pattern.
- Gap closures that reference symbol names use exact production identifiers
  (`rule_identifiers`, `filter_active_rules`, etc.) so the contract test can
  enforce them with substring assertions.
- Any new validation gate failure introduced by frac-0102c surfacing on
  re-run is fixed in this task and recorded in `ESCALATIONS.md`. If no
  failure surfaces, the escalation entry records the clean re-run result.

## Acceptance Criteria

1. The frac-0102d depth-completion contract test passes.
   VERIFY: `pytest tests/test_frac_0102d_depth_completion.py -q`

2. The pre-existing render-ablation notes contract still passes.
   VERIFY: `pytest tests/test_frac_0102a_notes.py -q`

3. The full render-ablation depth-gate plus regression suite remains green.
   VERIFY: `pytest tests/test_render_ablation.py tests/test_test_render_ablation_depth.py -q`

4. Startup identity hardening anchors remain green.
   VERIFY: `pytest tests/test_cli_identity_hardening.py tests/test_first_boot.py::TestStartupIdentityPersistence tests/test_first_boot.py::TestStartupIdentityModePersistence tests/test_governor_integration.py::TestStartupIdentityWiring tests/test_narrative_api_main.py::test_asgi_module_startup_bootstraps_identity_persistence_between_imports -q`

5. Product-facing task notes mention `frac-0102d`.
   VERIFY: `grep -n "frac-0102d" CHANGELOG.md progress.md ESCALATIONS.md`

6. Full project validation remains clean.
   VERIFY: `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/`
