# Task frac-0105 Specification: test_render_replay Depth 2

## Problem Statement

`tests/test_render_replay.py` currently covers the deterministic replay
surface at helper depth: replaying a short score produces matching hashes, and
audio export writes a delta track that can be consumed later. The test file
does not yet pin a full one-path replay lifecycle that starts with score event
mappings, overlays deltas from a sidecar-like payload, verifies immutable score
fields are preserved, persists provenance through audio export, and proves the
replayed output is JSON-safe for operator diagnostics.

The missing frac-0105 work is to deepen the replay test module from depth 1 to
depth 2 without broadening runtime behavior beyond the existing simple,
meaningful path.

## Technical Approach

- Keep production behavior in `my-claw/tools/senseweave/render/replay.py`
  unless tests reveal a genuine gap. Exploration shows the module already
  implements the simple path required by CCH-009:
  - accepts score events as `Event` objects, event dictionaries, mappings with
    an `events` list, or `PerformedPart`;
  - accepts delta tracks as paths, mappings, or sequences;
  - matches deltas by `event_id` first, then sequence index;
  - overlays performance-level fields only;
  - marks events rendered and returns a `PerformedPart` with applied rules and
    seed metadata.
- Add `tests/test_test_render_replay_depth.py`, matching recent frac depth-gate
  patterns, to require:
  - `RenderReplayEndToEndTests` exists in `tests/test_render_replay.py`;
  - a named end-to-end method exists;
  - `classify_depth("tests/test_render_replay.py").depth >= 2`.
- Add `RenderReplayEndToEndTests` to `tests/test_render_replay.py` after the red
  phase. The class will drive one complete replay lifecycle through public
  APIs only: `replay(...)`, `export_audio(...)`,
  `audio_delta_track_path(...)`, `read_audio_metadata_sidecar(...)`, and
  `PerformedPart`.
- Treat generated startup identity hardening bullets as regression anchors.
  Existing CLI, first-boot, daemon-ordering, and narrative ASGI tests already
  cover `bootstrap_identity()` before `FirstBootAnnouncer` and persistence
  across standalone/federated boots, so this task will re-run them rather than
  add unrelated startup code.

## Edge Cases

- Deltas that repeat score-level fields such as `pitch`, `role`, or
  `nominal_beat` must not mutate those score-owned fields.
- Delta `seed_path` values may arrive as JSON lists and should replay as tuples
  on `Event`.
- Delta `rule_stack` values should produce ordered unique `applied_rules`.
- Sidecar-like payloads with an `events` list are accepted by the replay loader
  and can represent exported delta payloads.
- Missing or unrelated hardening migrations are out of scope: no database
  columns, foreign keys, or migrations are introduced.

## Acceptance Criteria

1. `tests/test_render_replay.py` includes `RenderReplayEndToEndTests` with
   `test_mapping_score_sidecar_delta_audio_export_and_diagnostics_round_trip`.
   VERIFY: `pytest tests/test_test_render_replay_depth.py -q`

2. The end-to-end replay test drives score-event dictionaries through
   `replay(...)`, uses a sidecar-like delta mapping, and verifies meaningful
   `PerformedPart` output: rendered `Event` objects, seed metadata, unique
   applied rules, overlaid timing/duration/velocity/articulation/sensor fields,
   and preserved score-level fields.
   VERIFY: `pytest tests/test_render_replay.py::RenderReplayEndToEndTests::test_mapping_score_sidecar_delta_audio_export_and_diagnostics_round_trip -q`

3. The replay output and diagnostic payload round-trip through
   `json.dumps(..., sort_keys=True)` / `json.loads(...)`, preserving event
   count, applied rules, seed metadata, and event IDs.
   VERIFY: `pytest tests/test_render_replay.py::RenderReplayEndToEndTests -q`

4. Audio export persists the same delta entries to the default delta-track path
   and writes a readable metadata sidecar that points at that path; replaying
   from the persisted delta path reproduces the original event sequence hash.
   VERIFY: `pytest tests/test_render_replay.py -q`

5. Startup identity hardening remains green for CLI startup, first-boot
   persistence, daemon ordering, and narrative ASGI import persistence.
   VERIFY: `pytest tests/test_cli_identity_hardening.py tests/test_first_boot.py::TestStartupIdentityModePersistence tests/test_first_boot.py::TestStartupIdentityPersistence tests/test_governor_integration.py::TestStartupIdentityWiring tests/test_narrative_api_main.py::test_asgi_module_startup_bootstraps_identity_persistence_between_imports -q`

6. Full project validation passes before final commit.
   VERIFY: `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/`

7. Product-facing and progress notes mention frac-0105 render-replay depth-2
   coverage and no new dependencies or migrations.
   VERIFY: `grep -n "frac-0105" CHANGELOG.md progress.md ESCALATIONS.md`
