# Task frac-0060 Specification: test_audio_analysis Depth 2

## Problem Statement

`tests/test_audio_analysis.py` owns regression coverage for
`my-claw/tools/audio_analysis.py`, the pure stdlib listening helpers used by
CypherClaw audio/sampler workflows. The production module already provides
meaningful one-path implementations for amplitude measurement, autocorrelation
pitch detection, onset-state classification, click transient detection, broad
audio-content classification, pitch-to-note/key conversion, and spectral peak
extraction.

The production source already classifies above this task's target:
`sdp.fractal.classify_depth("my-claw/tools/audio_analysis.py")` reports depth
3. The affected surface for this task is the test file itself. The current test
file verifies the public functions with synthetic signals, but many tests are
short, single-call assertions. The fractal scanner reports
`tests/test_audio_analysis.py` at depth 1 (`21/40 trivial, 19 real`).

This task deepens `tests/test_audio_analysis.py` to depth 2 by adding a focused
depth gate and a one-path end-to-end test class that exercises the real public
audio-analysis API across complete synthetic listening paths. Existing
assertions are preserved unchanged.

## Technical Approach

- Preserve `my-claw/tools/audio_analysis.py` behavior unless the new tests
  expose a real regression. The source module already produces meaningful
  output and needs no planned production changes.
- Add `tests/test_audio_analysis_depth.py` with a red-phase assertion that
  `classify_depth("tests/test_audio_analysis.py").depth >= 2`.
- Add a `TestAudioAnalysisEndToEnd` class to
  `tests/test_audio_analysis.py`. The methods use looped and table-driven
  assertions so the scanner records real test logic rather than trivial
  one-call checks.
- Drive one simple public path through the existing API:
  - Analyze tonal sine signals through amplitude, pitch, note/key mapping,
    broad content classification, and spectral peak extraction.
  - Analyze deterministic speech-like/noise-like material through amplitude
    and content classification.
  - Analyze a sparse impulse through click-transient detection and transient
    content classification.
  - Analyze windowed silence/attack/sustain/release material through RMS
    measurement and `detect_onset`.
  - Confirm the public functions emit JSON-safe scalar/list/dict output that
    can feed downstream diagnostics.
- Keep this test-only change stdlib-only. No new dependencies, migrations,
  provider secrets, runtime state files, database columns, HTTP routes, or auth
  changes are required.
- Treat the generated startup hardening bullets as mandatory verification
  anchors. Existing startup identity tests cover `bootstrap_identity()`
  persistence, standalone/federated reuse, CLI startup invocation,
  bootstrap-before-`FirstBootAnnouncer` ordering, and ASGI app import
  persistence; those tests are re-run in this task.

## Edge Cases

- The depth gate asserts `depth >= 2` rather than an exact depth or reason so
  later test improvements remain compatible.
- Existing tests and assertions in `tests/test_audio_analysis.py` remain
  unchanged; new coverage is appended in a separate class.
- Synthetic tone assertions use tolerances instead of exact frequency-bin
  equality because autocorrelation interpolation and 1024-sample FFT bins are
  approximate by design.
- The speech-like signal is deterministic and uses only stdlib math, avoiding
  brittle random noise while still producing high zero-crossing rate and
  dynamic amplitude variance.
- The click path uses a sparse impulse, not a dense impulse train, so it checks
  the retained-transient path rather than the periodic-suppression path.
- No startup identity source changes are expected because the existing tree
  already has dedicated regression anchors for the generated hardening items.

## Acceptance Criteria

1. Existing audio-analysis behavioral tests remain unchanged and green.
   VERIFY: `pytest tests/test_audio_analysis.py -q`

2. The new red-phase depth gate confirms `tests/test_audio_analysis.py`
   reaches at least depth 2 after the end-to-end tests are added.
   VERIFY: `pytest tests/test_audio_analysis_depth.py -q`

3. The new end-to-end class covers tonal pitch/note/key/spectral output,
   speech-like content classification, sparse click/transient detection,
   onset-state transitions, and JSON-safe diagnostic output from the existing
   public API.
   VERIFY: `pytest tests/test_audio_analysis.py::TestAudioAnalysisEndToEnd -q`

4. The production audio-analysis source remains unchanged in behavior and
   still works through the public API.
   VERIFY: `python -c "import os, sys, math; sys.path.insert(0, os.path.join(os.getcwd(), 'my-claw', 'tools')); from audio_analysis import detect_amplitude, detect_pitch_autocorrelation, pitch_to_note_name, pitch_to_nearest_key, classify_audio_content, extract_spectral_peaks; sr=44100; samples=[int(12000*math.sin(2*math.pi*440*i/sr)) for i in range(sr//4)]; rms, peak=detect_amplitude(samples); freq, conf=detect_pitch_autocorrelation(samples, sr); root, scale=pitch_to_nearest_key(freq or 0); peaks=extract_spectral_peaks(samples, sr, max_peaks=1); assert rms > 0 and peak > rms and freq and abs(freq-440) < 5 and conf > 0.8 and pitch_to_note_name(freq) == 'A4' and root == 'A' and len(scale) == 7 and classify_audio_content(samples, sr)['type'] == 'tonal' and peaks; print(round(freq, 2), root, peaks[0])"`

5. Startup identity hardening remains covered for first-run identity
   persistence, standalone/federated reuse, CLI startup invocation,
   bootstrap-before-announcer ordering, and ASGI app import persistence.
   VERIFY: `pytest tests/test_cli_identity_hardening.py tests/test_first_boot.py::TestStartupIdentityPersistence tests/test_governor_integration.py::TestStartupIdentityWiring tests/test_narrative_api_main.py::test_asgi_module_startup_bootstraps_identity_persistence_between_imports -q`

6. Product-facing progress and changelog notes mention the depth-2
   audio-analysis test coverage.
   VERIFY: `grep -n "frac-0060" CHANGELOG.md progress.md`

7. Full project validation remains clean.
   VERIFY: `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/`
