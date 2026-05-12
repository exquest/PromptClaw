# PRD: CypherClaw Songwriter and EMSD Completion

## Overview

CypherClaw now has the first end-to-end songwriting and Electronic Music
Production and Sound Design (EMSD) spine:

- score-tree composition modules exist
- tracker compilation and runtime scheduling exist
- motif, harmonic, rhythm, transition, arrangement, and mix metadata survive
  into playback
- EMSD helper modules exist for sound palette, sampling, mixing, DSP,
  procedural arc, performance shaping, and artistic identity
- curriculum course directories exist under `my-claw/curriculum/EMSD-*`

That is not yet enough for CypherClaw to be a reliable autonomous songwriter
and electronic musician. The current system can produce longer forms, but many
modules are still thin: they expose metadata and first-pass behaviors, not a
fully verified composition practice. This PRD defines the remaining work needed
to complete the songwriter and EMSD layers as a cohesive production system.

The target is not a generic song bot. The target is a durable house musician
that composes complete pieces before playback, performs them with real
arrangement and sound-design intent, listens back, revises future work, and
accumulates a recognizable repertoire.

**Depends on:**

- `docs/cypherclaw-score-tree-composition-spec.md`
- `docs/cypherclaw-musicianship-roadmap.md`
- `docs/cypherclaw-emsd-roadmap.md`
- current tracker runtime, sampler, self-listener, and master-bus fixes

**Key files and modules:**

- `my-claw/tools/duet_composer.py`
- `my-claw/tools/self_listener.py`
- `my-claw/tools/face_display.py`
- `my-claw/tools/senseweave/piece_commission.py`
- `my-claw/tools/senseweave/piece_brief.py`
- `my-claw/tools/senseweave/form_grammar.py`
- `my-claw/tools/senseweave/score_tree.py`
- `my-claw/tools/senseweave/recursive_composer.py`
- `my-claw/tools/senseweave/composition_gate.py`
- `my-claw/tools/senseweave/tracker_compiler.py`
- `my-claw/tools/senseweave/music_tracker.py`
- `my-claw/tools/senseweave/music_tracker_runtime.py`
- `my-claw/tools/senseweave/harmonic_planner.py`
- `my-claw/tools/senseweave/reharmonizer.py`
- `my-claw/tools/senseweave/hook_engine.py`
- `my-claw/tools/senseweave/arrangement_engine.py`
- `my-claw/tools/senseweave/ear_engine.py`
- `my-claw/tools/senseweave/repertoire_memory.py`
- `my-claw/tools/senseweave/sound_palette_lab.py`
- `my-claw/tools/senseweave/sample_lab.py`
- `my-claw/tools/senseweave/sample_dsp_activity.py`
- `my-claw/tools/senseweave/sample_playback_engine.py`
- `my-claw/tools/senseweave/mix_engine.py`
- `my-claw/tools/senseweave/master_bus.py`
- `my-claw/tools/senseweave/dsp_scene_lab.py`
- `my-claw/tools/senseweave/theramini_duet.py`
- `my-claw/tools/senseweave/procedural_arc.py`
- `my-claw/curriculum/EMSD-*`

## Current State Analysis

### Implemented Foundation

The current live stack has the right macro-shape:

- `piece_commission.py` chooses form class, duration target, mode, ending, and
  reason tags.
- `piece_brief.py` translates world state into a concrete musical brief.
- `form_grammar.py` produces section functions and duration budgets.
- `score_tree.py` defines a canonical composition object.
- `recursive_composer.py` creates a first score tree from brief and grammar.
- `composition_gate.py` rejects the most underbuilt trees.
- `tracker_compiler.py` renders approved trees into tracker scenes.
- `music_tracker.py` now carries motif, progression, rhythm, transition,
  entry-window, arrangement-curve, and automation metadata.
- `music_tracker_runtime.py` schedules deterministic rows and publishes row
  automation.
- `master_bus.py` and `duet_composer.py` apply EMSD mix/automation to the real
  summed output.
- `sample_dsp_activity.py` and `sample_playback_engine.py` can render
  environmental sample layers.
- `repertoire_memory.py` stores titles, hook language, ear metrics, and
  score-tree summaries.

### Remaining Structural Gaps

The missing work is not one module. It is the set of deeper contracts that make
the modules musically accountable:

- score trees need stronger validation, serialization, and revision hooks
- forms need richer fractal expansion from macro form to section to phrase to
  motif to note cell
- narrative beats need direct, testable influence on section function,
  motif development, sound palette, and ending
- hooks and leitmotifs need lifecycle management across days and weeks
- harmony needs chord voicing, voice-leading, modulation, and cadence checking,
  not only root/progression metadata
- rhythm needs groove templates, swing, microtiming, polyrhythm, and
  body/room-pulse entrainment
- arrangement needs actual lane decisions, doubles, rests, register policy,
  density thinning, and mix curves that can be verified
- ear training needs audio-analysis feedback that modifies future pieces
- EMSD course scaffolds need reference content, prompts, exercises, and
  automated verification scripts
- sound design needs a verified SynthDef/palette registry, not only voice tags
- sampling needs reusable live buffers, sample banks, and transformation
  strategies tied to the score tree
- mix/master needs loudness and spectral regression tests
- Theramini collaboration needs explicit turn-taking and accompaniment policy
- GlyphWeave needs a stable cross-modal feature bus from audio and DSP
- long-running installation behavior needs marathon tests and resource budgets

## Goals

- Complete the score-tree composer so every piece is structurally whole before
  playback begins.
- Make songs feel like fractals: macro form recursively generates section
  form, phrase families, motif transformations, and note-level gestures.
- Support complete pieces from 30 seconds through 10 minutes, with longer
  forms available when narrative state earns them.
- Tie CypherClaw's narrative engine to musical decisions: section function,
  hook pressure, sound palette, dynamics, and ending.
- Turn EMSD modules into runtime-grade music production tools with tests.
- Add a generate -> perform -> listen -> critique -> revise loop.
- Store, recall, transform, and promote repertoire across days/weeks.
- Keep live safety: no silence regressions, no harsh top-register failures, no
  runaway sample/grain CPU load, no startup path that leaves the master bus dead.

## Non-Goals

- Do not replace the tracker runtime. The tracker remains the performance
  surface.
- Do not rebuild SuperCollider or the full audio stack from scratch.
- Do not introduce external provider secrets or hardcoded agent commands.
- Do not require human listening as the only verification path. Listening is
  useful, but acceptance must use structural metadata and audio analysis.
- Do not make all pieces long. Micro and short-form pieces remain valid when
  complete.

## Product Requirements

| ID | Description | Priority | Tier | Acceptance Criteria |
|---|---|---|---|---|
| SWE-001 | Strengthen `ScoreTree` persistence and authority so complete pieces can be serialized, resumed, compared, and stored before playback. | MUST | T1 | - `ScoreTree` round-trips through JSON without losing commission, brief, form, motif, section, harmonic, arrangement, and narrative fields<br/>- `/tmp/current_score_tree.json` or configured state path is written when a live piece starts<br/>- tests verify restart-safe load of active and queued score trees |
| SWE-002 | Extend `composition_gate.py` from a shallow structural check into a full song-quality gate. | MUST | T1 | - gate rejects missing recurrence, missing transformation, missing ending, flat arrangement, unbalanced duration, no narrative payoff, and drone-like long sections<br/>- gate accepts intentionally short complete `micro` pieces<br/>- gate report exposes numeric metrics for duration fit, recurrence, transformation, arrangement contrast, energy curve, and motif clarity |
| SWE-003 | Implement a fractal form expansion layer from macro piece shape to section functions, phrase families, motif transforms, and note cells. | MUST | T1 | - each `song`, `extended`, and `suite` tree includes nested phrase-family metadata, not just section names<br/>- section bodies derive from reusable seed material through transformation operations<br/>- tests verify macro/section/phrase/motif relationships and prevent literal looping across long sections |
| SWE-004 | Add a richer song-form library and deformation system for recognizable but varied forms. | MUST | T1 | - form grammar includes verse/chorus-like, AABA-like, build/drop, ambient arc, rondo/return, bridge, afterglow, and through-composed families expressed as section functions<br/>- form selection avoids recent-form fatigue from repertoire memory<br/>- tests verify valid form complexity for `micro`, `song`, `extended`, and `suite` classes |
| SWE-005 | Make narrative engine state a first-class musical authoring input. | MUST | T1 | - `PieceBrief` includes concrete opening, turn, payoff, and residue beats derived from world/narrative state<br/>- narrative beats map to section functions, hook pressure, motif development, sound palette, and ending family<br/>- tests verify stable degradation when narrative fields are absent and stronger specificity when present |
| SWE-006 | Implement hook and leitmotif lifecycle management across one piece and across repertoire. | MUST | T1 | - hooks have class, contour, rhythm, anchor degrees, answer degrees, text hook, and timbral tags<br/>- motifs move through statement, variation, contrast, recall, answer, liquidation, and residue states<br/>- repertoire can recall a motif shape without exact self-copying<br/>- tests verify motif transformation and answer behavior |
| SWE-007 | Expand harmonic planning into chord voicing, guide-tone voice-leading, cadence verification, and modulation planning. | MUST | T1 | - harmonic planner produces chord symbols or chord-degree sets per section<br/>- bass/counter/color/melody lanes receive voice-leading metadata<br/>- cadence types are detectable in score-tree and tracker output<br/>- tests verify no illegal leaps beyond configured limits, cadence target resolution, and modulation continuity |
| SWE-008 | Add rhythm and groove craft beyond duration cells. | MUST | T1 | - groove engine supports swing, shuffle, push/pull, microtiming, polyrhythm, polymeter, and body/room-pulse entrainment inputs<br/>- tracker/runtime can carry groove metadata without breaking deterministic scheduling<br/>- tests verify IOI ratios, swing offsets, phrase breath points, and section-specific groove identity |
| SWE-009 | Upgrade arrangement/orchestration from static roles to time-based decisions. | MUST | T1 | - arrangement plan defines lane entries/exits, doubles, dropouts, foreground/background, register bands, density gates, and automation curves<br/>- optional support events can thin without dropping primary melody/bass continuity<br/>- tests verify staged ensemble growth, sparse/medium/full variants, register safety, and non-flat automation |
| SWE-010 | Complete row-level performance automation across tracker, master bus, sampler, and face state. | MUST | T1 | - row automation is exposed in tracker state and consumed by master bus updates<br/>- sampler scene profiles align with tracker scene/row buckets<br/>- composer/face state includes current section curve and active automation values<br/>- tests verify state contract and that scene starts are not the only automation update |
| SWE-011 | Build an ear-training feedback loop that analyzes generated audio and changes future composition decisions. | MUST | T1 | - `ear_engine.py` computes pitch/interval, onset density, spectral centroid, flatness, roughness, cadence strength, hook clarity, and repetition/development metrics from tracker output or captured audio<br/>- feedback writes structured scores into learner and repertoire memory<br/>- next-piece commission can use these metrics to correct static, harsh, muddy, or underdeveloped music<br/>- tests use synthetic audio and tracker events |
| SWE-012 | Implement self-critique and revision passes before performance when practical. | SHOULD | T2 | - offline or fast preview render can be analyzed before playback for new pieces<br/>- composition gate can request one bounded rewrite pass for failed metrics<br/>- tests verify rewrite improves at least one target metric without changing piece identity |
| SWE-013 | Turn EMSD course scaffolds into executable curriculum units. | MUST | T1 | - each EMSD course directory has meaningful README, reference docs, prompts, exercise specs, and `COMPLETION.md` criteria<br/>- core courses include at least one automated exercise verifier<br/>- tests verify directory completeness and exercise metadata validity |
| SWE-014 | Build a verified sound palette and SynthDef registry. | MUST | T1 | - palette covers subtractive, additive, FM, wavetable/waveshaping, physical-model, and granular methods<br/>- each voice has timbral tags, safe role mappings, register range, macro controls, and spectral expectations<br/>- tests verify registry completeness, safe fallbacks, and no known leak-prone voice is used live without quarantine |
| SWE-015 | Expand environmental sampling into a compositional source layer. | MUST | T1 | - room/Perform-VE condenser, contact mic, Theramini input, and self bus can become sample banks with freshness and fallback rules<br/>- sample plans can slice, stretch, freeze, grain, reverse, and pitch-window material according to section function<br/>- tracker or score tree can request sample gestures as arrangement voices<br/>- tests verify source fallback, trigger keys, render paths, and bounded event density |
| SWE-016 | Add live-buffer and sample-bank abstractions for SenseWeave inputs. | SHOULD | T2 | - stable buffers expose source name, capture path, freshness, RMS, spectral profile, and transform history<br/>- sample banks can retain selected clips on archive storage with metadata<br/>- tests verify buffer refresh and archive path selection |
| SWE-017 | Complete mix and mastering verification. | MUST | T1 | - mix engine defines role frequency lanes, stereo width, reverb sends, target LUFS, peak ceiling, and Theramini ducking<br/>- master bus and per-note render shaping are tested against clipping, silence, harshness, and masking proxies<br/>- tests verify output loudness targets on synthetic renders or deterministic proxies |
| SWE-018 | Add creative DSP and cross-modal feature publication. | MUST | T1 | - DSP scene lab supports spectral freeze, smear, morph, convolution, delay, and physical-model gestures as named blocks<br/>- `/tmp/glyph_audio_features.json` or successor state includes brightness, motion, density, texture, salience, DSP blocks, and mapping hints<br/>- tests verify feature values correlate with known synthetic inputs |
| SWE-019 | Implement Theramini collaboration as a complete musical protocol. | MUST | T1 | - Theramini listener, MIDI/CC output, and duet logic share a state contract for listening, speaking, and conversation<br/>- policy supports turn-taking, imitation, counterpoint, accompaniment, and silence request<br/>- tests verify no doubling/crowding when human gesture is active and recovery to solo mode after inactivity |
| SWE-020 | Add live performance resource governance for music quality. | MUST | T1 | - CPU, node count, sampler load, capture freshness, self-listener RMS, and master bus health influence degradation rules<br/>- degradation reduces optional voices/samples/grains before interrupting primary form<br/>- tests verify graceful fallback under simulated CPU pressure, stale capture, and dead master bus |
| SWE-021 | Add installation-aware acoustic ecology policies. | SHOULD | T2 | - day/night, occupied/away, dwell-time, presence, and room activity shape volume, density, sound source choice, and silence windows<br/>- environmental/keynote sounds can be privileged over generated material<br/>- tests verify sleep/wind-down never exceed configured density/brightness ceilings |
| SWE-022 | Build repertoire promotion, curation, and archive integration. | MUST | T1 | - completed pieces store score tree summary, ear metrics, audio render reference, source samples, hook text, motif ids, form class, and ending<br/>- strong motifs/forms can be promoted into house repertoire<br/>- archive storage uses the 10TB storage root when available<br/>- tests verify promotion rules, no exact duplicate titles/hooks when alternatives exist, and archive path resolution |
| SWE-023 | Add artistic identity and portfolio reporting. | SHOULD | T2 | - system can summarize its current musical identity from repertoire metrics, preferred forms, patches, motifs, and EMSD practice history<br/>- face/operator surfaces can show current song title, section caption, practice block, and artistic-intent line<br/>- tests verify stable identity summaries without hallucinated missing data |
| SWE-024 | Add end-to-end musical integration and marathon tests. | MUST | T1 | - tests compose, gate, compile, schedule, analyze, store, and recall at least one piece without live hardware<br/>- tests include a 5-minute proxy for the 30-minute dramatic arc and a multi-piece queue run<br/>- tests assert no silent output, no single-note drone sections, non-flat automation, and valid repertoire storage |
| SWE-025 | Provide operator diagnostics and SDP rollout controls. | SHOULD | T2 | - new health/status output identifies current score tree, section function, arrangement curve, ear metrics, sample source, master bus, and self-listener state<br/>- feature flags allow enabling curriculum/exercise, preview-render, self-critique, and long-form suite behavior independently<br/>- docs include safe rollout order and rollback files |

## Dependency Map

```text
SWE-001 -> SWE-002 -> SWE-003 -> SWE-004
SWE-005 -> SWE-003, SWE-006, SWE-018
SWE-006 -> SWE-022, SWE-023
SWE-007 -> SWE-002, SWE-003, SWE-011
SWE-008 -> SWE-003, SWE-009, SWE-011
SWE-009 -> SWE-010, SWE-017, SWE-020
SWE-010 -> SWE-017, SWE-024
SWE-011 -> SWE-012, SWE-022, SWE-024
SWE-013 -> SWE-014, SWE-015, SWE-017, SWE-018
SWE-014 -> SWE-017, SWE-020
SWE-015 -> SWE-016, SWE-018, SWE-024
SWE-016 -> SWE-022
SWE-017 -> SWE-020, SWE-024
SWE-018 -> SWE-023, SWE-024
SWE-019 -> SWE-020, SWE-024
SWE-020 -> SWE-021, SWE-024
SWE-021 -> SWE-024
SWE-022 -> SWE-023, SWE-024
SWE-024 -> SWE-025
```

## Suggested Implementation Phases

### Phase 1: Composition Authority and Gate

Focus requirements:

- SWE-001
- SWE-002
- SWE-003
- SWE-004
- SWE-005

Goal:

- every piece has a restart-safe score tree, a real fractal structure, and a
  stronger quality gate before playback.

### Phase 2: Songwriter Craft

Focus requirements:

- SWE-006
- SWE-007
- SWE-008
- SWE-009
- SWE-010

Goal:

- pieces have hooks, harmonic voice-leading, groove identity, arrangement
  motion, and runtime automation that sound like authored songs rather than
  decorated loops.

### Phase 3: Ear and Revision Loop

Focus requirements:

- SWE-011
- SWE-012
- SWE-022

Goal:

- CypherClaw can hear what it made, score it, store it, and improve the next
  piece instead of only generating novelty.

### Phase 4: EMSD Production Spine

Focus requirements:

- SWE-013
- SWE-014
- SWE-015
- SWE-016
- SWE-017
- SWE-018

Goal:

- sound design, sampling, mixing, DSP, and course exercises become verified
  runtime capabilities.

### Phase 5: Collaboration, Installation, and Capstone

Focus requirements:

- SWE-019
- SWE-020
- SWE-021
- SWE-023
- SWE-024
- SWE-025

Goal:

- the system survives live operation, collaborates with Theramini/human
  gestures, behaves appropriately in the home, and can prove multi-piece
  musical growth through marathon tests.

## Runtime State Contracts

The implementation must keep these state surfaces coherent:

- `/tmp/composer_state.json`
  - song title, section, arc phase, practice block, caption, EMSD context,
    current score-tree reference, master-bus values
- `/tmp/tracker_runtime_state.json`
  - scene name, row, active lanes, section metadata, arrangement curve,
    interpolated automation
- `/tmp/self_listen.json`
  - RMS/peak/pitch/centroid/onset/capture backend, tracker correlation
- `/tmp/glyph_audio_features.json`
  - audio-derived cross-modal features and EMSD/GlyphWeave mapping hints
- `/tmp/sample_dsp_activity.json`
  - sample source, resolved source, transforms, scene profile, transport key
- `/tmp/sample_playback_state.json`
  - actual sample playback status and render path
- `/home/user/cypherclaw-data/state/piece_queue.json`
  - active/next/sketch score trees or references
- repertoire memory state
  - score-tree summaries, motifs, hooks, ear metrics, archive references

## Verification Strategy

Verification must be automated where possible:

- structural tests for score-tree validity and form richness
- tracker tests for section metadata, motif recall, rhythm identity,
  arrangement curves, and event density
- harmonic tests for chord/scale validity, cadence resolution, and voice-leading
- rhythm tests for swing, IOI ratios, phrase breath, and polyrhythm alignment
- audio-analysis tests for pitch, onset, centroid, flatness, loudness, and
  clipping proxies
- sampler tests for source fallback, freshness, transform selection, and render
  outputs
- long-run tests for multi-piece queue, no silence, no drone, bounded CPU, and
  state-file coherence
- curriculum tests for course directory completeness and exercise verifier
  presence

## Rollout Notes

- Keep feature flags for high-risk behavior:
  - preview render and rewrite
  - long-form suite generation
  - live sample transforms
  - Theramini autonomous speaking
  - DSP-heavy effects
- Deploy composition/gate changes before deeper DSP changes.
- Preserve current live safety fallbacks:
  - master bus reseed on composer restart
  - self-listener JACK backend with fallback
  - grain voice quarantine unless leak is verified fixed
  - low-density optional-event thinning
  - top-register fold-down and shaping
- For each live deploy, back up the touched files on CypherClaw before copying
  and restart through `scripts/restart_composer.sh`.

## Success Criteria

This PRD is complete when:

- CypherClaw can generate and perform complete `micro`, `song`, `extended`, and
  `suite` pieces without falling into single-note drones or flat loops.
- Most pieces have identifiable motif/hook identity, section contrast, and a
  deliberate ending.
- Long sections develop recursively through phrase families, harmonic motion,
  rhythm changes, arrangement curves, and density changes.
- Narrative state changes the music in inspectable ways.
- EMSD sound palette, sampling, mix, and DSP choices are verified by tests, not
  only by tags.
- Ear analysis affects future commissions, arrangement choices, and repertoire
  promotion.
- Repertoire memory can recall and transform prior motifs/forms without exact
  cloning.
- Theramini collaboration has explicit listen/speak/conversation behavior.
- A multi-piece marathon test can compose, perform, analyze, store, and recall
  pieces with no silent runtime and bounded resource use.
