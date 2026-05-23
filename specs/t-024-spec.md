# T-024 Specification - JACK Output Opus Segment Streamer

## Problem Statement

CypherClaw needs a lightweight archival streamer that captures the live JACK
output bus and writes playable Opus segment files for downstream review or
publication workflows. The current tree has short self-listener captures and
sample-capture ring buffers, but no long-running `audio_streamer.py` that
segments the live output bus into approximately 6-second, approximately
96 kbps Opus files.

The streamer must be hardware-friendly: one ffmpeg JACK client, explicit
connections from the SuperCollider stereo output bus, bounded encoder work, and
operator-verifiable duration, bitrate, and CPU checks.

## Technical Approach

- Add `my-claw/tools/audio_streamer.py` as a typed stdlib-only tool.
- Use ffmpeg's JACK input to create a named client
  `cypherclaw-opus-stream`.
- Connect `SuperCollider:out_1` and `SuperCollider:out_2` to
  `cypherclaw-opus-stream:input_1` and `cypherclaw-opus-stream:input_2`.
- Encode with `libopus`, `-b:a 96k`, constrained VBR, audio application mode,
  20 ms frames, one thread, and the segment muxer.
- Write Ogg/Opus `.opus` segment files with `-segment_time 6`,
  `-reset_timestamps 1`, and strftime-based names under
  `/home/user/cypherclaw-data/streams` by default.
- Support an optional JACK wrapper such as `pw-jack` for hosts whose JACK graph
  is exposed through PipeWire compatibility.
- Write an optional pid file so live operators can check the exact streamer
  process.
- Provide `--verify-dir` that runs `ffprobe` on segment files and validates
  duration and bitrate tolerances.
- Provide `--check-cpu PID` that reads process CPU from `ps` and fails when it
  is above the configured max, defaulting to 10%.
- Call `bootstrap_identity()` before starting ffmpeg or connecting JACK ports.
  The CLI exposes standalone/federated identity mode arguments so this startup
  path is usable in both modes without changing existing announcer behavior.

## Edge Cases

- If ffmpeg starts but its JACK input ports do not appear before the timeout,
  the streamer terminates ffmpeg and reports a failure.
- If `jack_connect` fails for any configured source, startup fails rather than
  silently recording the wrong bus.
- Segment validation skips non-`.opus` files and reports a clear failure when no
  segment files are present.
- `ffprobe` payloads without duration or bitrate are treated as invalid.
- Bitrate is approximate because Opus framing and Ogg container overhead vary;
  validation allows a tolerance around the target.
- CPU checks fail closed when `ps` output is missing or unparsable.
- No database schemas, migrations, provider secrets, HTTP routes, or agent
  command strings are changed.
- The generated startup-hardening items are addressed by bootstrapping identity
  in this new daemon path and by re-running existing identity persistence
  anchors. `FirstBootAnnouncer` remains outside this streamer's responsibility.

## Acceptance Criteria

1. The ffmpeg command captures JACK audio as a named client and writes
   approximately 6-second Ogg/Opus `.opus` segments at approximately 96 kbps.
   - **VERIFY:** `pytest tests/test_audio_streamer.py::test_ffmpeg_command_segments_jack_output_to_constrained_96k_opus -q`

2. Streamer startup creates the output directory, bootstraps identity before
   JACK work, waits for ffmpeg JACK inputs, writes the pid file, and connects
   the SuperCollider stereo output bus to the ffmpeg client inputs.
   - **VERIFY:** `pytest tests/test_audio_streamer.py::test_start_streamer_bootstraps_identity_waits_for_ports_and_connects_output_bus -q`

3. Segment files can be verified from disk for duration and bitrate tolerance.
   - **VERIFY:** `pytest tests/test_audio_streamer.py::test_segment_validation_accepts_expected_duration_and_bitrate -q`
   - **VERIFY:** `python my-claw/tools/audio_streamer.py --verify-dir /home/user/cypherclaw-data/streams --segment-seconds 6 --bitrate-kbps 96`

4. Streamer CPU can be checked against the under-10% acceptance target.
   - **VERIFY:** `pytest tests/test_audio_streamer.py::test_cpu_check_reports_under_and_over_limit_from_ps -q`
   - **VERIFY:** `python my-claw/tools/audio_streamer.py --check-cpu "$(cat /tmp/cypherclaw-audio-streamer.pid)" --max-cpu 10`

5. Startup identity hardening remains covered for standalone and federated
   identity persistence without broadening this task into unrelated startup
   rewiring.
   - **VERIFY:** `pytest tests/test_cli_identity_hardening.py tests/test_first_boot.py::TestStartupIdentityPersistence tests/test_first_boot.py::TestStartupIdentityModePersistence tests/test_governor_integration.py::TestStartupIdentityWiring tests/test_narrative_api_main.py::test_asgi_module_startup_bootstraps_identity_persistence_between_imports -q`

6. Documentation and task metadata mention T-024, the Opus streamer behavior,
   no new dependencies, and the live verification commands.
   - **VERIFY:** `rg -n "T-024|audio_streamer|Opus|96 kbps|6-second" specs/t-024-spec.md CHANGELOG.md progress.md ESCALATIONS.md`

7. Full repository validation passes.
   - **VERIFY:** `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/`
