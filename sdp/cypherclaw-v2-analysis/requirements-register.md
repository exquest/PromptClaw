# Requirements Register — CypherClaw v2 — Performance, Tuning, Space, and Public Presence PRD

**Extracted:** 2026-05-23T02:04:45.157421+00:00
**Total requirements:** 74

| ID | Description | Priority | Tier | Section |
|----|-------------|----------|------|---------|
| CC-001 | Provision seven dedicated FX buses, one per voice, in master_smooth.scd. | MUST | T1 |  |
| CC-002 | Tune a per-voice reverb on each FX bus to match its space description in `cypherclaw-v2-design-statement-2026-05-22.md` §4. | MUST | T2 |  |
| CC-003 | Route per-voice audio into the matching FX bus via the `fx_bus_id` parameter on each voice synthdef. | MUST | T1 |  |
| CC-004 | Implement mood-driven space selection per scene: matched (default), expressive (deliberate mismatch), house-bound (all voices share the active house's space). | MUST | T2 |  |
| CC-005 | Unit tests verify each voice's audio reaches the correct FX bus under each mood mode. | MUST | T1 |  |
| CC-010 | Watch the directory `/home/user/cypherclaw/midi-inbox/` for new MIDI files via `midi_intake_daemon.py`. | MUST | T1 |  |
| CC-011 | After ingestion, move each processed file to a `processed/` subfolder with a `.json` sidecar manifest of what was extracted. | MUST | T1 |  |
| CC-012 | Fragment extractor identifies melodic motifs (3 to 7 notes), rhythm cells, chord progressions, and groove patterns from each MIDI file. | MUST | T2 |  |
| CC-013 | Persist extracted vocabulary in a SQLite database `midi_vocabulary.sqlite` with sufficient schema for composer query (id, source_file, kind, interval_pattern_json, duration_pattern_json, source_key, source_tempo, harmonic_context_json). | MUST | T1 |  |
| CC-014 | Composer consults vocabulary DB and probabilistically incorporates fragments into generated arcs. | MUST | T2 |  |
| CC-015 | Faithful-transmission mode bypasses fragment extraction and renders an imported MIDI file as a scene preserving its pitch sequence and rhythm while applying CypherClaw's tunings, voices, and spaces. | MUST | T2 |  |
| CC-016 | Unit tests cover parsing of MIDI files of varying complexity (single track, multi-track, CC data, pitch bend). | MUST | T1 |  |
| CC-017 | A dropped MIDI file appears as vocabulary within 60 seconds. | MUST | T1 |  |
| CC-020 | `audio_streamer.py` produces Opus segments at approximately 6 seconds and approximately 96 kbps from the JACK output bus. | MUST | T2 |  |
| CC-021 | Cloudflare Worker accepts segment POSTs at `/api/cypherclaw/segment` and stores them in R2. | MUST | T2 |  |
| CC-022 | Cloudflare Worker serves a valid HLS playlist at `/api/cypherclaw/live.m3u8`. | MUST | T1 |  |
| CC-023 | The `cypherclaw.holdenu.com` DNS record plus Worker route resolves over HTTPS with a valid certificate. | MUST | T1 |  |
| CC-024 | The static page at the root URL renders, plays the live stream, displays a GlyphWeave backdrop, and runs a canvas visualizer driven by the SSE feed. | MUST | T2 |  |
| CC-025 | `session_archiver.py` produces a session approximately every 8 minutes or more, names it per CypherClaw's pattern (`{House-Imagery} / {Tuning-Character} — {DD Month}`), and uploads it to the R2 archive path. | MUST | T2 |  |
| CC-026 | The archive feed on the page lists sessions in reverse chronological order; each session is playable. | MUST | T1 |  |
| CC-027 | The composer code contains no consumer of viewer or listener counts. | MUST | T1 |  |
| CC-028 | End-to-end test confirms a tone-generator signal flows from JACK through the streamer, Worker, R2, and back to a browser `<audio>` element within 30 seconds. | MUST | T2 |  |
| CC-030 | Extend `GrooveProfile` with a `metric_modulations: list[ModulationEvent]` field. | MUST | T1 |  |
| CC-031 | `music_tracker.py` applies metric modulations row-by-row at the correct positions. | MUST | T2 |  |
| CC-032 | The composer plans multi-scene meter trajectories per arc; scene metadata carries the trajectory. | MUST | T2 |  |
| CC-033 | Unit tests cover metric-modulation correctness for ratios 3:2, 4:3, and 5:4. | MUST | T1 |  |
| CC-040 | Implement `TuningSystem` abstract base plus concrete `TwelveTET`, `JustIntonation5Limit`, and `GamelanSlendro` classes. | MUST | T1 |  |
| CC-041 | Implement `MorphOperator.pitch_table_at(t)` returning a linearly interpolated pitch table for `t` in `[0.0, 1.0]`. | MUST | T1 |  |
| CC-042 | Implement `pitch_hz(scale_degree, octave, tuning, tonal_center_hz)` that returns the correct frequency for every supported tuning. | MUST | T1 |  |
| CC-043 | The composer emits Hz directly in OSC events when the active tuning is not 12-TET. | MUST | T1 |  |
| CC-044 | Provide a backward-compatible 12-TET tuning system for legacy scenes. | MUST | T1 |  |
| CC-045 | Scene metadata carries the tuning system, morph target, and morph curve. | MUST | T1 |  |
| CC-046 | Composer applies CypherClaw's per-phase tuning rule: 5-limit JI for Listen and Divination; Slendro for Conversation and Procession; morph at stillness-to-motion transitions. | MUST | T2 |  |
| CC-047 | The `CYPHERCLAW_V2_TUNING_MORPH` env flag controls activation, defaulting OFF. | MUST | T1 |  |
| CC-048 | Unit tests verify pitch frequencies match expected ratios within 0.1 cent for all supported tuning systems. | MUST | T1 |  |
| CC-050 | Add a `morph_voice` synthdef containing parallel source voices with crossfaded gains controlled by `morph_x`. | MUST | T1 |  |
| CC-051 | The composer can request a single-line morph phrase with a source/target voice pair and a morph curve. | MUST | T2 |  |
| CC-052 | A section-boundary crossfade scheduler computes per-section release tails that overlap with new section attacks. | MUST | T1 |  |
| CC-053 | Within-family parameter walks generate continuous low-rate modulation on key parameters per voice. | MUST | T1 |  |
| CC-054 | The `CYPHERCLAW_V2_INSTRUMENT_MORPH` env flag controls activation, defaulting OFF. | MUST | T1 |  |
| CC-055 | Unit tests cover crossfade scheduling and morph curve shapes. | MUST | T1 |  |
| CC-060 | All voice synthdefs accept the expression control parameters: `vib_rate`, `vib_depth`, `trem_rate`, `trem_depth`, `bend_start_hz`, `bend_end_hz`, `bend_curve_shape`, `attack_mode`, `late_release_extension`, `harmonic_resonance_profile_id`, `spectral_granulation_amount`, `spectral_smear_amount`. | MUST | T2 |  |
| CC-061 | Each voice provides internal LFOs (vibrato pitch LFO, tremolo amplitude LFO, spectral granulation) where allowed by the voice's gesture allowlist. | MUST | T2 |  |
| CC-062 | The expression module implements 11 named gestures (Weeping, Shimmering, Ghostly, Sighing, Agitated, Breath-shaped, Pulsing, Fracturing, Hollowing, Tension-Build, Echo-Location). | MUST | T2 |  |
| CC-063 | The voice-to-gesture allowlist per `cypherclaw-v2-design-statement-2026-05-22.md` §7.3 is enforced; forbidden combinations are rejected. | MUST | T1 |  |
| CC-064 | The scene-phase intensity multiplier table per §7.4 is applied at gesture application time. | MUST | T1 |  |
| CC-065 | Pedal logic (Sustain, Resonant with Decay Modulation, Half-pedal) is implemented per voice family. | MUST | T2 |  |
| CC-066 | Contour analysis classifies each note as peak, ascending, descending, static, or valley. | MUST | T1 |  |
| CC-067 | The composer applies contour-aware dynamics multipliers and attack shapes when emitting notes. | MUST | T1 |  |
| CC-068 | The renamed terminology (Spectral Granulation, Harmonic Resonance Profile, Spectral Smear) is used consistently across code, schemas, and documentation. | SHOULD | T1 |  |
| CC-069 | Unit tests cover each gesture's expression-parameter output. | MUST | T1 |  |
| CC-070 | Provision an `affective_state_bus` SuperCollider control bus shared across voices. | MUST | T1 |  |
| CC-071 | Each voice writes its rolling-window expression intensity to the bus. | MUST | T1 |  |
| CC-072 | Each voice reads the bus and applies a coupling multiplier to its modulator depths. | MUST | T2 |  |
| CC-073 | The bus slow-decays toward 0 in the absence of contributors with a ~5 second time constant. | MUST | T1 |  |
| CC-074 | The `CYPHERCLAW_V2_COUPLING` env flag controls activation, defaulting OFF. | MUST | T1 |  |
| CC-075 | Integration test demonstrates one voice's high vibrato causes a measurable shift in another voice's vibrato depth. | MUST | T1 |  |
| CC-080 | Per-voice fatigue counter with exponential decay (half-life ~30 seconds) is implemented. | MUST | T1 |  |
| CC-081 | When the counter exceeds 0.7, a fatigue multiplier reduces subsequent expression-parameter magnitudes. | MUST | T1 |  |
| CC-082 | Long silences allow the counter to recover toward 0. | MUST | T1 |  |
| CC-083 | The `CYPHERCLAW_V2_FATIGUE` env flag controls activation, defaulting OFF. | MUST | T1 |  |
| CC-084 | Unit tests verify decay behavior, threshold behavior, and recovery behavior. | MUST | T1 |  |
| CC-090 | The composer publishes live MIDI events (note_on, note_off, control_change, pitch_bend) to a `live_midi_emitter.py` daemon that batches and POSTs them to the Cloudflare Worker's `/api/cypherclaw/midi-event` endpoint. Events are tagged with voice, scene, and tuning context. | MUST | T2 |  |
| CC-091 | The Cloudflare Worker exposes a `/api/cypherclaw/live-midi` WebSocket (Durable Object backed) that fans out received MIDI events to connected browser clients with sub-second latency. | MUST | T2 |  |
| CC-092 | The canvas visualizer on cypherclaw.holdenu.com consumes the live MIDI WebSocket and renders discrete event-driven graphics (e.g. notes appear as discrete shapes with pitch-to-position and velocity-to-size mappings) in addition to the continuous audio-feature reactions. The MIDI feed and audio-feature feed are composited in the same canvas. | MUST | T2 |  |
| CC-100 | Depends on CC-001 through CC-005 and CC-102. Render a 60-second reference sample of CypherClaw composing with per-voice reverb spaces active, upload it via `session_archiver.py` as `cypherclaw/archive/checkpoints/feature-1-reverb-spaces-{timestamp}/`, send a Telegram notification with the archive URL on cypherclaw.holdenu.com, and pause the queue until Anthony returns APPROVE / REWORK / REJECT via the checkpoint approval mechanism. | MUST | T1 |  |
| CC-101 | Depends on CC-010 through CC-017 and CC-102. Render a 60-second reference sample of CypherClaw composing with MIDI-influenced vocabulary fragments active (with a known seed MIDI in the inbox), upload as `cypherclaw/archive/checkpoints/feature-2-midi-ingestion-{timestamp}/`, send a Telegram notification with the archive URL, and pause until APPROVE / REWORK / REJECT. | MUST | T1 |  |
| CC-102 | Render a 60-second reference sample of CypherClaw streaming live on cypherclaw.holdenu.com. CC-020 and CC-022 and CC-024 must be complete. Save a captured copy to `/home/user/cypherclaw/var/reference-renders/feature-3-stream-{timestamp}.opus` for local backup, send a Telegram notification with the public page URL, and pause until Anthony returns APPROVE / REWORK / REJECT. This is the first checkpoint; subsequent checkpoints rely on this streaming pipeline being approved. | MUST | T1 |  |
| CC-103 | Depends on CC-030 through CC-033 and CC-102. Render a 60-second reference sample of CypherClaw composing with meter morphing active (a scripted arc that exercises per-scene meter changes plus a metric modulation event), upload as `cypherclaw/archive/checkpoints/feature-4-meter-morph-{timestamp}/`, send a Telegram notification with the archive URL, and pause until APPROVE / REWORK / REJECT. | MUST | T1 |  |
| CC-104 | Depends on CC-040 through CC-048 and CC-102. Render a 60-second reference sample with `CYPHERCLAW_V2_TUNING_MORPH=1` (5-limit JI for Listen, Slendro for Conversation, with a morph at the transition), upload as `cypherclaw/archive/checkpoints/feature-5-tuning-morph-{timestamp}/` with both flag-on and flag-off A/B excerpts, send a Telegram notification with the archive URL, and pause until APPROVE / REWORK / REJECT. | MUST | T1 |  |
| CC-105 | Depends on CC-050 through CC-055 and CC-102. Render a 60-second reference sample with `CYPHERCLAW_V2_INSTRUMENT_MORPH=1` (a scripted phrase exercising single-line morph, section-boundary crossfade, and within-family parameter walk), upload as `cypherclaw/archive/checkpoints/feature-6-instrument-morph-{timestamp}/` with A/B excerpts, send a Telegram notification with the archive URL, and pause until APPROVE / REWORK / REJECT. | MUST | T1 |  |
| CC-106 | Depends on CC-060 through CC-069 and CC-102. Render a 60-second reference sample with the expression layer fully active (all 11 gestures available, voice allowlists enforced, scene-phase scaling applied), upload as `cypherclaw/archive/checkpoints/feature-7-expression-{timestamp}/`, send a Telegram notification with the archive URL, and pause until APPROVE / REWORK / REJECT. | MUST | T1 |  |
| CC-107 | Depends on CC-070 through CC-075 and CC-102. Render a 60-second reference sample with `CYPHERCLAW_V2_COUPLING=1` (a scripted multi-voice arc that exercises cross-voice coupling), upload as `cypherclaw/archive/checkpoints/feature-8-coupling-{timestamp}/` with A/B excerpts, send a Telegram notification with the archive URL, and pause until APPROVE / REWORK / REJECT. | MUST | T1 |  |
| CC-108 | Depends on CC-080 through CC-084 and CC-102. Render a 60-second reference sample with `CYPHERCLAW_V2_FATIGUE=1` (a scripted high-intensity passage followed by a recovery passage), upload as `cypherclaw/archive/checkpoints/feature-9-fatigue-{timestamp}/` with A/B excerpts, send a Telegram notification with the archive URL, and pause until APPROVE / REWORK / REJECT. | MUST | T1 |  |