# CypherClaw Sampler Artistic Intent

This page is the short artistic-intent companion to the sampler PRD
([my-claw/sdp/prd-cypherclaw-sampler.md](../my-claw/sdp/prd-cypherclaw-sampler.md)),
the implementation/status snapshot in
[docs/cypherclaw-musicianship-roadmap.md](cypherclaw-musicianship-roadmap.md),
and the current-tree reference in
[docs/cypherclaw-sampler-architecture.md](cypherclaw-sampler-architecture.md).
Those documents explain the plan, the rollout state, and the landed
subsystem. This page answers a narrower question: what should
`sw_sampler` make CypherClaw feel like?

## Aesthetic Goals

The sampler exists to turn memory into musical material. It should make
CypherClaw sound less like a closed synth rig and more like an organism
that remembers where it is, what it has already played, and what kinds
of sound belong to this house.

Three usages define that goal:

- **Memory of place.** Contact-mic and room captures let the building
  leave fingerprints inside later pieces. A floor resonance, appliance
  hum, knock, scrape, or accidental chord can return as atmosphere,
  pressure, or harmonic grit.
- **Self-quotation.** When CypherClaw makes a phrase worth keeping, the
  music can hear itself back later in altered form. The point is not a
  literal replay but the feeling that yesterday's phrase still lives in
  today's piece.
- **Curated found-sound library.** A hand-built found-sound palette of
  field recordings, Theramini phrases, keyboard captures, and reference
  textures gives the sampler a wider memory than the current room alone.
  These sounds are palette colors, not sample-pack tricks.

The aesthetic target is continuity, not novelty. The sampler should
make the room feel metabolized, not decorated.

## Role In The Ensemble

Inside the quintet, `sw_sampler` is the memory voice. The other four
signature voices — `sw_bell_warm`, `sw_bowed`, `sw_breath`, and
`sw_pad` — provide the core synth body. `sw_sampler` contributes the
one thing those voices cannot: historical and environmental recall.

That means the sampler is not an ornamental extra laid on top of an
already-complete texture. It is a structural partner. Sometimes it may
replace a color line, sometimes it may become the soft harmonic bed,
and sometimes it may carry the most intimate melodic residue in the
piece. Its job is to let the ensemble remember, so the quartet becomes
a quintet with memory rather than a quartet with occasional FX.

## Listener Experience

A listener ideally should not think, "now the sample is playing." They
should feel that the house hears itself back through the music. A room
noise from yesterday might return as a veil around a pad, a self-
quotation might surface like a half-remembered melody, and a library
recording might briefly feel less like an imported object than like a
room memory translated into another dialect.

The intended listener experience is a balance of recognition and
transformation. The material should be recognizable enough to suggest
memory, but transformed enough to stay alive in the present tense. In
quiet modes this can feel intimate, interior, and self-listening. In
denser scenes it can feel like accumulated weather or emotional
pressure moving through the ensemble. The listener should sense that
the installation is building continuity across days, not starting from
zero every time.

## Five Principles

The PRD's five principles still govern the sampler:

1. **Granular by default, never one-shot.** The sampler is a granular
   voice, so stored sound returns as reshaped texture, phrase dust, or
   stretched contour rather than as a button-triggered quote.
2. **Memory-tagged and mood-aware selection.** Sample choice should be
   tied to arc, context, and mood-aware recall rather than random grab
   bag behavior.
3. **Effects bus parity with the rest of the orchestra.** The dedicated
   effects bus is part of the voice's identity, not a cosmetic add-on.
4. **Self-listening as composition.** CypherClaw's own prior output is
   valid source material, so reflection is built into the instrument.
5. **Restraint earned, not eroded.** The sampler must deepen the music
   without making it busier by default. Heavy use replaces other weight;
   it does not excuse excess.

If this voice is working, the listener hears a room that remembers
itself, a composer that can hear itself back, and an ensemble whose
continuity comes from lived sound instead of synthesis alone.
