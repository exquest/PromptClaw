# T-016 Specification

## Problem Statement

The MIDI intake path can extract fragments and persist them in
`midi_vocabulary.sqlite`, but the composer does not yet consult that database
while authoring score-tree arcs. As a result, imported MIDI vocabulary remains
runtime-adjacent data instead of becoming transformed material inside generated
scenes, and operator logs cannot show which source fragments influenced a
scene.

## Technical Approach

- Add a typed composer vocabulary bridge that reads the existing
  `cypherclaw.midi_vocabulary_store` schema without adding columns or
  dependencies.
- Convert usable vocabulary rows into JSON-safe fragment objects containing
  fragment id, kind, source file, derived scale degrees, and duration cells.
- Plan scene-level vocabulary citations with a deterministic pseudo-random
  decision per scene. The probability is the `curiosity` parameter, clamped to
  `[0.0, 1.0]`; default live curiosity is `0.15`.
- Extend score-tree composition with optional `vocabulary_db_path` and
  `vocabulary_curiosity` parameters. When a populated database is supplied,
  attach selected citations under `arrangement_plan["vocabulary_fragments"]`
  and record citation-rate metadata on the tree.
- During score-tree compilation, transform cited scene phrases with the
  selected fragment's derived degrees and rhythm cell, then copy citation
  metadata onto compiled tracker scenes.
- Teach the live composer scene-start log line to include cited vocabulary
  fragment ids when scene metadata contains a citation.
- Wire live tracker composition to consult
  `CYPHERCLAW_MIDI_VOCABULARY_DB` or the default
  `/home/user/cypherclaw-data/state/midi_vocabulary.sqlite` path.

## Edge Cases

- Missing vocabulary DB path: composition proceeds unchanged and cites no
  fragments.
- Empty vocabulary DB: composition proceeds unchanged and reports zero cited
  scenes.
- Corrupt JSON in a fragment row: that row is skipped.
- Unsupported or structurally incomplete fragments: skipped rather than
  crashing the composer.
- Curiosity below `0.0` or above `1.0`: clamped before citation decisions.
- Curiosity `0.0`: no scenes are cited.
- Curiosity `1.0`: every scene is cited when usable fragments exist.
- A scene can cite at most one fragment in this task; later tasks can expand to
  layered citations.
- No schema migration is required because the feature reads the existing
  T-015 schema only.
- The generated startup identity hardening bullets are regression anchors for
  the existing identity startup subsystem; this task does not alter startup
  flow.

## Acceptance Criteria

1. A populated MIDI vocabulary DB can be converted into composer-ready
   fragments, preserving fragment ids and deriving bounded musical material.
   - **VERIFY:** `pytest tests/test_composer_vocabulary_bridge.py::test_load_vocabulary_fragments_derives_composer_material -q`

2. Scene citation rate follows the curiosity parameter: `0.0` cites none,
   `1.0` cites all scenes, and an intermediate value converges near that rate
   over a large deterministic scene set.
   - **VERIFY:** `pytest tests/test_composer_vocabulary_bridge.py::test_plan_vocabulary_citations_rate_tracks_curiosity -q`

3. `compose_score_tree(...)` consults a populated vocabulary DB, stores
   scene-level citation metadata, and records citation-rate metadata.
   - **VERIFY:** `pytest tests/test_score_tree_composer.py::test_score_tree_composer_cites_vocabulary_fragments_from_db -q`

4. Compiled tracker scenes expose cited fragment ids and transformed phrase
   metadata, and the composer log suffix includes the cited id.
   - **VERIFY:** `pytest tests/test_tracker_compiler.py::test_compiled_scene_carries_vocabulary_fragment_citation -q`

5. Existing MIDI vocabulary and score-tree/tracker behavior remains green.
   - **VERIFY:** `pytest tests/test_midi_vocabulary_store.py tests/test_score_tree_composer.py tests/test_tracker_compiler.py -q`

6. Mandatory startup identity hardening anchors remain covered without
   unrelated startup rewiring.
   - **VERIFY:** `pytest tests/test_cli_identity_hardening.py tests/test_first_boot.py::TestStartupIdentityPersistence tests/test_first_boot.py::TestStartupIdentityModePersistence tests/test_governor_integration.py::TestStartupIdentityWiring tests/test_narrative_api_main.py::test_asgi_module_startup_bootstraps_identity_persistence_between_imports -q`

7. Product-facing handoff docs, changelog, and progress mention vocabulary
   citations.
   - **VERIFY:** `rg -n "vocabulary fragment|vocabulary citation|midi_vocabulary" docs/handoff-protocol.md CHANGELOG.md progress.md`

8. Full validation passes.
   - **VERIFY:** `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/`
