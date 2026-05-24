# T-058b Specification

## Problem Statement

T-058b must capture a 60-second reference sample from the public CypherClaw
live stream and save an on-box backup at:

`/home/user/cypherclaw/var/reference-renders/feature-3-stream-{timestamp}.opus`

The capture must also log a checksum so the verifier can prove the saved
artifact is the exact file produced by the capture command. Prior verification
found three blockers: the deployed HLS playlist was cold, the destination path
belongs to the remote CypherClaw Linux host, and this repository had no helper
that captures HLS to Opus and logs a checksum.

This slice resolves the missing helper. It does not fabricate audio, start the
remote producer, or write to the CypherClaw host from this Darwin checkout.

## Technical Approach

- Add a small typed stdlib Python tool under `my-claw/tools/` for on-box use.
- Default inputs:
  - playlist URL: `https://cypherclaw.holdenu.com/api/cypherclaw/live.m3u8`
  - output directory: `/home/user/cypherclaw/var/reference-renders`
  - filename prefix: `feature-3-stream`
  - duration: `60` seconds
  - codec: `libopus`
- Before running ffmpeg, fetch the playlist and require at least one media
  segment line. A cold playlist should fail fast with an actionable error.
- Build an ffmpeg command that reads the HLS playlist for the requested
  duration and writes a single Ogg Opus artifact.
- Compute a SHA-256 checksum after successful capture.
- Append one JSONL record per capture to a checksum log in the output
  directory. Each record includes output path, checksum, byte size, duration,
  playlist URL, ffmpeg command, and timestamp.
- Expose a CLI with dry-run support so operators can verify paths and command
  construction without contacting ffmpeg.

## Edge Cases

- Cold HLS playlist: fail before ffmpeg with a clear "no media segments" error.
- Output directory missing: create it before capture.
- Existing filename collision: fail rather than overwrite.
- ffmpeg failure: propagate a RuntimeError with stderr/stdout detail.
- Empty or missing output file after ffmpeg: fail before logging checksum.
- Checksum log path override: support a custom `--checksum-log` for tests or
  operator workflows.
- Timestamp injection: allow tests to pass a deterministic timestamp while the
  default runtime uses UTC wall clock.

## Acceptance Criteria

1. The capture tool builds the correct 60-second HLS-to-Opus ffmpeg command,
   names files as `feature-3-stream-{timestamp}.opus`, creates the reference
   render directory, and appends a JSONL checksum record after a successful
   mocked capture.
   VERIFY: `pytest tests/test_live_reference_capture.py -q`

2. A cold HLS playlist is rejected before ffmpeg runs.
   VERIFY: `pytest tests/test_live_reference_capture.py::test_cold_playlist_fails_before_ffmpeg_runs -q`

3. The command-line dry-run path reports the planned output path, checksum log,
   and ffmpeg command without writing an artifact.
   VERIFY: `python my-claw/tools/live_reference_capture.py --dry-run --timestamp 20260524T000000Z`

4. The recurring SuperCollider hardening anchors stay clean: voice SynthDefs
   declare `fx_bus_id`, and `sw_sampler.scd` routes its send through
   `fx_bus_id`.
   VERIFY: `pytest tests/test_space_reverb_profiles.py::test_voice_synthdefs_declare_fx_bus_id_routing_contract tests/test_sw_sampler.py::TestRoutingAndFxSend::test_fx_send_writes_to_fx_bus -q`

5. Full repository validation remains green before final commit.
   VERIFY: `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/`
