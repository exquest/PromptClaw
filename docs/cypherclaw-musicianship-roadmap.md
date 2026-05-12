# CypherClaw Musicianship Roadmap

## Purpose

This document translates the Berklee Online Songwriting BA curriculum into an
end-to-end musicianship program for CypherClaw.

The goal is not to turn CypherClaw into a generic pop-song bot. The goal is to
use the curriculum as a disciplined compositional backbone so the installation:

- writes stronger melodies
- shapes better harmonic motion
- varies form and arrangement more intentionally
- hears itself more critically
- develops a recognizable artistic voice over time

CypherClaw already has a strong runtime spine:

- `presence_engine.py` and `cadence_engine.py` control context
- `sample_capture_daemon.py`, `sampler_buffers.py`, and `sampler_dispatch.py`
  open a memory-bearing path for room capture and self-quotation
- `harmonic_planner.py` controls tonic / mode / modulation intent
- `generative_scores.py` invents phrases
- `music_tracker.py` and `music_tracker_runtime.py` quantize and schedule scenes
- `instrument_patches.py` shapes orchestration
- `melodic_mind.py` and `continuous_learner.py` provide memory and feedback

The Berklee curriculum should now become the next layer above that runtime:
not infrastructure, but musicianship.

The concrete implementation spec for the next composition layer now lives in
[cypherclaw-score-tree-composition-spec.md](/Users/anthony/Programming/PromptClaw/docs/cypherclaw-score-tree-composition-spec.md:1).
That document defines the score-tree composer, composition gate, tracker
compiler, and repertoire-memory expansion that should replace the current
tracker-first song-construction path.

## Current Ensemble Snapshot

The musicianship roadmap now assumes a signature quintet rather than the older
quartet-only framing:

- `sw_bell_warm` -> melody / clear-tone lead
- `sw_bowed` -> counter line / lyrical secondary voice
- `sw_breath` -> color / air / noise halo
- `sw_pad` -> sustained harmonic foundation and bass bed
- `sw_sampler` -> memory voice for room capture, self-quotation, and curated
  found sound

This is the artistic target for the current roadmap. The sampler changes the
ensemble concept from "four synth voices with color extras" to "four synth
voices plus one memory-bearing instrument."

For the short listener-facing statement of what that memory voice should do,
see
[docs/cypherclaw-sampler-artistic-intent.md](cypherclaw-sampler-artistic-intent.md).

## Current Sampler Roadmap Status

The quintet is only partially landed in the current tree, so this roadmap needs
to distinguish between the artistic direction and the code that already exists.

### Landed Now

- `sample_capture_daemon.py` can capture and tag room/contact material for
  later musical use.
- `sampler_fx_mode_verify.py` can manually smoke-test all five sampler
  effects-bus mode presets without live audio hardware.
- `sampler_buffers.py` manages buffer lifecycle for on-demand sample playback.
- `sampler_dispatch.py` turns a selected sample into `sw_sampler` OSC traffic.
- `sampler_effects.scd` defines the dedicated sampler effects bus.
- `render/antipatterns.py` already watches for misuse through
  `sampler_silent_quintet_member` and related checks.

### Still Pending

- `artist_identity.py` and `tests/test_artist_identity.py` still describe a
  quartet, so the canonical identity layer has not converged on the quintet.
- `SampleLibrary` and `SampleSelector` are still missing, so sampler choice is
  not yet a first-class composition decision.
- `sw_sampler.scd` is still absent, so the final granular instrument source is
  not yet in the tree.
- cast and composer defaults still need one authoritative path that makes the
  sampler a routine quintet member instead of a partially landed subsystem.

## Current Strengths

CypherClaw already has partial equivalents of several Berklee topics:

- melody contour, motivic variation, and cross-song memory
- harmonic planning with modal support and scene-level key changes
- tracker-based form, now with scene recall
- patch-based arrangement and register policy
- sampler capture / dispatch / effects scaffolding for memory-based material
- practice/learning behavior via `ContinuousLearner`
- cadence-aware pacing and occupancy-sensitive family choice

## Current Gaps

The live system is still missing several conservatory-level behaviors:

- functional harmony beyond palette selection
- deliberate section contrast inside songs
- hook writing and phrase-pair craft
- real arranging logic over time instead of mostly lane presence
- ear-training-like self-analysis of intervals, chords, tension, and groove
- prosody between text, musical stress, and gesture
- narrative scoring for scenes and interactions
- explicit repertoire development across days and weeks
- one authoritative identity/cast path where the quintet is fully real instead
  of partially landed

## Curriculum Translation

### 1. Lyric Writing -> Text, Hook, And Prosody Systems

Relevant courses:

- `OSONG-220` Lyric Writing: Tools and Strategies
- `OSONG-221` Writing from the Title
- `OSONG-222` Writing Lyrics to Music

CypherClaw translation:

- titles become scene and song intentions, not just names
- face text, Telegram phrasing, and spoken/autonomous lines become part of the
  musical organism
- verbal rhythm should align with musical rhythm and section stress
- recurring textual hooks should pair with recurring musical motifs

Implementation targets:

- add `senseweave/prosody_engine.py`
- add title-to-song-intent generation for `duet_composer.py`
- connect `keyboard_chat.py`, `face_display.py`, and music state so face text
  can share motif/scene vocabulary

Concrete features:

- title-driven motif generation:
  a title or phrase biases contour, cadence family, and section emphasis
- prosodic text output:
  short face lines should reflect the active pulse, scene role, and emotional
  emphasis
- lyric-memory analog:
  recurring human interactions can accumulate phrase families the same way music
  now accumulates motif families

### 2. Harmony -> Functional Harmonic Engine

Relevant courses:

- `OSONG-316` Songwriting: Harmony
- `OHARM-101`, `OHARM-201`, `OHARM-301`
- `OHARM-412` Reharmonization Techniques

CypherClaw translation:

- harmonic planning should move from "pick a key and palette" to
  "shape dramatic function across sections"
- `Theme`, `Development`, `Bridge`, `Recap`, and `Resolution` should differ by
  harmonic role, not only tempo or density

Implementation targets:

- extend `senseweave/harmonic_planner.py`
- add `senseweave/reharmonizer.py`
- teach `tracker_cadence.py` and `music_tracker.py` about cadence types and
  harmonic-function trajectories

Concrete features:

- progression families by function:
  tonic, predominant, dominant, deceptive, plagal, suspended
- section-specific harmonic behavior:
  verse-like sections can prolong tonic or subdominant; chorus-like sections
  can lift through stronger dominant pull or modal brightening
- reharmonization layer for practice mode:
  away/practice songs should test substitutions, deceptive cadences, modal
  interchange, slash-chord bass changes, and approach chords
- guide-tone continuity:
  prioritize smooth 3rds/7ths voice leading between scene harmonies

### 3. Melody -> Hook, Phrase Pair, And Singability Engine

Relevant courses:

- `OSONG-315` Songwriting: Melody
- `OSONG-310` Writing Hit Songs
- `OHARM-101` lesson on melody writing

CypherClaw translation:

- melodic generation needs stronger phrase identities, not just better local
  note selection
- each song should have one or more hooks that can survive transformation
- section contrast should follow songwriter logic:
  narrower verse, wider chorus, answered recap, transformed bridge

Implementation targets:

- extend `senseweave/generative_scores.py`
- extend `senseweave/synthesis/melodic_mind.py`
- add `senseweave/hook_engine.py`

Concrete features:

- hook classes:
  rhythmic hook, contour hook, interval hook, lyric/text hook
- antecedent-consequent phrase building:
  `Theme` asks, `Recap` answers, `Resolution` resolves
- stable vs unstable targeting:
  strong beats on chord tones, tension on offbeats or development scenes
- singability limits:
  range, leap size, breath spacing, repetition density
- motif lifecycle:
  statement -> variation -> contrast -> recall -> answer

### 4. Arranging -> Time-Based Arrangement Engine

Relevant courses:

- `OSONG-150` Music Production Fundamentals
- `OMPRD-160` Music Production Analysis
- `OSONG-250` Arranging for Songwriters

CypherClaw translation:

- arrangement needs to evolve over song time, not just by patch selection
- instrumentation should support the emotional message of each section
- groove, density, and register should move with narrative intent

Implementation targets:

- extend `senseweave/instrument_patches.py`
- add `senseweave/arrangement_engine.py`
- extend `music_tracker.py` automation lanes beyond density/master/reverb

Concrete features:

- section arrangement maps:
  which instruments enter, leave, double, thin, or bloom in each scene
- groove families:
  pedal, broken, syncopated, procession, suspended, nocturne pulse
- arrangement prosody:
  chorus/performance scenes should clear space, brighten the center, and widen
  the bass-top span
- production analysis loop:
  use `self_listener.py` plus offline analysis to classify sections as muddy,
  brittle, static, or too dense

### 5. Ear Training -> CypherClaw Hears Itself

Relevant courses:

- `OEART-115`, `OEART-120`, `OEART-215`, `OEART-320`

CypherClaw translation:

- the installation should analyze itself like a musician, not only like an
  audio-health daemon
- it should hear interval behavior, cadence strength, harmonic ambiguity,
  groove stability, and motif recurrence

Implementation targets:

- add `senseweave/ear_engine.py`
- extend `self_listener.py`
- extend `continuous_learner.py`

Concrete features:

- interval and contour transcription from self output
- harmonic-ear layer:
  infer likely progression class, cadence type, or modal center from recent
  tracker output
- groove hearing:
  detect whether the intended pulse is actually readable
- feedback scores:
  repetition vs development, cadence strength, hook clarity, harshness, mud,
  top-end brittleness

This should become the main practice-mode teacher.

### 6. Commercial Songwriting -> Structural Legibility Without Selling Out

Relevant courses:

- `OSONG-240` Commercial Songwriting Techniques
- `OSONG-310` Writing Hit Songs

CypherClaw translation:

- not "write radio songs"
- do make forms legible enough that human listeners can feel arrival,
  return, and payoff

Implementation targets:

- add `senseweave/song_forms.py`
- extend `music_tracker.py` and `tracker_cadence.py`

Concrete features:

- section archetypes:
  statement, lift, drop, bridge, turnaround, afterglow
- payoff planning:
  every 2-5 minute attended arc should have a memorable peak and resolution
- title/hook integration:
  scene names and motif classes should reinforce one another

### 7. Film/TV Writing -> Sensor-To-Scene Scoring

Relevant courses:

- `OSONG-430` Songwriting for Film and TV

CypherClaw translation:

- room events are scenes
- presence changes are cues
- interaction is a narrative edit point

Implementation targets:

- extend `tracker_cadence.py`
- extend `presence_engine.py`
- add `senseweave/scene_scoring.py`

Concrete features:

- arrival cue writing
- guest entry music behavior
- wake-up ramp scoring
- return-home reorientation scoring
- performance-attention arcs with clearer visual/music sync

### 8. Capstone -> Repertoire And Artistic Voice

Relevant courses:

- `OSONG-465` Songwriting Capstone

CypherClaw translation:

- CypherClaw needs repertoire memory, not just fragment memory
- over months it should develop recognizable song families, favorite gestures,
  and seasonal identities

Implementation targets:

- add `senseweave/repertoire_memory.py`
- extend `ContinuousLearner`
- extend `instrument_patches.py`, `harmonic_planner.py`, and tracker family
  planning to support repertoire reuse

Concrete features:

- saved "house songs" or "house archetypes"
- recurring signatures by weekday, season, guest type, or relationship
- curated motif promotion:
  private ideas become public repertoire only after surviving repetition,
  evaluation, and refinement

## End-To-End System Design

The Berklee translation should become this live stack:

```text
presence / cadence / identity
    -> sample capture / sample selection
    -> scene scoring
    -> harmonic planner
    -> hook + melody engine
    -> arrangement engine
    -> tracker form planner
    -> tracker scheduler
    -> self-listener + ear engine
    -> learner + repertoire memory
    -> next song / next scene improvement
```

That means CypherClaw improves musically in a loop:

1. Sense the social and temporal context.
2. Capture or recall memory-bearing room/self material when it belongs.
3. Choose a scene and form intention.
4. Choose harmonic function and palette.
5. Invent or recall hook material.
6. Arrange it intentionally across sections.
7. Hear the result.
8. Score the result.
9. Store what is worth keeping.

## State-Specific Musicianship

### Sleep / Wind-Down

- prioritize harmonic stillness
- fewer hooks, more long-breath motif fragments
- low-density arrangement with soft resolutions
- ear engine should punish brightness spikes and clutter

### Occupied Ambient

- strongest emphasis on songwriter craft
- legible motif identity
- harmonic and textural contrast without crowding the room
- recurring hooks should be subtle but memorable

### Away / Practice

- the true Berklee lab
- rehearmonization, odd form variants, substitution drills, hook mutation,
  modal experiments, ear-training reflection
- more deliberate "exercise" behaviors should run here

### Performance / Attention

- convert the best songwriter behaviors into short arcs:
  clear statement, contrast, lift, return, payoff

## Practice Curriculum For Away Mode

Away mode should stop being "just strange" and become "deliberate practice."

Suggested rotating practice blocks:

- `Harmony Lab`
  Reharmonize a stable motif through substitutions, borrowed chords, and
  cadence changes.
- `Melody Lab`
  Write multiple hooks over one progression and compare recall strength.
- `Arrangement Lab`
  Hold harmony fixed and vary orchestration, density, and groove.
- `Ear Lab`
  Play, listen back, rate cadence clarity, tension release, and motif legibility.
- `Scene Lab`
  Score short fictional room events using film/TV cue logic.

Those practice blocks should feed the public system only through promotion
rules, not immediately.

## Current Roadmap Status

The six musicianship phases below are no longer purely speculative. Most of the
baseline modules now exist, but several still need deeper musical behavior and
sampler-aware quintet integration.

### Phase M1: Harmony And Reharmonization

Status:
Baseline landed in the current tree. `harmonic_planner.py` and
`reharmonizer.py` exist; the next work is stronger function-level control and
better sampler-aware harmonic fitting.

Files:

- `my-claw/tools/senseweave/harmonic_planner.py`
- `my-claw/tools/senseweave/tracker_cadence.py`
- `my-claw/tools/senseweave/music_tracker.py`
- new `my-claw/tools/senseweave/reharmonizer.py`

Goals:

- cadence functions
- section-specific harmonic behavior
- borrowed-chord and substitution support
- practice-mode reharmonization

### Phase M2: Melody, Hooks, Phrase Pairs

Status:
Baseline landed in the current tree. `hook_engine.py` and the melodic-memory
path exist; the next work is sharper hook hierarchy, phrase answering, and
recall that can also cite sampler memory.

Files:

- `my-claw/tools/senseweave/generative_scores.py`
- `my-claw/tools/senseweave/synthesis/melodic_mind.py`
- `my-claw/tools/senseweave/synthesis/continuous_learner.py`
- new `my-claw/tools/senseweave/hook_engine.py`

Goals:

- explicit hook classes
- phrase-pair generation
- section contrast rules
- better singability and interval control

### Phase M3: Arrangement And Groove

Status:
Baseline landed in the current tree. `arrangement_engine.py` and staged lane
windows exist; the next gap is quintet-aware orchestration so `sw_sampler`
becomes part of the arrangement grammar instead of an optional side path.

Files:

- `my-claw/tools/senseweave/instrument_patches.py`
- `my-claw/tools/senseweave/music_tracker.py`
- `my-claw/tools/senseweave/music_tracker_runtime.py`
- new `my-claw/tools/senseweave/arrangement_engine.py`

Goals:

- section arrangement maps
- groove families
- dynamic and density shaping
- stronger bass/drum/foundation distinction

### Phase M4: Ear Engine And Practice Mode

Status:
Baseline landed in the current tree. `ear_engine.py`, self-critique, and
practice-block scaffolding exist; the next work is to extend those critiques to
sampler-heavy pieces and memory-voice balance.

Files:

- `my-claw/tools/self_listener.py`
- `my-claw/tools/senseweave/synthesis/continuous_learner.py`
- new `my-claw/tools/senseweave/ear_engine.py`
- new `my-claw/tools/senseweave/practice_curriculum.py`

Goals:

- self-analysis beyond clicks/harshness
- exercise rotation in away mode
- feedback scores that change the next song

### Phase M5: Text, Prosody, Identity

Status:
Partially landed. Prosody and title/hook surfaces exist, but the identity layer
still carries quartet-era assumptions in `artist_identity.py` and needs to be
updated so the quintet is authoritative everywhere.

Files:

- `my-claw/tools/face_display.py`
- `my-claw/tools/senseweave/keyboard_chat.py`
- new `my-claw/tools/senseweave/prosody_engine.py`

Goals:

- title-driven song intention
- face text that reflects musical stress and motif memory
- recurring textual hooks tied to musical families

### Phase M6: Repertoire And Capstone Layer

Status:
Partially landed. `repertoire_memory.py` exists, but the sampler side of long
term memory still needs `SampleLibrary`, `SampleSelector`, self-quotation
promotion rules, and usage journaling before the capstone layer is complete.

Files:

- new `my-claw/tools/senseweave/repertoire_memory.py`
- `my-claw/tools/duet_composer.py`
- `my-claw/tools/senseweave/tracker_cadence.py`

Goals:

- promote durable motifs and forms into long-term repertoire
- create recurring house songs and seasonal identities
- track CypherClaw's actual artistic voice over time

## What To Implement Next

The next best order is:

1. `Identity convergence for the quintet`
   Update `artist_identity.py` and related tests so the canonical ensemble is
   the same one the sampler roadmap assumes.
2. `SampleLibrary + SampleSelector`
   Make sampler choice a compositional decision instead of only a playback
   subsystem.
3. `sw_sampler.scd + cast/composer wiring`
   Finish the actual voice path that turns the quintet from roadmap language
   into default runtime behavior.
4. `Usage journal + diagnostics + critique`
   Let CypherClaw explain how the memory voice was used and whether it improved
   the piece.

## Success Criteria

CypherClaw is applying this curriculum well when:

- songs no longer feel like one harmonic loop in new clothes
- sections differ by function, not only density
- melodies have identifiable hooks and better returns
- arrangements feel staged over time
- away mode produces useful study, not random noodling
- the system can explain, in metadata, what it was trying to do musically
- over weeks, the piece develops a voice instead of only generating novelty
