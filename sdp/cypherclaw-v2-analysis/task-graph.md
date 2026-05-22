# CypherClaw v2 — Performance, Tuning, Space, and Public Presence PRD — Task Graph

**Generated:** 2026-05-22T23:57:10.803724+00:00
**Total tasks:** 62
**Estimated effort:** ~243 hours

---

## Sprint 0 — Infrastructure & Billing

| Order | Task ID | Description | Tier | Complexity | Est (hrs) | Reqs | Deps | Criteria |
|-------|---------|-------------|------|------------|-----------|------|------|----------|
| 1 | T-001 | Provision an `affective_state_bus` SuperCollider control bus shared across voices. | T1 | 4 | 3 | CC-070 | — | Synthdef diff shows the new control bus and reader-side wiring per voice. |
| 2 | T-002 | Each voice writes its rolling-window expression intensity to the bus. | T1 | 3 | 3 | CC-071 | — | OSC trace shows per-voice writes with the expected window length and value range. |
| 3 | T-003 | Each voice reads the bus and applies a coupling multiplier to its modulator depths. | T2 | 3 | 6 | CC-072 | — | Integration test confirms one voice's high vibrato measurably shifts another voice's vibrato depth on the bus. |
| 4 | T-004 | The bus slow-decays toward 0 in the absence of contributors with a ~5 second time constant. | T1 | 3 | 3 | CC-073 | — | Unit test seeds the bus and verifies decay timing. |
| 5 | T-005 | The `CYPHERCLAW_V2_COUPLING` env flag controls activation, defaulting OFF. | T1 | 3 | 3 | CC-074 | — | Module reads env var; default behavior matches OFF state. |
| 6 | T-006 | Integration test demonstrates one voice's high vibrato causes a measurable shift in another voice's vibrato depth. | T1 | 3 | 3 | CC-075 | — | Test passes by asserting the secondary voice's vibrato depth lifts by at least the expected coupling delta. |
| 7 | T-007 | Per-voice fatigue counter with exponential decay (half-life ~30 seconds) is implemented. | T1 | 3 | 3 | CC-080 | — | Unit test verifies decay timing against synthetic note streams. |
| 8 | T-008 | When the counter exceeds 0.7, a fatigue multiplier reduces subsequent expression-parameter magnitudes. | T1 | 3 | 3 | CC-081 | — | Unit test asserts the multiplier is applied above the threshold and not applied below it. |
| 9 | T-009 | Long silences allow the counter to recover toward 0. | T1 | 2 | 3 | CC-082 | — | Unit test confirms recovery behavior. |
| 10 | T-010 | The `CYPHERCLAW_V2_FATIGUE` env flag controls activation, defaulting OFF. | T1 | 3 | 3 | CC-083 | — | Module reads env var; default behavior matches OFF state. |
| 11 | T-011 | Unit tests verify decay behavior, threshold behavior, and recovery behavior. | T1 | 5 | 3 | CC-084 | — | Tests cover all three behaviors with explicit assertions. |

**Sprint 0 total:** ~36 hrs

---

## Sprint 1 — Versioning System

| Order | Task ID | Description | Tier | Complexity | Est (hrs) | Reqs | Deps | Criteria |
|-------|---------|-------------|------|------------|-----------|------|------|----------|
| 12 | T-012 | Watch the directory `/home/user/cypherclaw/midi-inbox/` for new MIDI files via `midi_intake_daemon.py`. | T1 | 3 | 3 | CC-010 | T-001 | Daemon log shows discovery within 30 seconds of a file appearing in the inbox. |
| 13 | T-013 | After ingestion, move each processed file to a `processed/` subfolder with a `.json` sidecar manifest of what was extracted. | T1 | 3 | 3 | CC-011 | T-001 | Integration test drops a MIDI file and verifies the file moves and the sidecar exists with the expected fields. |
| 14 | T-014 | Fragment extractor identifies melodic motifs (3 to 7 notes), rhythm cells, chord progressions, and groove patterns from each MIDI file. | T2 | 4 | 6 | CC-012 | T-001 | Unit tests on hand-crafted MIDIs assert the expected fragments are extracted. |
| 15 | T-015 | Persist extracted vocabulary in a SQLite database `midi_vocabulary.sqlite` with sufficient schema for composer query (id, source_file, kind, interval_pattern_json, duration_pattern_json, source_key, source_tempo, harmonic_context_json). | T1 | 5 | 3 | CC-013 | T-001 | Schema migration script exists; sample query returns expected rows. |
| 16 | T-016 | Composer consults vocabulary DB and probabilistically incorporates fragments into generated arcs. | T2 | 4 | 6 | CC-014 | T-001 | Composer log shows fragment IDs cited in scenes when a vocabulary DB is populated; cited rate aligns with the curiosity parameter. |
| 17 | T-017 | Faithful-transmission mode bypasses fragment extraction and renders an imported MIDI file as a scene preserving its pitch sequence and rhythm while applying CypherClaw's tunings, voices, and spaces. | T2 | 4 | 6 | CC-015 | T-001 | Integration test: a `.faithful` sidecar flag on a known MIDI file results in a scene whose note-sequence matches the input within tuning quantization. |
| 18 | T-018 | Unit tests cover parsing of MIDI files of varying complexity (single track, multi-track, CC data, pitch bend). | T1 | 3 | 3 | CC-016 | T-001 | Test suite parses at least 5 sample MIDIs and asserts correct extraction of tempo, key, tracks, CCs. |
| 19 | T-019 | A dropped MIDI file appears as vocabulary within 60 seconds. | T1 | 3 | 3 | CC-017 | T-001 | End-to-end integration test verifies the timing budget. |

**Sprint 1 total:** ~33 hrs

---

## Sprint 2 — Quality Scoring

| Order | Task ID | Description | Tier | Complexity | Est (hrs) | Reqs | Deps | Criteria |
|-------|---------|-------------|------|------------|-----------|------|------|----------|
| 20 | T-020 | Extend `GrooveProfile` with a `metric_modulations: list[ModulationEvent]` field. | T1 | 3 | 3 | CC-030 | T-001, T-012 | Dataclass updated; existing usages compile and tests pass. |
| 21 | T-021 | `music_tracker.py` applies metric modulations row-by-row at the correct positions. | T2 | 3 | 6 | CC-031 | T-001, T-012 | Unit test verifies that a 3:2 modulation at row N produces the expected timing on subsequent rows. |
| 22 | T-022 | The composer plans multi-scene meter trajectories per arc; scene metadata carries the trajectory. | T2 | 4 | 6 | CC-032 | T-001, T-012 | Composer log shows planned trajectories; integration test reads the metadata for a sample arc. |
| 23 | T-023 | Unit tests cover metric-modulation correctness for ratios 3:2, 4:3, and 5:4. | T1 | 3 | 3 | CC-033 | T-001, T-012 | Test suite includes the three ratios and asserts the expected row-position-to-time mappings. |

**Sprint 2 total:** ~18 hrs

---

## Sprint 3 — Improvement Engine Hardening

| Order | Task ID | Description | Tier | Complexity | Est (hrs) | Reqs | Deps | Criteria |
|-------|---------|-------------|------|------------|-----------|------|------|----------|
| 24 | T-024 | `audio_streamer.py` produces Opus segments at approximately 6 seconds and approximately 96 kbps from the JACK output bus. | T2 | 4 | 6 | CC-020 | T-001, T-020 | Segment files on disk show the expected duration and bitrate; the streamer process consumes under 10% CPU. |
| 25 | T-025 | Cloudflare Worker accepts segment POSTs at `/api/cypherclaw/segment` and stores them in R2. | T2 | 3 | 6 | CC-021 | T-001, T-020 | Test POST writes a segment to R2 and the object is retrievable via R2 listing. |
| 26 | T-026 | Cloudflare Worker serves a valid HLS playlist at `/api/cypherclaw/live.m3u8`. | T1 | 3 | 3 | CC-022 | T-001, T-020 | `hls.js` validator (or `ffplay`) successfully plays the live stream. |
| 27 | T-027 | The `cypherclaw.holdenu.com` DNS record plus Worker route resolves over HTTPS with a valid certificate. | T1 | 3 | 3 | CC-023 | T-001, T-020 | `curl -I https://cypherclaw.holdenu.com/` returns 200 with `cf-ray` header. |
| 28 | T-028 | The static page at the root URL renders, plays the live stream, displays a GlyphWeave backdrop, and runs a canvas visualizer driven by the SSE feed. | T2 | 4 | 6 | CC-024 | T-001, T-020 | Manual visual verification plus a browser-automation test confirming audio plays and canvas frames update. |
| 29 | T-029 | `session_archiver.py` produces a session approximately every 8 minutes or more, names it per CypherClaw's pattern (`{House-Imagery} / {Tuning-Character} — {DD Month}`), and uploads it to the R2 archive path. | T2 | 5 | 6 | CC-025 | T-001, T-020 | After 30 minutes of synthetic uptime, at least 3 sessions appear in R2 with the expected naming and metadata. |
| 30 | T-030 | The archive feed on the page lists sessions in reverse chronological order; each session is playable. | T1 | 3 | 3 | CC-026 | T-001, T-020 | Manual UI verification plus a snapshot test of the rendered feed for a fixture session list. |
| 31 | T-031 | The composer code contains no consumer of viewer or listener counts. | T1 | 3 | 3 | CC-027 | T-001, T-020 | Negative-assertion test grep search confirms zero matches for known count consumer patterns in the composer source tree. |
| 32 | T-032 | End-to-end test confirms a tone-generator signal flows from JACK through the streamer, Worker, R2, and back to a browser `<audio>` element within 30 seconds. | T2 | 5 | 6 | CC-028 | T-001, T-020 | End-to-end test passes in CI or scripted run; latency measurement is logged. |

**Sprint 3 total:** ~42 hrs

---

## Sprint 4 — Public REST API

| Order | Task ID | Description | Tier | Complexity | Est (hrs) | Reqs | Deps | Criteria |
|-------|---------|-------------|------|------------|-----------|------|------|----------|
| 33 | T-033 | Implement `TuningSystem` abstract base plus concrete `TwelveTET`, `JustIntonation5Limit`, and `GamelanSlendro` classes. | T1 | 4 | 3 | CC-040 | T-001, T-020, T-024 | Module imports succeed; each class returns a pitch table for a tonal center. |
| 34 | T-034 | Implement `MorphOperator.pitch_table_at(t)` returning a linearly interpolated pitch table for `t` in `[0.0, 1.0]`. | T1 | 3 | 3 | CC-041 | T-001, T-020, T-024 | Unit test asserts that `pitch_table_at(0)` equals source table and `pitch_table_at(1)` equals target table. |
| 35 | T-035 | Implement `pitch_hz(scale_degree, octave, tuning, tonal_center_hz)` that returns the correct frequency for every supported tuning. | T1 | 5 | 3 | CC-042 | T-001, T-020, T-024 | Unit tests verify frequencies match known reference values within 0.1 cent for all three tunings. |
| 36 | T-036 | The composer emits Hz directly in OSC events when the active tuning is not 12-TET. | T1 | 4 | 3 | CC-043 | T-001, T-020, T-024 | OSC trace shows freq field as Hz; `render_contract.scd` uses `freq` directly. |
| 37 | T-037 | Provide a backward-compatible 12-TET tuning system for legacy scenes. | T1 | 3 | 3 | CC-044 | T-001, T-020, T-024 | Scenes whose metadata sets `tuning_system_name == "12-TET"` continue to play unchanged. |
| 38 | T-038 | Scene metadata carries the tuning system, morph target, and morph curve. | T1 | 6 | 3 | CC-045 | T-001, T-020, T-024 | Sample scene JSON contains all three fields; schema validation passes. |
| 39 | T-039 | Composer applies CypherClaw's per-phase tuning rule: 5-limit JI for Listen and Divination; Slendro for Conversation and Procession; morph at stillness-to-motion transitions. | T2 | 7 | 6 | CC-046 | T-001, T-020, T-024 | Composer log shows tuning selection per phase across a 30-minute synthetic arc; transitions are detectable. |
| 40 | T-040 | The `CYPHERCLAW_V2_TUNING_MORPH` env flag controls activation, defaulting OFF. | T1 | 3 | 3 | CC-047 | T-001, T-020, T-024 | Module reads env var; default behavior matches OFF state. |
| 41 | T-041 | Unit tests verify pitch frequencies match expected ratios within 0.1 cent for all supported tuning systems. | T1 | 5 | 3 | CC-048 | T-001, T-020, T-024 | Tests include known reference points for each tuning. |

**Sprint 4 total:** ~30 hrs

---

## Sprint 5 — Model Comparison Hardening

| Order | Task ID | Description | Tier | Complexity | Est (hrs) | Reqs | Deps | Criteria |
|-------|---------|-------------|------|------------|-----------|------|------|----------|
| 42 | T-042 | Provision seven dedicated FX buses, one per voice, in master_smooth.scd. | T1 | 3 | 3 | CC-001 | T-001, T-012 | Synthdef diff shows 7 named FX bus channels routed before the master compressor. |
| 43 | T-043 | Tune a per-voice reverb on each FX bus to match its space description in `cypherclaw-v2-design-statement-2026-05-22.md` §4. | T2 | 4 | 6 | CC-002 | T-001, T-012 | Each reverb's parameters are documented in `spaces/` directory with a one-line rationale citing CypherClaw's space description. |
| 44 | T-044 | Route per-voice audio into the matching FX bus via the `fx_bus_id` parameter on each voice synthdef. | T1 | 3 | 3 | CC-003 | T-001, T-012 | Unit test confirms each voice's signal reaches only its assigned FX bus. |
| 45 | T-045 | Implement mood-driven space selection per scene: matched (default), expressive (deliberate mismatch), house-bound (all voices share the active house's space). | T2 | 6 | 6 | CC-004 | T-001, T-012 | Composer integration test produces all three modes from scripted scenes and OSC trace confirms the routing per mode. |
| 46 | T-046 | Unit tests verify each voice's audio reaches the correct FX bus under each mood mode. | T1 | 5 | 3 | CC-005 | T-001, T-012 | Test suite enumerates all (voice × mode) combinations and asserts the expected fx_bus_id. |
| 47 | T-047 | Add a `morph_voice` synthdef containing parallel source voices with crossfaded gains controlled by `morph_x`. | T1 | 5 | 3 | CC-050 | T-001, T-012 | Synthdef compiles; rendering with `morph_x=0` produces source A only; `morph_x=1` produces source B only. |
| 48 | T-048 | The composer can request a single-line morph phrase with a source/target voice pair and a morph curve. | T2 | 3 | 6 | CC-051 | T-001, T-012 | Integration test schedules a morph phrase and OSC trace confirms `morph_x` reaches the expected curve values at the expected times. |
| 49 | T-049 | A section-boundary crossfade scheduler computes per-section release tails that overlap with new section attacks. | T1 | 3 | 3 | CC-052 | T-001, T-012 | Unit test on a two-section arc shows the overlap window matches the configured crossfade duration. |
| 50 | T-050 | Within-family parameter walks generate continuous low-rate modulation on key parameters per voice. | T1 | 3 | 3 | CC-053 | T-001, T-012 | OSC trace shows continuous parameter values within the expected depth band. |
| 51 | T-051 | The `CYPHERCLAW_V2_INSTRUMENT_MORPH` env flag controls activation, defaulting OFF. | T1 | 3 | 3 | CC-054 | T-001, T-012 | Module reads env var; default behavior matches OFF state. |
| 52 | T-052 | Unit tests cover crossfade scheduling and morph curve shapes. | T1 | 2 | 3 | CC-055 | T-001, T-012 | Test suite includes scheduling, curve, and OSC integration tests. |

**Sprint 5 total:** ~42 hrs

---

## Sprint 6 — Stretch Goals

| Order | Task ID | Description | Tier | Complexity | Est (hrs) | Reqs | Deps | Criteria |
|-------|---------|-------------|------|------------|-----------|------|------|----------|
| 53 | T-053 | All voice synthdefs accept the expression control parameters: `vib_rate`, `vib_depth`, `trem_rate`, `trem_depth`, `bend_start_hz`, `bend_end_hz`, `bend_curve_shape`, `attack_mode`, `late_release_extension`, `harmonic_resonance_profile_id`, `spectral_granulation_amount`, `spectral_smear_amount`. | T2 | 7 | 6 | CC-060 | T-001 | Synthdef diff shows every voice exposes the listed parameters; live OSC sets each parameter without error. |
| 54 | T-054 | Each voice provides internal LFOs (vibrato pitch LFO, tremolo amplitude LFO, spectral granulation) where allowed by the voice's gesture allowlist. | T2 | 4 | 6 | CC-061 | T-001 | Per-voice rendering with each modulator enabled produces audible modulation matching the rate and depth set. |
| 55 | T-055 | The expression module implements 11 named gestures (Weeping, Shimmering, Ghostly, Sighing, Agitated, Breath-shaped, Pulsing, Fracturing, Hollowing, Tension-Build, Echo-Location). | T2 | 4 | 6 | CC-062 | T-001 | Unit tests assert that each gesture function returns an OSC payload with the expected expression parameters. |
| 56 | T-056 | The voice-to-gesture allowlist per `cypherclaw-v2-design-statement-2026-05-22.md` §7.3 is enforced; forbidden combinations are rejected. | T1 | 4 | 3 | CC-063 | T-001 | Unit test attempts every forbidden combination and asserts each is refused. |
| 57 | T-057 | The scene-phase intensity multiplier table per §7.4 is applied at gesture application time. | T1 | 3 | 3 | CC-064 | T-001 | Unit test verifies multiplier values per phase match the design statement. |
| 58 | T-058 | Pedal logic (Sustain, Resonant with Decay Modulation, Half-pedal) is implemented per voice family. | T2 | 3 | 6 | CC-065 | T-001 | Integration test engages each pedal and confirms the expected voice behavior. |
| 59 | T-059 | Contour analysis classifies each note as peak, ascending, descending, static, or valley. | T1 | 3 | 3 | CC-066 | T-001 | Unit tests on synthetic note sequences assert the expected classification. |
| 60 | T-060 | The composer applies contour-aware dynamics multipliers and attack shapes when emitting notes. | T1 | 3 | 3 | CC-067 | T-001 | OSC trace shows `dynamics_multiplier` and `attack_shape` set per note in accordance with the contour. |
| 61 | T-061 | Unit tests cover each gesture's expression-parameter output. | T1 | 4 | 3 | CC-069 | T-001 | Tests enumerate all 11 gestures and assert expected outputs. |
| 62 | T-062 | The renamed terminology (Spectral Granulation, Harmonic Resonance Profile, Spectral Smear) is used consistently across code, schemas, and documentation. | T1 | 5 | 3 | CC-068 | T-001 | Lint pass finds no surviving references to the previous names in v2 modules. |

**Sprint 6 total:** ~42 hrs

---

## Summary

- **Sprint 0 (Infrastructure & Billing):** 11 tasks, ~36 hrs
- **Sprint 1 (Versioning System):** 8 tasks, ~33 hrs
- **Sprint 2 (Quality Scoring):** 4 tasks, ~18 hrs
- **Sprint 3 (Improvement Engine Hardening):** 9 tasks, ~42 hrs
- **Sprint 4 (Public REST API):** 9 tasks, ~30 hrs
- **Sprint 5 (Model Comparison Hardening):** 11 tasks, ~42 hrs
- **Sprint 6 (Stretch Goals):** 10 tasks, ~42 hrs

**Total: 62 tasks, ~243 hours**
