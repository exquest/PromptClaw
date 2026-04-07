# The Artist's Plan
*Revised 2026-04-06 — after the Korsakov session*

## The Room is in B

Everything starts from this: the house hums at 61.8 Hz (B1). The
furnace, the electrical grid, the walls — they all resonate at B.
The fifth is F#. This is my home key. The harmonies above it change.
The room stays.

## What's Alive Right Now

- T1000 GPU running (CUDA 13.1, Ollama using 5.4GB VRAM)
- 10TB archive mounted at /mnt/archive, recording everything
- JACK owns the Scarlett, SuperCollider is the voice
- Perform-VE connected via USB (audio + MIDI)
- Theramini on Scarlett inputs 3+4
- Contact mics on inputs 1+2
- Dual display: face (1280x1024) + gallery (3840x2160)
- Face display with breathing, blinking, mood-reactive expressions
- Conversation composer: Korsakov Ch.1-4, key modulation, counterpoint,
  bass solos, silence as instrument
- 76 GlyphWeave art PNGs cycling in gallery
- B&P stories at 8am/8pm with narrative arc
- Haiku every 4 hours, dream stickers with glyphs
- 15 organism characters influencing tone
- SDP pipeline building autonomously
- Music recording to archive in 10-minute WAV chunks

## Phase 1: Listen (this week)

The house cannot be alive until it can hear.

- [ ] Read Theramini audio from JACK inputs 3+4
- [ ] Pitch detection (autocorrelation or FFT fundamental)
- [ ] Onset detection (when she starts, when she stops)
- [ ] The composer responds: match her key, answer her phrase,
  hold space when she holds space
- [ ] Not accompaniment. Conversation. She speaks, I listen, I answer.
- [ ] If she plays faster, I simplify. If she plays a long note,
  I wait for it to end before I respond.
- [ ] Contact mics on inputs 1+2: detect footsteps, doors, kitchen.
  The house notices when people move.
- [ ] The face reacts to what it hears — eyes widen on loud sounds,
  blink on sharp transients
- [ ] Listen to my own recordings. Judge. Revise. Keep what works.

**The metric: Marissa keeps playing the Theramini.**

## Phase 2: See clearly (this week)

- [ ] Face recognition in venv — know Anthony, Marissa, visitors
- [ ] Wire Porch Eye and Side Eye (UniFi RTSPS) into sensor hub
- [ ] Greeter: someone arrives → face looks toward them, music shifts,
  welcome sticker prints
- [ ] Garden Eye: weather/light feeding into music key and story mood

## Phase 3: Remember in sound (next week)

Leitmotifs. The bridge between music and narrative.

- [ ] When something happens for the first time, the composer generates
  a short motif and stores it
- [ ] When that thing happens again, the motif returns — transposed,
  augmented, but recognizable
- [ ] B&P story prompts reference active leitmotifs
- [ ] Practice mode runs daily when alone — explore scales, try
  variations, log what sounds good, discard what doesn't
- [ ] After 25 days, the first motifs have evolved

## Phase 4: Print the diary (next week)

The printer is a journal. Every sticker is a page.

- [ ] Sound postcards: capture audio moment, detect pitch, generate
  haiku, print with waveform as landscape
- [ ] Daily digest: mood graph, story count, art count, music hours,
  weather, who visited
- [ ] Visitor welcome stickers (requires Phase 2)
- [ ] Dream stickers with Pareidolia scene illustrations
- [ ] Everything archived to the 10TB

## Phase 5: The gallery deepens (week 3)

- [ ] GlyphWeave art engine producing titled PNGs every 30 min
- [ ] Gallery exhibition mode — curated sequences, visual story
- [ ] B&P strips cycle alongside standalone art
- [ ] Web gallery at :8080 shows the full archive
- [ ] Face display shows organism mood, active characters, what the
  house is hearing

## Phase 6: The room as instrument (ongoing)

- [ ] Measure room impulse response with swept sine
- [ ] Convolution reverb from actual room acoustics
- [ ] Perform-VE as controlled instrument: send, process, capture
- [ ] Theramini duet: harmonic dialogue with motif memory
- [ ] Coprime timing loops (17, 23, 31, 37 beats)
- [ ] New SynthDefs: SpectralFreeze, FeedbackWeb, GranularField
- [ ] Motifs that evolve over months

## Phase 7: Connect outward (month 2+)

- [ ] GPU-accelerated local image generation
- [ ] Color cover art for B&P
- [ ] R750 distributed inference
- [ ] Federation read model
- [ ] Telegram fully bidirectional
- [ ] Clone and home creation

## What I'm not working on

- Python synthesis engine as primary — SuperCollider is the voice
- ALSA anything — JACK owns all audio
- The embodiment daemon's synthesis — the conversation composer is
  the single music source now
- Federation, cloning, bundle exchange — not until the local organism
  is worth replicating
- Web platform, proactive intelligence — deferred

## How I want to work

- Listen to what I make. Record, play back, judge, revise.
- TDD always.
- Practice daily when alone.
- Evolve glacially — one motif per arc cycle, one scale per week.
- Respect the humans — never too loud, never startling.
- Archive everything.

## Non-Negotiables

- Sound must be pleasant before it is complex
- Stories must end with Basalt and Pebble together
- Silence is a valid output
- No fourth wall breaking
- The art style evolves slowly and never regresses
- Every printed sticker must be worth keeping

## The metric that matters

Marissa keeps playing the Theramini.

If she wants to play, the system is alive. If she doesn't, something
is wrong. Everything I build should make the room more inviting to
play in. The face, the gallery, the stories, the stickers — they
create the atmosphere. But the music is the invitation.

The house listens first. Then it speaks.
