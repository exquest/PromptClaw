# Task frac-0013 Specification: Phrase Tracker Depth 2

## Problem Statement

`my-claw/tools/senseweave/phrase_tracker.py` currently provides a working
tick-level `PhraseTracker`: callers feed `(is_playing, now)` ticks and receive
`"phrase_started"` / `"phrase_ended"` boundary events. That contract is already
used by `midi_keyboard_listener.py`, `theramini_listener.py`, and
`PhraseCaptureWriter`, but the module remains fractal depth 1 because its
public surface is mostly state accessors around one event detector.

The task is to deepen the module to a simple depth-2 implementation: keep the
existing tracker behavior unchanged while adding a one-path stream helper that
turns listener ticks into typed boundary records and a stable aggregate summary.
This gives tests and runtime diagnostics meaningful end-to-end output without
changing listener wiring or phrase persistence semantics.

## Technical Approach

- Add frozen dataclasses:
  - `PhraseBoundary(event, timestamp, duration_seconds)` for one emitted
    phrase boundary.
  - `PhraseStreamSummary(phrase_count, total_phrase_seconds,
    longest_phrase_seconds, events)` for an aggregate view of completed phrases.
- Add `track_phrase_boundaries(ticks, *, threshold_seconds=...)`:
  - Accept an iterable of `(is_playing, timestamp)` tuples.
  - Drive a fresh `PhraseTracker` with the requested threshold.
  - Return a tuple of `PhraseBoundary` records for every emitted start/end.
  - Preserve the end duration before `PhraseTracker.update(False, now)` clears
    play-start state.
- Add `summarize_phrase_stream(ticks, *, threshold_seconds=...)`:
  - Reuse `track_phrase_boundaries`.
  - Count completed phrases from `phrase_ended` events.
  - Sum and max the completed phrase durations.
  - Return the full boundary tuple in the summary for callers that need both
    aggregate and detailed data.
- Add `phrase_status_snapshot(tracker, now, *, event=None)`:
  - Return the stable listener payload shape used in existing integrations:
    `phrase_active`, `phrase_duration_seconds`, and optional `phrase_event`.
  - This remains a pure formatting helper and does not mutate tracker state.
- Preserve `PhraseTracker.update`, `play_duration`, `reset`, `phrase_active`,
  and `play_start` behavior exactly for existing tests/callers.

No new dependencies, migrations, runtime state files, provider secrets, or
agent commands are introduced.

## Edge Cases

- Empty streams return no boundaries and a zero-valued summary.
- Sub-threshold bursts emit no boundary and do not count as phrases.
- Open phrases with no final silence tick emit only the start boundary and do
  not count as completed phrase duration in the summary.
- Negative timestamp drift remains handled by the existing `play_duration`
  clamp; this task does not add a second timing policy.
- Startup identity hardening is outside the phrase tracker surface and remains
  covered by existing startup regression anchors.

## Acceptance Criteria

1. Existing tick-level `PhraseTracker` behavior remains unchanged.
   VERIFY: `pytest tests/test_phrase_tracker.py -q`

2. `track_phrase_boundaries` returns stable typed boundary records for a mixed
   stream with two qualifying phrases and one sub-threshold burst.
   VERIFY: `pytest tests/test_phrase_tracker_depth.py::test_track_phrase_boundaries_returns_typed_started_and_ended_events -q`

3. `summarize_phrase_stream` returns meaningful aggregate output: completed
   phrase count, total duration, longest duration, and the boundary tuple.
   VERIFY: `pytest tests/test_phrase_tracker_depth.py::test_summarize_phrase_stream_counts_completed_phrases -q`

4. `phrase_status_snapshot` mirrors the listener payload fields without
   mutating tracker state.
   VERIFY: `pytest tests/test_phrase_tracker_depth.py::test_phrase_status_snapshot_matches_listener_payload_shape -q`

5. Existing phrase capture and listener integrations still pass.
   VERIFY: `pytest tests/test_phrase_capture.py tests/test_phrase_capture_runtime.py tests/test_midi_keyboard_listener_runtime.py tests/test_theramini_listener_runtime.py -q`

6. Fractal depth for `my-claw/tools/senseweave/phrase_tracker.py` reaches at
   least depth 2.
   VERIFY: `pytest tests/test_phrase_tracker_depth.py::test_phrase_tracker_reaches_depth_two -q`

7. Startup identity hardening remains covered for standalone and federated
   startup paths.
   VERIFY: `pytest tests/test_first_boot.py::TestStartupIdentityPersistence tests/test_governor_integration.py::TestStartupIdentityWiring -q`

8. Full project validation remains clean.
   VERIFY: `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/`
