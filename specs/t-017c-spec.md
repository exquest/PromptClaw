# T-017c Specification

## Problem Statement

T-017b emits a faithful-transmission scene that preserves imported MIDI pitch
order and source-tick rhythm, but it still reads like a neutral MIDI scheduler
payload. The CypherClaw v2 design statement requires faithful transmission to
keep the imported structure while rendering it through CypherClaw's own
tunings, voice choices, and spaces. Downstream renderers need those decisions
in the faithful scene payload so they do not treat the scene as generic 12-TET
pluck playback.

## Technical Approach

- Extend `cypherclaw.midi_scene` with a typed render-settings layer for
  faithful scenes:
  - phase-to-tuning selection using CypherClaw's canonical rule:
    `Listen`/`Divination` use `just_intonation_5_limit`;
    `Conversation`/`Procession` use `gamelan_slendro`; unknown phases fall
    back to `twelve_tet`.
  - per-step tuned render frequency metadata while preserving the original
    imported MIDI `pitch` value.
  - per-step voice assignment metadata, with a deterministic voice sequence
    and safe fallback to `pluck` for unknown voices.
  - per-step matched space metadata derived from the seven CypherClaw voice
    spaces in `sdp/cypherclaw-v2-design-statement-2026-05-22.md` section 4,
    including stable FX bus ids and compact reverb profile values.
- Keep the T-017b scene shape backward compatible:
  - `pitch`, `duration_ticks`, `row`, and `length_rows` remain unchanged.
  - Existing top-level and lane fields remain present.
  - New render metadata is additive and JSON-safe.
- Wire `process_midi_file(..., faithful_transmission=True)` to render faithful
  scenes with the new settings, defaulting to a quiet `Listen` phase and the
  default matched space policy.
- Keep default fragment-extraction intake unchanged.
- No new dependency, database migration, provider secret, runtime state
  directory, HTTP route, or SuperCollider synth/bus implementation is required.
  Later T-033+ tuning and T-042+ FX-bus tasks own formal runtime audio plumbing;
  this task publishes the scene contract those paths can consume.
- The generated startup hardening bullets are mandatory regression anchors for
  the existing identity startup subsystem. `midi_intake_daemon.main()` already
  invokes `bootstrap_identity()` before `FirstBootAnnouncer()`, and existing
  CLI, first-boot, governor-ordering, standalone/federated, and ASGI startup
  tests remain the verification path instead of changing unrelated startup
  code.

## Edge Cases

- Empty faithful event lists still produce an empty lane and deterministic
  scene metadata without raising.
- Unknown arc phases use `twelve_tet` so malformed metadata does not select an
  unintended microtonal system.
- Unknown or blank voices fall back to `pluck`, and the original requested
  voice is retained in metadata.
- Empty voice sequences fall back to the lane voice.
- Unsupported space modes fall back to matched per-voice spaces.
- Non-positive tonal centers fall back to middle-C tuning.
- Pitch order and source duration are never recomputed by tuning or voice
  selection.

## Acceptance Criteria

1. Faithful scene rendering applies 5-limit JI for still phases while
   preserving source pitch order and rhythm, and each step carries tuned
   frequency, voice, synth, and matched space metadata.
   - **VERIFY:** `pytest tests/test_midi_scene.py::test_build_faithful_midi_scene_applies_cypherclaw_render_settings -q`

2. Faithful scene rendering applies the Slendro profile for motion phases
   without changing the imported MIDI `pitch` or source-tick duration fields.
   - **VERIFY:** `pytest tests/test_midi_scene.py::test_build_faithful_midi_scene_selects_slendro_for_motion_phase -q`

3. Invalid render settings are safe: unknown phases fall back to `twelve_tet`,
   unknown voices fall back to `pluck`, and empty inputs remain deterministic.
   - **VERIFY:** `pytest tests/test_midi_scene.py::test_build_faithful_midi_scene_safely_falls_back_for_unknown_render_settings -q`

4. Faithful intake manifests include the render settings in `faithful_scene`
   while keeping `faithful_events`, empty `fragments`, and no vocabulary
   metadata.
   - **VERIFY:** `pytest tests/test_midi_scene.py::test_process_midi_file_faithful_manifest_includes_cypherclaw_render_settings -q`

5. Existing T-017a/T-017b and adjacent MIDI/composer vocabulary behavior stays
   green.
   - **VERIFY:** `pytest tests/test_midi_scene.py tests/test_midi_faithful_loader.py tests/test_midi_intake_daemon.py tests/test_midi_fragment_extractor.py tests/test_midi_vocabulary_store.py tests/test_composer_vocabulary_bridge.py -q`

6. Mandatory startup identity hardening remains covered for bootstrap-before-
   announcer ordering and standalone/federated persistence.
   - **VERIFY:** `pytest tests/test_cli_identity_hardening.py tests/test_first_boot.py::TestStartupIdentityPersistence tests/test_first_boot.py::TestStartupIdentityModePersistence tests/test_governor_integration.py::TestStartupIdentityWiring tests/test_narrative_api_main.py::test_asgi_module_startup_bootstraps_identity_persistence_between_imports -q`

7. Product-facing notes and task bookkeeping document T-017c render tuning,
   voice, and space metadata.
   - **VERIFY:** `rg -n "T-017c|faithful.*render|tuning_system_name|space_mode|render_voice" CHANGELOG.md progress.md docs/handoff-protocol.md ESCALATIONS.md`

8. Full validation passes.
   - **VERIFY:** `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/`
