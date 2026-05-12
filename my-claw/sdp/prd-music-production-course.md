# PRD: CypherClaw Music Production Course Integration

## Overview

CypherClaw now has a working score-tree and tracker-based songwriting spine,
but the musical education layer still needs to be encoded as software behavior.
This PRD translates the CypherClaw Music Production Course into implementation
work: theory, harmony, rhythm, synthesis, mixing, mastering, critical listening,
SenseWeave interpretation, Theramini ensemble behavior, genre literacy, and
30-minute dramatic-arc production practice.

The goal is not to store a static course document. The goal is to make the
course operational. CypherClaw should consult these ideas while composing,
persist the resulting production choices in score trees and tracker metadata,
verify them with tests/audio proxies, and use them during live playback.

The production course is organized around the 30-minute dramatic arc:

- **Divination:** sparse listening, environmental responsiveness, wide space
- **Emergence:** motifs and pulse forming, modal identity, opening filters
- **Conversation:** dialogue, counterpoint, call-and-response, development
- **Convergence:** density, climax, harmonic/rhythmic/timbral saturation
- **Crystallization:** resolution, reduction, memory, reverb tail, archive

Every requirement below should make that arc more musically literate and more
verifiable.

**Depends on:**

- `my-claw/sdp/prd-songwriter-emsd-completion.md`
- `docs/cypherclaw-score-tree-composition-spec.md`
- `docs/cypherclaw-musicianship-roadmap.md`
- `docs/cypherclaw-emsd-roadmap.md`
- current `ScoreTree`, composition gate, tracker compiler, tracker runtime,
  master bus, sample, self-listener, repertoire, and Theramini modules

**Key files and modules:**

- `my-claw/tools/duet_composer.py`
- `my-claw/tools/senseweave/score_tree.py`
- `my-claw/tools/senseweave/recursive_composer.py`
- `my-claw/tools/senseweave/composition_gate.py`
- `my-claw/tools/senseweave/form_grammar.py`
- `my-claw/tools/senseweave/harmonic_planner.py`
- `my-claw/tools/senseweave/reharmonizer.py`
- `my-claw/tools/senseweave/hook_engine.py`
- `my-claw/tools/senseweave/tracker_compiler.py`
- `my-claw/tools/senseweave/music_tracker.py`
- `my-claw/tools/senseweave/music_tracker_runtime.py`
- `my-claw/tools/senseweave/arrangement_engine.py`
- `my-claw/tools/senseweave/mix_engine.py`
- `my-claw/tools/senseweave/master_bus.py`
- `my-claw/tools/senseweave/ear_engine.py`
- `my-claw/tools/senseweave/sound_palette_lab.py`
- `my-claw/tools/senseweave/sample_lab.py`
- `my-claw/tools/senseweave/dsp_scene_lab.py`
- `my-claw/tools/senseweave/theramini_duet.py`
- `my-claw/tools/senseweave/repertoire_memory.py`
- `my-claw/curriculum/EMSD-*`
- new production-course support modules under `my-claw/tools/senseweave/`

## Current State Analysis

### Implemented Foundation

- Score trees already represent commission, brief, form, motifs, sections,
  harmonic plan, arrangement plan, narrative map, and metadata.
- The composer can compile approved score trees into tracker scenes.
- The runtime can schedule tracker rows, apply some row automation, and publish
  current state.
- Harmony, hooks, arrangement, mix, sound palette, sample, DSP, ear, and
  repertoire helpers exist as first-pass modules.
- EMSD curriculum scaffolds exist and can be used as reference/curriculum
  targets.

### Remaining Production Gaps

- Pitch, scale, chord, voicing, and functional-harmony knowledge is scattered
  and not consistently encoded in one verified musical vocabulary.
- Rhythm currently uses duration cells, but not enough meter, swing,
  polyrhythm, phrase breath, metric modulation, or groove intent.
- Counterpoint and motivic development exist only in partial metadata; they
  need rules that can shape independent lanes.
- Synthesis, production, and mix choices are not yet explicitly selected from
  the course concepts per arc phase.
- Critical listening metrics exist as first-pass proxies but do not yet feed
  production choices strongly enough.
- SenseWeave mappings need musical interpretation rules for room, membrane,
  garden, Theramini, archive, and network sources.
- Genre literacy is not yet a strategy library that can influence form,
  rhythm, harmony, sound design, and arrangement.
- The 30-minute production score needs to become a runtime phase profile,
  not only prose.

## Goals

- Encode the course as a runtime production knowledge base with typed,
  testable concepts.
- Make pitch, harmony, rhythm, counterpoint, synthesis, mix, and production
  decisions visible in score-tree and tracker metadata.
- Improve long-form musical variety without losing live safety.
- Give each 30-minute arc phase a coherent production profile.
- Make SenseWeave and Theramini inputs musically interpretable through course
  concepts instead of arbitrary parameter mappings.
- Add automated verification that catches unmusical regressions such as flat
  loops, single-note drones, harsh registers, muddy mixes, missing transitions,
  and phase-inappropriate density.

## Non-Goals

- Do not replace the existing score-tree/tracker runtime.
- Do not require external music APIs or copyrighted training material.
- Do not require real SuperCollider rendering for every unit test. Deterministic
  metadata tests and synthetic audio proxies are acceptable where live rendering
  is impractical.
- Do not make every piece complex. Divination and Crystallization may be sparse
  by design, and micro pieces remain valid when complete.
- Do not hardcode one style as CypherClaw's identity. Genre literacy should be
  a strategy vocabulary, not an imitation machine.

## Product Requirements

| ID | Description | Priority | Tier | Acceptance Criteria |
|---|---|---|---|---|
| MPC-001 | Create a production-course knowledge base that the composer can consult at runtime. | MUST | T1 | - course concepts are represented as typed data or markdown references with stable IDs<br/>- arc-phase profiles exist for Divination, Emergence, Conversation, Convergence, and Crystallization<br/>- tests verify all required chapters/phase profiles are present and loadable |
| MPC-002 | Implement a verified pitch, interval, scale, and mode library. | MUST | T1 | - library includes chromatic, major/minor, seven modes, pentatonic, whole-tone, octatonic, blues, Hirajoshi, In Sen, Pelog, Bhairav, Hungarian minor, Prometheus, and microtonal/ratio helpers<br/>- interval metadata includes semitones, consonance/dissonance, character, and arc-phase affinity<br/>- tests verify interval/scale pitch-class sets and MIDI/frequency conversion |
| MPC-003 | Add chord construction and voicing support. | MUST | T1 | - triads, seventh chords, extended chords, altered dominants, suspended/add chords, drop voicings, close/open voicings, and rootless/guide-tone voicings are supported<br/>- voicing engine respects register limits and configured spacing<br/>- tests verify chord pitch classes, unique voicings, range safety, and smooth voice-leading choices |
| MPC-004 | Encode functional harmony and modulation strategies. | MUST | T1 | - harmonic planner can label tonic, subdominant, dominant, secondary dominant, modal-interchange, tritone-sub, chromatic-mediant, pedal, planing, and modulation functions<br/>- score trees expose harmonic function and transition intent per section<br/>- tests verify cadence resolution, pivot/common-tone modulation continuity, and phase-appropriate tension levels |
| MPC-005 | Expand rhythm, meter, groove, and time handling. | MUST | T1 | - rhythm engine supports 4/4, 3/4, 6/8, 5/4, 7/8, free/rubato, swing, shuffle, dotted cells, push/pull, polyrhythm, polymeter, and metric modulation<br/>- tracker metadata carries meter, subdivision, swing ratio, groove timing, and phrase breath without breaking deterministic row scheduling<br/>- tests verify IOI ratios, swing offsets, polyrhythm cycle length, and phase-specific meter policies |
| MPC-006 | Add counterpoint and linear voice-combination rules. | MUST | T1 | - arrangement/compiler can choose contrary, oblique, parallel, echo, commentary, and completion relationships between lanes<br/>- dissonance and resolution rules are available as metadata checks<br/>- tests verify independent lane contours, staggered climaxes, and no accidental lane crowding |
| MPC-007 | Add post-tonal, spectral, and microtonal material strategies. | SHOULD | T2 | - composer can request pitch-class sets, spectral partial-derived harmony, just-intonation ratios, and 24-TET/ratio pitch events when phase/style permits<br/>- SenseWeave spectral analysis can seed harmonic material<br/>- tests verify generated material remains bounded and tagged as post-tonal/spectral/microtonal |
| MPC-008 | Build a synthesis-architecture strategy registry. | MUST | T1 | - registry covers subtractive, FM, additive, granular, physical modeling, and spectral/FFT processing with safe parameter ranges and arc-phase affinities<br/>- score tree or tracker scenes can request synthesis architecture by production role<br/>- tests verify each architecture has role tags, macro controls, safe ranges, and fallbacks |
| MPC-009 | Add production-aware frequency allocation and EQ policy. | MUST | T1 | - mix engine assigns sub, bass, low-mid, midrange, upper-mid, presence, and air lanes to roles<br/>- production metadata includes HPF/LPF/EQ intent for bass, pad, lead, texture, noise, sample, and Theramini lanes<br/>- tests verify role frequency lanes avoid primary masking and preserve bass center policy |
| MPC-010 | Add dynamics, compression, sidechain, and deference policy. | MUST | T1 | - production profile maps arc phase to dynamic range, compression intensity, transient policy, and sidechain/deference rules<br/>- Theramini and environmental transients can request generated-material ducking or silence<br/>- tests verify dynamic targets, sidechain metadata, and no over-compression in Divination/Crystallization |
| MPC-011 | Add spatial, reverb, and delay production profiles. | MUST | T1 | - phase profiles define stereo width, near/far depth, reverb size/decay/damping, delay style, and transition-space behavior<br/>- tracker scenes expose spatial intent and reverb/delay sends<br/>- tests verify wide sparse openings, clearer Conversation space, focused Convergence, and long Crystallization tails |
| MPC-012 | Complete mastering and loudness policy for installation playback. | MUST | T1 | - master policy targets installation-safe LUFS/peak ranges, limiter ceiling, broad EQ intent, and phase-specific dynamic contrast<br/>- automated proxies catch clipping, silence, harshness, and low-end runaway<br/>- tests verify master profiles and synthetic render/loudness proxies |
| MPC-013 | Implement critical-listening and psychoacoustic interpretation rules. | MUST | T1 | - ear engine or production evaluator exposes spectral balance, dynamic contour, spatial distribution, timbral quality, rhythmic activity, harmonic tension, masking risk, and equal-loudness compensation hints<br/>- feedback can modify future density, register, EQ, dynamics, and sound-palette choices<br/>- tests use synthetic events/audio features to verify correction decisions |
| MPC-014 | Encode SenseWeave voice-to-music interpretation rules. | MUST | T1 | - room, membrane/contact mic, garden, Theramini, archive, and network sources have musical mappings for pitch, rhythm, density, harmony, timbre, mix, and deference<br/>- Perform-VE condenser/room mic fallback is represented as a source option<br/>- tests verify quiet/noisy room, rain/wind/contact vibration, garden inactivity, Theramini activity, archive recall, and network/weather mappings |
| MPC-015 | Implement ensemble-space and Theramini partner behavior from the course. | MUST | T1 | - policy supports listening first, complementary register, rhythmic sympathy, harmonic response intervals, accompaniment textures, call/response, imitation, commentary, completion, and silence<br/>- score/tracker metadata identifies current lead/support roles<br/>- tests verify no register crowding, no excessive overlap during human/Theramini gesture, and recovery to solo mode |
| MPC-016 | Add a genre-literacy strategy library. | MUST | T1 | - strategies exist for ambient/drone/generative, minimalism, jazz, IDM/electronic, classical/orchestral form, musique concrete/electroacoustic, spectral music, blues, world-music concepts, and post-rock/experimental builds<br/>- strategies can influence form, harmony, rhythm, synthesis, arrangement, and mix without hardcoding imitation<br/>- tests verify strategy selection, arc affinity, and no missing required genre strategy |
| MPC-017 | Make the 30-minute production score executable. | MUST | T1 | - procedural arc exposes per-phase density, dynamic, harmonic, rhythm, timbre, spatial, compression, SenseWeave, and synthesis targets<br/>- score-tree commissioning and tracker compilation use those targets for long pieces and 5-minute proxy tests<br/>- tests verify the five-phase contour and phase-specific production metadata |
| MPC-018 | Add phase-transition composition techniques. | MUST | T1 | - transition planner supports pivot event, breath/silence, metric modulation, timbral morph, harmonic pivot chord, and common-tone bridge<br/>- adjacent sections share at least one continuity element unless a deliberate hard cut is tagged<br/>- tests verify no untagged abrupt phase jumps and valid transition metadata |
| MPC-019 | Build SuperCollider recipe references without coupling tests to live audio. | SHOULD | T2 | - reference recipes exist for MIDI-to-frequency, intervals, scales, chord voicings, swing, polyrhythm, subtractive, FM, additive, granular, physical modeling, spectral freeze, EQ, compression, sidechain, reverb, delay, master bus, groups, buses, patterns, and envelopes<br/>- recipes are discoverable from curriculum/reference docs<br/>- tests verify recipe files and required labels exist |
| MPC-020 | Wire production-course choices into score trees and tracker output. | MUST | T1 | - score trees carry production vocabulary for mode/scale, harmonic function, meter/groove, counterpoint relation, synthesis architecture, mix role, spatial intent, genre strategy, phase profile, and transition type<br/>- tracker scenes/steps preserve enough metadata for runtime scheduling and diagnostics<br/>- tests verify metadata survives compose -> gate -> compile -> schedule |
| MPC-021 | Extend the composition gate with production-course checks. | MUST | T1 | - gate can reject phase-inappropriate density, missing harmonic/rhythm metadata, unsafe register, flat dynamics, missing transition continuity, missing mix role, and untagged genre/strategy choices for long pieces<br/>- intentionally sparse/micro pieces can pass when they carry valid sparse intent<br/>- tests cover both rejection and acceptance paths |
| MPC-022 | Add course-driven self-critique and revision targets. | SHOULD | T2 | - critique output names concrete course concepts behind failures, such as masking, no recurrence, no cadence, weak transition, over-compression, or unsupported density<br/>- bounded revision can adjust form, harmony, rhythm, register, mix, or strategy without changing piece identity<br/>- tests verify at least one metric improves after revision |
| MPC-023 | Turn the production course into executable curriculum exercises. | SHOULD | T2 | - curriculum includes exercises/tests for intervals/scales, chord voicings, progressions, rhythm/groove, counterpoint, synthesis architecture, mix/master, SenseWeave mapping, Theramini ensemble, genre strategy, and full arc production<br/>- exercise metadata includes objective, template, verifier, and expected features<br/>- tests verify curriculum completeness and runnable verifier stubs |
| MPC-024 | Add operator diagnostics for production-course decisions. | SHOULD | T2 | - face/status/operator output can show current phase, scale/mode, harmonic function, groove, production strategy, mix role, spatial profile, SenseWeave source, Theramini relation, and critique notes<br/>- diagnostics degrade gracefully when data is absent<br/>- tests verify status payload shape and no hallucinated unavailable fields |
| MPC-025 | Add end-to-end production-course integration tests. | MUST | T1 | - tests compose, gate, compile, schedule, and inspect a 5-minute proxy arc using production-course metadata<br/>- tests verify non-silent output proxy, no single-note long sections, phase contour, transition continuity, mix role allocation, and repertoire storage<br/>- tests run without live hardware and with mocked SenseWeave/Theramini inputs |

## Dependency Map

```text
MPC-001 -> MPC-002, MPC-008, MPC-017, MPC-019
MPC-002 -> MPC-003, MPC-004, MPC-007
MPC-003 -> MPC-004, MPC-006, MPC-020
MPC-004 -> MPC-017, MPC-018, MPC-020
MPC-005 -> MPC-006, MPC-017, MPC-018, MPC-020
MPC-006 -> MPC-015, MPC-020
MPC-007 -> MPC-008, MPC-014, MPC-020
MPC-008 -> MPC-009, MPC-011, MPC-020
MPC-009 -> MPC-010, MPC-012, MPC-021
MPC-010 -> MPC-012, MPC-015, MPC-021
MPC-011 -> MPC-017, MPC-018, MPC-020
MPC-012 -> MPC-013, MPC-021
MPC-013 -> MPC-014, MPC-022
MPC-014 -> MPC-015, MPC-017, MPC-020
MPC-015 -> MPC-020, MPC-025
MPC-016 -> MPC-017, MPC-020
MPC-017 -> MPC-018, MPC-020, MPC-025
MPC-018 -> MPC-020, MPC-021
MPC-019 -> MPC-023
MPC-020 -> MPC-021, MPC-024, MPC-025
MPC-021 -> MPC-022, MPC-025
MPC-022 -> MPC-025
MPC-023 -> MPC-024
MPC-024 -> MPC-025
```

## Suggested Implementation Phases

### Phase 1: Musical Vocabulary Runtime

Focus requirements:

- MPC-001
- MPC-002
- MPC-003
- MPC-004
- MPC-005

Goal:

- establish verified pitch, harmony, chord, rhythm, and production-course data
  that downstream modules can depend on.

### Phase 2: Production Strategy and Arc Profiles

Focus requirements:

- MPC-008
- MPC-009
- MPC-010
- MPC-011
- MPC-012
- MPC-017
- MPC-018

Goal:

- make each arc phase produce coherent synthesis, mix, dynamics, space, and
  transition decisions.

### Phase 3: Listening, Environment, and Ensemble

Focus requirements:

- MPC-006
- MPC-007
- MPC-013
- MPC-014
- MPC-015

Goal:

- connect critical listening, SenseWeave, Theramini, counterpoint, and spectral
  material to concrete score-tree and runtime choices.

### Phase 4: Genre Literacy and Curriculum

Focus requirements:

- MPC-016
- MPC-019
- MPC-023
- MPC-024

Goal:

- turn the course into reusable references, strategy libraries, exercises, and
  operator-visible diagnostics.

### Phase 5: Integration, Gate, and Revision

Focus requirements:

- MPC-020
- MPC-021
- MPC-022
- MPC-025

Goal:

- prove the production-course layer survives the full compose -> gate ->
  compile -> schedule -> critique -> store path.

## Verification Strategy

- Unit tests for theory primitives: intervals, pitch classes, scales, modes,
  MIDI/frequency conversion, chord construction, voicing uniqueness, cadence
  labels, and rhythm IOI ratios.
- Metadata tests for score-tree/tracker propagation: arc phase, production
  strategy, synthesis architecture, mix role, spatial profile, transition type,
  genre strategy, and SenseWeave/Theramini relation.
- Synthetic audio/proxy tests for mix/master: clipping, silence, harshness,
  low-end runaway, rough spectral balance, rough loudness target, and dynamic
  contour.
- Integration tests for 5-minute proxy arcs, mocked SenseWeave streams,
  mocked Theramini activity, repertoire storage, and course-driven critique.
- Curriculum tests that ensure references, recipes, prompts, exercises, and
  verifier stubs remain present as the course expands.

## Rollout Notes

- Load this PRD after the current songwriter/EMSD completion PRD.
- Keep the initial implementation behind the current fractal-form chain so it
  does not interrupt T-014 through T-020.
- Prefer metadata and deterministic proxy verification before adding expensive
  live SuperCollider rendering.
- Treat the production-course data as a compositional policy layer. Runtime
  modules should be able to ignore unavailable inputs and fall back to safe
  phase defaults.
