# Task frac-0051 Specification: PromptClaw Memory Depth 2

## Problem Statement

`promptclaw/memory.py` owns the project-memory journal that the orchestrator
appends a markdown block to after every run (clarification pause + completed
run) and reads back into the lead/verifier prompts on the next run. The module
currently classifies at fractal depth 1 because every method on `MemoryStore`
is a one-line trivial pass-through (`__init__`, `read`, `append_run_summary`),
and the run block string is built inline in `append_run_summary` with no
shared formatter.

That leaves callers and operator diagnostics with no module-owned way to:

- Render a single run's memory block as a string without going through the
  side-effecting `append_run_summary` write path.
- Parse the project-memory file back into structured run entries (run id,
  title, status, lead, verifier, final phase, body) for status reporting,
  resume flows, and tests.
- Aggregate the memory journal into a JSON-safe summary (entry count, latest
  run id, status counts, lead-agent counts) for diagnostics or dashboards.

This task deepens the module to a simple depth-2 implementation by adding
typed helpers, a frozen `MemoryEntry` dataclass, and a few read-side methods
on `MemoryStore` while keeping the existing `read` and `append_run_summary`
behavior, the on-disk markdown shape, and orchestrator call sites unchanged.

## Technical Approach

- Add a frozen `MemoryEntry` dataclass with fields: `run_id`, `title`,
  `status`, `lead_agent`, `verifier_agent`, `final_phase`, `body`.
- Add `format_run_block(state: RunState, summary_text: str) -> str` that
  renders one run's memory block. The rendered string is byte-identical to
  the block currently produced inside `MemoryStore.append_run_summary`
  (leading newline, `## Run <run_id>` header, the five `- Field: value`
  bullets with `n/a` fallbacks for empty lead/verifier, blank line, then
  stripped summary text plus a trailing newline).
- Add `parse_memory_log(text: str) -> tuple[MemoryEntry, ...]` that splits
  the project-memory markdown on `## Run <run_id>` headers, captures the
  five canonical bullets that follow, and treats the remaining lines until
  the next header as the entry body (stripped).
- Add `summarize_memory_log(text: str) -> dict[str, object]` that emits a
  JSON-safe dictionary with `entry_count`, `latest_run_id`, `statuses`
  (sorted status → count), and `lead_agents` (sorted lead-agent name → count,
  excluding the `n/a` placeholder).
- Add `MemoryStore.entries() -> tuple[MemoryEntry, ...]` returning the
  parsed entries from the current memory file (empty when the file is
  missing).
- Add `MemoryStore.latest_entry() -> MemoryEntry | None` returning the most
  recently appended entry or `None` when the journal is empty.
- Add `MemoryStore.summary() -> dict[str, object]` returning the JSON-safe
  aggregate for the current memory file.
- Reroute `MemoryStore.append_run_summary` through `format_run_block` so the
  block string has exactly one source of truth. Existing call sites in
  `promptclaw/orchestrator.py` (clarification pause + final summary) keep
  the same signature and observable file output.
- Use only the standard library plus existing imports. No new dependencies,
  migrations, database columns, secrets, runtime state files, HTTP routes,
  or auth header changes are required. The narrative HTTP smoke surface
  (`/healthz`, `/readyz`, bearer auth) is not modified by this task.

## Edge Cases

- Empty `lead_agent` / `verifier_agent` continue to render as `n/a` in the
  rendered block, matching today's `state.lead_agent or 'n/a'` behavior.
- Summary text is stripped before being appended so trailing blank lines
  do not accumulate in the journal file.
- `parse_memory_log("")` returns an empty tuple.
- A memory file with no `## Run` header returns an empty tuple and a
  summary with `entry_count=0`, `latest_run_id=""`, and empty status /
  lead-agent maps.
- Bullets that follow a `## Run` header but do not match a known canonical
  field name are ignored for header capture; once any non-bullet body line
  appears, all subsequent lines (including bullets) are treated as body
  content for that entry.
- `n/a` lead/verifier values do not increment the lead-agent counter in
  `summarize_memory_log` so aggregate dashboards do not double-count the
  placeholder.
- `MemoryStore.entries()` and `MemoryStore.summary()` return an empty tuple
  / zeroed summary when the memory file does not yet exist.
- The generated startup hardening checks (`/healthz` + `/readyz` endpoints,
  bearer-token auth, `tests/test_smoke_narrative_script.py` regression
  anchor) target narrative HTTP startup wiring outside `promptclaw/memory.py`.
  This task re-runs those anchors to prove memory deepening does not affect
  the narrative HTTP contract.

## Acceptance Criteria

1. Existing orchestrator memory behavior remains unchanged end-to-end.
   VERIFY: `pytest tests/test_orchestrator.py -q`

2. `format_run_block` renders the canonical run block matching the existing
   `MemoryStore.append_run_summary` output byte-for-byte.
   VERIFY: `pytest tests/test_promptclaw_memory_depth.py::test_format_run_block_matches_canonical_layout -q`

3. `MemoryStore.append_run_summary` writes the same block as
   `format_run_block` to the project memory file.
   VERIFY: `pytest tests/test_promptclaw_memory_depth.py::test_append_run_summary_uses_format_run_block -q`

4. `parse_memory_log` parses appended run entries back into typed
   `MemoryEntry` records preserving run id, title, status, lead, verifier,
   final phase, and body content.
   VERIFY: `pytest tests/test_promptclaw_memory_depth.py::test_parse_memory_log_round_trips_appended_entries -q`

5. `parse_memory_log("")` and a memory log with no `## Run` headers return
   empty tuples without raising.
   VERIFY: `pytest tests/test_promptclaw_memory_depth.py::test_parse_memory_log_handles_empty_inputs -q`

6. `summarize_memory_log` emits a JSON-safe aggregate with entry count,
   latest run id, sorted status counts, and sorted lead-agent counts that
   excludes the `n/a` placeholder.
   VERIFY: `pytest tests/test_promptclaw_memory_depth.py::test_summarize_memory_log_is_json_safe_and_aggregates -q`

7. `MemoryStore.entries`, `latest_entry`, and `summary` work end-to-end
   against the on-disk memory file, including the missing-file path.
   VERIFY: `pytest tests/test_promptclaw_memory_depth.py::test_memory_store_read_helpers -q`

8. Fractal depth for `promptclaw/memory.py` reaches at least depth 2.
   VERIFY: `pytest tests/test_promptclaw_memory_depth.py::test_memory_module_reaches_depth_two -q`

9. Startup identity hardening remains covered for CLI startup and
   standalone/federated first-boot persistence.
   VERIFY: `pytest tests/test_cli_identity_hardening.py tests/test_first_boot.py::TestStartupIdentityPersistence tests/test_governor_integration.py::TestStartupIdentityWiring -q`

10. Narrative HTTP smoke surface (`/healthz`, `/readyz`, bearer auth)
    remains green.
    VERIFY: `pytest tests/test_smoke_narrative_script.py -q`

11. Full project validation remains clean.
    VERIFY: `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/`
