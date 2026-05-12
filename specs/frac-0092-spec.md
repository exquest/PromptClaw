# Task frac-0092 Specification: test_musical_integration_runtime Depth 2

## Problem Statement

`tests/test_musical_integration_runtime.py` already exercises the
end-to-end musical runtime by driving `sample_playback_engine`,
`self_listener`, and the `senseweave.sample_*` helpers through one shared
scene state. The single existing function
`test_composer_sampler_listener_and_face_share_one_scene_state` proves the
composer/sampler/listener/face surfaces converge on the same room-mic
scene.

The missing work for frac-0092 is to make the depth-2 contract explicit
for this file. The test module should expose a named end-to-end class that
drives one meaningful public musical-runtime path (build sample/DSP
activity → launch a sample event → re-read playback state → derive a glyph
audio state → render the face status text → JSON-safe diagnostic payload)
and a companion depth gate that pins the class plus the repo-local
fractal classifier at depth >= 2.

The production modules already produce meaningful one-path output for
this scope, so no production behavior change is expected unless the new
tests expose a concrete gap.

The generated startup identity hardening bullets target the existing
identity startup subsystem. This checkout already documents and tests CLI
startup, daemon bootstrap-before-`FirstBootAnnouncer` ordering,
standalone/federated identity persistence, and narrative ASGI import
persistence. This task keeps those tests as mandatory regression anchors
rather than modifying unrelated startup code without a discovered gap.

## Technical Approach

- Add `tests/test_test_musical_integration_runtime_depth.py` with a
  deterministic depth gate requiring
  `tests/test_musical_integration_runtime.py` to contain
  `MusicalIntegrationRuntimeEndToEndTests` and classify at depth >= 2
  through the repo-local `sdp.fractal.classify_depth`.
- Confirm the red phase by running the new depth gate before the
  end-to-end class exists.
- Append `MusicalIntegrationRuntimeEndToEndTests` to
  `tests/test_musical_integration_runtime.py`.
- Drive one public end-to-end path inside the class:
  - render a deterministic room capture WAV with `write_wav_mono`;
  - assemble composer/cadence/self/sensor/capture state and call
    `build_sample_dsp_activity` to get the activity payload;
  - patch `STATE_PATH`, `OUTPUT_DIR`, and `launch_pw_play` so
    `maybe_launch_event` runs hermetically;
  - drive `maybe_launch_event` to a successful launch and read back
    `playback_state` from disk;
  - call `self_listener.build_glyph_audio_state` with realistic audio
    analysis features so the glyph reflects the same `room_mic` scene;
  - call `senseweave.sample_status.sample_status_text` to get the
    operator-facing face string;
  - serialize the combined `{activity, playback_state, glyph,
    face_text}` diagnostic payload through
    `json.dumps(..., sort_keys=True)` and `json.loads(...)` to prove it
    is JSON-safe.
- Preserve the existing focused assertions and module-level imports.
- Introduce no new dependencies, migrations, provider secrets, database
  columns, runtime state files, HTTP routes, or auth behavior.

## Edge Cases

- The end-to-end path intentionally covers one simple happy path
  (`room_mic` scene that triggers a launch), not every sample source,
  cooldown branch, missing-capture branch, render failure, or transport
  trigger key permutation.
- Existing focused tests remain responsible for cooldown logic,
  missing-capture short-circuits, render failures, and other
  non-happy-path branches.
- The diagnostic payload must stay JSON-safe without custom encoders so
  downstream reports can persist it.
- Startup identity hardening remains covered by the existing CLI,
  first-boot, daemon-ordering, and narrative ASGI tests.

## Acceptance Criteria

1. Existing musical integration runtime assertions remain green.
   VERIFY: `pytest tests/test_musical_integration_runtime.py -q`

2. The depth gate confirms `tests/test_musical_integration_runtime.py`
   reaches depth >= 2 and contains
   `MusicalIntegrationRuntimeEndToEndTests`.
   VERIFY: `pytest tests/test_test_musical_integration_runtime_depth.py -q`

3. `MusicalIntegrationRuntimeEndToEndTests` drives one meaningful public
   path from sample/DSP activity through launch, playback state, glyph
   audio state, face status text, and JSON-safe diagnostics.
   VERIFY: `pytest tests/test_musical_integration_runtime.py::MusicalIntegrationRuntimeEndToEndTests -q`

4. Startup identity hardening remains covered for CLI startup, daemon
   startup ordering, standalone/federated identity persistence, and
   narrative ASGI import persistence.
   VERIFY: `pytest tests/test_cli_identity_hardening.py tests/test_first_boot.py::TestStartupIdentityPersistence tests/test_governor_integration.py::TestStartupIdentityWiring tests/test_narrative_api_main.py::test_asgi_module_startup_bootstraps_identity_persistence_between_imports -q`

5. Product-facing task notes mention the frac-0092 musical integration
   runtime test deepening.
   VERIFY: `grep -n "frac-0092" CHANGELOG.md progress.md`

6. Full project validation remains clean.
   VERIFY: `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/`
