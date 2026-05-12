# Task frac-0091 Specification: test_music_theory Depth 2

## Problem Statement

`tests/test_music_theory.py` already exercises
`my-claw/tools/senseweave/music_theory.py` at the function level: MIDI and
frequency conversion, note-name parsing, interval metadata, scale catalogues,
chord symbol parsing, chord voicing generation, just-intonation helpers, and
post-tonal/spectral helpers.

The missing work for frac-0091 is to make the depth-2 contract explicit. The
test file should include a named end-to-end class that drives one meaningful
public music-theory path from scale selection through chord construction,
voicing, interval interpretation, frequency conversion, microtonal ratio
checks, spectral partial generation, and JSON-safe diagnostic output. A
companion depth gate should pin that class and the repo-local fractal
classifier.

The production module already appears to produce meaningful one-path output for
this scope, so no production behavior change is expected unless the new tests
expose a concrete gap.

The generated startup identity hardening bullets target the existing identity
startup subsystem. This checkout already documents and tests CLI startup,
daemon bootstrap-before-`FirstBootAnnouncer` ordering, standalone/federated
identity persistence, and narrative ASGI import persistence. This task keeps
those tests as mandatory regression anchors rather than modifying unrelated
startup code without a discovered gap.

## Technical Approach

- Add `tests/test_test_music_theory_depth.py` with a deterministic depth gate
  requiring `tests/test_music_theory.py` to contain `MusicTheoryEndToEndTests`
  and classify at depth >= 2 through `sdp.fractal.classify_depth`.
- Confirm the red phase by running the new depth gate before the end-to-end
  class exists.
- Append `MusicTheoryEndToEndTests` to `tests/test_music_theory.py`.
- Drive one public end-to-end path:
  - resolve C ionian and a ii-V-I chord progression;
  - parse chord symbols, generate smooth close voicings, and confirm chord
    tones stay inside the resolved key;
  - derive interval metadata between melody targets and assert meaningful
    consonance/character fields;
  - convert MIDI notes to note names and frequencies;
  - compare equal-tempered fifths to just-intonation fifths in cents;
  - generate a small just-intonation chord and spectral partial set;
  - serialize the combined diagnostic payload through
    `json.dumps(..., sort_keys=True)` and `json.loads(...)`.
- Preserve existing focused assertions and production behavior.
- Introduce no new dependencies, migrations, provider secrets, database
  columns, runtime state files, HTTP routes, or auth behavior.

## Edge Cases

- The end-to-end path intentionally covers one simple happy path, not every
  scale, chord quality, enharmonic spelling, or voicing style.
- Existing focused tests remain responsible for invalid frequencies, unknown
  note names, unknown scales, unknown chord qualities, configured register
  failures, and microtonal boundary errors.
- The diagnostic payload must stay JSON-safe without custom encoders so
  downstream reports can persist it.
- Startup identity hardening remains covered by the existing CLI, first-boot,
  daemon-ordering, and narrative ASGI tests.

## Acceptance Criteria

1. Existing music theory assertions remain green.
   VERIFY: `pytest tests/test_music_theory.py -q`

2. The depth gate confirms `tests/test_music_theory.py` reaches depth >= 2 and
   contains `MusicTheoryEndToEndTests`.
   VERIFY: `pytest tests/test_test_music_theory_depth.py -q`

3. `MusicTheoryEndToEndTests` drives one meaningful public path from scale and
   chord resolution through voicing, intervals, frequencies, just intonation,
   spectral helpers, and JSON-safe diagnostics.
   VERIFY: `pytest tests/test_music_theory.py::MusicTheoryEndToEndTests -q`

4. Startup identity hardening remains covered for CLI startup, daemon startup
   ordering, standalone/federated identity persistence, and narrative ASGI
   import persistence.
   VERIFY: `pytest tests/test_cli_identity_hardening.py tests/test_first_boot.py::TestStartupIdentityPersistence tests/test_governor_integration.py::TestStartupIdentityWiring tests/test_narrative_api_main.py::test_asgi_module_startup_bootstraps_identity_persistence_between_imports -q`

5. Product-facing task notes mention the frac-0091 music-theory test
   deepening.
   VERIFY: `grep -n "frac-0091" CHANGELOG.md progress.md`

6. Full project validation remains clean.
   VERIFY: `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/`
