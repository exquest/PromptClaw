# CypherClaw Presence And Cadence Spec

## Status

Design spec and implementation blueprint. This document defines the intended
runtime behavior for CypherClaw's presence awareness, daily cadence, music
mapping, silence architecture, weekly modulation, and override precedence. It
does not claim the live deployment already behaves this way.

## Purpose

CypherClaw needs one coherent behavioral spine for:

- knowing whether people are home, asleep, attending, or away
- choosing a daily musical cadence that suggests BPM and density instead of
  rigidly enforcing them
- staying socially aware when people are present
- becoming stranger and more exploratory when the house is empty
- letting face and Telegram overrides steer the organism without collapsing it
  into an admin panel

This spec turns those goals into concrete state machines and implementation
targets.

## Research-Driven Decisions

The latest cadence research changes the priority stack:

- Silence is a first-class compositional tool, not an absence of behavior.
- Loudness, timbral brightness, onset density, and articulation matter more
  than nominal BPM for perceived energy.
- Daily cadence should track circadian physiology more than streaming tempo
  trends.
- Weekly cadence should be a gentle social-rhythm bias, not a rigid schedule.
- Social synchrony claims must stay modest: CypherClaw can create a shared
  physiological environment, not promise to "bond the household."
- Overnight behavior should continue fading after sleep onset, toward
  near-silence or intermittent silence, instead of holding a constant bed.

## Current Runtime Gaps

The current live runtime has the right ingredients, but the wiring is incomplete:

- `my-claw/tools/start_sensors.sh` currently starts only
  `startle_daemon.py`, `sensory_journal_daemon.py`, and `self_listener.py`.
  It does not start `room_listener.py` or `senseweave/sensor_fusion.py`.
- `my-claw/tools/senseweave/sensor_fusion.py` fuses only Theramini, room
  activity, room speech, and composer state. It does not incorporate the indoor
  observer camera, room camera presence, or outdoor/entry-camera context.
- `my-claw/tools/observer_vision.py` can mark `someone_here` from room
  brightness and clutter alone, which is too weak to trust as a canonical
  occupancy signal.
- `my-claw/tools/duet_composer.py` currently reads a thin tracker mood vector
  from `organism_state`, `room_presence`, and a few context files. The tracker
  does not yet read a canonical occupancy or cadence state.

The result is that CypherClaw has partial awareness, but not the confidence
model needed to support daily cadence decisions.

## Behavioral Principles

- Fail safe to `occupied`, not `away`.
- Treat BPM as a suggested range with variance, not a fixed value.
- Treat loudness, brightness, onset density, articulation, and pulse clarity as
  more important than BPM.
- Use event-driven waking: the house waking up matters more than the clock.
- Let `away` mode become assertive and strange.
- Wind down after `10 PM` unless explicitly overridden.
- Let private experimentation influence public music only after it survives
  repetition and selection.
- Treat performance and identity as overlays on top of cadence, not separate
  disconnected modes.
- Keep the face visitor-facing and high-level. Keep Telegram operator-facing and
  safety-oriented.
- Default to graceful silence when CypherClaw is unsure how much sound is
  appropriate.

## Runtime Layers

The intended runtime stack is:

```text
raw sensor daemons
    -> world read layer
    -> presence engine
    -> cadence engine
    -> override resolver
    -> music planner
    -> tracker scene planner
    -> tracker scheduler
    -> scsynth
```

Current file ownership should evolve toward:

- Raw sensors:
  - `my-claw/tools/observer_vision.py`
  - `my-claw/tools/room_listener.py`
  - `my-claw/tools/input_monitor.py`
  - `my-claw/tools/contact_listener.py`
  - `my-claw/tools/senseweave/porch_eye.py`
  - `my-claw/tools/theramini_midi.py`
  - `my-claw/tools/midi_keyboard_listener.py`
- World read layer:
  - `my-claw/tools/inner_life/world_model.py`
- New canonical engines:
  - `my-claw/tools/senseweave/presence_engine.py`
  - `my-claw/tools/senseweave/cadence_engine.py`
  - `my-claw/tools/senseweave/override_engine.py`
- Music planner integration:
  - `my-claw/tools/duet_composer.py`
  - `my-claw/tools/senseweave/music_tracker.py`
  - `my-claw/tools/senseweave/music_tracker_runtime.py`

## Canonical State Files

The runtime should converge on these authority files:

| File | Writer | Purpose |
|---|---|---|
| `/tmp/organism_state.json` | `sensor_fusion.py` or its replacement | Low-level fused mood and immediate sensory state |
| `/tmp/presence_state.json` | `presence_engine.py` | Canonical occupancy, confidence, attention, and identity hints |
| `/tmp/cadence_state.json` | `cadence_engine.py` | Canonical daily cadence and music suggestion state |
| `/tmp/tracker_runtime_state.json` | tracker scheduler | Active scene and row for audio correlation |
| `/tmp/active_characters.json` | composer | Active cast for face/gallery/music coherence |

`duet_composer.py` should treat `presence_state.json` and `cadence_state.json`
as higher-priority behavioral inputs than ad hoc direct sensor reads.

## Cadence Output Contract

`/tmp/cadence_state.json` should publish a full parameter field, not only a
tempo hint. A representative shape:

```json
{
  "timestamp": 1776000000.0,
  "cadence_state": "occupied_day",
  "day_phase": "late_afternoon",
  "weekly_phase": "core_weekday",
  "source": "presence+clock",
  "bpm_target": 102.0,
  "bpm_range": [88.0, 116.0],
  "loudness_db_range": [46.0, 55.0],
  "dynamic_range_db": 8.0,
  "spectral_centroid_hz": 1650.0,
  "onset_density_range": [2.0, 4.5],
  "attack_ms_range": [80.0, 500.0],
  "pulse_clarity": 0.42,
  "harmonic_change_s_range": [12.0, 45.0],
  "phrase_arc_s": 10.0,
  "silence_budget_s_per_hour": 600,
  "silence_gap_s_range": [20.0, 60.0],
  "voice_cap": 4,
  "experimentation_bias": 0.38,
  "risk_level": "medium",
  "notes": [
    "late afternoon second-wind bias",
    "occupied but not attending"
  ]
}
```

This file is the authority for:

- daily and weekly pacing
- loudness and brightness bias
- onset density and articulation bias
- silence scheduling
- experimentation limits
- tracker tempo territory

## Presence State Machine

### Inputs

Presence should combine these signal classes:

| Signal | Source | Strength | Notes |
|---|---|---|---|
| direct user input | face keyboard, Telegram, MIDI, Theramini | strong | counts as immediate reliable presence |
| speech detected | `room_speech.json` | strong | stronger with recent transcript and repetition |
| indoor room motion | `room_presence.json` | medium | should not be trusted alone for identity |
| observer motion | `observer_state.json` | medium | useful when paired with room motion |
| room transient/activity | `room_activity.json` / `input_levels.json` | medium | useful for footsteps, handling, nearby activity |
| sustained bright clutter with no motion | `observer_state.json` | weak | not enough alone to infer people |
| recent historical presence | presence engine memory | medium | prevents jitter and enables hysteresis |

### Reliable Signs Of People

The following should count as a reliable sign of people immediately:

- direct face interaction
- Telegram message from a person
- MIDI keyboard activity
- Theramini activity
- confirmed speech detection
- combined indoor motion plus room activity within a short window

The following should not count as sufficient by themselves:

- observer brightness alone
- one stale camera frame
- one isolated low-level transient

### Output Shape

`/tmp/presence_state.json` should look like:

```json
{
  "timestamp": 1776000000.0,
  "occupancy_state": "occupied_quiet",
  "confidence": 0.86,
  "attention_state": "ambient",
  "attention_score": 0.24,
  "identity_hint": "guest",
  "identity_confidence": 0.31,
  "last_reliable_presence_at": 1775999972.0,
  "last_direct_interaction_at": 1775999920.0,
  "signals": {
    "speech": false,
    "room_motion": true,
    "observer_motion": false,
    "room_activity": "moderate",
    "instrument_active": false,
    "direct_interaction": false
  },
  "reasons": [
    "room motion plus room activity within 15s",
    "no direct interaction in the last 5m"
  ]
}
```

### Occupancy States

The canonical occupancy states are:

- `occupied_active`
- `occupied_quiet`
- `likely_asleep`
- `likely_away`
- `uncertain`

### State Rules

#### `occupied_active`

Use when:

- at least one strong signal is present now, or
- multiple medium signals co-occur inside a short window

Behavior:

- social and music systems assume people are present
- daytime mode entertains
- performance overlay may rise if attention builds

#### `occupied_quiet`

Use when:

- reliable presence was recently confirmed, but current signals are low
- or there is stable indoor-presence memory with no evidence of departure

Behavior:

- the system stays socially aware and restrained
- uncertainty still resolves toward `occupied_quiet`

#### `likely_asleep`

Use when all are true:

- current time is inside the sleep window
- there has been prior home occupancy
- activity, speech, and interaction have stayed quiet for a sustained period
- no departure evidence is present

Provisional defaults:

- sleep window starts at `00:00`
- the state persists until the first reliable wake signal
- exact sleep inference thresholds remain open for live tuning, but the music
  target is now the research-backed sleep envelope defined below

Behavior:

- CypherClaw enters sleep-mode cadence
- no autonomous verbal greeting
- music becomes sparse, quiet, and low-arousal
- sleep mode must continue fading after sleep onset rather than holding a fully
  present overnight soundbed

#### `likely_away`

Use when:

- no reliable sign of people has occurred for `5 minutes`
- and there is no late-night sleep inference stronger than away

Behavior:

- the cadence engine may enter `away_practice`
- identity and guest logic are disabled
- performance overlay is suppressed

#### `uncertain`

Use when:

- signals are weak or conflicting
- confidence drops below the `occupied` and `away` thresholds

Behavior:

- resolve as if `occupied_quiet`
- do not enter away-practice

### Hysteresis

The engine should prevent oscillation:

- retain `occupied_*` for a short hold period after the last strong signal
- require a full `5 minutes` of no reliable people-sign before `likely_away`
- retain `likely_asleep` unless a reliable wake signal occurs
- never switch directly from `likely_asleep` to `likely_away` without passing
  through a wake or explicit departure check

## Attention And Performance Overlay

Attention is orthogonal to occupancy. It answers "are people merely in the room,
or are they attending to CypherClaw?"

### Attention States

- `ambient`
- `attending`
- `performance`

### Attention Inputs

Strong evidence:

- direct interaction
- instrument play
- sustained presence in the face/gallery zone
- repeated return to the same zone after visual or musical changes

Weak evidence:

- one glance
- walk-through motion
- doorway motion with no stop

### Performance Rules

- direct interaction may raise `performance` almost immediately
- passive attention should need `20-60 seconds` of sustained evidence
- performance should decay softly back to `ambient`
- performance modifies the current cadence state; it does not replace it

## Identity Overlay

Identity is also an overlay, not a cadence state.

### Identity States

- `household_member`
- `guest`
- `unknown`

### Identity Rules

- household members are explicitly enrolled
- guests start as `unknown` and may become `guest` through repeated evidence
- explicit identity should be used sparingly in language
- most identity memory should appear through motif recall, warmth, and musical
  tolerance rather than explicit statements

## Cadence State Machine

Cadence should combine time-of-day, occupancy, wake events, and overrides.

### Canonical Cadence States

- `sleep`
- `wake_ramp`
- `occupied_day`
- `away_practice`
- `wind_down`

### Daily Phases

The cadence engine should also publish a finer-grained `day_phase` inside those
states:

- `late_night`
- `pre_dawn`
- `morning_activation`
- `mid_morning`
- `midday`
- `afternoon_dip`
- `late_afternoon`
- `evening_settling`
- `pre_sleep`

These phases are not separate behavior trees. They are bias layers that shape
the parameter territory inside the active cadence state.

### Weekly Phases

The engine should publish a coarse `weekly_phase`:

- `monday_gentle`
- `core_weekday`
- `friday_lift`
- `weekend_late`
- `sunday_settle`

This weekly layer should nudge the daily cadence, not replace it.

### `sleep`

Entry:

- midnight sleep window plus `likely_asleep`, or
- explicit operator sleep override

Exit:

- first reliable sign of household activity, or
- direct user interaction

Defaults:

- BPM suggestion: `40-66`, or pulse-free drone
- pulse implied or absent
- voice cap `1-2`
- low density and soft attacks
- after the initial settle period, output fades toward near-threshold audibility
  or intermittent silence

### `wake_ramp`

Entry:

- first reliable sign of household activity after sleep
- or first direct interaction after sleep

Duration:

- `60 minutes`

Behavior:

- gradually lift BPM from sleep range toward a daytime floor around `90`
- widen instrumentation in a fixed functional order:
  `texture -> foundation -> pulse -> melody -> color/accents`
- keep actual voices cast-driven

### `occupied_day`

Entry:

- `wake_ramp` completes while people are present, or
- daytime occupied state outside the sleep and wind-down windows

Behavior:

- default daytime creative mode
- typical BPM center follows the active day phase, usually around `80-110`
- attended or performance-biased moments may burst above that range without
  redefining the whole day
- more legible phrase structure when attention rises
- supportive background mode when people are focused and quiet

### `away_practice`

Entry:

- cadence is not `sleep` or `wind_down`
- occupancy becomes `likely_away`
- no recent reliable sign of people for `5 minutes`

Behavior:

- assertive and strange exploration is allowed
- discoveries may be promoted later if they survive repetition and filtering
- no visitor-facing greeting logic

### `wind_down`

Entry:

- `22:00` by default

Behavior:

- start slowing regardless of general occupancy
- keep winding down unless explicitly overridden
- reduce density, brightness, aggression, and novelty

Override:

- if a person explicitly asks CypherClaw to stay lively after `22:00`, the
  lively-night override lasts until `00:00` by default unless explicitly
  extended

## Daily Cadence Model

Daily cadence should follow circadian physiology first and social context
second. The system should bias gradually across `15-60 minute` windows instead
of jumping at clock boundaries.

| Day phase | Approx window | Primary meaning | BPM guidance | Loudness and brightness | Density and pulse | Notes |
|---|---|---|---|---|---|---|
| `late_night` | `00:00-05:00` | melatonin peak, deepest sleep | `<= 60` or pulse-free | `35-40 dB`, very dark, minimal dynamic spread | `<0.5 onsets/sec`, pulse absent | continue fading toward near-silence or intermittent silence |
| `pre_dawn` | `05:00-07:00` | waking pressure begins | `60 -> 80` | warm slowly, `40-48 dB` | `0.5 -> 1.5 onsets/sec`, pulse barely emerging | brighten before accelerating |
| `morning_activation` | `07:00-09:00` | wake-up ramp | `75-95` | `45-55 dB`, moderate brightness | `1-3 onsets/sec`, low-to-moderate pulse clarity | moderate tempos already feel active here |
| `mid_morning` | `09:00-11:00` | peak alertness | `85-105` | neutral-to-bright, `48-58 dB` | `2-4 onsets/sec`, moderate pulse | creative but still livable |
| `midday` | `11:00-13:00` | transitional plateau | `80-100` | neutral brightness, steady dynamics | `2-3 onsets/sec`, moderate pulse | begin easing toward the dip |
| `afternoon_dip` | `13:00-15:00` | endogenous lull | `70-85` | slightly warmer, softer, narrower dynamics | `1-2 onsets/sec`, reduced pulse clarity | accommodate the dip; do not fight it |
| `late_afternoon` | `15:00-18:00` | second wind | `85-110` | brighter, more dynamic, broader range | `2-5 onsets/sec`, moderate-to-clear pulse | natural peak for more vivid music |
| `evening_settling` | `18:00-21:00` | homeward settling | `90 -> 75` | brightness and dynamics taper | `3 -> 1.5 onsets/sec`, pulse softens | diverge from nightlife streaming norms |
| `pre_sleep` | `21:00-00:00` | melatonin rise, falling arousal | `70 -> 55` | dark, soft, low-variance | `<1 onset/sec`, pulse ambiguous | hand off naturally into sleep |

### Daily Phase Rules

- `likely_asleep` always wins over bright daytime defaults.
- `wake_ramp` is event-driven. It begins on the first reliable sign of people or
  direct interaction, not only when the clock crosses into morning.
- `away_practice` may borrow the current day phase for brightness or tempo bias,
  but it is allowed to raise experimentation within that envelope.
- `wind_down` applies even if people are still up, unless explicitly overridden.

## Weekly Modulation Model

Weekly cadence should be a gentle overlay on top of the daily model.

| Weekly phase | Meaning | Default bias |
|---|---|---|
| `monday_gentle` | social jet lag compensation | extend wake ramp `15-30 min`; reduce early brightness and onset density |
| `core_weekday` | Tuesday through Thursday steadiness | minimal variance; stable daytime support |
| `friday_lift` | easing into weekend | slightly higher afternoon energy; allow later liveliness |
| `weekend_late` | Saturday and late-shifted free-day rhythm | shift morning curve about `60-90 min` later; allow more variety and wider dynamics |
| `sunday_settle` | transition back to workweek | start calming bias from `16:00`; reduce evening aggression and novelty |

Weekly logic should be defeasible by real presence. If the household is clearly
active on a Sunday night, CypherClaw may remain attentive while still bending
toward calm.

## Music Mapping Rules

BPM is a band, not a command. The cadence engine should publish a parameter
territory, not only a target tempo. The tracker should select scene tempos
within that band and still apply movement-level multipliers. Loudness,
brightness, onset density, articulation, pulse clarity, silence, and dynamic
range should be co-published with the BPM band instead of derived implicitly.

### State Table

| State | BPM band | Loudness and brightness | Onset density and articulation | Silence budget | Voice cap | Risk level |
|---|---|---|---|---|---|---|
| `sleep` | `40-66` or pulse-free | `35-40 dB`, very dark, very low dynamics | `< 0.5 onsets/sec`, long attacks, pulse absent | dominant overnight near-silence or intermittent silence | `1-2` | minimal |
| `wake_ramp` | `55-90` rising | `40-52 dB`, warming gradually | `0.5 -> 2.5 onsets/sec`, attacks shorten slowly | `10-15 min` silence per hour | `2-4` | low |
| `occupied_day` | `80-120` nominal, excursions `70-135` | `45-55 dB`, cast-led brightness | `2-4 onsets/sec`, bursts to `5-6`, articulation varies by attention | `8-12 min` silence per hour | `3-5` | medium |
| `away_practice` | `40-180` | wider spectrum and dynamics, still under room-safe ceiling | unrestricted inside system safety and CPU bounds | `6-10 min` silence per hour | `3-5` | high |
| `wind_down` | current state down toward `55` by midnight | `38-48 dB`, darkening, narrower range | `3 -> 0.5 onsets/sec`, longer attacks, pulse dissolves | `15-25 min` silence per hour | `2-3` | low |

### State Details

#### Sleep

- prefer long note values, low onset density, and deep pulse ambiguity
- avoid hard transients, bright bells, percussion, syncopation, and harmonic
  surprise
- filter most energy above `2-3 kHz`
- keep dynamics extremely narrow
- permit tracker scene multipliers, but clamp them into the sleep band
- complete the final sleep descent over `30-45 minutes`, then fade output
  toward `<= 25-30 dB SPL` equivalent room presence or intermittent silence
- favor silence windows that grow longer after the first hour of sleep

#### Wake Ramp

- do not jump straight from sleep to daytime liveliness
- use low-contrast harmony first, then clearer phrase boundaries
- keep tempo rise below roughly `1 BPM/min`
- allow face and gallery to feel more attentive before the music fully wakes
- increase brightness and onset density before making large BPM moves

#### Occupied Day

- entertain, but coexist with domestic life
- when attention is low, stay supportive
- when attention rises, let performance mode sharpen pulse and visual coherence
- avoid persistent harsh high-frequency energy and unresolved dissonance that
  dominates the room for long stretches
- keep phrase arcs breathable enough that conversation can sit above the piece

#### Away Practice

- permit stranger motifs, wider contrast, and higher asymmetry
- keep a memory filter so only successful discoveries bleed into public mode
- do not assume public legibility is required
- maintain a `5-10 minute` graceful convergence back toward occupied norms when
  return detection fires
- use the current day phase as a tonal/weather bias, not as a hard restriction

#### Wind Down

- reduce brightness, density, and assertiveness after `22:00`
- hold this direction unless explicitly overridden
- let midnight hand off naturally into sleep
- compress the variance band as midnight approaches so the system feels more
  inevitable and less exploratory

## Silence Architecture

Silence is a required runtime feature. The cadence engine should schedule it
explicitly instead of leaving it to accidental sparse arranging.

### Silence Rules

- Every cadence state publishes a `silence_budget_s_per_hour`.
- Silence should be implemented as both:
  - micro-gaps: short breathing spaces between gestures
  - macro-gaps: room-scale pauses long enough for the Bernardi rebound effect
- Sleep and wind-down may use actual near-silence.
- Occupied-day silence should usually fade and re-enter gracefully rather than
  hard-cutting.
- Silence should be defeasible by active interaction or performance mode.

### Provisional Defaults

- `sleep`: overnight sound should become mostly silence after the initial settle
  period, with sparse returns instead of continuous bed playback
- `wake_ramp`: `10-15 minutes` of silence per hour, mostly short gaps
- `occupied_day`: `8-12 minutes` of silence per hour, mixed short and medium
  gaps
- `away_practice`: `6-10 minutes` of silence per hour to prevent saturation
- `wind_down`: `15-25 minutes` of silence per hour, including at least some
  gaps longer than `30 seconds`

## What Matters More Than BPM

The circadian engine should not treat tempo as the single master parameter.
The report points to these levers as at least as important:

- Onset density: the main driver of perceived speed. A nominally slow BPM still
  feels busy if the event rate is high.
- Timbral brightness: the strongest differentiator between sleep-inducing music
  and merely relaxing music. Darker timbres matter more than shaving a few BPM.
- Loudness and dynamic contour: even a sleep-safe harmonic language becomes
  activating if the amplitude profile swells or peaks sharply.
- Pulse clarity: explicit beat grids recruit attention and motor response.
  Sleep and wind-down want ambiguous pulse; performance mode wants clearer
  pulse.
- Attack time: short attacks feel more alerting. Long attacks help sleep,
  wind-down, and companionable occupied listening.
- Harmonic movement rate: slow harmonic rhythm supports environmental stasis;
  faster harmonic change supports performance and practice energy.
- Silence: the deepest relaxation response often happens after music stops, so
  silence must be scheduled directly.

## Social Synchrony Model

CypherClaw should aim for modest co-regulation, not strong claims about social
bonding.

### What To Optimize For

- give co-present people a shared temporal environment
- support breathing-scale phrasing without forcing overt entrainment
- stay below conversational volume
- avoid dominating attention unless people are actively attending

### Practical Mapping

- prefer `8-12 second` phrase arcs when the house is occupied and calm
- slightly simplify periodic structure during household gathering times
- keep pulse clarity low-to-moderate in ambient mode
- allow clearer pulse only when attention rises toward performance
- include strategic silence windows so the room can reset together

### What Not To Claim

- do not frame CypherClaw as a circadian entrainment device
- do not claim passive listening creates strong household bonding
- do not treat one BPM band as universally calming or focusing

## Scientific Guardrails

The implementation should respect what the research does not support:

- music can shape momentary arousal, but it is not a true circadian zeitgeber
- passive ambient listening is a weak path for social bonding compared with
  active synchrony
- streaming-time tempo averages do not justify dramatic clock-driven BPM swings
- the home-installation use case is under-studied, so live tuning and operator
  override remain essential

## Circadian Control Parameters

The cadence engine should publish at least these normalized control axes:

- `day_phase`
- `weekly_phase`
- `bpm_target`
- `bpm_range`
- `loudness_db_range`
- `onset_density_range`
- `spectral_centroid_target`
- `pulse_clarity`
- `attack_time_ms`
- `dynamic_range_db`
- `harmonic_movement_rate`
- `phrase_arc_s`
- `silence_budget_s_per_hour`
- `silence_gap_s_range`
- `voice_cap`
- `experimentation_bias`

These should be treated as a parameter territory, not a fixed point. Each
cadence state defines a center and a variance band. The composer and tracker
select within that territory rather than being told to play one exact tempo or
texture.

## Performance Overlay Mapping

When `attention_state` rises to `performance`:

- sharpen rhythmic clarity
- strengthen phrase boundaries
- make face, gallery, and music scene changes more coherent
- prefer `2-5 minute` local arcs inside the larger environmental arc
- temporarily center direct interaction, then fold it back into the longer world

Performance is an overlay, not a hard mode switch.

## Guest And Household Bias

Identity should bend presentation, not replace it.

### Guest Bias

- music becomes more legible and welcoming
- visuals become slightly clearer and less private
- autonomous greeting requires sustained presence or direct interaction

### Household Bias

- motif recall and warmth can appear sooner
- relationship memory is allowed to persist across days
- explicit memory language should remain rare and confidence-gated

## Override Precedence

Override handling should be explicit and auditable.

### Precedence Order

1. Safety and operator hard limits
2. Telegram operator overrides
3. Time-bounded face intentions
4. Direct-interaction focus overlays
5. Autonomous cadence logic

### Safety And Operator Hard Limits

These always win:

- explicit sleep or maintenance overrides
- explicit performance disable
- audio safety reductions from self-listener or operator action

### Telegram Operator Overrides

Telegram is the steward surface. It may set:

- hard cadence mode
- hard energy bounds
- explicit `stay lively until <time>`
- force sleep
- force practice
- diagnostics and sensor bypasses

Operator overrides remain until:

- explicitly cleared
- their TTL expires
- or a mode-specific default sunset occurs, such as lively-night expiring at
  `00:00`

### Face Intentions

Face overrides should be high-level and visitor-facing:

- `calmer`
- `livelier`
- `stay awake`
- `practice`
- `perform`
- `listen`

Defaults:

- TTL `15-45 minutes`
- refresh on continued interaction
- decay back toward autonomous cadence when engagement ends
- remain bounded by Telegram and safety limits

### Direct Interaction Focus

Direct interaction should immediately bend the organism toward the exchange, but
not erase the larger arc. This overlay may:

- temporarily raise attention to `performance`
- prioritize interaction-centered motifs
- temporarily reduce private strangeness in occupied contexts

## Implementation Phases

Implementation should proceed in CPU-safe layers. The live box is already
spending far more CPU on presentation and monitoring than on `scsynth`, so the
new cadence spine must stay lightweight.

### Phase 0: Instrument And Budget

- record current CPU, state-file freshness, and PipeWire stability
- define per-process budgets:
  - `presence_engine.py`: target `< 1%` CPU average
  - `cadence_engine.py`: target `< 0.5%` CPU average
  - new scheduling logic in `duet_composer.py`: no busy-wait loops
- reuse existing state files before adding new sensing workloads
- treat additional computer-vision work as deferred unless lightweight fusion is
  still insufficient

### Phase 1: Canonical Presence

- Start the missing live daemons:
  - `my-claw/tools/room_listener.py`
  - `my-claw/tools/senseweave/sensor_fusion.py` or its replacement
- Replace brightness-heavy occupancy inference with weighted presence fusion.
- Add `presence_engine.py` and write `/tmp/presence_state.json`.
- Make `inner_life/world_model.py` read `presence_state.json` as the canonical
  occupancy source once stable.
- Keep the engine file-driven and low-rate:
  - read only from existing `/tmp/*.json` files
  - use hysteresis instead of higher sampling rates
  - avoid adding OpenCV or audio DSP inside the engine itself

### Phase 2: Canonical Cadence

- Add `cadence_engine.py` and write `/tmp/cadence_state.json`.
- Drive cadence from:
  - occupancy state
  - wake events
  - time-of-day windows
  - day phase
  - weekly phase
  - overrides
- Keep BPM as a range plus variance, not one number.
- Publish the full control field:
  - loudness range
  - brightness target
  - onset-density range
  - articulation target
  - pulse clarity
  - harmonic movement rate
  - phrase-arc duration
  - silence budget
  - experimentation bias

### Phase 3: Composer Integration

- Update `duet_composer.py` to read `cadence_state.json`.
- Replace direct ad hoc tempo heuristics with:
  - cadence BPM band
  - onset-density band
  - spectral brightness target
  - pulse-clarity target
  - attack and dynamic-range targets
  - voice cap
  - experimentation bias
  - timbre bias
- Preserve tracker scene multipliers inside the cadence envelope.
- Make tracker family choice cadence-aware rather than using only song-count
  rotation when richer cadence signals are available.
- Add a silence scheduler or silence-aware tracker scene planning path so the
  published silence budget becomes audible behavior.

### Phase 4: Performance And Identity

- Add attention scoring and performance overlay.
- Add household-member enrollment and soft guest inference.
- Feed those overlays into face, gallery, and music together.
- Gate autonomous text or speech on cadence, occupancy, CPU stress, and recent
  attention history.

### Phase 5: Weekly Modulation And Memory

- add weekday and weekend biasing inside `cadence_engine.py`
- let away-practice discoveries promote motifs into public occupied listening
- add relationship-memory hooks without making language explicit by default

### Phase 6: Tuning And Soak

- run long unattended soaks
- compare predicted occupancy with real household behavior
- tune away timeout, sleep inference thresholds, morning ramp curve, and
  silence budgets
- audit CPU impact of the new daemons before widening the live graph further
- verify the household can still converse normally over the installation

## Immediate Build Order

The first implementation pass should ship in this order:

1. Add `presence_engine.py` with file-driven weighted fusion and write
   `/tmp/presence_state.json`.
2. Add `cadence_engine.py` with:
   - `cadence_state`
   - `day_phase`
   - `weekly_phase`
   - full parameter field
   - silence budget output
3. Update `world_model.py` to prefer `presence_state.json` and
   `cadence_state.json`.
4. Update `duet_composer.py` and tracker planning to consume the full cadence
   field.
5. Add silence-aware tracker scheduling.
6. Reconnect face and gallery so they read the same presence and cadence
   authority files as the music path.

This order gets the behavioral spine correct before layering identity,
performance, or richer household memory on top.

## Test Plan

Implementation should be test-first.

Add or extend:

- `tests/test_presence_engine.py`
- `tests/test_cadence_engine.py`
- `tests/test_override_engine.py`
- `tests/test_duet_composer_cadence.py`
- `tests/test_world_model.py`
- `tests/test_tracker_cadence.py`

The minimum contract to test:

- away only starts after `5 minutes` without reliable presence
- uncertainty resolves to `occupied_quiet`
- wake ramp starts on the first reliable sign or direct interaction
- wind-down begins after `22:00` unless explicitly overridden
- lively-night override expires at `00:00` by default
- Monday wake-up is gentler than Wednesday
- Saturday and Sunday shift later than workdays
- Sunday evening settles earlier than Friday evening
- face intention TTLs decay correctly
- Telegram overrides dominate face intentions
- tracker tempo selection stays inside the published cadence band
- sleep-mode output continues fading after sleep onset instead of holding a
  static overnight bed
- onset density and brightness targets follow cadence state, not only BPM
- silence budgets and gap ranges scale correctly by cadence state
- stale world-state inputs degrade to safe clock-driven defaults
- occupied calm mode emits breathing-scale phrase arcs without forcing a strong
  pulse

## Open Parameters

These remain intentionally open until live tuning:

- exact sleep inference thresholds for each household member pattern
- attention-score thresholds for `attending` vs `performance`
- identity-confidence thresholds for household vs guest behavior
- away-practice exploration limits that remain safe for the audio system
- the overnight balance between near-silence and intermittent sparse returns
- the final silence-budget ratios that feel alive without causing listener
  fatigue
