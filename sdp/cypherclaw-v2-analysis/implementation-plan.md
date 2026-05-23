# CypherClaw v2 — Performance, Tuning, Space, and Public Presence PRD — Implementation Plan

**Generated:** 2026-05-23T02:04:45.156402+00:00
**Source:** PRD v1.0
**Total tasks:** 74
**Estimated effort:** ~288 hours

---

## Execution Order

Sprints are sequential. Tasks within a sprint can run in parallel unless a dependency is noted.

### Sprint 0: Infrastructure & Billing

- **T-001** [T1] Provision an `affective_state_bus` SuperCollider control bus shared across voices. (~3h)
- **T-002** [T1] Each voice writes its rolling-window expression intensity to the bus. (~3h)
- **T-003** [T2] Each voice reads the bus and applies a coupling multiplier to its modulator depths. (~6h)
- **T-004** [T1] The bus slow-decays toward 0 in the absence of contributors with a ~5 second time constant. (~3h)
- **T-005** [T1] The `CYPHERCLAW_V2_COUPLING` env flag controls activation, defaulting OFF. (~3h)
- **T-006** [T1] Integration test demonstrates one voice's high vibrato causes a measurable shift in another voice's vibrato depth. (~3h)
- **T-007** [T1] Per-voice fatigue counter with exponential decay (half-life ~30 seconds) is implemented. (~3h)
- **T-008** [T1] When the counter exceeds 0.7, a fatigue multiplier reduces subsequent expression-parameter magnitudes. (~3h)
- **T-009** [T1] Long silences allow the counter to recover toward 0. (~3h)
- **T-010** [T1] The `CYPHERCLAW_V2_FATIGUE` env flag controls activation, defaulting OFF. (~3h)
- **T-011** [T1] Unit tests verify decay behavior, threshold behavior, and recovery behavior. (~3h)

*Subtotal: ~36 hours*

### Sprint 1: Versioning System

**Depends on:** Sprint 0 (Infrastructure & Billing)

- **T-012** [T1] Watch the directory `/home/user/cypherclaw/midi-inbox/` for new MIDI files via `midi_intake_daemon.py`. (~3h) → deps: T-001
- **T-013** [T1] After ingestion, move each processed file to a `processed/` subfolder with a `.json` sidecar manifest of what was extracted. (~3h) → deps: T-001
- **T-014** [T2] Fragment extractor identifies melodic motifs (3 to 7 notes), rhythm cells, chord progressions, and groove patterns from each MIDI file. (~6h) → deps: T-001
- **T-015** [T1] Persist extracted vocabulary in a SQLite database `midi_vocabulary.sqlite` with sufficient schema for composer query (id, source_file, kind, interval_pattern_json, duration_pattern_json, source_key, source_tempo, harmonic_context_json). (~3h) → deps: T-001
- **T-016** [T2] Composer consults vocabulary DB and probabilistically incorporates fragments into generated arcs. (~6h) → deps: T-001
- **T-017** [T2] Faithful-transmission mode bypasses fragment extraction and renders an imported MIDI file as a scene preserving its pitch sequence and rhythm while applying CypherClaw's tunings, voices, and spaces. (~6h) → deps: T-001
- **T-018** [T1] Unit tests cover parsing of MIDI files of varying complexity (single track, multi-track, CC data, pitch bend). (~3h) → deps: T-001
- **T-019** [T1] A dropped MIDI file appears as vocabulary within 60 seconds. (~3h) → deps: T-001

*Subtotal: ~33 hours*

### Sprint 2: Quality Scoring

**Depends on:** Sprint 0 (Infrastructure & Billing), Sprint 1 (Versioning System)

- **T-020** [T1] Extend `GrooveProfile` with a `metric_modulations: list[ModulationEvent]` field. (~3h) → deps: T-001, T-012
- **T-021** [T2] `music_tracker.py` applies metric modulations row-by-row at the correct positions. (~6h) → deps: T-001, T-012
- **T-022** [T2] The composer plans multi-scene meter trajectories per arc; scene metadata carries the trajectory. (~6h) → deps: T-001, T-012
- **T-023** [T1] Unit tests cover metric-modulation correctness for ratios 3:2, 4:3, and 5:4. (~3h) → deps: T-001, T-012

*Subtotal: ~18 hours*

### Sprint 3: Improvement Engine Hardening

**Depends on:** Sprint 0 (Infrastructure & Billing), Sprint 2 (Quality Scoring)

- **T-024** [T2] `audio_streamer.py` produces Opus segments at approximately 6 seconds and approximately 96 kbps from the JACK output bus. (~6h) → deps: T-001, T-020
- **T-025** [T2] Cloudflare Worker accepts segment POSTs at `/api/cypherclaw/segment` and stores them in R2. (~6h) → deps: T-001, T-020
- **T-026** [T1] Cloudflare Worker serves a valid HLS playlist at `/api/cypherclaw/live.m3u8`. (~3h) → deps: T-001, T-020
- **T-027** [T1] The `cypherclaw.holdenu.com` DNS record plus Worker route resolves over HTTPS with a valid certificate. (~3h) → deps: T-001, T-020
- **T-028** [T2] The static page at the root URL renders, plays the live stream, displays a GlyphWeave backdrop, and runs a canvas visualizer driven by the SSE feed. (~6h) → deps: T-001, T-020
- **T-029** [T2] `session_archiver.py` produces a session approximately every 8 minutes or more, names it per CypherClaw's pattern (`{House-Imagery} / {Tuning-Character} — {DD Month}`), and uploads it to the R2 archive path. (~6h) → deps: T-001, T-020
- **T-030** [T1] The archive feed on the page lists sessions in reverse chronological order; each session is playable. (~3h) → deps: T-001, T-020
- **T-031** [T1] The composer code contains no consumer of viewer or listener counts. (~3h) → deps: T-001, T-020
- **T-032** [T2] End-to-end test confirms a tone-generator signal flows from JACK through the streamer, Worker, R2, and back to a browser `<audio>` element within 30 seconds. (~6h) → deps: T-001, T-020

*Subtotal: ~42 hours*

### Sprint 4: Public REST API

**Depends on:** Sprint 0 (Infrastructure & Billing), Sprint 2 (Quality Scoring), Sprint 3 (Improvement Engine Hardening)

- **T-033** [T1] Implement `TuningSystem` abstract base plus concrete `TwelveTET`, `JustIntonation5Limit`, and `GamelanSlendro` classes. (~3h) → deps: T-001, T-020, T-024
- **T-034** [T1] Implement `MorphOperator.pitch_table_at(t)` returning a linearly interpolated pitch table for `t` in `[0.0, 1.0]`. (~3h) → deps: T-001, T-020, T-024
- **T-035** [T1] Implement `pitch_hz(scale_degree, octave, tuning, tonal_center_hz)` that returns the correct frequency for every supported tuning. (~3h) → deps: T-001, T-020, T-024
- **T-036** [T1] The composer emits Hz directly in OSC events when the active tuning is not 12-TET. (~3h) → deps: T-001, T-020, T-024
- **T-037** [T1] Provide a backward-compatible 12-TET tuning system for legacy scenes. (~3h) → deps: T-001, T-020, T-024
- **T-038** [T1] Scene metadata carries the tuning system, morph target, and morph curve. (~3h) → deps: T-001, T-020, T-024
- **T-039** [T2] Composer applies CypherClaw's per-phase tuning rule: 5-limit JI for Listen and Divination; Slendro for Conversation and Procession; morph at stillness-to-motion transitions. (~6h) → deps: T-001, T-020, T-024
- **T-040** [T1] The `CYPHERCLAW_V2_TUNING_MORPH` env flag controls activation, defaulting OFF. (~3h) → deps: T-001, T-020, T-024
- **T-041** [T1] Unit tests verify pitch frequencies match expected ratios within 0.1 cent for all supported tuning systems. (~3h) → deps: T-001, T-020, T-024

*Subtotal: ~30 hours*

### Sprint 5: Library & CRUD Polish

**Depends on:** Sprint 0 (Infrastructure & Billing), Sprint 1 (Versioning System)

- **T-042** [T1] Provision seven dedicated FX buses, one per voice, in master_smooth.scd. (~3h) → deps: T-001, T-012
- **T-043** [T2] Tune a per-voice reverb on each FX bus to match its space description in `cypherclaw-v2-design-statement-2026-05-22.md` §4. (~6h) → deps: T-001, T-012
- **T-044** [T1] Route per-voice audio into the matching FX bus via the `fx_bus_id` parameter on each voice synthdef. (~3h) → deps: T-001, T-012
- **T-045** [T2] Implement mood-driven space selection per scene: matched (default), expressive (deliberate mismatch), house-bound (all voices share the active house's space). (~6h) → deps: T-001, T-012
- **T-046** [T1] Unit tests verify each voice's audio reaches the correct FX bus under each mood mode. (~3h) → deps: T-001, T-012
- **T-047** [T1] Add a `morph_voice` synthdef containing parallel source voices with crossfaded gains controlled by `morph_x`. (~3h) → deps: T-001, T-012
- **T-048** [T2] The composer can request a single-line morph phrase with a source/target voice pair and a morph curve. (~6h) → deps: T-001, T-012
- **T-049** [T1] A section-boundary crossfade scheduler computes per-section release tails that overlap with new section attacks. (~3h) → deps: T-001, T-012
- **T-050** [T1] Within-family parameter walks generate continuous low-rate modulation on key parameters per voice. (~3h) → deps: T-001, T-012
- **T-051** [T1] The `CYPHERCLAW_V2_INSTRUMENT_MORPH` env flag controls activation, defaulting OFF. (~3h) → deps: T-001, T-012
- **T-052** [T1] Unit tests cover crossfade scheduling and morph curve shapes. (~3h) → deps: T-001, T-012
- **T-053** [T2] The composer publishes live MIDI events (note_on, note_off, control_change, pitch_bend) to a `live_midi_emitter.py` daemon that batches and POSTs them to the Cloudflare Worker's `/api/cypherclaw/midi-event` endpoint. Events are tagged with voice, scene, and tuning context. (~6h) → deps: T-001, T-012
- **T-054** [T2] The Cloudflare Worker exposes a `/api/cypherclaw/live-midi` WebSocket (Durable Object backed) that fans out received MIDI events to connected browser clients with sub-second latency. (~6h) → deps: T-001, T-012
- **T-055** [T2] The canvas visualizer on cypherclaw.holdenu.com consumes the live MIDI WebSocket and renders discrete event-driven graphics (e.g. notes appear as discrete shapes with pitch-to-position and velocity-to-size mappings) in addition to the continuous audio-feature reactions. The MIDI feed and audio-feature feed are composited in the same canvas. (~6h) → deps: T-001, T-012
- **T-056** [T1] Depends on CC-001 through CC-005 and CC-102. Render a 60-second reference sample of CypherClaw composing with per-voice reverb spaces active, upload it via `session_archiver.py` as `cypherclaw/archive/checkpoints/feature-1-reverb-spaces-{timestamp}/`, send a Telegram notification with the archive URL on cypherclaw.holdenu.com, and pause the queue until Anthony returns APPROVE / REWORK / REJECT via the checkpoint approval mechanism. (~3h) → deps: T-001, T-012
- **T-057** [T1] Depends on CC-010 through CC-017 and CC-102. Render a 60-second reference sample of CypherClaw composing with MIDI-influenced vocabulary fragments active (with a known seed MIDI in the inbox), upload as `cypherclaw/archive/checkpoints/feature-2-midi-ingestion-{timestamp}/`, send a Telegram notification with the archive URL, and pause until APPROVE / REWORK / REJECT. (~3h) → deps: T-001, T-012
- **T-058** [T1] Render a 60-second reference sample of CypherClaw streaming live on cypherclaw.holdenu.com. CC-020 and CC-022 and CC-024 must be complete. Save a captured copy to `/home/user/cypherclaw/var/reference-renders/feature-3-stream-{timestamp}.opus` for local backup, send a Telegram notification with the public page URL, and pause until Anthony returns APPROVE / REWORK / REJECT. This is the first checkpoint; subsequent checkpoints rely on this streaming pipeline being approved. (~3h) → deps: T-001, T-012
- **T-059** [T1] Depends on CC-030 through CC-033 and CC-102. Render a 60-second reference sample of CypherClaw composing with meter morphing active (a scripted arc that exercises per-scene meter changes plus a metric modulation event), upload as `cypherclaw/archive/checkpoints/feature-4-meter-morph-{timestamp}/`, send a Telegram notification with the archive URL, and pause until APPROVE / REWORK / REJECT. (~3h) → deps: T-001, T-012
- **T-060** [T1] Depends on CC-040 through CC-048 and CC-102. Render a 60-second reference sample with `CYPHERCLAW_V2_TUNING_MORPH=1` (5-limit JI for Listen, Slendro for Conversation, with a morph at the transition), upload as `cypherclaw/archive/checkpoints/feature-5-tuning-morph-{timestamp}/` with both flag-on and flag-off A/B excerpts, send a Telegram notification with the archive URL, and pause until APPROVE / REWORK / REJECT. (~3h) → deps: T-001, T-012
- **T-061** [T1] Depends on CC-050 through CC-055 and CC-102. Render a 60-second reference sample with `CYPHERCLAW_V2_INSTRUMENT_MORPH=1` (a scripted phrase exercising single-line morph, section-boundary crossfade, and within-family parameter walk), upload as `cypherclaw/archive/checkpoints/feature-6-instrument-morph-{timestamp}/` with A/B excerpts, send a Telegram notification with the archive URL, and pause until APPROVE / REWORK / REJECT. (~3h) → deps: T-001, T-012
- **T-062** [T1] Depends on CC-060 through CC-069 and CC-102. Render a 60-second reference sample with the expression layer fully active (all 11 gestures available, voice allowlists enforced, scene-phase scaling applied), upload as `cypherclaw/archive/checkpoints/feature-7-expression-{timestamp}/`, send a Telegram notification with the archive URL, and pause until APPROVE / REWORK / REJECT. (~3h) → deps: T-001, T-012
- **T-063** [T1] Depends on CC-070 through CC-075 and CC-102. Render a 60-second reference sample with `CYPHERCLAW_V2_COUPLING=1` (a scripted multi-voice arc that exercises cross-voice coupling), upload as `cypherclaw/archive/checkpoints/feature-8-coupling-{timestamp}/` with A/B excerpts, send a Telegram notification with the archive URL, and pause until APPROVE / REWORK / REJECT. (~3h) → deps: T-001, T-012
- **T-064** [T1] Depends on CC-080 through CC-084 and CC-102. Render a 60-second reference sample with `CYPHERCLAW_V2_FATIGUE=1` (a scripted high-intensity passage followed by a recovery passage), upload as `cypherclaw/archive/checkpoints/feature-9-fatigue-{timestamp}/` with A/B excerpts, send a Telegram notification with the archive URL, and pause until APPROVE / REWORK / REJECT. (~3h) → deps: T-001, T-012

*Subtotal: ~87 hours*

### Sprint 6: Stretch Goals

**Depends on:** Sprint 0 (Infrastructure & Billing)

- **T-065** [T2] All voice synthdefs accept the expression control parameters: `vib_rate`, `vib_depth`, `trem_rate`, `trem_depth`, `bend_start_hz`, `bend_end_hz`, `bend_curve_shape`, `attack_mode`, `late_release_extension`, `harmonic_resonance_profile_id`, `spectral_granulation_amount`, `spectral_smear_amount`. (~6h) → deps: T-001
- **T-066** [T2] Each voice provides internal LFOs (vibrato pitch LFO, tremolo amplitude LFO, spectral granulation) where allowed by the voice's gesture allowlist. (~6h) → deps: T-001
- **T-067** [T2] The expression module implements 11 named gestures (Weeping, Shimmering, Ghostly, Sighing, Agitated, Breath-shaped, Pulsing, Fracturing, Hollowing, Tension-Build, Echo-Location). (~6h) → deps: T-001
- **T-068** [T1] The voice-to-gesture allowlist per `cypherclaw-v2-design-statement-2026-05-22.md` §7.3 is enforced; forbidden combinations are rejected. (~3h) → deps: T-001
- **T-069** [T1] The scene-phase intensity multiplier table per §7.4 is applied at gesture application time. (~3h) → deps: T-001
- **T-070** [T2] Pedal logic (Sustain, Resonant with Decay Modulation, Half-pedal) is implemented per voice family. (~6h) → deps: T-001
- **T-071** [T1] Contour analysis classifies each note as peak, ascending, descending, static, or valley. (~3h) → deps: T-001
- **T-072** [T1] The composer applies contour-aware dynamics multipliers and attack shapes when emitting notes. (~3h) → deps: T-001
- **T-073** [T1] Unit tests cover each gesture's expression-parameter output. (~3h) → deps: T-001
- **T-074** [T1] The renamed terminology (Spectral Granulation, Harmonic Resonance Profile, Spectral Smear) is used consistently across code, schemas, and documentation. (~3h) → deps: T-001

*Subtotal: ~42 hours*

---

## Requirements Coverage

- **MUST requirements:** 73/73 covered
- **SHOULD requirements:** 1 included as stretch

**✓ All MUST requirements covered.**

---

## Critical Path

The critical path runs through: Sprint 0 (Infrastructure) → Sprint 1 (Versioning) → Sprint 2 (Scoring) → Sprint 3 (Improvement) → Sprint 4 (API). Sprint 5 (Polish) can overlap with Sprints 2–4. Sprint 6 (Stretch) is fully deferrable.
