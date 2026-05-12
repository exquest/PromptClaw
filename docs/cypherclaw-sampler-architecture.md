# CypherClaw Sampler Architecture

## Scope

This document is the architectural reference for the CypherClaw sampler
subsystem as it stands in the current tree. It is meant for an engineer
who needs to understand how the landed sampler pieces fit together,
where to make a change, and which misuse patterns the system already
guards against.

It deliberately does *not* duplicate two adjacent documents:

- [docs/cypherclaw-sampler-artistic-intent.md](cypherclaw-sampler-artistic-intent.md)
  is the short artistic statement for the sampler. Read it when you
  need the aesthetic goals, the sampler's role inside the quintet, and
  the intended listener experience without the implementation detail.
- [my-claw/sdp/prd-cypherclaw-sampler.md](../my-claw/sdp/prd-cypherclaw-sampler.md)
  is the product requirements document. It defines the artistic intent,
  the five governing principles, the five-phase delivery plan, and the
  end-to-end acceptance demonstration. Read the PRD when you need to
  know *why* a piece exists or *what* the eventual quintet should feel
  like.
- [docs/cypherclaw-musicianship-roadmap.md](cypherclaw-musicianship-roadmap.md)
  records the current ensemble snapshot — the signature quintet
  (`sw_bell_warm`, `sw_bowed`, `sw_breath`, `sw_pad`, `sw_sampler`) and
  the landed-vs-pending status of the sampler rollout. Read the roadmap
  when you need a one-page status of where the sampler sits in the
  larger musicianship plan.

This file fills the gap between those two: it describes the components,
the signal flow, the antipatterns, and the integration seams that exist
*today*, with concrete file paths so a reader can jump straight to the
code.

## Components

The sampler is built from a small set of files spread across the
`my-claw/tools/` tree. Each module has one responsibility.

| File | Responsibility |
| --- | --- |
| `my-claw/tools/sample_capture_daemon.py` | Long-running capture process. Maintains 60-second JACK ring buffers for the contact mic, room mic, and the SuperCollider self bus. Hosts the `InterestingMomentDetector`, the `AcousticFeatures` analyzer, the contextual+acoustic tagger (`build_sample_tags`), the `SampleIndex` SQLite persistence layer, the `save_capture` write path, and the post-song `self_quote()` hook. |
| `my-claw/tools/sample_capture_verify.py` | Deterministic smoke verifier. Synthesizes a known room sound, drives `save_capture`, and asserts the descriptor lands in `index.sqlite` with the expected context and acoustic tags. Used to sanity-check the capture pipeline without requiring live audio hardware. |
| `my-claw/tools/sampler_fx_mode_verify.py` | Hardware-free smoke verifier for the sampler effects bus. Drives `EffectsBus.apply_mode(mode)` through all five canonical ArtistModes and asserts the resulting `/n_set` state on `sw_sampler_fx` matches `FX_PRESETS_BY_MODE`. |
| `my-claw/tools/senseweave/sampler_buffers.py` | `BufferLoader` — an LRU-bounded scsynth buffer pool. Issues `/b_alloc` and `/b_allocRead` over OSC, evicts the least-recently-used buffer through `on_sampler_free()` when capacity is reached, and returns a stable `bufnum` to the dispatcher. |
| `my-claw/tools/senseweave/sampler_dispatch.py` | `SamplerDispatcher` — turns a `(SampleRecord, params)` pair into the OSC bundle that triggers the granular voice. Acquires a buffer through the loader, ships `/s_new sw_sampler bufnum=… grain_size=… density=…`, and returns a handle for sustained voices to release later. Folds the per-sample `gain_db` into the synth `amp` so peak-normalized captures play back at consistent loudness. `EffectsBus` (also in this file) manages the per-mode FX preset application to the shared bus. |
| `my-claw/tools/senseweave/synthesis/sampler_effects.scd` | SuperCollider source for the `sw_sampler_fx` SynthDef — the dedicated effects bus that sits between the sampler voice and the master bus. Owns the long delay, convolution/FreeVerb reverb, spectral freeze, and the comb resonance tuned to the room's B fundamental (61.74 Hz). |
| `my-claw/tools/senseweave/render/antipatterns.py` | Render-time misuse detection. Hosts `detect_sampler_dominating` and `detect_sampler_silent_quintet_member`, both of which surface through the metrics gate and operator diagnostics. |

Pieces named in the PRD but **not** in the tree yet — `SampleLibrary`,
`SampleSelector`, the `sw_sampler.scd` granular SynthDef itself, and a
quintet-aware `artist_identity.py` — are tracked under "Status" below
and in the roadmap.

## Signal Flow

A captured moment moves through the system in one direction. The chain
below traces a single fragment from the room to the speakers.

1. **JACK input.** The capture daemon opens `system:capture_1`
   (contact mic) and `system:capture_2` (room mic), plus a managed
   loopback from `SuperCollider:out_1` for self-quotation. JACK xruns
   are logged but never crash the daemon.
2. **Rolling buffer.** Each input feeds a 60-second numpy ring buffer
   at 48 kHz inside `sample_capture_daemon.py`. The
   `InterestingMomentDetector` pulls 1-second windows every 250 ms and
   runs spectral-flux, RMS, and transient-density checks against
   tunable thresholds.
3. **Interesting-moment flag.** When a window crosses the thresholds
   (and the `since_last_capture` cooldown has elapsed), the detector
   expands it to a 4–8 second capture window centered on the flagged
   sub-window. The size scales with spectral richness.
4. **Tag.** `build_sample_tags()` merges contextual tags pulled from
   `/tmp/organism_state.json` and `/tmp/room_presence.json`
   (`arc_phase`, `mood`, `presence`, time-of-day) with acoustic tags
   derived from `AcousticFeatures` heuristics (`warm`, `metallic`,
   `sustained`, `percussive`, `harmonic`, …). Tags are validated
   against the controlled `CHARACTER_TAGS` vocabulary.
5. **Store.** `save_capture()` writes a 24-bit / 48 kHz mono WAV to
   `samples/contact/`, `samples/room/`, or `samples/self/`,
   peak-normalizes to −1 dBFS unless the input is below −30 dBFS, and
   inserts a row into `index.sqlite` carrying the flattened tag
   columns plus the JSON tag payload and the `gain_db` adjustment.
6. **Selection.** *(pending — see Status.)* Today the composer drives
   sampler events through a placeholder selection path. Once the
   `SampleSelector` lands, it will pick a `SampleRecord` per piece
   based on mode, arc phase, mood, and rolling avoid-recent windows.
7. **Dispatch.** The composer calls `SamplerDispatcher.dispatch_sample()`
   (or `play_sampler()` / `start_sampler()` / `stop_sampler()` for
   fire-and-forget vs. sustained lifecycles). The dispatcher acquires
   a `bufnum` from the `BufferLoader`, evicting an older buffer if
   needed, then ships an OSC bundle with `/s_new sw_sampler bufnum=…
   grain_size=… density=… pitch_transpose=… amp=… fx_send=…`. The
   composer also calls `EffectsBus.apply_mode(mode)` on mode changes
   to update the effects bus parameters. `sampler_fx_mode_verify.py`
   is the manual smoke path for this seam: it walks every mode and
   asserts the bus reflects the canonical preset after each change.
8. **Sampler effects bus.** The `sw_sampler_fx` SynthDef defined in
   `sampler_effects.scd` reads the granular cloud, applies delay,
   reverb, optional spectral freeze, and the comb-to-B resonance, and
   writes the processed signal onward.
9. **Master bus.** The sampler effects bus output lands in the
   sampler mix slot inside `master_bus.py`, peak-normalized with a
   gentler 1.5:1 compression ratio so grain transients survive the
   mix. From there the signal joins the rest of the orchestra and
   reaches the speakers.

The reverse path — composer self-quotation — is a short branch off
step 1: when a piece ends with `arc_payoff > 0.6` and `click_count == 0`
(and the mode is not `working_ambience`), `self_quote()` captures a
4-second window from the SuperCollider loopback and feeds it back into
step 4.

## Antipatterns

Two render-time detectors live in
`my-claw/tools/senseweave/render/antipatterns.py`. Both surface through
the existing metrics-gate path and into operator diagnostics.

- **`sampler_dominating`** — fires per piece when the sampler accounts
  for more than ~60% of total events (`SAMPLER_DOMINATING_RATIO_THRESHOLD`).
  It opens at `severity="warning"` and escalates to `"fail"` after a
  configurable consecutive-piece streak. Guards against the sampler
  taking over the ensemble: the quintet discipline is "heavy sampler
  use replaces, not adds."
- **`sampler_silent_quintet_member`** — fires across a rolling
  50-piece window when sampler usage drops below a mode-weighted
  floor. The threshold scales with the active mode's `sampler_density`
  reference, so `working_ambience` (density 0.1) does not trip it
  while `solitary` (density 0.7) holds the full bar. Guards against
  the sampler quietly disappearing from the quintet so that no one
  notices the memory voice has gone silent for days.

Both detectors take their identifiers verbatim from
`render/antipatterns.py`; the doc regression test pins those names so
a rename in code forces a doc update.

## Mode Density Reference

`sampler_density` is the canonical scheduling weight for `sw_sampler`.
It does not mean gain, wetness, or prominence in the mix. It tells the
composer and diagnostics how much of a piece's phrase grid the memory
voice should occupy on average. CCS-023 turns it into
`floor(density * total_phrases) + Bernoulli(density)` scheduled sampler
events, and CCS-030 uses the same value as the reference weight for the
rolling "silent quintet member" detector.

| Mode | `sampler_density` | Scheduling intent |
| --- | --- | --- |
| `solitary` | `0.70` | Heavy memory-voice presence; the room can listen back to itself often. |
| `companion` | `0.25` | Light sampler participation; memory colors the piece without taking over. |
| `working_ambience` | `0.10` | Minimal sampler usage so focused work stays undisturbed. |
| `evening_reflection` | `0.65` | Frequent sampler entries during the most reflective, risk-tolerant mode. |
| `storm` | `0.45` | Moderate-heavy sampler use to add pressure without dominating the ensemble. |

## Integration Points

The sampler does not run in isolation. These are the seams where it
plugs into the rest of CypherClaw.

- **Identity layer — `my-claw/tools/senseweave/artist_identity.py`.**
  Owns `SIGNATURE_VOICES`, the per-mode `sampler_density`, and the
  `VOICE_ROLES` map. The quintet target is documented in the
  musicianship roadmap; the file itself is on the pending list (see
  Status). The capture daemon also calls `bootstrap_identity()` from
  `src/cypherclaw/first_boot.py` during `main()` so a first boot mints
  and persists an `InstanceIdentity` before any JACK connection or
  capture write happens.
- **Cast planner — `my-claw/tools/senseweave/cast_planner.py`.**
  `select_cast_ids` takes `preferred_synths` and `voice_count_target`;
  the sampler joins the cast through this same path. Once
  `SampleSelector` lands, a `SampleRecord` will be attached to sampler
  cast entries at commission time so the dispatcher does not have to
  re-pick.
- **Mix engine — `my-claw/tools/senseweave/master_bus.py` and
  `mix_engine.py`.** Defines the `sampler_bus` mix slot, its peak-
  normalized gain staging, and the gentler `compression_ratio = 1.5`
  used to preserve grain transients. The `sw_master_smooth` SynthDef
  exposes `sampler_amp` and `sampler_bypass_comp` controls so live
  rebalancing does not require restarting scsynth.
- **Composer hooks — `my-claw/tools/duet_composer.py`.** Hosts the
  per-piece sampler density gate, the post-piece self-quotation hook
  that calls into the capture daemon, and the dispatch path that turns
  cast metadata into sampler OSC traffic.
- **Operator diagnostics —
  `my-claw/tools/senseweave/operator_diagnostics.py`.** Reads
  `/tmp/sampler_state.json` (written by the capture daemon every
  ~1 sec) and exposes a `sampler_status()` summary covering capture
  liveness, last-capture descriptor, and currently-playing sample
  handles. The face / inkplate renderers consume the same surface to
  display "♫ sampling room" and "♫ memory: …" banners.

## Status

The sampler is a partial-rollout subsystem. This document covers what
exists today; the broader plan and per-task status live elsewhere.

**Landed and described above:**

- Capture daemon, smoke verifier, ring buffers, interesting-moment
  detector, contextual+acoustic tagger, SQLite index, `save_capture`
  write path, `self_quote` hook.
- `sampler_fx_mode_verify.py` hardware-free mode-preset smoke verifier.
- `BufferLoader` LRU pool (`sampler_buffers.py`).
- `SamplerDispatcher` and per-mode FX presets (`sampler_dispatch.py`).
- `sw_sampler_fx` effects-bus SynthDef
  (`synthesis/sampler_effects.scd`).
- `sampler_dominating` and `sampler_silent_quintet_member` detectors
  (`render/antipatterns.py`).
- Master-bus slot, `sampler_amp` / `sampler_bypass_comp` controls on
  `sw_master_smooth`, capture-daemon `bootstrap_identity()` invocation.

**Still pending — referenced by the PRD but not in the tree yet:**

- `SampleLibrary` — on-disk store + tag index abstraction over
  `index.sqlite`.
- `SampleSelector` — mode/arc/mood-aware deterministic picker.
- `sw_sampler.scd` — the granular SynthDef itself (the effects-bus
  SynthDef that processes its output is present, the source is not).
- Quintet convergence in `artist_identity.py` and
  `tests/test_artist_identity.py`, which still encode a quartet.

For the longer plan, the five phases, the principles, and the
end-of-PRD demonstration, see
[my-claw/sdp/prd-cypherclaw-sampler.md](../my-claw/sdp/prd-cypherclaw-sampler.md).
For the shorter listener-facing statement of why the memory voice
exists, see
[docs/cypherclaw-sampler-artistic-intent.md](cypherclaw-sampler-artistic-intent.md).
For the per-piece status snapshot in the larger musicianship program,
see
[docs/cypherclaw-musicianship-roadmap.md](cypherclaw-musicianship-roadmap.md).
