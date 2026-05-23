# T-017d Specification

## Problem Statement

T-017c implemented the faithful-transmission render contract, but the current
coverage is concentrated in broad scene-builder tests. T-017d adds focused
regression tests for the contract that must not drift: faithful rendering keeps
the imported MIDI pitch sequence and source-tick rhythm intact while applying
CypherClaw tuning, voice, synth, and matched-space assignments.

## Technical Approach

- Add focused tests in a new test module,
  `tests/test_midi_faithful_render_contract.py`, so prior T-017b/T-017c
  assertions remain unchanged.
- Exercise `cypherclaw.midi_scene.build_faithful_midi_scene(...)` with
  explicit `FaithfulRenderSettings` rather than mocking downstream renderers.
- Verify three independent contract surfaces:
  - preserved source fields: `pitch`, `duration_ticks`, `row`, `length_rows`,
    and source metadata remain tied to the incoming `FaithfulMidiEvent` values.
  - tuning application: `render_pitch_hz` follows explicit and phase-selected
    tuning systems without changing the source MIDI fields.
  - voice/space assignment: every canonical voice maps to the expected synth,
    matched space id, FX bus id, and step metadata; `sw_`-prefixed voice names
    normalize to the canonical voice while preserving the requested value.
- Treat the generated startup-hardening bullets as regression anchors for the
  existing identity startup subsystem. `midi_intake_daemon.main()` already calls
  `bootstrap_identity()` before `FirstBootAnnouncer()`, and existing
  standalone/federated persistence tests remain the verification path.
- No new dependencies, migrations, provider secrets, database schema changes,
  runtime state directories, HTTP routes, or SuperCollider synth changes are in
  scope.

## Edge Cases

- Uneven source durations still preserve exact `duration_ticks` while row
  lengths are scheduler handoff values derived from the original ticks.
- Explicit `tuning_system_name` overrides the arc-phase default, but the
  original `pitch` field remains the imported MIDI value.
- All seven canonical voices have deterministic synth and matched-space
  assignments.
- A requested `sw_` voice alias normalizes for rendering and retains the raw
  requested voice in metadata.
- Startup identity hardening is verified as existing coverage, not broadened
  into this faithful-render regression task.

## Acceptance Criteria

1. Faithful render tests prove source pitch order, source durations, row order,
   and per-step source metadata are preserved while render metadata is added.
   - **VERIFY:** `pytest tests/test_midi_faithful_render_contract.py::test_faithful_render_preserves_source_pitch_and_rhythm_with_render_metadata -q`

2. Faithful render tests prove explicit tuning selection computes
   `render_pitch_hz` while preserving imported MIDI `pitch` and
   `duration_ticks`.
   - **VERIFY:** `pytest tests/test_midi_faithful_render_contract.py::test_faithful_render_applies_explicit_tuning_without_rewriting_source_fields -q`

3. Faithful render tests prove canonical voice, synth, and matched-space
   assignment across all seven voices, including an `sw_` alias normalization.
   - **VERIFY:** `pytest tests/test_midi_faithful_render_contract.py::test_faithful_render_assigns_voice_synth_and_matched_space_sequence -q`

4. Existing faithful MIDI loader, scene, intake, fragment, vocabulary, and
   composer-vocabulary behavior remains green.
   - **VERIFY:** `pytest tests/test_midi_faithful_render_contract.py tests/test_midi_scene.py tests/test_midi_faithful_loader.py tests/test_midi_intake_daemon.py tests/test_midi_fragment_extractor.py tests/test_midi_vocabulary_store.py tests/test_composer_vocabulary_bridge.py -q`

5. Mandatory startup identity hardening remains covered for bootstrap-before-
   announcer ordering and standalone/federated persistence.
   - **VERIFY:** `pytest tests/test_cli_identity_hardening.py tests/test_first_boot.py::TestStartupIdentityPersistence tests/test_first_boot.py::TestStartupIdentityModePersistence tests/test_governor_integration.py::TestStartupIdentityWiring tests/test_narrative_api_main.py::test_asgi_module_startup_bootstraps_identity_persistence_between_imports -q`

6. Task bookkeeping documents T-017d scope, assumptions, and validation.
   - **VERIFY:** `rg -n "T-017d|faithful.*render regression|pitch/rhythm preservation|voice/space assignment" specs/t-017d-spec.md CHANGELOG.md progress.md ESCALATIONS.md`

7. Full validation passes.
   - **VERIFY:** `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/`
