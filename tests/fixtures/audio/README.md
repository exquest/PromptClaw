# Canned audio fixtures

Deterministic 1-second mono 16-bit PCM WAV files at 8 kHz, used by the
detector-branch smoke test in `tests/test_sample_capture_daemon.py` to
exercise `InterestingMomentDetector` without depending on JACK or live
capture.

| Fixture | Detector branch | Seed |
| --- | --- | --- |
| `silence.wav` | baseline; must not flag | — |
| `dishwasher.wav` | steady hum baseline; must not flag | 7 |
| `footsteps.wav` | broadband transients | 11 |
| `music.wav` | tonal pad + plucks | (deterministic) |
| `dogs.wav` | bark-style tonal bursts | 17 |
| `transient_cluster.wav` | dense transient cluster | 23 |

## Regenerating the fixtures

The generator lives next to the WAVs at `generate.py`. It uses fixed RNG
seeds, so the bytes on disk are reproducible across machines as long as
NumPy's `default_rng` stream is stable.

```bash
python tests/fixtures/audio/generate.py
```

That rewrites every fixture in this directory in place. To refresh only
one fixture, edit its generator function (e.g. `dogs()`) and rerun the
script — non-edited fixtures regenerate to identical bytes.

## When to regenerate

- The synthesis parameters in `generate.py` change (frequencies,
  envelopes, burst counts, durations).
- `SAMPLE_RATE` or `DURATION_SECONDS` change.
- A new detector branch needs a dedicated fixture (add a generator,
  register it in `FIXTURES`, rerun, then add a parametrize case in
  `test_detector_branch_smoke_test_flags_on_matching_fixture`).

After regenerating, run the smoke test locally before committing:

```bash
pytest tests/test_sample_capture_daemon.py -k "fixture or smoke"
```

The same selector runs in the `detector-branch-smoke` GitHub Actions
job (`.github/workflows/detector-smoke.yml`), which is wall-clock
bounded to 30 seconds.

## Format invariants

All fixtures must be mono, 16-bit PCM, 8 kHz, exactly 1 second long.
`test_canned_fixtures_are_one_second_at_eight_kilohertz` enforces this
on every run; if it fails after a regen, check that you did not change
`SAMPLE_RATE` or `DURATION_SECONDS` without updating the test.
