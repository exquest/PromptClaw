# Task frac-0030 Specification: Senseweave Voice Depth 2

## Problem Statement

`my-claw/tools/senseweave/synthesis/senseweave_voice.py` owns the
ADSR-controlled senseweave texture instrument used by the live
composer: the frozen `ADSR` envelope, six named presets (`PAD`,
`SWELL`, `STAB`, `RHYTHMIC`, `BREATH`, `SHIMMER`), the `TIMBRE_MAP`
synth lookup, the `ActiveNote` record, and the `SenseweaveVoice` class
that owns `note_on`, `note_off`, `chord`, `set_preset`, `set_adsr`,
`set_timbre`, polyphony enforcement, and the convenience helpers
`pad_chord`, `stab_chord`, `rhythmic_hit`, `breath_tone`,
`shimmer_note`, and `swell`. Existing callers and
`tests/test_senseweave_voice.py` rely on the OSC `/s_new` payload
shape (`[synth, nid, 0, 0, "freq", freq, "amp", amp, "attack", attack,
"release", release]`), the percussive-vs-sustained distinction, the
polyphony cap, and `release_all`/`note_off` behavior.

The module already works end-to-end for the one live path: the
composer chooses a preset and a frequency, the voice triggers a
synth, and percussive vs sustained envelopes are released through the
shared `_release_note` path. It currently classifies at fractal
depth 1 (`15/20 trivial, 5 real`) because the small one-line presets
and convenience methods outnumber the real `note_on`/`note_off`/
`set_preset`/`set_timbre`/`_release_note` logic. This task deepens
the module to a simple depth-2 implementation by adding a typed
diagnostic/report surface that delegates to the existing voice path
and produces stable operator-readable output.

The generated startup hardening checks for `bootstrap_identity()` and
`FirstBootAnnouncer` target the daemon identity subsystem, not this
voice instrument module. The current tree already calls
`bootstrap_identity()` before `FirstBootAnnouncer` in both daemon
startup paths and contains integration coverage for
standalone/federated identity persistence. This task keeps those
tests as mandatory regression anchors.

## Technical Approach

Extend `senseweave.synthesis.senseweave_voice` in place with
stdlib-only, typed helpers. No new dependencies, migrations, runtime
state files, provider secrets, database columns, or agent command
strings are introduced.

- Preserve the `ADSR` dataclass, every named preset, `PRESETS`,
  `TIMBRE_MAP`, `ActiveNote`, and the live `SenseweaveVoice` class
  (its OSC payload shape, polyphony cap, percussive vs sustained
  distinction, `note_off` semantics, and convenience helpers) so
  `tests/test_senseweave_voice.py` remains unchanged.
- Add frozen dataclass `VoiceADSRSnapshot` containing one resolved
  envelope view: `preset_name`, `attack`, `decay`, `sustain`,
  `release`, `total_duration`, `is_percussive`, and `envelope_band`.
- Add frozen dataclass `VoiceNoteSnapshot` containing one active
  note view: `node_id`, `freq`, `synth`, `amp`, `register_band`,
  `amp_band`, `envelope`, and `elapsed_seconds`.
- Add frozen dataclass `VoicePlanReport` containing one voice
  decision: `timbre`, `synth`, `preset_name`, `envelope`,
  `max_polyphony`, `active_count`, `polyphony_band`, `is_playing`,
  `notes`, `mean_amp`, `total_amp`, `lowest_frequency_hz`,
  `highest_frequency_hz`, `register_band_counts`, `amp_band_counts`,
  and `synth_counts`.
- Add `voice_envelope_band(adsr)`:
  - `adsr.is_percussive` -> `"percussive"`
  - `adsr.attack >= 2.0` -> `"long_attack"`
  - `adsr.attack >= 1.0` -> `"medium_attack"`
  - otherwise -> `"short_attack"`
- Add `voice_amp_band(amp)`:
  - `amp <= 0.0` -> `"silent"`
  - `0.0 < amp <= 0.05` -> `"quiet"`
  - `0.05 < amp <= 0.1` -> `"medium"`
  - `amp > 0.1` -> `"loud"`
- Add `voice_register_band(frequency_hz)`:
  - `< 65.4` -> `"pedal"`
  - `65.4 <= value < 130.8` -> `"bass"`
  - `130.8 <= value < 523.3` -> `"middle"`
  - `>= 523.3` -> `"upper"`
- Add `voice_polyphony_band(active_count, max_polyphony)`:
  - `active_count <= 0` -> `"idle"`
  - `active_count / max_polyphony < 0.5` -> `"sparse"`
  - `active_count / max_polyphony < 1.0` -> `"filling"`
  - `active_count >= max_polyphony` -> `"full"`
  - `max_polyphony <= 0` falls back to `"full"` because the cap is
    saturated by definition.
- Add `preset_name_for_adsr(adsr)` returning the canonical preset
  name (`"pad"`, `"swell"`, `"stab"`, `"rhythmic"`, `"breath"`,
  `"shimmer"`) or `None` when no preset matches.
- Add `preset_envelope_band(name)` returning the envelope band for a
  named preset, or `"unknown"` for an unmapped name.
- Add `voice_synth_for_timbre(timbre)` returning the configured
  synth from `TIMBRE_MAP`, falling back to `TIMBRE_MAP["pad"]` for an
  unknown timbre.
- Add `summarize_active_notes(notes)`:
  - Aggregate count, total amp, mean amp, lowest/highest frequency,
    register-band counts, amp-band counts, and synth counts across
    the active note list.
  - Round aggregate floats to 4 decimal places.
- Add `build_voice_adsr_snapshot(adsr)`:
  - Resolve the matching preset name, percussive flag, and envelope
    band from the existing `ADSR` data.
- Add `build_voice_note_snapshot(note, now)`:
  - Resolve register band, amp band, envelope snapshot, and
    `elapsed_seconds` (clamped to `>= 0` and rounded to 4 decimals).
- Add `build_voice_plan_report(voice, *, now=None)`:
  - Snapshot the live voice's timbre, configured envelope, polyphony
    cap, active-note state, and aggregate metrics.
  - When `now` is `None`, default to `time.time()` so callers can
    supply a deterministic clock for tests.
- Add `summarize_voice_plan_report(report)` returning a JSON-safe
  dictionary containing all report fields, the nested envelope
  snapshot, the per-note snapshots, register/amp/synth counts, and
  no tuple values (tuples are converted to lists).
- Keep the implementation simple and one-path: the report surface
  uses existing voice state and helpers rather than adding a second
  voice algorithm.

## Edge Cases

- Band helper cutpoints are inclusive at the upper end as documented
  above.
- Unknown preset/timbre names report the documented `"unknown"` /
  pad-fallback values rather than raising.
- `summarize_active_notes` is tolerant of an empty sequence and
  reports zero counts/metrics.
- `voice_polyphony_band` treats a non-positive `max_polyphony` as a
  saturated cap (`"full"`) so reports never divide by zero.
- `build_voice_note_snapshot` clamps a future `started_at` (now <
  started_at) to a non-negative `elapsed_seconds`.
- `summarize_voice_plan_report` keeps dict-keyed band counts as JSON
  objects and converts the notes tuple into a list.
- Startup identity hardening is owned by the daemon identity
  subsystem and remains a regression anchor through
  `tests/test_first_boot.py::TestStartupIdentityPersistence` and
  `tests/test_governor_integration.py::TestStartupIdentityWiring`.

## Acceptance Criteria

1. Existing voice ADSR, preset, timbre, polyphony, OSC, and
   convenience-helper behavior remains unchanged.
   VERIFY: `pytest tests/test_senseweave_voice.py -q`

2. Band/name helpers map envelope, amp, register, polyphony, preset,
   and timbre values to the documented named outputs at their
   cutpoints.
   VERIFY: `pytest tests/test_senseweave_voice_depth.py::test_voice_helper_bands_map_values_to_named_outputs -q`

3. `build_voice_adsr_snapshot` returns a frozen `VoiceADSRSnapshot`
   whose fields mirror the existing `ADSR` data and preset lookup.
   VERIFY: `pytest tests/test_senseweave_voice_depth.py::test_build_voice_adsr_snapshot_summarizes_envelope -q`

4. `build_voice_plan_report` returns a frozen `VoicePlanReport` that
   captures the live voice timbre, envelope, polyphony state, and
   active-note aggregates end-to-end.
   VERIFY: `pytest tests/test_senseweave_voice_depth.py::test_build_voice_plan_report_resolves_end_to_end_state -q`

5. `summarize_voice_plan_report` returns a stable JSON-safe operator
   summary that round-trips through `json.dumps`.
   VERIFY: `pytest tests/test_senseweave_voice_depth.py::test_summarize_voice_plan_report_returns_json_safe_summary -q`

6. The new report path agrees with `voice_envelope_band`,
   `voice_register_band`, `voice_amp_band`, `voice_polyphony_band`,
   `voice_synth_for_timbre`, `preset_name_for_adsr`, and the live
   `SenseweaveVoice` state for a deterministic case.
   VERIFY: `pytest tests/test_senseweave_voice_depth.py::test_voice_plan_report_agrees_with_existing_helpers -q`

7. Fractal depth for
   `my-claw/tools/senseweave/synthesis/senseweave_voice.py` reaches
   at least depth 2.
   VERIFY: `pytest tests/test_senseweave_voice_depth.py::test_senseweave_voice_reaches_depth_two -q`

8. Startup identity hardening remains covered for first-boot
   persistence and startup wiring in both daemon entrypoints.
   VERIFY: `pytest tests/test_first_boot.py::TestStartupIdentityPersistence tests/test_governor_integration.py::TestStartupIdentityWiring -q`

9. Full project validation remains clean.
   VERIFY: `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/`
