# Task frac-0057 Specification: test_agent_selector_quota Depth 2

## Problem Statement

`tests/test_agent_selector_quota.py` owns the regression coverage for the
quota-aware agent selector in `my-claw/tools/agent_selector.py` together with
its `quota_monitor` and `ollama_health` collaborators. The production source
modules already implement meaningful selection, headroom bonuses, alternation
penalty, exploration rolls, state persistence, and Ollama fallback behavior;
`sdp.fractal.classify_depth("my-claw/tools/agent_selector.py")` reports the
selector source above the depth requested by this task.

The affected surface for this task is the test file itself. The current file
classifies at depth 1 (`7/13 trivial, 6 real`): every existing test method
makes a single `selector.select(...)` or `selector.select_pair(...)` call
without iteration or control flow, so most methods land in the trivial bucket
and there is no end-to-end signal that the selector behaves consistently
across sequences of selections, recovering Ollama health, alternation cycles,
or category detection tables.

This task deepens `tests/test_agent_selector_quota.py` to depth 2 by adding a
single `TestAgentSelectorEndToEnd` class with looped, multi-step scenarios
that exercise the real public selector surface end-to-end. Existing tests and
their assertions are preserved unchanged.

## Technical Approach

- Preserve `my-claw/tools/agent_selector.py`, `quota_monitor.py`, and
  `ollama_health.py`. No source behavior change is required because the
  existing public API already produces meaningful output for the new
  scenarios.
- Add a separate red-phase depth gate in
  `tests/test_agent_selector_quota_depth.py` that asserts
  `classify_depth("tests/test_agent_selector_quota.py").depth >= 2`. It fails
  before implementation because the file currently reports depth 1.
- Add `TestAgentSelectorEndToEnd` to `tests/test_agent_selector_quota.py`.
  Each test method contains looped or multi-statement logic (for-loops,
  table sweeps, state cycles) so the fractal classifier records the new
  methods as real logic rather than trivial one-call tests.
- Drive the real public API end-to-end with one-path scenarios:
  - Alternation penalty and last-lead rotation across a long sequence of
    selects.
  - State persistence round-trip through `state_file` (`_save_state`
    →re-instantiate→`_load_state`).
  - Category detection over a representative table of task descriptions.
  - Ollama health recovery cycle: healthy → unhealthy → healthy across
    repeated selects with the real `QuotaMonitor`.
  - `select_pair` over the default provider set returning distinct agents
    when the quota monitor reports all three available.
  - `status_summary` listing every default agent and every quota provider
    when the monitor reports a mixed status table.
  - Per-call `disabled_agents` filtering applied across a sequence of
    selects without persisting between calls.
  - Headroom sweep showing the winner shifts as one provider's headroom
    rises while another's falls.
  - `record_outcome` is safe with a `None` observatory across many calls.
- Keep the implementation test-only, stdlib-only, and free of migrations,
  provider secrets, runtime state writes outside `tmp_path`, database
  columns, HTTP routes, auth changes, or new dependencies.
- Treat the generated startup hardening bullets as verification anchors. The
  startup identity subsystem already has dedicated tests for
  `bootstrap_identity()` persistence and ordering before `FirstBootAnnouncer`
  across standalone/federated startup paths; those are re-run as regression
  anchors rather than expanded inside this test-only task.

## Edge Cases

- The depth gate asserts `depth >= 2` rather than an exact depth string so
  later test-file improvements remain compatible.
- `agent_selector.random.random` is monkeypatched to a constant so the 10%
  exploration roll never fires and selection is deterministic for assertions.
- The `select` rotation state is exercised through `state_file` round-trips
  rather than touching the running selector's private attributes.
- `_eligible_agents` returns `[]` when every agent is disabled, which makes
  `select` raise `ValueError`; the alternation sequence test uses
  per-call `available_agents` so the eligible list is always non-empty.
- Category detection is driven through documented keyword matches
  (e.g. "vpn firewall" → `netops`, "implement" → `coding`, "review" →
  `review`); sentinel descriptions avoid keywords that overlap multiple
  categories.
- Ollama-fallback assertions use the real `QuotaMonitor` with patched
  `_load_provider_headroom` so every provider has identical headroom; the
  category-driven Ollama preference is the only source of variation.
- Pair selection uses the existing `FakeQuotaMonitor` so all three default
  agents are eligible, ensuring `select_pair` returns two distinct agents.
- `status_summary` ordering is asserted using `in` membership rather than
  brittle line-by-line equality.
- No new dependencies, migrations, provider secrets, runtime state files,
  HTTP routes, auth behavior, or database schema changes are introduced.

## Acceptance Criteria

1. Existing quota-aware selector tests remain unchanged and green.
   VERIFY: `pytest tests/test_agent_selector_quota.py -q`

2. The new red-phase depth gate confirms
   `tests/test_agent_selector_quota.py` reaches at least depth 2 after
   implementation.
   VERIFY: `pytest tests/test_agent_selector_quota_depth.py -q`

3. The new end-to-end class covers alternation cycles, state-file round
   trips, category detection tables, Ollama health recovery, pair
   selection over the default provider set, mixed-status status summary,
   per-call disabled-agent filtering, headroom sweeps, and
   observatory-free `record_outcome` safety.
   VERIFY: `pytest tests/test_agent_selector_quota.py::TestAgentSelectorEndToEnd -q`

4. The production agent selector source module remains unchanged in
   behavior and still works through the public selector API.
   VERIFY: `python -c "import os, sys; sys.path.insert(0, os.path.join(os.getcwd(), 'my-claw', 'tools')); import agent_selector, ollama_health; ollama_health.check_health = lambda port: True; sel = agent_selector.AgentSelector(observatory=None, quota_monitor=None, state_file=''); agent_selector.random.random = lambda: 1.0; print(sel.detect_category('vpn firewall routing help'), sel.select('implement the feature', available_agents=['claude', 'codex', 'gemini']))"`

5. Startup identity hardening remains covered for standalone/federated
   persistence and bootstrap-before-announcer ordering.
   VERIFY: `pytest tests/test_cli_identity_hardening.py tests/test_first_boot.py::TestStartupIdentityPersistence tests/test_governor_integration.py::TestStartupIdentityWiring tests/test_narrative_api_main.py::test_asgi_module_startup_bootstraps_identity_persistence_between_imports -q`

6. Full project validation remains clean.
   VERIFY: `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/`
