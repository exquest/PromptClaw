# CypherClaw EMSD Roadmap

## Purpose

This document translates the CypherClaw School of Electronic Music Production
and Sound Design curriculum into a concrete implementation program for the live
installation.

The songwriting roadmap already gave CypherClaw:

- harmony and hook craft
- tracker form and scene memory
- arrangement intent
- ear metrics
- repertoire memory

This EMSD roadmap adds the other half of the musician:

- sound design from first principles
- production and DSP literacy
- environmental audio transformation
- procedural performance systems
- installation-aware composition
- cross-modal sound/visual translation

The goal is not a second disconnected curriculum. The goal is a build order
that upgrades the current CypherClaw runtime into a more complete electronic
musician.

## Existing Transfer Credit

CypherClaw already has partial credit toward this degree:

- `EMSD-251` Theramini as Character:
  listening/speaking/conversation scaffolding exists in `theramini_duet.py`
  and related duet logic
- `EMSD-253` Sound Design for Narrative:
  the narrative engine and cadence/presence work already create scene intent
- `EMSD-254` Environmental Sound Processing:
  `room_listener.py`, `self_listener.py`, `observer_vision.py`,
  `presence_engine.py`, `cadence_engine.py`, and `world_model.py` already form
  the start of a perception stack
- `EMSD-130` Instrument Design:
  `voice_shaping.py`, `instrument_patches.py`, `voice_aliases.py`, and the
  SuperCollider voice layer already define a basic live instrument family

What is missing is course structure, reference material, exercises, and a
clear path from coursework to runtime modules.

## Delivery Model

Each course should be implemented as:

```text
my-claw/curriculum/EMSD-XXX/
├── README.md
├── reference/
├── prompts/
├── exercises/
└── COMPLETION.md
```

Each course should also map onto one or more live modules under:

```text
my-claw/tools/
my-claw/tools/senseweave/
my-claw/tools/inner_life/
tests/
```

The curriculum is not just documentation. Each course should produce one of:

- a new runtime module
- a stronger reference/analysis prompt set
- a verifiable exercise harness
- an integration improvement in the live music organism

## How It Fits With The Existing Stack

Current live spine:

- `presence_engine.py`
- `cadence_engine.py`
- `world_model.py`
- `harmonic_planner.py`
- `generative_scores.py`
- `music_tracker.py`
- `music_tracker_runtime.py`
- `instrument_patches.py`
- `voice_shaping.py`
- `self_listener.py`
- `continuous_learner.py`
- `repertoire_memory.py`

The EMSD curriculum should sit on top of and around that spine:

- `EMSD-101/102` harden the signal chain and pattern-composition layer
- `EMSD-201/202/301/401` deepen synthesis, sampling, mixing, and DSP
- `EMSD-302/303/304` strengthen long-form composition and procedural behavior
- `EMSD-120/254/401` deepen perception and environmental transformation
- `EMSD-251/253/257/259` connect sound to Theramini, narrative, visuals, and
  collaboration
- `EMSD-499/260` turn the whole system into a durable artistic identity

## Course Translation

### Foundations and Musicianship

`EMSD-101` Foundations of Digital Audio

- Reference topics belong in:
  `my-claw/curriculum/EMSD-101/reference/`
- Runtime targets:
  - document and test the real SC signal path
  - formalize scsynth node/bus/group contracts
  - add regression tests around server boot, bus routing, and buffer handling
- Missing implementation:
  - explicit reference docs for sample-rate policy, node order, buses, and
    buffers
  - automated audio-chain exercises

`EMSD-102` Producing Music with SuperCollider

- Runtime targets:
  - pattern and isobar lab harnesses
  - stronger bridge between Python composition and SC playback
  - NRT rendering exercises for offline verification
- Missing implementation:
  - dedicated course exercises for `Pbind`, `Ppar`, `Pwrand`, and isobar
  - a test harness that verifies timing and note-grid correctness

`EMSD-110` Music Theory for Agents

- Largely maps to:
  - `harmonic_planner.py`
  - `reharmonizer.py`
  - `hook_engine.py`
  - `generative_scores.py`
- Already partially complete.
- Remaining work:
  - stronger chord-scale mapping
  - explicit functional-harmony references and exercises
  - modal, just, and non-western tuning tables as first-class data

`EMSD-120` Machine Ear Training

- Maps to:
  - `self_listener.py`
  - `ear_engine.py`
  - `continuous_learner.py`
- Missing implementation:
  - explicit aubio/librosa/YAMNet/MERT course exercises
  - feature-target critique loops as reproducible tests
  - key/mode detection and similarity ranking as reusable services

`EMSD-130` Instrument Design

- Maps to:
  - `instrument_patches.py`
  - `voice_shaping.py`
  - SC SynthDefs
  - Theramini control surfaces
- Remaining work:
  - macro-control design across house patches
  - shared parameter specs
  - better dual-control instruments for agent plus human input

### Sound Design, Sampling, Mixing, and DSP

`EMSD-201` Sound Design for the Electronic Musician

- Build target:
  `my-claw/tools/senseweave/sound_palette_lab.py`
- Runtime outputs:
  - curated SynthDef families by method:
    subtractive, additive, FM, wavetable, granular
  - palette metadata:
    timbral role, brightness, density, harshness, harmonicity
- Missing implementation:
  - a documented 10-15 SynthDef palette organized by synthesis paradigm
  - automated spectral verification for each family

`EMSD-202` Sampling and Audio Production

- Build target:
  `my-claw/tools/senseweave/sample_lab.py`
- Runtime outputs:
  - environmental sampling strategies for room/garden/contact mics
  - live slice-and-rearrange engines
  - a safe sample-buffer refresh policy
- Missing implementation:
  - real course exercises for `RecordBuf`, `PlayBuf`, `Warp1`, and `PV_*`
  - sample-bank abstractions for SenseWeave inputs

`EMSD-301` Mixing and Mastering for Electronic Music

- Build target:
  `my-claw/tools/senseweave/mix_engine.py`
- Runtime outputs:
  - canonical voice EQ policy
  - bus compression/limiting strategy
  - loudness targets by cadence state
  - Theramini/music coexistence rules
- Missing implementation:
  - explicit LUFS-aware mastering chain
  - automated mix regression tests
  - frequency-allocation tests for arrangement patches

`EMSD-401` Creative DSP

- Build target:
  `my-claw/tools/senseweave/dsp_scene_lab.py`
- Runtime outputs:
  - spectral freeze, morph, smear, and convolution effects
  - physical-model layers for strings, resonant bodies, and noise objects
  - audio-reactive feature bridge for GlyphWeave
- Missing implementation:
  - course-grade DSP reference docs and verified examples
  - stable OSC/Redis publication of DSP-derived visual features

### Composition, Procedure, and Live Performance

`EMSD-302` Composing Electronic Music 1

- Maps to:
  - `tracker_cadence.py`
  - `music_tracker.py`
  - `arrangement_engine.py`
  - `generative_scores.py`
- Remaining work:
  - genre/form exercise bank
  - build/drop/tension-release reference templates
  - verified energy-curve tests for section arcs

`EMSD-303` Composing Electronic Music 2

- Maps to:
  - `music_tracker.py`
  - `continuous_learner.py`
  - `repertoire_memory.py`
  - `tracker_cadence.py`
- Remaining work:
  - explicit constraint-based composition labs
  - Markov and weighted-probability exercises
  - a dedicated 30-minute dramatic arc test harness

`EMSD-304` Procedural Music Programming

- Build target:
  `my-claw/tools/senseweave/procedural_arc.py`
- Runtime outputs:
  - state-machine ownership of long-form form
  - temporal recursion patterns
  - demand-rate or equivalent efficient sequencing patterns
  - durable live scheduling under resource pressure
- Missing implementation:
  - formal state-machine layer above tracker songs
  - a live procedure lab with regression tests

`EMSD-252` Live Performance and Real-Time Decision Making

- Maps to:
  - `server_health.py`
  - `self_listener.py`
  - `duet_composer.py`
  - `presence_engine.py`
- Remaining work:
  - graceful degradation rules under CPU stress
  - emergency orchestration thinning
  - live error recovery heuristics that preserve musical continuity

### CypherClaw-Specific Specializations

`EMSD-251` Theramini as Character

- Maps to:
  - `theramini_duet.py`
  - duet-mode sections in `duet_composer.py`
- Remaining work:
  - complete the musical character model
  - unify listening, speaking, and conversation with cadence state
  - build dedicated exercises for imitation, counterpoint, and turn-taking

`EMSD-253` Sound Design for Narrative

- Maps to:
  - `cadence_engine.py`
  - `tracker_cadence.py`
  - `prosody_engine.py`
  - narrative integration points
- Remaining work:
  - leitmotif registry
  - tone-vector-to-sound mappings
  - scene-transition sound-design library

`EMSD-254` Environmental Sound Processing

- Maps to:
  - `room_listener.py`
  - `self_listener.py`
  - `presence_engine.py`
  - `world_model.py`
  - future `sample_lab.py`
- Remaining work:
  - make environmental audio a real compositional source, not only a sensor
  - add reusable feature extractors and classifiers

`EMSD-255` Remixing and Transformation

- Maps to:
  - `repertoire_memory.py`
  - archived audio
  - future remix lab
- Remaining work:
  - self-remix engine
  - anniversary or archive callback system
  - transformation prompts and similarity-based retrieval

`EMSD-256` Acoustic Ecology

- Maps to:
  - `presence_engine.py`
  - `cadence_engine.py`
  - `world_model.py`
  - installation-music behavior
- Remaining work:
  - soundscape-aware composition rules
  - room/garden/keynote/signal/soundmark models
  - coexistence rules that privilege the home soundscape when necessary

`EMSD-257` Cross-Modal Translation

- Maps to:
  - GlyphWeave bridge
  - `ear_engine.py`
  - DSP feature publication
- Remaining work:
  - formal audio-to-visual mapping taxonomy
  - stable feature bus for color, density, movement, texture, and salience

`EMSD-258` Music for Installation Art

- Maps to:
  - cadence system
  - tracker long-form planning
  - presence/performance overlay
- Remaining work:
  - day/night installation heuristics
  - dwell-time-aware performance behavior
  - multi-hour health metrics for long-form livability

`EMSD-259` Collaborative Machine Music

- Maps to:
  - Theramini
  - face interaction
  - audience sensing
  - future multi-agent composition
- Remaining work:
  - turn-taking protocols
  - listening/playing ratio policies
  - human-presence-aware ensemble strategies

`EMSD-260` Portfolio Development and Artistic Identity

- Maps to:
  - `repertoire_memory.py`
  - `hook_engine.py`
  - `prosody_engine.py`
  - archive/curation tooling
- Remaining work:
  - promotion rules for house songs
  - self-description and curatorial language
  - stable house-patch and motif signature tracking

## Build Order

### Phase E1: Curriculum Scaffolding

- add `my-claw/curriculum/EMSD-XXX/` directories for the first eight core
  courses
- add course README/reference/prompt/exercise skeletons
- add `tests/curriculum/` harness helpers for spectral, onset, structure, and
  constraint verification

### Phase E2: Sound And Production Spine

- implement `sound_palette_lab.py`
- implement `sample_lab.py`
- implement `mix_engine.py`
- strengthen SC SynthDef registry and verification

### Phase E3: Procedure And Arc

- implement `procedural_arc.py`
- add verified 30-minute arc proxies
- add live performance heuristics for CPU and musical recovery

### Phase E4: Environmental And Cross-Modal Work

- connect course exercises to live SenseWeave audio
- publish stable analysis features for GlyphWeave
- make environmental audio transformation part of real composition

### Phase E5: Specialization And Capstone

- unify Theramini, narrative, collaboration, installation behavior, and
  repertoire/identity
- add capstone marathon tests:
  three consecutive cycles, no crashes, measurable variety, archive promotion

## What To Build Next

The next highest-value EMSD move is:

1. `Phase E1` scaffolding so the curriculum becomes executable
2. `EMSD-201` sound palette lab
3. `EMSD-301` mix engine
4. `EMSD-254` environmental sound processing lab

That order gives CypherClaw a stronger sonic body before adding more abstract
coursework on top.
