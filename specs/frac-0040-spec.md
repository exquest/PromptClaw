# Task frac-0040 Specification: PromptClaw Artifacts Depth 2

## Problem Statement

`promptclaw/artifacts.py` owns the on-disk artifact layout for every
PromptClaw run: input task, routing, prompts, agent outputs, handoffs,
summary, and the JSONL event log. It currently classifies at fractal
depth 1 because most of `ArtifactManager`'s methods are three-statement
write wrappers with no validation and no read path. The orchestrator
can write events into `events.jsonl` but no in-process consumer can
read them back through the same module, and operators have no helper
to flag missing filenames before they reach disk.

This task deepens the module to a simple depth-2 implementation by
adding one read path (`read_events`) plus filename validation on the
filename-taking write helpers, while preserving every existing call
site and on-disk filename. No new dependencies, migrations, columns,
or persisted state are introduced.

## Technical Approach

- Add `ArtifactManager.read_events(self) -> list[Event]` that parses
  `events.jsonl` line by line and reconstructs `Event` dataclasses
  using only the fields appended by `append_event`. Missing log file
  returns `[]`. Blank lines are skipped.
- Add filename validation to the four `ArtifactManager` write helpers
  whose path is composed from a caller-supplied filename
  (`write_prompt`, `write_output`, `write_handoff`, `write_summary`).
  Empty/whitespace-only filenames raise `ValueError` before any I/O so
  callers fail fast at the boundary instead of writing an artifact at
  the directory root.
- Preserve all existing public method signatures and return types so
  every existing call site (orchestrator + tests) keeps working
  without changes.
- Keep the module under 100 source lines so `sdp.fractal.classify_depth`
  recognizes it as a "simple implementations" depth-2 module.

## Edge Cases

- `read_events` on a run whose `events.jsonl` does not exist must
  return `[]` rather than raise.
- `read_events` must tolerate trailing blank lines and reconstruct
  every documented `Event` field, defaulting missing keys to the same
  defaults the `Event` dataclass uses.
- `write_*` filename validation must reject empty strings and pure
  whitespace; non-empty filenames pass through unchanged.
- The three filename-less writers (`write_task`, `write_route_json`,
  `write_route_markdown`) keep their existing trivial bodies because
  their inputs are payloads, not paths.
- `append_event` continues to serialize the same JSON shape so the
  round-trip with `read_events` is exact.
- No new dependencies, migrations, database columns, secrets, or
  runtime state files.

## Acceptance Criteria

1. Existing artifact, orchestrator, and config behavior remains
   unchanged.
   VERIFY: `pytest tests/test_orchestrator.py tests/test_config.py -q`

2. `ArtifactManager.read_events` round-trips events written via
   `append_event` and produces meaningful output (full Event list).
   VERIFY: `pytest tests/test_promptclaw_artifacts_depth.py::test_read_events_round_trips_appended_events -q`

3. `read_events` returns `[]` when no event log exists yet.
   VERIFY: `pytest tests/test_promptclaw_artifacts_depth.py::test_read_events_returns_empty_when_log_missing -q`

4. The four filename-taking write helpers reject empty filenames at
   the boundary and accept normal filenames.
   VERIFY: `pytest tests/test_promptclaw_artifacts_depth.py::test_write_helpers_reject_empty_filename tests/test_promptclaw_artifacts_depth.py::test_write_helpers_accept_normal_filenames -q`

5. Fractal depth for `promptclaw/artifacts.py` reaches at least depth 2.
   VERIFY: `pytest tests/test_promptclaw_artifacts_depth.py::test_artifacts_module_reaches_depth_two -q`

6. Full project validation remains clean.
   VERIFY: `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/`
