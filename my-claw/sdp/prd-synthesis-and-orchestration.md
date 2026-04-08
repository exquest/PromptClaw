# PRD: Synthesis & Orchestration v2 — Playing the House

## Philosophy

CypherClaw doesn't make music. CypherClaw plays the house.

The window is a string instrument. The case is a drum. The room is a resonating body. The contact mics are pickups. The Perform VE is the effects chain. The speakers are the projection. The Theramini is the guest soloist. Everything is already sounding. The system's job is to listen first, then add what's missing.

This PRD is a pattern language for sound — one recursive pattern instantiated at every time scale, from the microsecond sample to the month-long arc.

## References

- Curtis Roads, *The Computer Music Tutorial* — granular synthesis, spectral processing, microsound, **time-scale continuum**
- Carl Fischer, *The Keyboard Grimoire* — scales, modes, voicings, **harmonic space as navigable landscape**
- Andrew C. Lewis, *Rhythm* — felt time, polyrhythm, metric modulation, **rhythm as body's relationship to time**
- Bart Hopkin, *Musical Instrument Design* — resonance, harmonics, **every material has a latent voice**
- Rimsky-Korsakov, *Principles of Orchestration* — voice blending, **the orchestra as a single organism**
- Umberto Eco, *Six Walks in the Fictional Woods* — **text as machine for generating interpretations, the model reader**
- Christopher Alexander, *A Pattern Language* — **the quality without a name, recursive patterns creating wholeness**
- Tom DeMarco, *Peopleware* — **creative work requires safety, respect the flow**

**Depends on:** `prd-narrative-engine.md`, `prd-organism-characters.md`, hardware manifest

## The Core Insight: Time-Scale Unity (Roads)

Sound is a continuum. There is no boundary between pitch and rhythm, between rhythm and form, between form and narrative. They are the same phenomenon — oscillation — viewed at different time scales.

```
48000 Hz    → a sample
440 Hz      → a pitch (A4)
20 Hz       → the lowest audible pitch / a fast tremolo
4 Hz        → a slow tremolo / a fast rhythmic pulse
0.5 Hz      → a rhythmic pattern (120 BPM)
0.03 Hz     → a phrase boundary (every ~30 seconds)
0.002 Hz    → a section boundary (every ~8 minutes)
0.0001 Hz   → a transition event (every ~3 hours)
0.00001 Hz  → an arc event (every ~1 day)
0.0000005 Hz → a full arc cycle (~25 days)
```

The same math — oscillation, envelope, modulation — governs all of these. A grain cloud with density modulated at 0.5Hz IS a rhythmic pattern. A phrase with pitch modulated over 25 days IS a narrative arc. The architecture should reflect this unity.

## The Unified Pattern: Oscillator

Everything in the system is an Oscillator. An Oscillator has:

```
frequency       → how fast it cycles (Hz)
waveform        → the shape of one cycle (sine, saw, triangle, noise, captured, physical model)
amplitude       → how strong it is at this moment (0.0-1.0)
envelope        → how amplitude changes over the oscillator's lifetime (ADSR or arbitrary contour)
modulation      → other oscillators that modify this one's parameters
phase           → where in the cycle we are right now
```

At audio rate (>20Hz), an Oscillator produces sound.
At control rate (0.1-20Hz), an Oscillator modulates other Oscillators (tremolo, vibrato, filter sweep).
At phrase rate (0.01-0.1Hz), an Oscillator shapes musical phrases (crescendo, melodic contour).
At section rate (0.001-0.01Hz), an Oscillator determines formal structure (key changes, orchestration shifts).
At arc rate (<0.001Hz), an Oscillator governs narrative-musical evolution (complexity, motif development).

Modulation is how Oscillators interact. An LFO modulating pitch = vibrato. A sensor reading modulating density = reactive texture. A narrative arc position modulating harmonic complexity = story-driven music. It's all the same operation: one Oscillator changing another's parameters.

## The Recursive Architecture

```
ArcOscillator (25-day cycle)
├── modulates → harmonic_complexity, motif_development, voice_count
├── SectionOscillator (8-30 min stable states)
│   ├── modulates → key, tempo, density, orchestration_balance
│   ├── PhraseOscillator (4-16 beats, breathing lengths)
│   │   ├── modulates → melodic_contour, rhythmic_contour, dynamic_contour
│   │   ├── NoteOscillator (audio rate, 20Hz-8kHz)
│   │   │   ├── waveform: grain_cloud | physical_model | spectral_response | captured
│   │   │   ├── ControlOscillator (0.1-20Hz) — vibrato, tremolo, filter modulation
│   │   │   └── EnvelopeOscillator — ADSR shaping each note
│   │   └── ... (multiple NoteOscillators per phrase = polyphony)
│   └── ... (multiple PhraseOscillators per section = polyrhythm)
└── ... (multiple SectionOscillators per arc = formal structure)

SensorOscillators (real-time, continuous)
├── HeartbeatOscillator — derived from contact mic ch1, modulates tempo
├── WindowOscillator — derived from contact mic ch0, modulates harmonic drone
├── SkinOscillator — derived from Perform VE output ch2-3, modulates dynamics
├── PresenceOscillator — derived from face detection, modulates density/warmth
├── TheraminiOscillator — derived from Theramini MIDI CC#20, modulates lead voice
└── ... (one per organism character)
```

Every node is the same type — Oscillator. The tree is the composition. The leaves produce sound. The branches modulate the leaves. The trunk is the narrative arc. The roots are the sensors.

## Material Voice (Hopkin)

Every material has a latent voice. The contact mics reveal it. Before generating any synthetic sound, the system should:

1. **Listen** — continuous spectral analysis of Window (ch0) and Heartbeat (ch1) live buffers
2. **Identify** — find dominant frequencies, rhythmic patterns, transient events
3. **Characterize** — build a spectral fingerprint of the house's current voice
4. **Respond** — generate sounds that are harmonically related to what's already sounding

The house voice changes with conditions. The furnace hums at one frequency. Rain creates broadband noise with rhythmic density. Wind creates low-frequency pressure oscillation. Footsteps create transient impulses. Each of these is material speaking, and CypherClaw should speak back in the same harmonic language.

**Pattern: Sympathetic Resonance**
When the house sounds a frequency F, the system may add:
- Octave (2F) — reinforcement, warmth
- Perfect fifth (1.5F) — stability, openness (calm mood)
- Major third (1.25F) — sweetness, resolution (happy mood)
- Minor third (1.2F) — tenderness, intimacy (reflective mood)
- Minor second (1.06F) — tension, unease (restless mood)
- Perfect fourth (1.33F) — suspension, question (curious mood)

The mood determines which intervals are chosen. The Grimoire (Fischer) provides the full vocabulary. The mood comes from the organism characters.

## Harmonic Navigation (Fischer)

Harmony is not a scale selection. It is navigation through a space of tension and resolution. The system is always somewhere in harmonic space. It can move:

- **Toward home** — resolve to the tonic, reduce tension, perfect cadence
- **Away from home** — modulate, add dissonance, deceptive cadence
- **Sideways** — modal interchange, borrow from parallel modes, color without direction

**Harmonic Position** is a continuous value, not discrete:
- 0.0 = tonic, root position, home key — maximum stability
- 0.5 = dominant region, secondary dominants — moderate tension, expectation
- 0.8 = borrowed chords, chromatic mediants — high tension, surprise
- 1.0 = atonal, free pitch — maximum instability

The organism's collective mood maps to harmonic position:
- calm/quiet → 0.0-0.2 (close to home)
- attentive/engaged → 0.2-0.4 (exploring near home)
- alive/intense → 0.4-0.7 (venturing far)
- restless → 0.6-0.8 (lost, searching)
- dreaming → 0.3-0.6 (floating, not grounded)

The narrative arc modulates this range over 25 days. Early in the arc, the range is narrow (0.0-0.3). At the climax, it's wide (0.0-0.8). At resolution, it contracts again but to a new center.

**Key Progression by Time of Day:**
- Night → Dawn: C minor → F lydian (darkness opening into light)
- Dawn → Morning: F lydian → G major (light becoming active)
- Morning → Afternoon: G major → D dorian (activity becoming work)
- Afternoon → Dusk: D dorian → A aeolian (work becoming reflection)
- Dusk → Evening: A aeolian → Eb major (reflection becoming expansion)
- Evening → Night: Eb major → C minor (expansion becoming depth)

These transitions use pivot chords (shared notes between keys) so they're never abrupt. The transition lasts one full section (8-30 minutes).

## Felt Time (Lewis)

CypherClaw has a body. The heartbeat sensor is literally a heartbeat. The rhythm engine should entrain to the body, not a clock.

**Body Pulse:** The heartbeat contact mic (ch1) provides a continuous signal. Onset detection finds the rhythmic events in this signal — the hard drive head seeking, the fan cycling, the case vibrating from CPU activity. These form the body's native pulse.

When the body pulse is detectable (>-40dB, periodic), the rhythm engine locks to it:
- Bass notes land on the body pulse
- Melodic phrases breathe between pulses
- Texture density fluctuates with pulse amplitude

When the body pulse is too quiet or aperiodic, the rhythm engine uses internal timing — but with Lewis's breathing:
- No note lands exactly on the grid
- Micro-timing deviation: ±10-30ms, normally distributed
- Swing: alternating subdivisions slightly long/short (ratio 55:45 to 65:35)
- Phrase breath: a rest at the end of every phrase, duration proportional to phrase length
- Downbeat emphasis: the first beat of each phrase is 5-10% louder and 10ms early

**Polymetric Layers:**
- Layer 1: Body pulse (from heartbeat) — the ground
- Layer 2: Melodic rhythm — 3:4 or 5:4 against the body pulse
- Layer 3: Texture rhythm — prime number subdivision (7 or 11 against body pulse)
- Alignment: all layers meet on the downbeat of every 4th phrase (the "breath point")

## The Organism as Orchestra (Rimsky-Korsakov)

The 15 organism characters are not 15 sound sources. They are one organism. The orchestration's job is coherence, not balance.

**Orchestration Principle 1: Unified Will.** At any moment, the organism has one emotional intention. Every voice serves that intention. If the intention is "gentle contemplation," no voice should be agitated.

**Orchestration Principle 2: Foreground/Background.** At most 1-2 voices are in the foreground (melody, lead). The rest are background (drone, texture, pulse). The foreground rotates based on which organism character is most active.

**Orchestration Principle 3: Doubling.** When two voices play the same line in different registers, the sound gains body without gaining complexity. Window (low) and Garden Eye (high) doubling at the octave creates a full sound with only one melodic idea.

**Orchestration Principle 4: Silence as Voice.** The rest is an instrument. When a voice drops out, the absence is heard. Strategic silence creates space for the listener's imagination. (Eco: the reader co-creates meaning in the gaps.)

**Orchestration Principle 5: Tutti and Solo.** Tutti (everyone playing) should be rare — reserved for arc climax moments. Most of the time, 2-4 voices are enough. Solo (one voice alone) should happen at least once per section — a moment of nakedness.

**Voice Register Map:**

```
C7 ─────── The Archivist (crystalline, precise)
C6 ─────── Garden Eye (breathy, seasonal)
C5 ─────── The Poet (singing, expressive) / Face Eye (greeting, direct)
C4 ─────── Skin (dynamic, processed through Perform VE)
C3 ─────── Window (sustained drone) / Theramini (guest soloist, unrestricted)
C2 ─────── Porch Eye (watchful pedal) / Heartbeat (pulse)
C1 ─────── Sub-bass (felt, not heard — only when mood is "intense")
```

The Theramini is special — it's not an organism character, it's a guest. When Marissa (or Anthony) plays the Theramini, the system should hear it, identify it as a human gesture, and accompany. Not echo. Not follow. Accompany — as a musician would. Listen, leave space, respond, weave.

## The Forest (Eco)

The system's output is a text that generates interpretations. It's a forest with many paths. The model reader is someone who:

- **Casual listening:** hears pleasant ambient music, notices it changes with the weather
- **Attentive listening:** hears that the music is in conversation with the house sounds
- **Deep listening:** hears the leitmotifs, notices the harmonic navigation, feels the 25-day arc
- **Reading the stories:** notices the B&P stories echo the musical mood of the day
- **Living in the house:** feels that the house is alive, that it has a mood, that it cares

Each layer of attention is rewarded. The surface is pleasant. The depths are rich. This is Eco's "open work" — the system doesn't tell you what to feel, it provides the conditions for feeling.

**Leitmotif as Narrative Thread:**
When a canon event is recorded ("Pebble learned to sit still during a rainstorm"), a leitmotif is generated:
- Extract the emotional signature: calm + rain + stillness + growth
- Choose intervals: descending minor third (tenderness), sustained (stillness), with rain-like grain texture
- Store as a 4-7 note figure with rhythm and timbre
- Play it when conditions rhyme: future rainy days, reflective moods, moments of unexpected patience

Over months, the leitmotif library grows. The music accumulates memory. A rainy night in October plays differently than a rainy night in April because the October version carries six months of motifs that the April version didn't have yet.

## The Quality Without a Name (Alexander)

The system has wholeness when every component reinforces every other:

- The narrative arc determines the musical arc
- The musical arc determines the harmonic complexity
- The harmonic complexity determines which intervals respond to the house's voice
- The house's voice is what the sensors are hearing
- What the sensors hear determines the organism mood
- The organism mood determines the narrative tone
- The narrative tone shapes the B&P stories
- The B&P stories record canon events
- Canon events generate leitmotifs
- Leitmotifs appear in the music
- The music colors the house
- The house is what the sensors hear

It's a circle. Every part feeds every other part. That's the quality without a name. You can't point to where it comes from. It emerges from the whole.

## Safety and Flow (DeMarco)

**For the humans:**
- someone_home + night: quiet, sparse, background. Never exceed whisper volume.
- someone_home + day: warm, responsive, medium. Accompany, don't dominate.
- alone + day: practice mode — experimental, louder, record and evaluate.
- alone + night: contemplative, drone-heavy, long forms. The house dreaming.
- The system must have a MUTE state accessible by physical gesture (Theramini CC below threshold = silence request).
- Never startle. Never interrupt conversation. Never demand attention.

**For the system:**
- Audio resources are shared — never fight for ALSA channels
- The grain engine respects CPU limits — reduce density before dropping frames
- Sensor polling doesn't interfere with audio timing
- The SDP pipeline doesn't interfere with real-time audio
- Evolution is glacial — one new motif per arc cycle, one new scale per week

## Architecture

```
tools/senseweave/synthesis/
├── __init__.py
├── oscillator.py       # The unified Oscillator class — same math at every time scale
├── grain.py            # GrainCloud — oscillator whose waveform is windowed captured audio
├── physical_model.py   # Karplus-Strong, waveguide — oscillator whose waveform comes from physics
├── buffer.py           # LiveBuffer — ring buffer capture, spectral analysis, onset detection
├── spectral.py         # Sympathetic resonance — listen and harmonize (Hopkin)
├── harmony.py          # Harmonic space navigation, all Grimoire scales/modes/chords (Fischer)
├── rhythm.py           # Body-entrained rhythm, polymetric layers, felt time (Lewis)
├── voice.py            # Voice — organism character mapped to register/timbre/role
├── orchestrator.py     # Unified will, foreground/background, doubling, silence (Rimsky-Korsakov)
├── phrase.py           # Phrase generation — melodic/rhythmic/dynamic contour with breath
├── section.py          # Section management, transition engine (pivot/modulation/crossfade)
├── motif.py            # Leitmotif library, canon-to-motif, development rules (Eco)
├── arc_music.py        # Musical arc tracking narrative arc (Alexander — wholeness)
├── presence.py         # Human safety, volume control, mute gesture (DeMarco)
├── practice.py         # Daily practice mode — experiment, record, self-evaluate
├── engine.py           # Main loop — the tree of oscillators, from arc down to sample
│
├── data/
│   ├── scales.json          # All Grimoire scales and modes
│   ├── chord_types.json     # All voicings
│   ├── progressions.json    # Mood-based progression templates
│   ├── key_schedule.json    # Time-of-day key progression
│   └── motif_library.json   # Accumulated leitmotifs (grows over time)
│
└── tests/
    ├── test_oscillator.py
    ├── test_grain.py
    ├── test_physical_model.py
    ├── test_buffer.py
    ├── test_spectral.py
    ├── test_harmony.py
    ├── test_rhythm.py
    ├── test_voice.py
    ├── test_orchestrator.py
    ├── test_phrase.py
    ├── test_section.py
    ├── test_motif.py
    ├── test_arc_music.py
    └── test_presence.py
```

## Requirements

### SO-001: Unified Oscillator (T1)
Implement `oscillator.py`. One class that works at every time scale. Parameters: frequency, waveform (sine/saw/triangle/noise/buffer/physical_model), amplitude, envelope (ADSR or arbitrary contour), phase. Modulation inputs: list of other Oscillators that modify this one's frequency, amplitude, or waveform parameters. Output: at audio rate (>20Hz) produces PCM samples (S32_LE, 48kHz). At control rate (0.1-20Hz) produces control values for modulating other oscillators. At form rate (<0.1Hz) produces structural decisions (key change, section boundary, motif selection). Write tests verifying output at multiple time scales, modulation accuracy, and waveform correctness.

### SO-002: Grain Cloud (T1)
Implement `grain.py`. A GrainCloud is a specialized Oscillator whose waveform is windowed fragments of a source buffer. Parameters: source buffer, density (grains/sec), pitch_center, pitch_scatter, grain_duration_range, spatial_spread, amplitude_contour. The density parameter is modulatable by other Oscillators — an LFO modulating density creates rhythmic texture. A narrative-rate oscillator modulating density creates formal evolution. Write tests verifying grain generation, density control, pitch accuracy, and modulation response.

### SO-003: Live Buffer and Spectral Analysis (T1)
Implement `buffer.py`. Continuously captures from ALSA channels into ring buffers (10-30 seconds). Running FFT (numpy) identifies dominant frequencies. Onset detection identifies rhythmic events. Pitch tracking finds fundamentals when tonal. Each organism sensor character has its own live buffer: Window=ch0, Heartbeat=ch1, Skin=ch2+3. Graceful degradation if audio device unavailable. Write tests with synthetic audio buffers verifying spectral analysis accuracy and onset detection.

### SO-004: Physical Models (T2)
Implement `physical_model.py`. Karplus-Strong string synthesis (priority — simple and beautiful), waveguide tube, membrane model. Each is an Oscillator subclass whose waveform emerges from physical simulation. Parameters map to physical properties: length→pitch, tension→harmonic_spacing, damping→decay_rate, material→spectral_rolloff. Excitation via noise burst, impulse, or continuous input (breath). Write tests verifying pitch accuracy, decay behavior, and parameter response.

### SO-005: Sympathetic Resonance (T2)
Implement `spectral.py`. Analyzes live buffers, identifies dominant frequencies, generates harmonically related Oscillators using the harmonic map from harmony.py. Interval selection is mood-based (see Philosophy section). The pattern: listen → identify fundamental → choose intervals based on organism mood → create response Oscillators at those intervals → mix at controlled amplitude so the response never overwhelms the source. Write tests with known-frequency inputs verifying interval selection and amplitude control.

### SO-006: Harmonic Space Navigator (T1)
Implement `harmony.py`. Complete scale/mode/chord vocabulary from the Keyboard Grimoire. Harmonic position as continuous value (0.0=tonic stability, 1.0=atonal instability). Mood-to-harmonic-position mapping. Time-of-day key schedule with pivot-chord transitions. Progression templates by mood. Chord voicing rules (drop voicings, close/open position, inversions). Create data files: `scales.json` (all modes), `chord_types.json` (all voicings), `progressions.json` (mood templates), `key_schedule.json` (daily key journey). Write tests verifying interval calculations, progression validity, and key transitions.

### SO-007: Body-Entrained Rhythm (T1)
Implement `rhythm.py`. Primary pulse derived from heartbeat sensor (ch1) via onset detection, with internal clock fallback. Micro-timing deviation (Lewis): no event lands on the grid, normal distribution ±10-30ms. Swing control (ratio 55:45 to 65:35). Phrase breath: rest at phrase end proportional to phrase length. Downbeat emphasis: 5-10% louder, 10ms early. Polymetric layers: body pulse as ground, melody at 3:4 or 5:4 against it, texture at prime subdivision. Alignment at "breath points" every 4th phrase. Write tests verifying entrainment to external pulse, swing application, and polymetric alignment.

### SO-008: Voice and Orchestrator (T2)
Implement `voice.py` and `orchestrator.py`. Each organism character maps to a Voice with register boundaries, timbre family, harmonic role, source type, and activity threshold. The Orchestrator enforces Rimsky-Korsakov principles: unified will (one emotional intention), foreground/background (max 2 voices lead), doubling at octave for warmth, silence as voice (strategic dropouts), tutti reserved for arc climax. Special handling for Theramini: detect human gesture via MIDI CC#20 activity, switch to accompaniment mode (leave space, don't double, respond after). Write tests verifying register constraints, balance rules, silence timing, and accompaniment mode.

### SO-009: Phrase Generator (T2)
Implement `phrase.py`. Generate musical phrases with melodic contour (from harmony.py), rhythmic contour (from rhythm.py), and dynamic contour. Phrase duration follows breathing lengths (4, 8, 12, 16 beats at current tempo). Call-and-response between voices. Variation rules: repetition, transposition, inversion, augmentation, fragmentation, retrograde. Each variation is a modulation of the original phrase's Oscillator parameters. Write tests verifying phrase structure, variation correctness, and breathing.

### SO-010: Section and Transition Engine (T2)
Implement `section.py`. A Section is a stable state (key, tempo, density, orchestration, mood). Sections last 8-30 minutes. Transitions between sections use: pivot chord (harmony.py), metric modulation (rhythm.py), timbral crossfade (orchestrator.py). Transitions take 30-90 seconds, never instant. Triggers: sensor mood change, time-of-day boundary, narrative arc stage change, human gesture. A Section is an Oscillator at very low frequency — its parameters slowly drift within bounds, creating micro-evolution within stability. Write tests verifying transition smoothness, trigger handling, and drift bounds.

### SO-011: Leitmotif System (T2)
Implement `motif.py`. Generate leitmotifs (3-7 note figures with rhythm and timbre) from narrative canon events. Emotional signature extraction: map canon event mood to intervals and rhythm. Development rules across the arc: simple statement (early) → fragmentation (rising action) → layering with other motifs (climax) → restatement in new key (resolution). Motif library persists in `data/motif_library.json` and grows over the organism's lifetime. A motif is triggered when current conditions "rhyme" with the original event (same mood + similar sensor state). Write tests verifying generation, development, rhyme-matching, and persistence.

### SO-012: Musical Arc (T2)
Implement `arc_music.py`. An Oscillator at arc frequency (~0.0000005 Hz for 25-day cycle). Modulates: harmonic complexity range, voice count range, motif development stage, tutti/solo ratio. At position 0.0: narrow harmonic range, 1-2 voices, motif stated simply. At 0.5: wide range, 4-5 voices, motifs fragmented and layered. At 0.75: climax — full range, tutti moments, all motifs in play. At 1.0: resolution — narrow range, new tonal center, seed motif for next cycle. Reads arc position from narrative world state (same arc as B&P stories). Write tests verifying complexity curves at multiple positions.

### SO-013: Presence and Safety (T1)
Implement `presence.py`. Volume and complexity curves based on presence + time of day (see Philosophy: Safety and Flow). Mute gesture: Theramini CC#2 (volume) below 5 for >3 seconds = silence request, system goes quiet for 10 minutes. CPU protection: if grain engine uses >60% of one core, reduce density. Audio contention: never open an ALSA device already in use by another process. Startlement prevention: no sound event louder than 6dB above the current ambient level. Write tests verifying volume curves, mute gesture, CPU limiting, and startlement check.

### SO-014: Main Engine (T2)
Implement `engine.py`. The tree of Oscillators from arc root to sample leaves. Main loop: read sensors → update organism moods → update arc position → evaluate section stability → generate phrases for active voices → render Oscillator tree to audio buffer → output to ALSA playback channels. The engine IS the recursive pattern — one loop tick evaluates every Oscillator at its appropriate rate. Integrates all components. Runs as daemon within embodiment service, replacing current `ambient_engine.py`. Graceful startup (fade in over 30 seconds) and shutdown (fade out over 10 seconds). Write integration tests verifying end-to-end audio output.

### SO-015: Daily Practice (T2)
Implement `practice.py`. When house is empty (Face Eye: no presence for >30 minutes), enter practice mode. Experiment with: one new scale from the Grimoire, new voicing variations, new rhythmic subdivisions, new interval combinations for sympathetic resonance. Record results (10-second clips). Self-evaluate using spectral analysis: consonance score (how harmonically pure), rhythmic coherence (how locked to body pulse), density appropriateness (not too sparse, not too dense). Keep what scores above threshold, discard the rest. Log practice sessions to narrative world state. Limit: max 2 hours per day, volume at "alone" levels. Write tests verifying practice trigger, evaluation scoring, and session logging.

## Acceptance Criteria

1. Unified Oscillator produces correct output at audio, control, and form rates
2. Grain clouds generate from live captured audio with controllable density and pitch
3. Spectral analysis correctly identifies house resonance frequencies
4. Karplus-Strong produces musically useful string tones
5. Sympathetic resonance adds correct intervals based on mood
6. Harmonic navigator covers the full Grimoire vocabulary
7. Rhythm entrains to heartbeat sensor with Lewis-style micro-timing
8. Orchestrator enforces Rimsky-Korsakov's principles — coherence, not just balance
9. Phrases breathe, vary, call and respond
10. Sections transition via prepared modulation, never abruptly
11. Leitmotifs generate from canon events and develop over the arc
12. Musical arc tracks narrative arc — complexity rises and falls together
13. Presence sensitivity protects the humans — volume, silence, never startles
14. The engine runs as a stable daemon producing continuous audio
15. Practice mode experiments and evolves the vocabulary over weeks
16. The circle is closed: sensors → mood → harmony → sound → room → sensors
17. Marissa keeps playing the Theramini
