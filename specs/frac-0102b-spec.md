# Task frac-0102b Specification: Primary Render Path Depth 2

## Problem Statement

`tests/test_render_pass.py` covers the primary SenseWeave render path
implemented by `my-claw/tools/senseweave/render/pass_.py`: `RenderPass`
canonicalizes registered `RenderRule` instances to `RULE_ORDER`, derives
`effective_k(...)` from enabled flags and quantities, gates rules through
`_roles_allowed_by_rule(...)`, and produces a `PerformedPart` whose
`score`, `applied_rules`, `quantities`, and `metadata` capture the rendered
output of one ordered apply pass. The existing tests focus on per-feature
contracts (rule order, quantity-k, role gating, apply mechanics) but do not
yet have an explicit depth-2 gate or one end-to-end class that drives the
public render-pass surface through a complete register → enable → quantity →
gate → apply → JSON-safe diagnostic lifecycle.

The frac-0102b work is to make the depth-2 contract explicit for the primary
render path test module: add a deterministic depth gate that names the new
end-to-end class, then append one `RenderPassEndToEndTests` class that drives
the existing public render-pass surface through one meaningful lifecycle and
asserts the rendered output is structurally correct (non-empty applied-rules
tuple, ordered canonical IDs, per-rule effective quantities, role-gated
trace, and JSON-safe diagnostic) rather than just running without error.

The generated startup identity hardening bullets target the existing
identity startup subsystem, not this pure render utility. This checkout
already wires `bootstrap_identity()` before `FirstBootAnnouncer` in the
daemon and narrative ASGI startup paths, with standalone/federated identity
persistence covered by regression tests. This task keeps those tests as
mandatory hardening anchors rather than changing unrelated startup code
without a discovered gap.

## Technical Approach

- Add `tests/test_test_render_pass_depth.py` with a deterministic depth gate
  requiring `tests/test_render_pass.py` to contain `RenderPassEndToEndTests`
  and classify at depth >= 2 through the repo-local
  `sdp.fractal.classify_depth`.
- Confirm the red phase by running the new depth gate before
  `RenderPassEndToEndTests` exists.
- Append `RenderPassEndToEndTests` to `tests/test_render_pass.py` without
  modifying existing locked assertions.
- Drive one meaningful primary render-pass lifecycle inside the class:
  - assemble a deterministic three-rule stack registered out of canonical
    order (`R3`, `R1`, `R2`) using the existing `StubRule` test double, with
    `R1` quantity-disabled (`enabled_flags={"R1": False}`), `R2` carrying a
    custom quantity (`quantities={"R2": 0.5}`), and `R3` role-gated
    (`role_gates={"R3": frozenset({"melody", "bass"})}`);
  - confirm `rule_order` canonicalizes to `("R1", "R2", "R3")` and
    `effective_k(...)` returns `0.0` / `0.5` / `1.0` respectively;
  - call `apply(score_tree="root", seeds={"composition": 7})` and assert the
    returned `PerformedPart`:
    - `applied_rules == ("R2", "R3")` (canonical order, `R1` filtered);
    - `quantities == {"R1": 0.0, "R2": 0.5, "R3": 1.0}`;
    - `score["trace"]` contains structurally correct entries (`rule_id`,
      `k`, and forwarded `roles`) for `R2` and `R3`;
    - `metadata == {}` defaults are preserved;
  - call `apply(...)` a second time with a `quantity_overrides={"R1": 0.75}`
    re-enable to assert overrides override the disabled flag and append
    `R1` to `applied_rules`;
  - serialize a JSON-safe diagnostic of `rule_order`, both performed-part
    snapshots (rule IDs, quantities, trace entries with role lists), and
    `effective_k` values through `json.dumps(..., sort_keys=True)` and
    `json.loads(...)`.
- Preserve existing production behavior unless the red tests expose a
  concrete gap.
- Introduce no new dependencies, migrations, provider secrets, database
  columns, runtime state directories, HTTP routes, or auth behavior.

## Edge Cases

- The end-to-end path intentionally covers one happy three-rule baseline
  plus one quantity-override re-enable. Existing focused tests in
  `TestRuleOrder`, `TestQuantityK`, `TestRoleGating`, and `TestApply`
  continue to own duplicate-ID raising, full-stack canonical order,
  non-canonical appending, motif-memory R9, ungated `roles=None` defaults,
  grid-locked role-gate skipping, empty-pass passthrough, seed forwarding,
  and metadata defaults.
- Diagnostics serialize through `json.dumps(..., sort_keys=True)` so the
  payload contains only JSON primitives (lists, dicts, strings, ints,
  floats, bools), with `frozenset` role gates explicitly converted to
  sorted lists before serialization.
- Startup identity hardening remains covered by the existing CLI,
  first-boot, daemon-ordering, and narrative ASGI tests; this task does
  not change identity startup wiring.

## Acceptance Criteria

1. Existing render-pass regression assertions remain green.
   VERIFY: `pytest tests/test_render_pass.py -q`

2. The depth gate confirms `tests/test_render_pass.py` reaches depth >= 2
   and contains `RenderPassEndToEndTests`.
   VERIFY: `pytest tests/test_test_render_pass_depth.py -q`

3. `RenderPassEndToEndTests` drives one meaningful render-pass lifecycle
   through `RenderPass` registration, `rule_order`, `effective_k`,
   `apply(...)`, `quantity_overrides`, `PerformedPart`, and JSON-safe
   diagnostics.
   VERIFY: `pytest tests/test_render_pass.py::RenderPassEndToEndTests -q`

4. Startup identity hardening remains covered for CLI startup, daemon
   startup ordering, standalone/federated identity persistence, and
   narrative ASGI import persistence.
   VERIFY: `pytest tests/test_cli_identity_hardening.py tests/test_first_boot.py::TestStartupIdentityPersistence tests/test_first_boot.py::TestStartupIdentityModePersistence tests/test_governor_integration.py::TestStartupIdentityWiring tests/test_narrative_api_main.py::test_asgi_module_startup_bootstraps_identity_persistence_between_imports -q`

5. Product-facing task notes mention the frac-0102b primary render-path
   deepening.
   VERIFY: `grep -n "frac-0102b" CHANGELOG.md`

6. Full project validation remains clean.
   VERIFY: `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/`
