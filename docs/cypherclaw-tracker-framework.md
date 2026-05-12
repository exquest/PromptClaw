# CypherClaw Tracker Framework

## Purpose

CypherClaw's current music engine generates notes directly inside
`my-claw/tools/duet_composer.py` and sends OSC to `scsynth` in real time.
That is expressive, but it leaves timing, density, and continuity spread
across many loops and threads.

A tracker layer gives CypherClaw a framework to work within:

- ideas are generated freely
- scenes are quantized into rows and lanes
- a scheduler emits only bounded, validated events
- sensors modulate tracker state instead of firing arbitrary notes

The local tracker path now lives in:

- [my-claw/tools/senseweave/music_tracker.py](/Users/anthony/Programming/PromptClaw/my-claw/tools/senseweave/music_tracker.py)
- [my-claw/tools/senseweave/music_tracker_runtime.py](/Users/anthony/Programming/PromptClaw/my-claw/tools/senseweave/music_tracker_runtime.py)

`duet_composer.py` now uses this scheduler for solo mode by default.
Set `CYPHERCLAW_TRACKER_SOLO=0` to force the legacy solo engine.

## Placement In The Chain

The tracker should sit between phrase generation and OSC dispatch:

```text
sensors / mood / inner-life / Theramini
    -> MelodicMind + generative_scores + orchestral helpers
    -> tracker scene planner
    -> tracker row scheduler
    -> OSC note/control events
    -> scsynth
```

This preserves the current musical intelligence while giving the runtime a
deterministic transport and a hard constraint layer.

## Mapping To The Current Composer

The existing solo form already has a natural tracker shape:

| Current movement | Tracker scene | Main lanes | Constraint goal |
|---|---|---|---|
| Emergence | `Emergence` | `foundation`, `melody` | Max 2 voices, wide headroom |
| Theme | `Theme` | `foundation`, `melody`, `texture` | Max 3 voices, stable pulse |
| Development | `Development` | `foundation`, `melody`, `counter`, `texture` | Max 5 voices, brightest density |
| Recap | `Recap` | `foundation`, `melody`, `counter`, `texture` | Max 3 voices, reduced pressure |
| Resolution | `Resolution` | `melody`, `texture` | Max 2 voices, sparse close |

The tracker scaffold encodes this as a five-scene form with per-scene
polyphony limits and default automation lanes such as `density`,
`master_amp`, and `reverb_send`.

## What The Tracker Owns

The tracker should become the owner of:

- row timing
- lane membership
- note start/length quantization
- scene-level automation
- max polyphony and density limits
- deterministic replay of a scene that produced a problem

The generator should keep owning:

- phrase invention
- harmonic suggestions
- movement-to-movement narrative choice
- sensor interpretation at the semantic level

## Keyboard Grimoire Harmonic Layer

The Keyboard Grimoire material changes the scope of the harmonic plan.
CypherClaw should not think only in terms of `root key` or `major/minor`.
It needs a richer harmonic state that can carry:

- tonic
- scale or mode family
- chord vocabulary
- voicing profile
- modulation intent

The source material is broad enough to justify treating harmony as a first-class
planner layer. The screenshots show coverage for:

- diatonic and minor systems:
  - major
  - melodic minor
  - harmonic minor
  - Hungarian minor / major
  - Neapolitan minor
  - Persian / enigmatic variants
- pentatonic and folk-like collections:
  - minor pentatonic / blues
  - kumoi
  - hirajoshi
- symmetrical and synthetic collections:
  - whole tone
  - augmented
  - diminished
  - eight-tone Spanish
  - bebop major / dominant / dorian / locrian variants
- chordal color systems:
  - sus/add6/7/9/11/13
  - altered dominant families
  - polychords
  - inversion and arpeggio treatments

That means the next tracker plan should evolve from:

```text
key root -> score -> tracker
```

to:

```text
tonic + mode family + chord-color grammar + voicing profile
    -> score shaping
    -> scene-level harmonic plan
    -> tracker lanes and automation
```

In practice, CypherClaw should hold a harmonic state like:

- `tonic`: `C`, `D`, `Bb`
- `mode_family`: `major`, `melodic_minor`, `harmonic_minor`, `dorian`,
  `mixolydian`, `whole_tone`, `diminished`, `hirajoshi`, `kumoi`, `bebop_dominant`
- `chord_palette`: `triadic`, `sus`, `extended`, `altered`, `polychord`
- `voicing_profile`: `open`, `clustered`, `quartal`, `spread_low`, `glass_high`
- `modulation_intent`: `static`, `borrowed_color`, `pivot`, `lift`, `drift`

This is the correct place to make the music more varied and less trapped in
bright major-key loops.

## Keyboard Grimoire Control Surface

The grimoire should be wired as a real control surface, not just a display idea.

The keyboard path should eventually do four things:

- notes and played pitch-sets suggest tonic and mode family
- chord shapes suggest chord palette and voicing profile
- pedal gestures suggest tension, pedal point, or modulation
- repeated keyboard behavior teaches CypherClaw which harmonic colors belong to
  a given person, time of day, or mode of attention

Current live reality is much thinner:

- `midi_keyboard_listener.py` only writes note names and frequencies
- tracker solo only snaps to the nearest major-key root if the keyboard is active
- `pedals_to_key.py` exists, but is not in the live composer path

So the next harmonic implementation should add a canonical grimoire state, for
example `/tmp/keyboard_grimoire_state.json`, containing:

- tonic
- mode family
- chord quality
- tension value
- modulation suggestion
- voicing profile
- freshness / source confidence

The tracker should then use that state to bias:

- scene key or mode
- allowable chord progressions
- lane voicing and register
- modulation points between `Theme`, `Development`, `Recap`, and `Resolution`

## Sensor Routes

Instead of letting sensors directly perturb note emission, route them into
tracker controls:

| Source | Tracker target | Effect |
|---|---|---|
| `organism_state.energy` | `density` | More or fewer active rows |
| `organism_state.valence` | `tint` / lane choice | Brighter or darker scene color |
| `room_presence.motion` | accent/fill lane | Short ornament window, not full scene rewrite |
| `theramini_state` | transpose / duet-scene override | Quantized response inside the current row grid |
| `keyboard_grimoire_state` | tonic / mode / chord color / modulation | Live harmonic steering instead of major-root snapping |
| `self_listener` click-risk or harshness | `master_amp`, `density`, voice cap | Automatic de-intensification when output gets brittle |
| `garden_state.music_key` / outdoor brightness | key palette / scene selection | Bias the next scene, not the current row clock |

## Concrete Integration Plan

1. Replace direct movement loops with scene planning.
   This now exists for solo mode: `duet_composer.py` builds a tracker song from
   the current mood/key context and hands timing to `schedule_song()`.

2. Keep expanding scene coverage.
   The current integration uses mood-driven score material projected onto the
   five-scene form. Sparse mood scores are now enriched into tracker-ready
   foundation / counter / texture lanes before projection, and scene planning
   now applies role floors so `Theme`, `Development`, and `Recap` keep a quiet
   foundation lane even when the source score is nearly sleeping. The next
   improvement is to let the richer character/movement generators fill tracker
   lanes directly instead of only the score layer. Harmonic planning should be
   expanded at the same time so the tracker can carry mode families and chord
   palettes, not just a root-note key.

3. Centralize automation.
   Master chain changes, density, reverb-send drift, and scene transitions
   should move out of scattered note loops and into scene automation lanes.

4. Log tracker provenance.
   Each emitted event should carry scene name, row number, lane name, and
   source phrase metadata. When a click is detected, the system can then say
   exactly which scene and row were active.

5. Derive lane identity from the live cast.
   The tracker now accepts role hints from the active CypherClaw character
   cast, so melody / foundation / texture / counter lanes can inherit the
   cast's chosen voices and character IDs instead of defaulting to generic
   tracker voices.

6. Add a harmonic planner between mood and scene projection.
   The next live music pass should introduce a harmonic planner that consumes
   mood, cadence, keyboard grimoire state, and fresh context files, then emits:
   tonic, mode family, progression family, chord palette, and scene modulation
   hints before `build_korsakov_tracker_song()` runs.

## Why This Helps Audio Stability

The audio investigation exposed two structural problems:

- multiple runtime owners can create discontinuities
- free-form event logic is hard to correlate with audible faults

The tracker helps with both:

- one scheduler becomes the event owner
- every event is quantized and attributable
- scene constraints cap voice buildup before scsynth gets stressed
- self-listener feedback can reduce density without killing the piece

## Current Live Audit Context

As of April 12, 2026, the live box is stable after:

- removing stray SDL audio streams from display processes
- eliminating duplicate `composer_supervisor.sh` instances with a lock
- stopping per-song master-chain recreation in the live composer

The remaining non-root-cause risks are:

- avoidable CPU pressure from `ollama` and display processes
- click-detector false positives on short capture windows

The scheduler path is now implemented locally and emits runtime state to
`/tmp/tracker_runtime_state.json`, which the self-listener can attach to click
events for correlation.
