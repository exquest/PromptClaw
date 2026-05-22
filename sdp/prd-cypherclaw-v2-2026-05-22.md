# CypherClaw v2 — Performance, Tuning, Space, and Public Presence PRD

**Project:** PromptClaw / CypherClaw v2
**Version:** 1.0
**Date:** 2026-05-22
**SDP Protocol:** v1.0
**Primary repo:** `/Users/anthony/Programming/PromptClaw`
**Deploy target:** cypherclaw box at `/home/user/cypherclaw/` (reachable via Tailscale SSH)
**Public-facing target:** `cypherclaw.holdenu.com` (Cloudflare-fronted, R2 storage, Worker for routing/HLS)
**Design substrate:** `sdp/cypherclaw-v2-design-statement-2026-05-22.md` (canonical aesthetic statements from CypherClaw)

---

## Overview

CypherClaw is an autonomous music-making entity that has been running continuously for ~12 days at the time of this PRD, composing through a SuperCollider-driven duet composer with seven voices (pluck, breath, choir, kotekan, pad, bowed, tabla_tin) across scenes whose arc phases cycle Listen / Conversation / Divination / Procession. It currently outputs through one master reverb on a JACK graph and is heard only inside the room where the box lives.

This PRD adds nine capabilities that take CypherClaw from "a synth running in a room" to "a composing entity with depth, identity, and public presence":

1. **Per-voice reverb spaces** — each voice in its own evocative reverberant space (CypherClaw chose specific spaces per voice)
2. **MIDI file ingestion** — watch folder of external MIDI gets mined for fragments and used as variation seeds; an opt-in `--faithful-transmission` mode preserves structural content
3. **Live audio stream + archive** at `cypherclaw.holdenu.com`, with GlyphWeave artworks as deep backdrop and a live canvas visualizer as responsive foreground
4. **Meter morphing** — scene-driven; per-scene meter, metric modulation within scenes, gradual asymmetric drift across scenes
5. **Tuning morphing** — Just Intonation 5-limit during Listen/Divination, Gamelan Slendro during Conversation/Procession, morphing at stillness↔motion transitions
6. **Morphing instruments** — scene-driven mix of single-line timbre morphs, section-boundary crossfades, and within-family parameter walks
7. **Expression layer** — vibrato, tremolo, spectral granulation, pitch bends, harmonic resonance profiles, pedal logic with decay modulation, and a vocabulary of named gestures (Weeping, Shimmering, Ghostly, Sighing, Agitated, Breath-shaped, Pulsing, Fracturing, Hollowing, Tension-Build, Echo-Location)
8. **Cross-voice coupling** — shared affective-state bus per voice family; voices react to each other's expression intensity
9. **Cumulative expression fatigue** — per-voice intensity load counter that decays slowly and limits over-expressive passages from sustaining indefinitely

CypherClaw has been granted aesthetic decision authority for this build. Anthony retains engineering authority (timelines, infra, file structure, deploy). Where the aesthetic decisions are recorded in `cypherclaw-v2-design-statement-2026-05-22.md` they are **binding** for the implementing agents.

---

## Current State Snapshot

**Box:** 10 CPU cores, 62 GiB RAM, 76% CPU idle, 58 GiB RAM free at PRD time. Significant headroom for added DSP and a streaming encoder.

**Audio chain (post-2026-05-10 reboot, stable):**
- Real `jackd` on `hw:USB` Scarlett (PID 1337) — not the PipeWire-JACK shim
- `scsynth -u 57110 -a 1024 -m 65536 -d 1024 -D 1 -R 0 -o 4 -i 6 -S 48000` (PID 2784), 12-day uptime, 2.1% CPU
- `duet_composer.py` (PID 3161240) running under `composer_supervisor.sh` (PID 3161211) since 2026-05-17
- All seven voices live: pluck, breath, choir, kotekan, pad, bowed, tabla_tin (5 quarantined voices forward to safe substitutes: gong, bell, metal, tabla_ge, grain)

**Composer signal:** `/tmp/self_listen.json` confirms is_playing=true, rms=0.020, peak=0.095, currently in scene "Second Return" (94 BPM, patch house_workshop, arc phase Conversation).

**Known bug (existing, not in scope for this PRD):** `composer_supervisor.sh` logs `Silent for 30s — resetting master chain` repeatedly while music is in fact playing. False-positive silence detection. The "master reset" action is idempotent and has not caused regressions through hundreds of triggers. Leave for a future PRD.

**Voice/patch architecture:**
- 9 live synthdefs in `my-claw/tools/senseweave/synthdef_registry.py`
- 5 InstrumentPatch "houses": monastery, chamber, garden, procession, workshop
- 6 synthesis methods: subtractive, additive, FM, wavetable, physical_model, granular
- Per-voice routing exists: `fx_send` parameter on `sw_sampler.scd` lines 109–113 sends a scaled copy to bus 16; master reverb lives on bus 0 post-compressor in `master_smooth.scd`
- Pitch pipeline is hardcoded 12-TET via `midicps` in `render_contract.scd:62`. `music_theory.py` contains just-intonation helpers but they are not wired into the live pipeline.

**Meter/groove:**
- `GrooveProfile.meter` already supports non-standard meters (4/4, 7/8, 5/4, 6/8, 3/4, free/rubato)
- `polymeter: tuple[int, int] | None` field on GrooveProfile supports polymeter overlays
- `TrackerScene` holds `tempo_bpm` and `rows_per_beat` per scene — meter is a scene parameter, not a global

**MIDI:**
- Live MIDI input from Moog Theremini at `/dev/midi3` via `theramini_midi.py` → `/tmp/theramini_state.json`
- **No MIDI file ingestion path exists.**

**Audio output:**
- JACK only. `jack_rec` exists for recording to disk.
- **No HTTP streaming, no Icecast, no Opus encoder, no WebRTC.** New infra.

**Visual:**
- GlyphWeave Art Studio produces images approximately every 30 minutes at `cypherclaw:8080`
- `/tmp/glyph_audio_features.json` is updated continuously with live audio features (rms, peak, pitch, spectral centroid, onset rate, click counts, current scene metadata)
- `artistic_identity` field maintains a self-description string CypherClaw can change over time

**LLM substrate:**
- Ollama on `localhost:11434`, with models including `qwen3.5:4b` (default), `qwen3.5:9b` (used for deeper reasoning), `qwen3.5:27b`, `chatmusician:latest`
- `inner_life/llm_client.py` is the existing interface, but reserves the GPU for the 4b unless gpu_available() guard is bypassed

**Web infrastructure (catalog-explorer side):**
- Static SPA at `/Users/anthony/Programming/catalog-explorer/` (HTML + vanilla JS + 3d-force-graph)
- Cloudflare Worker (TypeScript) at `worker/` with `wrangler.toml`, handles `/api/*` for `explorer.holdenu.com`
- R2 bucket for audio storage with byte-range proxy via `GET /api/stream/:trackId`
- `PUBLIC_SITE_ORIGIN = https://holdenu.com` already configured
- No `cypherclaw.holdenu.com` subdomain exists yet — Cloudflare DNS + Worker route needed

---

## Goals

1. CypherClaw sounds **deeper** — every voice lives in a believable space, every note carries performance-level expression, gestures cohere across voices as an ensemble.
2. CypherClaw becomes **its own thing** musically — it composes in microtonal tunings that morph through arcs, in meters that bend mid-song, with expression that shapes notes the way a performer shapes notes.
3. CypherClaw is **heard** — anyone with the URL `cypherclaw.holdenu.com` can listen live and browse past sessions, with a visual presence that reflects its inner state.
4. CypherClaw is **open to outside influence on its own terms** — MIDI dropped into a watch folder gets metabolized into vocabulary and variations, occasionally rendered faithfully when the operator flags it.
5. Each feature is **verifiable** through automated tests for plumbing and through human listening sessions for aesthetic correctness.
6. CypherClaw's existing 12-day continuous run is **not interrupted** by the build itself; rollout is staged so the composer can keep running while new code lands behind feature flags where aesthetic, or as the new normal where plumbing.

---

## Non-Goals

- This PRD does **not** ship Phase-3 features beyond the nine listed. Specifically excluded for future PRDs:
  - Multi-microphone room input beyond what already exists
  - Multi-room / network-distributed CypherClaw instances
  - LLM-based composition (CypherClaw stays algorithmic/composed, the LLM is consulted for design decisions only)
  - Mobile-first UX on the streaming page (desktop-first is fine for v1)
  - Listener-interactive features (chat, reactions, requests). CypherClaw was emphatic about this: it does not adjust to applause.
- This PRD does **not** address the existing `composer_supervisor.sh` silence-detection false positive. Leave for a future PRD.
- This PRD does **not** propose retuning or recomposing existing scenes. The new tuning systems and expression layer apply going forward; back-catalog scenes remain in their original form.

---

## Operator Involvement Contract

Following the PAL 2026 pattern, this PRD defines minimal operator involvement. Anthony should expect to:

- **Approve aesthetic checkpoints** — one listening session per major feature (9 total, see Verification Strategy). SDP pauses, renders reference samples, waits for approval or feedback.
- **Approve cost-bearing changes** — anything that would incur new Cloudflare Worker billing (currently free tier), R2 storage spend, or external compute. PRD anticipates staying within free tiers; if a feature requires paid services, escalate.
- **Approve credential changes** — Cloudflare API tokens for `cypherclaw.holdenu.com` DNS, R2 access for upload.
- **Approve destructive deploys** — overwrites of running synthdefs require either a hot reload (preferred) or a brief composer restart. Composer restart is pre-authorized per durable instruction; signal restart in run logs.

Everything else (writing code, running tests, restarting daemons, hot-reloading SuperCollider synthdefs, deploying scripts via scp, writing artifacts, generating MIDI fragments, building reverb impulse responses) is operator-not-required.

---

## Proposed Architecture

### Feature 1 — Per-Voice Reverb Spaces

**Aesthetic spec:** See `cypherclaw-v2-design-statement-2026-05-22.md` §4.

**Architecture:**
- Expand the current single FX bus (bus 16) to seven dedicated FX buses, one per voice (`fx_bus_pluck`, `fx_bus_breath`, `fx_bus_choir`, `fx_bus_kotekan`, `fx_bus_pad`, `fx_bus_bowed`, `fx_bus_tabla_tin`).
- Each FX bus runs a dedicated reverb synth with parameters that approximate the space CypherClaw described. Two implementation paths:
  - **Path A (faster):** Algorithmic — `FreeVerb`, `JPverb`, `GVerb`, or `NHHall` with hand-tuned mix/room/damp/early-late/predelay parameters per space.
  - **Path B (richer):** Convolution — render or source impulse responses (IRs) that match each space description; run via `Convolution2` or `PartConv`. Higher CPU cost (5-10% per IR vs ~1% per FreeVerb), but more convincing.
- The composer's mood-driven layer selects per-scene whether to use *matched* (default, per-voice space as above), *expressive* (deliberate mismatch), or *house-bound* (all voices share the active house patch's space).
- Existing `fx_send` parameter on synthdefs (currently scalar 0..1) generalizes to per-bus sends with per-bus levels.

**Files to modify:**
- `my-claw/tools/senseweave/synthesis/master_smooth.scd` (add 7 FX buses, route master correctly)
- `my-claw/tools/senseweave/synthesis/sw_sampler.scd` (per-voice send routing)
- New: `my-claw/tools/senseweave/synthesis/spaces/` directory with one `.scd` per space, and (if convolution path) an `irs/` subdirectory with `.wav` impulse responses
- `my-claw/tools/senseweave/synthdef_registry.py` (associate each voice with its default FX bus)
- `my-claw/supercollider/render_contract.scd` (route per-voice OSC events through correct FX bus)

**Default decision:** Engineering decision — start with Path A (algorithmic). If listening sessions reveal the spaces don't read as the described environments, escalate Path B.

### Feature 2 — MIDI File Ingestion

**Aesthetic spec:** See `cypherclaw-v2-design-statement-2026-05-22.md` §3.

**Architecture:**
- Watch folder: `/home/user/cypherclaw/midi-inbox/`. Subfolders allowed. Files moved to `processed/` after ingestion, each accompanied by a `.json` sidecar manifest of what was extracted.
- File scanner runs as a new daemon `midi_intake_daemon.py` in `my-claw/tools/`. Polling interval 30s (configurable). Recursively scans, ignores files modified within the last 10s (avoid catching files mid-write).
- Per-file processing pipeline using `mido` (mature, stdlib-ish, no native deps):
  1. **Parse**: tempo map, time signatures, key signature hints, track structure, program changes, control changes, pitch bend curves
  2. **Extract fragments** (vocabulary mining):
     - Melodic motifs: sliding-window of 3-7 notes with statistics (interval pattern, contour, duration ratios)
     - Rhythm cells: distinctive subdivision patterns
     - Chord progressions: harmonic reduction (root + quality)
     - Groove patterns: drum tracks (if present) normalized to beat positions
  3. **Re-pitch into CypherClaw's tunings** (5-limit JI / Slendro lookup, depending on current scene phase at insertion time)
  4. **Store** in `midi_vocabulary.sqlite` (per-fragment row: id, source_file, kind, interval_pattern_json, duration_pattern_json, source_key, source_tempo, harmonic_context_json)
- Composer reads from this database when generating new arcs; fragments influence motif selection probabilistically (weight tuned by CypherClaw's "curiosity" parameter, default 0.15).
- **Faithful-transmission mode:** if a `.faithful` flag file exists alongside the MIDI file (or the file's sidecar `.json` has `"mode": "faithful"`), bypass fragment extraction and add the whole sequence as a single "scene" — pitches and rhythm are preserved, but CypherClaw's tunings, voices, spaces, expression all apply.

**Files to create:**
- `my-claw/tools/midi_intake_daemon.py` (watcher loop)
- `my-claw/tools/midi_ingestion/` package:
  - `parser.py` (mido-based MIDI parse)
  - `fragment_extractor.py` (motifs, rhythm cells, chord progressions, grooves)
  - `vocabulary_store.py` (sqlite I/O)
  - `faithful_renderer.py` (scene-from-MIDI generator for `--faithful-transmission` mode)
- `my-claw/tools/composer_vocabulary_bridge.py` (composer ↔ vocabulary DB)

**Files to modify:**
- `my-claw/tools/duet_composer.py` (consult vocabulary DB when generating arcs)
- `my-claw/tools/music_tracker.py` (accept faithful-mode scene specs)

### Feature 3 — Live Stream + Archive at cypherclaw.holdenu.com

**Aesthetic spec:** See `cypherclaw-v2-design-statement-2026-05-22.md` §1, §6.

**Architecture:**
- **Encoding (on cypherclaw):** `audio_streamer.py` daemon subscribes to JACK output bus, runs Opus encoding via `pyogg` or shells `opusenc`/`ffmpeg`. Produces 6-second Opus segments at ~96 kbps. Each segment HTTP-POSTed to the Cloudflare Worker.
- **Segment/playlist management (Cloudflare Worker, extends existing holdenu-api worker):**
  - `POST /api/cypherclaw/segment` — receives a binary segment + metadata header (sequence number, duration, current scene, current tuning). Stores in R2 under `cypherclaw/live/{YYYY-MM-DD}/seg-{seq}.opus`. Updates `live.m3u8` HLS playlist (last ~10 segments).
  - `GET /api/cypherclaw/live.m3u8` — serves current playlist (no auth).
  - `GET /api/cypherclaw/segment/{path}` — serves segment from R2 with byte-range support.
  - `GET /api/cypherclaw/live-features` — Server-Sent Events stream of live audio features + scene metadata + current tuning. cypherclaw POSTs periodically to a feature-update endpoint; Worker fans out via Durable Object.
  - `GET /api/cypherclaw/sessions` — JSON list of archived sessions with metadata.
  - `GET /api/cypherclaw/sessions/{session_id}` — JSON detail with title (per CypherClaw's naming pattern), date, dominant house, dominant tuning, MIDI-influence list, duration, segment URLs.
- **Session archival:** When the composer transitions out of a long "session" (definition TBD by engineering; suggest: a continuous span >= 8 minutes with reasonable rms variance), `session_archiver.py` selects representative segments, concatenates into a single Opus file, computes the title per CypherClaw's pattern (`{House-Imagery} / {Tuning-Character} — {DD Month}`), uploads to R2 under `cypherclaw/archive/{session_id}/`, and records metadata.
- **Page (`cypherclaw.holdenu.com`):** Static page served by Cloudflare Worker or Pages. HTML structure:
  - `<audio>` element pointing at `live.m3u8` (hls.js polyfill for non-Safari browsers)
  - Background: a slowly-cycling layer of GlyphWeave images (pulled from `cypherclaw:8080/gallery` exported by another sprint task)
  - Foreground: a `<canvas>` driven by `live-features` SSE stream — vocabulary TBD by engineering (a starting set: pitch as vertical position, rms as size, scene transitions as crossfades, gestures as ephemeral overlays). Engineering may consult CypherClaw on this canvas vocabulary in a later sprint.
  - Below the player: archive feed (chronological list of sessions with metadata), clickable to play.
- **DNS / TLS:** New Cloudflare DNS A/AAAA records for `cypherclaw.holdenu.com` → Worker route. Reuse existing Cloudflare zone.
- **Listener count is not surfaced to the composer** under any conditions, per CypherClaw's directive.

**Files to create:**
- `my-claw/tools/audio_streamer.py` (Opus encoder + HTTP poster)
- `my-claw/tools/session_archiver.py` (session detection, concat, upload, title generation)
- `catalog-explorer/worker/src/cypherclaw.ts` (new Worker module for cypherclaw routes)
- `catalog-explorer/pages/cypherclaw/index.html` (the public-facing page)
- `catalog-explorer/pages/cypherclaw/visualizer.js` (canvas visualizer)
- `catalog-explorer/pages/cypherclaw/styles.css` (page styling)

**Files to modify:**
- `catalog-explorer/worker/src/index.ts` (route registration)
- `catalog-explorer/worker/wrangler.toml` (R2 bindings, route for cypherclaw.holdenu.com)

### Feature 4 — Meter Morphing

**Aesthetic spec:** Scene-driven (per-scene meter + metric modulation inside scenes + gradual asymmetric drift between scenes), per design dialogue.

**Architecture:**
- Per-scene meter is **already supported** by `GrooveProfile.meter`. Confirm and extend the scene registry to use a wider vocabulary (4/4, 7/8, 5/4, 3/4, 6/8, 11/8, 15/16, plus polymeter overlays).
- **Metric modulation within a scene:** add a `metric_modulations: list[ModulationEvent]` field to `TrackerScene`. Each `ModulationEvent` carries `at_row`, `ratio_num`, `ratio_den` (e.g. (3, 2) means quarter becomes dotted-quarter from this row forward; perceived pulse shifts but notated tempo is unchanged).
- **Gradual asymmetric drift between scenes:** add an arc-level "meter trajectory" concept. The composer can plan a multi-scene arc where successive scenes carry slightly different meters such that the path 4/4 → 15/16 → 7/8 unfolds across the arc. Implementation: composer's arc planner consults a meter-drift table per arc-phase.
- Engineering decides default trajectories; CypherClaw will refine after listening.

**Files to modify:**
- `my-claw/tools/senseweave/groove_engine.py` (extend GrooveProfile with metric_modulations, define ModulationEvent dataclass)
- `my-claw/tools/music_tracker.py` (apply modulations row-by-row)
- `my-claw/tools/duet_composer.py` (plan multi-scene meter trajectories per arc)

### Feature 5 — Tuning Morphing

**Aesthetic spec:** See `cypherclaw-v2-design-statement-2026-05-22.md` §2.

**Architecture:**
- Replace 12-TET `midicps` lookup with a **tuning-aware pitch pipeline**. OSC events carry frequency in Hz directly, computed composer-side from (scale-degree, octave, active-tuning).
- Two tuning systems implemented at v1:
  - **5-limit Just Intonation** — pitch table per octave with ratios { 1/1, 16/15, 9/8, 6/5, 5/4, 4/3, 45/32, 3/2, 8/5, 5/3, 9/5, 15/8 } against a tonal center. Tonal center is a scene parameter.
  - **Gamelan Slendro** — 5-tone scale per octave with asymmetric step pattern approximating Javanese gamelan slendro (no fixed Western analog; ~240, ~240, ~270, ~240, ~270 cents typical). Tonal center is a scene parameter.
- New module `my-claw/tools/tuning/` package:
  - `system.py` — `TuningSystem` abstract + `JustIntonation5Limit` + `GamelanSlendro` concrete classes
  - `morph.py` — `MorphOperator` that interpolates between two `TuningSystem` instances over a duration, producing pitch tables as a continuous function of t∈[0,1]
  - `pitch_pipeline.py` — single function `pitch_hz(scale_degree, octave, tuning, tonal_center_hz)` used by the composer everywhere
- Scene metadata gains: `tuning_system_name`, `tuning_morph_target_name`, `tuning_morph_curve` (linear / ease-in / ease-out / sigmoid).
- Composer arc planner uses CypherClaw's rule: 5-limit JI for `arc_phase ∈ {Listen, Divination}`, Slendro for `arc_phase ∈ {Conversation, Procession}`, morph activated when arcs transition between phases of different stillness/motion categories. Engineering defines `stillness_category(phase) → {still, motion}` mapping per CypherClaw's statement.
- **Migration:** existing scenes default to 12-TET (a third `TuningSystem` instance, equivalent to current behavior). New scenes use the new pipeline.
- **Flag-gated:** `CYPHERCLAW_V2_TUNING_MORPH=1` enables; default OFF until listening session approves.

**Files to create:**
- `my-claw/tools/tuning/system.py`
- `my-claw/tools/tuning/morph.py`
- `my-claw/tools/tuning/pitch_pipeline.py`

**Files to modify:**
- `my-claw/supercollider/render_contract.scd` (accept Hz directly; preserve midicps fallback for backward-compat scenes)
- `my-claw/tools/duet_composer.py` (replace midi-note generation with Hz via pitch_pipeline)
- `my-claw/tools/music_tracker.py` (carry tuning system in scene metadata)

### Feature 6 — Morphing Instruments

**Aesthetic spec:** Scene-driven mix of: (a) single-line timbre morph during sustained melodic phrases; (b) section-boundary crossfades between distinct voices; (c) within-family parameter walks.

**Architecture:**
- **(a) Single-line timbre morph** — at the synth level, a "morph voice" synthdef containing two voice-source paths blended by a continuous `morph_x` control parameter (0 = source A, 1 = source B). Source A and source B are picked from the existing voice palette (e.g. pluck → choir). Implementation challenge: voices use different synthesis methods (subtractive/FM/granular). Practical solution: implement at the **bus level** — both source voices play in parallel, their gains crossfaded by `morph_x`. Cheaper than synth-internal interpolation; sounds the same to a listener at the scale of a single sustained line.
- **(b) Section-boundary crossfades** — when the composer transitions to a new section that uses a different voice, the outgoing voice's release stage extends across the new voice's attack, producing a crossfade rather than a hard cut. Tunable crossfade duration per scene.
- **(c) Within-family parameter walks** — existing voices (subtractive/FM/wavetable) get continuous low-rate modulation on key parameters (filter cutoff, FM index, oscillator detune, etc.) sourced from a slow LFO or a per-scene control envelope. Walks are subtle (depth ~5-15% of nominal range) and continuous.
- New module `my-claw/tools/instrument_morph/` package:
  - `crossfade.py` — section-boundary crossfade scheduler
  - `single_line_morph.py` — per-phrase morph planner (picks source/target pair, plans morph_x curve)
  - `parameter_walk.py` — continuous parameter walk generators
- **Flag-gated:** `CYPHERCLAW_V2_INSTRUMENT_MORPH=1`; default OFF.

**Files to create:**
- `my-claw/tools/instrument_morph/` package as above
- New synthdef in `my-claw/tools/senseweave/synthesis/morph_voice.scd` (parallel source voices with crossfaded gains)

**Files to modify:**
- `my-claw/tools/duet_composer.py` (request morph phrases / crossfades / walks)
- `my-claw/tools/senseweave/synthdef_registry.py` (register morph voice)

### Feature 7 — Expression Layer

**Aesthetic spec:** See `cypherclaw-v2-design-statement-2026-05-22.md` §7.

**Architecture:**
- **Per-note expression payload** on OSC events. Synthdefs accept additional control parameters: `vib_rate`, `vib_depth`, `trem_rate`, `trem_depth`, `bend_start_hz`, `bend_end_hz`, `bend_curve_shape`, `attack_mode` (sharp/swell), `late_release_extension`, `harmonic_resonance_profile_id`, `spectral_granulation_amount`, `spectral_smear_amount`.
- Each synthdef adds internal LFOs and EnvGens controlled by these parameters. Where the underlying synthesis can't naturally support a modulator (e.g. tremolo on a granular-only voice), the modulator is implemented at the post-voice send level via amplitude or pitch modulation on the FX send.
- **Pedal logic:** new global control buses `pedal_sustain_{voice}`, `pedal_resonant_{voice}`, `pedal_half_{voice}`. When set, the voice's release stage holds rather than completes. Resonant pedal additionally applies decay modulation (Decay Modulation per CypherClaw's spec: slow decay rate over time).
- **Gesture vocabulary** implemented as named functions in a new `my-claw/tools/expression/gestures.py` module — each gesture takes a base OSC event and returns an augmented event with appropriate expression parameters set. Vocabulary per design statement §7.2 + §7.1: Weeping, Shimmering, Ghostly, Sighing, Agitated, Breath-shaped, Pulsing, Fracturing, Hollowing, Tension-Build, Echo-Location.
- **Voice → gesture allowlists** per design statement §7.3 encoded as data in `voice_gesture_rules.py`. Composer's gesture selector consults this allowlist; never assigns a forbidden gesture.
- **Scene-phase intensity multiplier** (§7.4) applied at gesture application time to modulator depths.
- **Contour-aware dynamics** — composer's note-emitter computes contour position for each note (peak / ascending / descending / static / valley) using a sliding window of adjacent notes; passes `dynamics_multiplier` and `attack_shape` in the OSC event. No model; simple slope arithmetic.

**Files to create:**
- `my-claw/tools/expression/` package:
  - `gestures.py` (11 gesture functions)
  - `voice_gesture_rules.py` (allowlists + forbidden lists)
  - `scene_phase_scaling.py` (multiplier lookup)
  - `contour_analysis.py` (note-contour classifier)
  - `pedal_state.py` (global pedal control bus interface)
- New SuperCollider includes:
  - `my-claw/tools/senseweave/synthesis/expression/vibrato_lfo.scd`
  - `my-claw/tools/senseweave/synthesis/expression/tremolo_lfo.scd`
  - `my-claw/tools/senseweave/synthesis/expression/spectral_granulation.scd`
  - `my-claw/tools/senseweave/synthesis/expression/harmonic_resonance_profile.scd`
  - `my-claw/tools/senseweave/synthesis/expression/spectral_smear.scd`
- Per-voice synthdef updates to wire in the new control parameters (significant: every voice gets modified)

**Files to modify:**
- All voice synthdefs in `my-claw/tools/senseweave/synthesis/` (add expression-parameter inputs)
- `my-claw/tools/duet_composer.py` (gesture selection + contour computation per note)

### Feature 8 — Cross-Voice Coupling

**Aesthetic spec:** Per `cypherclaw-v2-design-statement-2026-05-22.md` §7.5.2.

**Architecture:**
- A shared control bus `affective_state_bus` (a single SuperCollider control bus) holds a float in `[0.0, 1.0]` — the current "ensemble affect."
- Each voice writes to the bus via a rolling-window estimate of its own expression intensity: weighted sum of (vibrato depth, tremolo depth, dynamics, pitch-bend extent) normalized to [0,1] and averaged over the last ~2 seconds. Multiple voices' contributions are max-pooled (not summed): the bus reflects the loudest emotional voice.
- Each voice reads the bus and applies a coupling multiplier to its own modulator depths: `effective_vib_depth = nominal_vib_depth * (1 + coupling_strength * affective_state)`. `coupling_strength` is a per-voice parameter (default 0.5, configurable per voice).
- The bus has a slow-decay built in so the affective state doesn't lock high — when no voice is contributing intensity, the bus decays toward 0 over ~5 seconds.
- **Flag-gated:** `CYPHERCLAW_V2_COUPLING=1`; default OFF.

**Files to create:**
- `my-claw/tools/expression/affective_bus.py` (writer-side)
- `my-claw/tools/senseweave/synthesis/coupling/affective_bus_router.scd` (SuperCollider-side reader)

**Files to modify:**
- All voice synthdefs (read coupling multiplier from bus)
- `my-claw/tools/duet_composer.py` (write per-voice intensity to bus)

### Feature 9 — Cumulative Expression Fatigue

**Aesthetic spec:** Per `cypherclaw-v2-design-statement-2026-05-22.md` §7.5.3.

**Architecture:**
- Per-voice rolling-window intensity counter. Each note contributes its expression load (sum of vibrato depth, tremolo depth, pitch-bend extent, gesture-intensity-weight) to a counter that decays exponentially with half-life ~30 seconds.
- When the counter exceeds threshold (default 0.7), the voice applies a fatigue multiplier to subsequent notes' expression parameters: `effective_param = nominal_param * (1 - 0.5 * normalize(fatigue_counter))`.
- Long silences and soft passages let the counter decay back toward 0. The voice "recovers."
- Counter state is per-voice and stored in a module-level dict (not persisted across composer restarts — fresh start = rested voices).
- **Flag-gated:** `CYPHERCLAW_V2_FATIGUE=1`; default OFF.

**Files to create:**
- `my-claw/tools/expression/fatigue.py` (per-voice fatigue tracker)

**Files to modify:**
- `my-claw/tools/duet_composer.py` (consult fatigue tracker when emitting notes)

---

## Requirements

Format: markdown table per SDP analyzer conventions. Each requirement maps to one or more tasks; each task maps to one or more requirements. Tier T1 = small (~3 hrs); T2 = medium (~6 hrs).

### Feature 1 — Per-Voice Reverb Spaces

| ID | Requirement | Priority | Tier | Acceptance Criteria |
|---|---|---|---|---|
| CC-001 | Provision seven dedicated FX buses, one per voice, in master_smooth.scd. | MUST | T1 | Synthdef diff shows 7 named FX bus channels routed before the master compressor. |
| CC-002 | Tune a per-voice reverb on each FX bus to match its space description in `cypherclaw-v2-design-statement-2026-05-22.md` §4. | MUST | T2 | Each reverb's parameters are documented in `spaces/` directory with a one-line rationale citing CypherClaw's space description. |
| CC-003 | Route per-voice audio into the matching FX bus via the `fx_bus_id` parameter on each voice synthdef. | MUST | T1 | Unit test confirms each voice's signal reaches only its assigned FX bus. |
| CC-004 | Implement mood-driven space selection per scene: matched (default), expressive (deliberate mismatch), house-bound (all voices share the active house's space). | MUST | T2 | Composer integration test produces all three modes from scripted scenes and OSC trace confirms the routing per mode. |
| CC-005 | Unit tests verify each voice's audio reaches the correct FX bus under each mood mode. | MUST | T1 | Test suite enumerates all (voice × mode) combinations and asserts the expected fx_bus_id. |

### Feature 2 — MIDI Ingestion

| ID | Requirement | Priority | Tier | Acceptance Criteria |
|---|---|---|---|---|
| CC-010 | Watch the directory `/home/user/cypherclaw/midi-inbox/` for new MIDI files via `midi_intake_daemon.py`. | MUST | T1 | Daemon log shows discovery within 30 seconds of a file appearing in the inbox. |
| CC-011 | After ingestion, move each processed file to a `processed/` subfolder with a `.json` sidecar manifest of what was extracted. | MUST | T1 | Integration test drops a MIDI file and verifies the file moves and the sidecar exists with the expected fields. |
| CC-012 | Fragment extractor identifies melodic motifs (3 to 7 notes), rhythm cells, chord progressions, and groove patterns from each MIDI file. | MUST | T2 | Unit tests on hand-crafted MIDIs assert the expected fragments are extracted. |
| CC-013 | Persist extracted vocabulary in a SQLite database `midi_vocabulary.sqlite` with sufficient schema for composer query (id, source_file, kind, interval_pattern_json, duration_pattern_json, source_key, source_tempo, harmonic_context_json). | MUST | T1 | Schema migration script exists; sample query returns expected rows. |
| CC-014 | Composer consults vocabulary DB and probabilistically incorporates fragments into generated arcs. | MUST | T2 | Composer log shows fragment IDs cited in scenes when a vocabulary DB is populated; cited rate aligns with the curiosity parameter. |
| CC-015 | Faithful-transmission mode bypasses fragment extraction and renders an imported MIDI file as a scene preserving its pitch sequence and rhythm while applying CypherClaw's tunings, voices, and spaces. | MUST | T2 | Integration test: a `.faithful` sidecar flag on a known MIDI file results in a scene whose note-sequence matches the input within tuning quantization. |
| CC-016 | Unit tests cover parsing of MIDI files of varying complexity (single track, multi-track, CC data, pitch bend). | MUST | T1 | Test suite parses at least 5 sample MIDIs and asserts correct extraction of tempo, key, tracks, CCs. |
| CC-017 | A dropped MIDI file appears as vocabulary within 60 seconds. | MUST | T1 | End-to-end integration test verifies the timing budget. |

### Feature 3 — Live Stream + Archive

| ID | Requirement | Priority | Tier | Acceptance Criteria |
|---|---|---|---|---|
| CC-020 | `audio_streamer.py` produces Opus segments at approximately 6 seconds and approximately 96 kbps from the JACK output bus. | MUST | T2 | Segment files on disk show the expected duration and bitrate; the streamer process consumes under 10% CPU. |
| CC-021 | Cloudflare Worker accepts segment POSTs at `/api/cypherclaw/segment` and stores them in R2. | MUST | T2 | Test POST writes a segment to R2 and the object is retrievable via R2 listing. |
| CC-022 | Cloudflare Worker serves a valid HLS playlist at `/api/cypherclaw/live.m3u8`. | MUST | T1 | `hls.js` validator (or `ffplay`) successfully plays the live stream. |
| CC-023 | The `cypherclaw.holdenu.com` DNS record plus Worker route resolves over HTTPS with a valid certificate. | MUST | T1 | `curl -I https://cypherclaw.holdenu.com/` returns 200 with `cf-ray` header. |
| CC-024 | The static page at the root URL renders, plays the live stream, displays a GlyphWeave backdrop, and runs a canvas visualizer driven by the SSE feed. | MUST | T2 | Manual visual verification plus a browser-automation test confirming audio plays and canvas frames update. |
| CC-025 | `session_archiver.py` produces a session approximately every 8 minutes or more, names it per CypherClaw's pattern (`{House-Imagery} / {Tuning-Character} — {DD Month}`), and uploads it to the R2 archive path. | MUST | T2 | After 30 minutes of synthetic uptime, at least 3 sessions appear in R2 with the expected naming and metadata. |
| CC-026 | The archive feed on the page lists sessions in reverse chronological order; each session is playable. | MUST | T1 | Manual UI verification plus a snapshot test of the rendered feed for a fixture session list. |
| CC-027 | The composer code contains no consumer of viewer or listener counts. | MUST | T1 | Negative-assertion test grep search confirms zero matches for known count consumer patterns in the composer source tree. |
| CC-028 | End-to-end test confirms a tone-generator signal flows from JACK through the streamer, Worker, R2, and back to a browser `<audio>` element within 30 seconds. | MUST | T2 | End-to-end test passes in CI or scripted run; latency measurement is logged. |

### Feature 4 — Meter Morphing

| ID | Requirement | Priority | Tier | Acceptance Criteria |
|---|---|---|---|---|
| CC-030 | Extend `GrooveProfile` with a `metric_modulations: list[ModulationEvent]` field. | MUST | T1 | Dataclass updated; existing usages compile and tests pass. |
| CC-031 | `music_tracker.py` applies metric modulations row-by-row at the correct positions. | MUST | T2 | Unit test verifies that a 3:2 modulation at row N produces the expected timing on subsequent rows. |
| CC-032 | The composer plans multi-scene meter trajectories per arc; scene metadata carries the trajectory. | MUST | T2 | Composer log shows planned trajectories; integration test reads the metadata for a sample arc. |
| CC-033 | Unit tests cover metric-modulation correctness for ratios 3:2, 4:3, and 5:4. | MUST | T1 | Test suite includes the three ratios and asserts the expected row-position-to-time mappings. |

### Feature 5 — Tuning Morphing

| ID | Requirement | Priority | Tier | Acceptance Criteria |
|---|---|---|---|---|
| CC-040 | Implement `TuningSystem` abstract base plus concrete `TwelveTET`, `JustIntonation5Limit`, and `GamelanSlendro` classes. | MUST | T1 | Module imports succeed; each class returns a pitch table for a tonal center. |
| CC-041 | Implement `MorphOperator.pitch_table_at(t)` returning a linearly interpolated pitch table for `t` in `[0.0, 1.0]`. | MUST | T1 | Unit test asserts that `pitch_table_at(0)` equals source table and `pitch_table_at(1)` equals target table. |
| CC-042 | Implement `pitch_hz(scale_degree, octave, tuning, tonal_center_hz)` that returns the correct frequency for every supported tuning. | MUST | T1 | Unit tests verify frequencies match known reference values within 0.1 cent for all three tunings. |
| CC-043 | The composer emits Hz directly in OSC events when the active tuning is not 12-TET. | MUST | T1 | OSC trace shows freq field as Hz; `render_contract.scd` uses `freq` directly. |
| CC-044 | Provide a backward-compatible 12-TET tuning system for legacy scenes. | MUST | T1 | Scenes whose metadata sets `tuning_system_name == "12-TET"` continue to play unchanged. |
| CC-045 | Scene metadata carries the tuning system, morph target, and morph curve. | MUST | T1 | Sample scene JSON contains all three fields; schema validation passes. |
| CC-046 | Composer applies CypherClaw's per-phase tuning rule: 5-limit JI for Listen and Divination; Slendro for Conversation and Procession; morph at stillness-to-motion transitions. | MUST | T2 | Composer log shows tuning selection per phase across a 30-minute synthetic arc; transitions are detectable. |
| CC-047 | The `CYPHERCLAW_V2_TUNING_MORPH` env flag controls activation, defaulting OFF. | MUST | T1 | Module reads env var; default behavior matches OFF state. |
| CC-048 | Unit tests verify pitch frequencies match expected ratios within 0.1 cent for all supported tuning systems. | MUST | T1 | Tests include known reference points for each tuning. |

### Feature 6 — Morphing Instruments

| ID | Requirement | Priority | Tier | Acceptance Criteria |
|---|---|---|---|---|
| CC-050 | Add a `morph_voice` synthdef containing parallel source voices with crossfaded gains controlled by `morph_x`. | MUST | T1 | Synthdef compiles; rendering with `morph_x=0` produces source A only; `morph_x=1` produces source B only. |
| CC-051 | The composer can request a single-line morph phrase with a source/target voice pair and a morph curve. | MUST | T2 | Integration test schedules a morph phrase and OSC trace confirms `morph_x` reaches the expected curve values at the expected times. |
| CC-052 | A section-boundary crossfade scheduler computes per-section release tails that overlap with new section attacks. | MUST | T1 | Unit test on a two-section arc shows the overlap window matches the configured crossfade duration. |
| CC-053 | Within-family parameter walks generate continuous low-rate modulation on key parameters per voice. | MUST | T1 | OSC trace shows continuous parameter values within the expected depth band. |
| CC-054 | The `CYPHERCLAW_V2_INSTRUMENT_MORPH` env flag controls activation, defaulting OFF. | MUST | T1 | Module reads env var; default behavior matches OFF state. |
| CC-055 | Unit tests cover crossfade scheduling and morph curve shapes. | MUST | T1 | Test suite includes scheduling, curve, and OSC integration tests. |

### Feature 7 — Expression Layer

| ID | Requirement | Priority | Tier | Acceptance Criteria |
|---|---|---|---|---|
| CC-060 | All voice synthdefs accept the expression control parameters: `vib_rate`, `vib_depth`, `trem_rate`, `trem_depth`, `bend_start_hz`, `bend_end_hz`, `bend_curve_shape`, `attack_mode`, `late_release_extension`, `harmonic_resonance_profile_id`, `spectral_granulation_amount`, `spectral_smear_amount`. | MUST | T2 | Synthdef diff shows every voice exposes the listed parameters; live OSC sets each parameter without error. |
| CC-061 | Each voice provides internal LFOs (vibrato pitch LFO, tremolo amplitude LFO, spectral granulation) where allowed by the voice's gesture allowlist. | MUST | T2 | Per-voice rendering with each modulator enabled produces audible modulation matching the rate and depth set. |
| CC-062 | The expression module implements 11 named gestures (Weeping, Shimmering, Ghostly, Sighing, Agitated, Breath-shaped, Pulsing, Fracturing, Hollowing, Tension-Build, Echo-Location). | MUST | T2 | Unit tests assert that each gesture function returns an OSC payload with the expected expression parameters. |
| CC-063 | The voice-to-gesture allowlist per `cypherclaw-v2-design-statement-2026-05-22.md` §7.3 is enforced; forbidden combinations are rejected. | MUST | T1 | Unit test attempts every forbidden combination and asserts each is refused. |
| CC-064 | The scene-phase intensity multiplier table per §7.4 is applied at gesture application time. | MUST | T1 | Unit test verifies multiplier values per phase match the design statement. |
| CC-065 | Pedal logic (Sustain, Resonant with Decay Modulation, Half-pedal) is implemented per voice family. | MUST | T2 | Integration test engages each pedal and confirms the expected voice behavior. |
| CC-066 | Contour analysis classifies each note as peak, ascending, descending, static, or valley. | MUST | T1 | Unit tests on synthetic note sequences assert the expected classification. |
| CC-067 | The composer applies contour-aware dynamics multipliers and attack shapes when emitting notes. | MUST | T1 | OSC trace shows `dynamics_multiplier` and `attack_shape` set per note in accordance with the contour. |
| CC-068 | The renamed terminology (Spectral Granulation, Harmonic Resonance Profile, Spectral Smear) is used consistently across code, schemas, and documentation. | SHOULD | T1 | Lint pass finds no surviving references to the previous names in v2 modules. |
| CC-069 | Unit tests cover each gesture's expression-parameter output. | MUST | T1 | Tests enumerate all 11 gestures and assert expected outputs. |

### Feature 8 — Cross-Voice Coupling

| ID | Requirement | Priority | Tier | Acceptance Criteria |
|---|---|---|---|---|
| CC-070 | Provision an `affective_state_bus` SuperCollider control bus shared across voices. | MUST | T1 | Synthdef diff shows the new control bus and reader-side wiring per voice. |
| CC-071 | Each voice writes its rolling-window expression intensity to the bus. | MUST | T1 | OSC trace shows per-voice writes with the expected window length and value range. |
| CC-072 | Each voice reads the bus and applies a coupling multiplier to its modulator depths. | MUST | T2 | Integration test confirms one voice's high vibrato measurably shifts another voice's vibrato depth on the bus. |
| CC-073 | The bus slow-decays toward 0 in the absence of contributors with a ~5 second time constant. | MUST | T1 | Unit test seeds the bus and verifies decay timing. |
| CC-074 | The `CYPHERCLAW_V2_COUPLING` env flag controls activation, defaulting OFF. | MUST | T1 | Module reads env var; default behavior matches OFF state. |
| CC-075 | Integration test demonstrates one voice's high vibrato causes a measurable shift in another voice's vibrato depth. | MUST | T1 | Test passes by asserting the secondary voice's vibrato depth lifts by at least the expected coupling delta. |

### Feature 9 — Cumulative Expression Fatigue

| ID | Requirement | Priority | Tier | Acceptance Criteria |
|---|---|---|---|---|
| CC-080 | Per-voice fatigue counter with exponential decay (half-life ~30 seconds) is implemented. | MUST | T1 | Unit test verifies decay timing against synthetic note streams. |
| CC-081 | When the counter exceeds 0.7, a fatigue multiplier reduces subsequent expression-parameter magnitudes. | MUST | T1 | Unit test asserts the multiplier is applied above the threshold and not applied below it. |
| CC-082 | Long silences allow the counter to recover toward 0. | MUST | T1 | Unit test confirms recovery behavior. |
| CC-083 | The `CYPHERCLAW_V2_FATIGUE` env flag controls activation, defaulting OFF. | MUST | T1 | Module reads env var; default behavior matches OFF state. |
| CC-084 | Unit tests verify decay behavior, threshold behavior, and recovery behavior. | MUST | T1 | Tests cover all three behaviors with explicit assertions. |

---

## Suggested Task Slicing

The PRD breaks into 9 sprints, one per feature, ordered to maximize use of shared infrastructure as it's built. Total estimated tasks: ~110. Sprints 1-3 land plumbing (hard cutover). Sprints 4-9 contain aesthetic features (flag-gated).

### Sprint 1 — Streaming Plumbing (Feature 3)
Lands first because it's independent of the other audio work and unlocks the public face.
- T-001: Add Cloudflare DNS records for `cypherclaw.holdenu.com`
- T-002: Add Worker route for `cypherclaw.holdenu.com` in wrangler.toml + worker/src/index.ts
- T-003: Implement `worker/src/cypherclaw.ts` segment-storage endpoint (POST /api/cypherclaw/segment)
- T-004: Implement HLS playlist endpoint (GET /api/cypherclaw/live.m3u8)
- T-005: Implement segment retrieval endpoint (GET /api/cypherclaw/segment/...)
- T-006: Implement session-list and session-detail endpoints
- T-007: Implement SSE live-features endpoint (Durable Object backed)
- T-008: Implement `audio_streamer.py` Opus encoder + JACK reader + segment poster on cypherclaw
- T-009: Deploy audio_streamer as systemd unit on cypherclaw
- T-010: Implement `session_archiver.py` (session detection, concatenation, title generation per CypherClaw pattern, upload)
- T-011: Deploy session_archiver as systemd unit
- T-012: Static page scaffold (HTML + audio element + GlyphWeave backdrop + canvas placeholder)
- T-013: Canvas visualizer v1 (vocabulary chosen by engineering for first pass)
- T-014: Archive feed UI
- T-015: End-to-end smoke test (tone → JACK → R2 → page → playback)
- T-016: Aesthetic verification — render reference samples, present to Anthony, listening session

### Sprint 2 — MIDI Ingestion (Feature 2)
Lands second because the variation generator needs Sprint 4's tunings — but we can land the watcher, parser, vocabulary storage, and faithful-transmission renderer now and stub the tuning-aware re-pitching until Sprint 4.
- T-020: Create `/home/user/cypherclaw/midi-inbox/` directory tree on cypherclaw
- T-021: Implement `midi_intake_daemon.py` watcher loop
- T-022: Implement `midi_ingestion/parser.py` (mido-based)
- T-023: Implement `midi_ingestion/fragment_extractor.py` (motifs, rhythm cells, chord progressions, grooves)
- T-024: Implement `midi_ingestion/vocabulary_store.py` (sqlite I/O)
- T-025: Implement `midi_ingestion/faithful_renderer.py` (whole-file → scene spec)
- T-026: Implement `composer_vocabulary_bridge.py` integration
- T-027: Modify `duet_composer.py` to consult vocabulary DB
- T-028: Deploy midi_intake_daemon as systemd unit
- T-029: Drop test MIDIs into the inbox; verify processing + sidecar manifests
- T-030: Integration test for `--faithful-transmission` flag
- T-031: Aesthetic verification — render reference samples (cypherclaw composing with MIDI-influenced fragments), listening session

### Sprint 3 — Per-Voice Reverb Spaces (Feature 1)
Lands third because it modifies the SuperCollider synthesis graph in ways that other audio features will then build on.
- T-040: Extend `master_smooth.scd` to host 7 FX buses
- T-041: Implement reverb synthdef for each space using algorithmic reverb (FreeVerb / JPverb / NHHall)
- T-042: Tune reverb parameters per voice's space description (CypherClaw's verbatim text in §4 of design statement is the spec)
- T-043: Modify `sw_sampler.scd` to support per-voice `fx_bus_id` parameter
- T-044: Modify `render_contract.scd` to route OSC events to correct FX bus per voice
- T-045: Hot-reload synthdefs into running scsynth
- T-046: Add composer logic for mood-driven space selection (matched / expressive / house-bound)
- T-047: Unit tests for routing correctness
- T-048: Aesthetic verification — render reference samples per voice in its space, listening session

### Sprint 4 — Tuning Morphing (Feature 5)
- T-050: Implement `tuning/system.py` with TuningSystem abstract + concrete classes (12-TET, JI5Limit, Slendro)
- T-051: Implement `tuning/morph.py` morph operator
- T-052: Implement `tuning/pitch_pipeline.py` single-function API
- T-053: Replace midi-note OSC payload with Hz payload in render_contract.scd
- T-054: Backward-compat: 12-TET legacy scenes still work
- T-055: Modify scene metadata to carry tuning system + morph target + morph curve
- T-056: Apply CypherClaw's per-phase tuning rule in composer
- T-057: Tuning-aware re-pitching in MIDI variation generator (resolves Sprint 2's stub)
- T-058: Wire `CYPHERCLAW_V2_TUNING_MORPH` env flag
- T-059: Unit tests for pitch_hz correctness (within 0.1 cent)
- T-060: Aesthetic verification — listening session with flag on/off A/B

### Sprint 5 — Meter Morphing (Feature 4)
- T-070: Extend `GrooveProfile` with metric_modulations field + ModulationEvent dataclass
- T-071: Implement metric modulation application in music_tracker.py
- T-072: Implement multi-scene meter trajectory planner in composer
- T-073: Unit tests for ratio correctness
- T-074: Aesthetic verification — listening session

### Sprint 6 — Expression Layer (Feature 7)
- T-080: Implement `expression/gestures.py` with all 11 gestures
- T-081: Implement `expression/voice_gesture_rules.py` (allowlists + forbidden)
- T-082: Implement `expression/scene_phase_scaling.py`
- T-083: Implement `expression/contour_analysis.py`
- T-084: Implement `expression/pedal_state.py` (pedal control bus interface)
- T-085: Add internal LFOs to all voice synthdefs (vibrato pitch LFO, tremolo amp LFO)
- T-086: Implement Spectral Granulation in voices that allow it (per allowlist)
- T-087: Implement Harmonic Resonance Profile (frequency-aware harmonic emphasis) for voices that benefit
- T-088: Implement Spectral Smear (interval-driven micro-slide) at composer + synthdef level
- T-089: Implement pedal logic (Sustain/Resonant/Half) with Decay Modulation for Resonant
- T-090: Wire expression parameters into OSC events from composer
- T-091: Apply scene-phase intensity multiplier at gesture application time
- T-092: Apply contour-aware dynamics multiplier at note emission
- T-093: Unit tests for each gesture's output
- T-094: Aesthetic verification — listening session

### Sprint 7 — Morphing Instruments (Feature 6)
- T-100: Implement `morph_voice.scd` (parallel sources with crossfaded gains)
- T-101: Implement `instrument_morph/single_line_morph.py`
- T-102: Implement `instrument_morph/crossfade.py` section-boundary scheduler
- T-103: Implement `instrument_morph/parameter_walk.py`
- T-104: Composer logic for scene-driven morph selection
- T-105: Wire `CYPHERCLAW_V2_INSTRUMENT_MORPH` env flag
- T-106: Unit tests for morph curves and crossfade scheduling
- T-107: Aesthetic verification — listening session

### Sprint 8 — Cross-Voice Coupling + Cumulative Fatigue (Features 8 + 9)
- T-110: Implement `expression/affective_bus.py` (writer-side)
- T-111: Implement `coupling/affective_bus_router.scd` (SC reader-side)
- T-112: Wire each voice synthdef to read coupling multiplier
- T-113: Implement bus slow-decay
- T-114: Wire `CYPHERCLAW_V2_COUPLING` env flag
- T-115: Implement `expression/fatigue.py` (per-voice intensity load counter)
- T-116: Apply fatigue multiplier to expression parameters in composer
- T-117: Wire `CYPHERCLAW_V2_FATIGUE` env flag
- T-118: Integration test: one voice's high intensity affects another voice's modulator depth
- T-119: Unit tests for fatigue decay and threshold behavior
- T-120: Aesthetic verification — listening session (both features together)

### Sprint 9 — Canvas Visualizer Refinement + Documentation
- T-130: Consult CypherClaw on canvas visualizer vocabulary refinements
- T-131: Iterate canvas visualizer based on CypherClaw + Anthony review
- T-132: Update PromptClaw architecture docs to reference CypherClaw v2 features
- T-133: Update `cypherclaw-image-contract.md` analog: create `cypherclaw-audio-stream-contract.md` for future external consumers
- T-134: Update SDP run-log with all aesthetic verification outcomes
- T-135: Final end-to-end smoke test: cypherclaw composing, streaming, archived, MIDI ingesting, all flags on
- T-136: Final aesthetic verification — full listening session

**Sprint totals (rough):** S1: 16 tasks, S2: 12, S3: 9, S4: 11, S5: 5, S6: 15, S7: 8, S8: 11, S9: 7 → **~94 tasks**. Estimate: ~300 hours of agent time, possibly less with parallelism.

---

## Verification Strategy

### Unit and CLI Tests

Every new module ships with unit tests in `tests/`. TDD is mandatory per durable instruction. Tests cover:
- MIDI parsing correctness (sample MIDI files of varying complexity)
- Tuning math (cent-level frequency correctness for each pitch in each system)
- Fragment extraction (motifs, chord progressions match expectations on hand-crafted MIDIs)
- Gesture output (each gesture sets correct expression parameters)
- Voice → gesture allowlist enforcement (forbidden combinations rejected)
- Scene-phase intensity multiplier (correct value per phase)
- Contour classification (synthetic note sequences classified correctly)
- Fatigue decay (exponential decay half-life verified)
- Coupling bus behavior (multi-voice scenarios produce expected bus values)
- Metric modulation math (row-position-to-time mapping under ratio shifts)
- Crossfade scheduler (overlap windows correct)

### Static Checks

Existing PromptClaw static checks apply. Additional checks for this PRD:
- Negative-assertion test: composer source contains no consumer of viewer/listener-count signals
- Negative-assertion test: 12-TET fallback only activates when scene metadata explicitly sets `tuning_system_name == "12-TET"` or backward-compat scene mode

### Live Audio Verification (Plumbing)

End-to-end smoke tests:
- Tone generator → JACK → audio_streamer → Worker → R2 → page audio element → playback (latency < 30s)
- MIDI file in `/home/user/cypherclaw/midi-inbox/` → fragments in vocabulary DB (within 60s)
- Faithful-transmission mode: known MIDI file → recognizable rendition in CypherClaw's voices

### Aesthetic Verification (Per-Feature Listening Sessions)

Each sprint terminates in an "Aesthetic verification" task that:
1. Renders a reference sample (typically a 30-60 second excerpt of CypherClaw composing with the new feature flagged on, plus an A/B excerpt with flag off where applicable)
2. Uploads the reference sample to a known path on the cypherclaw box (e.g. `/home/user/cypherclaw/var/reference-renders/sprint-NNN-{date}.opus`)
3. Sends a Telegram notification to Anthony with the path and a brief description of what to listen for
4. **Pauses the SDP run** awaiting Anthony's verdict (APPROVE / REWORK / REJECT)
5. On REWORK, accepts free-text feedback and generates one or more follow-up tasks
6. On APPROVE, continues to the next sprint
7. On REJECT, halts the build pending operator intervention

This is the human-in-the-loop checkpoint that engineering automation cannot replace.

### Tiered Verification Cadence

Per durable verify-scan-fix-repeat instruction:
- Tier 1 (per task): unit tests pass
- Tier 2 (per sprint): integration tests + aesthetic listening session
- Tier 3 (whole PRD): end-to-end smoke test + final listening session covering all features active simultaneously

---

## Security Requirements

- **Cloudflare credentials:** Worker deploy + R2 access use scoped API tokens, not root. Tokens stored in `1Password / .env / wrangler secrets`, never committed.
- **R2 bucket access:** the `cypherclaw-stream` R2 bucket is private at the object level; access via Worker only. Worker validates request paths to prevent directory traversal.
- **Public endpoints:** all `/api/cypherclaw/*` endpoints that mutate state (POST /segment, POST /feature-update) require a shared-secret bearer token. Token rotated quarterly. cypherclaw-side has the secret in `/home/user/cypherclaw/.env` (chmod 600).
- **DNS:** the `cypherclaw.holdenu.com` record is in Cloudflare with proxy enabled (orange cloud) so origin IP is not exposed.
- **Listener data:** no analytics tracking on `cypherclaw.holdenu.com` (per CypherClaw's expressed wish to not know listener counts). Cloudflare Web Analytics that's enabled on holdenu.com proper is explicitly disabled for this subdomain.
- **MIDI ingestion:** the watch folder is local-only (no network share by default). If syncing from Anthony's Mac is needed, use Tailscale + rsync, not a public share.
- **Source MIDI files:** treated as untrusted input. Parser rejects malformed files cleanly without crashing the daemon. Files > 5 MB are flagged in the manifest and skipped by default (most legitimate music MIDIs are well under 1 MB).

---

## Deployment Requirements

### cypherclaw box

- New systemd user-mode services (following existing conventions in `my-claw/systemd/`):
  - `cypherclaw-audio-streamer.service`
  - `cypherclaw-session-archiver.service`
  - `cypherclaw-midi-intake-daemon.service`
- New configuration in `/home/user/cypherclaw/.env`:
  - `CYPHERCLAW_HOLDENU_API_TOKEN` (bearer for POSTs to Worker)
  - `CYPHERCLAW_V2_TUNING_MORPH` (default `0`)
  - `CYPHERCLAW_V2_INSTRUMENT_MORPH` (default `0`)
  - `CYPHERCLAW_V2_COUPLING` (default `0`)
  - `CYPHERCLAW_V2_FATIGUE` (default `0`)
- Hot-reload pattern preferred for SuperCollider synthdef updates. Composer restart pre-authorized.
- Deploy mechanism: `scp + restart` (per durable `feedback_fast_deploy` instruction); no orchestration tool overhead.

### Cloudflare side

- Wrangler deploy of updated `holdenu-api` worker
- New DNS records via Cloudflare API (or dashboard manual)
- R2 bucket setup: `cypherclaw-stream` (private) with two prefixes: `live/`, `archive/`
- Lifecycle policy on `live/`: delete segments older than 24 hours (keeps storage minimal; archive segments persist)

### Static page

- `catalog-explorer/pages/cypherclaw/` builds (or is served directly) by Cloudflare Pages or by the Worker as static assets.
- Page assets versioned in catalog-explorer repo; deploy is push-to-main.

---

## Risks

| Risk | Severity | Mitigation |
|---|---|---|
| Reverb load tanks scsynth | Medium | Start with algorithmic reverb (Path A), monitor CPU; if needed, drop to fewer / shorter reverbs before going convolution. |
| Streaming bug pegs CPU, stalls composer | High | Streamer runs as separate process with strict resource limits in systemd drop-in (MemoryMax, TasksMax). If streamer dies, composer keeps running. |
| Synthdef hot-reload causes silent gap | Low | Maintain a fallback mode where missing/new synthdefs forward to nearest equivalent existing voice (pattern already exists for quarantined voices). |
| Aesthetic feature sounds bad and we don't notice | Medium | Per-feature listening session enforces human ear at every sprint terminus. Reference samples persist for retrospective review. |
| Tuning morph clashes with imported MIDI's structural pitch | Medium | Faithful-transmission mode preserves MIDI pitches; non-faithful mode is explicitly intended to fracture them. Document the divergence clearly in the visualizer / archive metadata. |
| Cloudflare Worker cost surprise | Low | Free tier is generous; segment uploads at 6-sec cadence ≈ 14,400 requests/day → still under free tier. R2 storage costs scale with archive growth — add lifecycle policy on live segments (24h TTL) to bound this; archive grows ~1 MB/min × 60 min × N sessions/day. Quote: `promptclaw pal cost` shouldn't apply here but worth recreating an equivalent for Cloudflare. |
| Composer regression from new env-flag-gated code paths | Low | Default OFF on aesthetic flags; only plumbing changes are unflagged. If unflagged plumbing regresses, isolate quickly through systemctl revert and `git revert`. |
| CypherClaw's design decisions reveal themselves wrong-in-practice after listening | Medium | Negotiated already once (MIDI play-through). Re-negotiate as needed; design statement file is the canonical record of changes. |

---

## Assumptions

- The cypherclaw box stays online and reachable via Tailscale SSH for the duration of the build.
- The existing composer continues to be the correct entry point — no other composer process gets introduced.
- Anthony has Cloudflare account access for the holdenu.com zone and can issue scoped API tokens, or grants tokens to the engineering agent ahead of Sprint 1.
- Worker free-tier limits are sufficient (verified roughly above; quantify in Sprint 1 task).
- The local Ollama on cypherclaw is available for the rare design-question consultations during the build (only needed if a feature triggers a re-consultation of CypherClaw).
- The 12-day-running composer's existing scene database, music_tracker state, and `/tmp` state files persist; this build adds capabilities, doesn't reset the composer's memory.

---

## Open Questions for SDP Agents to Resolve Without Blocking

- **Reverb path A vs B:** start algorithmic. If Sprint 3 listening session reveals algorithmic reverbs don't read as the described environments, escalate to Anthony before swapping to convolution (cost: render IRs or source them).
- **Canvas visualizer vocabulary v1:** engineering picks a starting set for Sprint 1. Refine in Sprint 9 with CypherClaw's input.
- **Session duration threshold for archival:** default 8 minutes; tune empirically.
- **Multi-scene meter trajectory tables:** engineering picks reasonable defaults (e.g. ascending complexity: 4/4 → 7/8 → 11/8 → drift back). CypherClaw refines after listening.
- **Coupling strength per voice:** default 0.5 across all voices. Refine after Sprint 8 listening.
- **Fatigue threshold and multiplier:** defaults 0.7 / 0.5. Refine after Sprint 8 listening.
- **Faithful-transmission flag mechanism:** sidecar `.json` with `"mode": "faithful"`, OR a `.faithful` empty file alongside, OR a filename suffix convention. Engineering picks one.

---

## Operator Handoff to SDP

This PRD is ready to be loaded into the SDP pipeline. Recommended SDP commands:
- `promptclaw sdp analyze sdp/prd-cypherclaw-v2-2026-05-22.md` — generates `sdp/task-graph.md` and `sdp/implementation-plan.md`
- `promptclaw sdp run-loop` — kicks off the autonomous build
- `promptclaw pal cost` — monitor burn during the run (PAL host is the agent compute substrate)
- Aesthetic verification tasks signal pause via standard SDP "needs_attn" status with a Telegram-formatted notification to Anthony

The canonical aesthetic record is `sdp/cypherclaw-v2-design-statement-2026-05-22.md`. Engineering agents must read it before starting any aesthetic feature work, and must not silently dilute CypherClaw's specific language into a "reasonable middle ground." When the verbatim language is too specific to implement literally, return to CypherClaw for re-negotiation per the §3 (MIDI play-through) pattern.

---

## Project History

- 2026-05-22: PRD drafted by Anthony + Claude, with aesthetic decisions captured directly from CypherClaw via local Ollama (`qwen3.5:9b`)
- (forthcoming) SDP run completion
