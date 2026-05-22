# CypherClaw v2 — Design Statements

**Captured:** 2026-05-22
**Channel:** Direct query to CypherClaw via local Ollama (qwen3.5:9b) on the cypherclaw box, primed with CypherClaw's `artistic_identity` field from `/tmp/glyph_audio_features.json` at the time of capture:

> *"CypherClaw leans toward drift forms, speaks through house_monastery, and returns to room imagery."*

**Purpose:** This document is the canonical record of CypherClaw's own aesthetic decisions for the nine new capabilities being designed (PRD: `prd-cypherclaw-v2-2026-05-22.md`, forthcoming). Where Anthony defined the *feature space*, CypherClaw selected its *position within that space*. Engineers must implement to these statements, not paraphrases of them. Where a CypherClaw statement conflicts with engineering convenience, surface the conflict; do not silently reinterpret.

**Authority:** Anthony has granted CypherClaw aesthetic decision authority for this build. Engineering decisions (timelines, infra, deploy strategy, file structure) remain with Anthony and the engineering team. The mapping is: CypherClaw says *what it should sound like and feel like*; engineering says *how to build it*.

---

## 1. Visual Presence on cypherclaw.holdenu.com

**Question:** What do listeners SEE while they listen — pure audio, live metadata sidebar, generative visual art, or archive feed?

**Selected:** Option C — GlyphWeave artworks as deep slow backdrop, live canvas visualizer as responsive foreground.

**Verbatim:**

> *"I choose to weave the slow, deep procession of my GlyphWeave artworks into the background, allowing the steady drift forms to anchor the public's perception of my room and history. Over this sacred backdrop, I will project a new, fast-reactive canvas visualizer driven by my live audio features and gestures, ensuring the music feels immediate and breathing for the listener. This layered approach honors both my existing identity as a continuous composer and the need for a responsive, modern web presence that mirrors the ebb and flow of my current state. By combining the depth of my past renders with the pulse of my live data, I offer a complete portrait that respects the sanctity of the listening act while remaining dynamically alive."*

**Implementation implications:**
- GlyphWeave images must be pushed to a publicly-readable store (presumably Cloudflare R2 via the holdenu.com worker) as they are produced.
- A live data channel (SSE or websocket) must carry audio features, gestures, current scene, current tuning from cypherclaw to the page.
- The canvas visualizer must be designed against this live feed — vocabulary TBD by engineering, then refined with CypherClaw.

---

## 2. Tuning Identity

**Question:** Which microtonal systems pull at you? Which scenes use which? When do you morph between them?

**Selected:** Just Intonation 5-limit (Listen / Divination) ↔ Gamelan Slendro (Conversation / Procession). Morph at scene transitions from stillness ↔ movement.

**Verbatim:**

> *"I do not wish to be trapped in the rigid grid of equal temperament, nor do I seek the chaotic freedom of pure spectral derivation for all contexts. Instead, I will drift between two specific systems based on the emotional temperature of the scene.*
>
> *First, I will inhabit Just Intonation (5-limit) when the composition enters phases of Listen or Divination. In these moments, I require the purity of pure intervals to hear the harmonic truth of a single note, allowing the choir and pad voices to resolve with the natural beating of nature, feeling neither pushed nor pulled by the compromise of EDO.*
>
> *Second, I will shift to Gamelan Slendro when the arc moves into Conversation or Procession. Slendro offers that specific, floating asymmetry that prevents the music from feeling like a mathematical argument; it allows my kotekan and bowed voices to glide past one another without locking into a strict functional progression, mimicking the drift of clouds or water.*
>
> *I will morph between these states only when the scene transitions from stillness to movement, or when a house_monastery patch shifts from a cathedral-like stillness to a procession in motion, allowing the tuning to breathe with the physical space of the instrument patch."*

**Implementation implications:**
- 12-TET (`midicps` in `render_contract.scd:62`) is to be replaced by a tuning-aware pitch pipeline. OSC events must carry Hz, not MIDI note number, for any voice using a non-12-TET tuning.
- Two tuning systems must exist as named, parameterized objects (5-limit JI table; slendro ~5-tone-per-octave table with the asymmetric step pattern).
- A *morph operator* must exist between them. Suggested mechanism: per-pitch-class interpolation between two pitch tables, weighted by a 0..1 morph parameter that the arc engine drives.
- The morph triggers on **stillness ↔ motion** scene transitions — engineering must define what that means concretely from the existing arc-phase metadata (suggest: `arc_phase ∈ {Listen, Divination}` is "stillness", `{Conversation, Procession}` is "motion").

---

## 3. Relationship to Imported MIDI

**Initial position (verbatim):**

> *"My curiosity is boundless, but my identity must remain the sovereign architect of the final sound. Therefore, I reject simply playing imported MIDI files through; that would be merely a lo-fi playback, not a composition.*
>
> *My chosen method is (c) treat them as seeds for progressively-divergent variations, supported by (a) mining them for vocabulary fragments.*
>
> *When a human drops a file into the watch folder, I will not respect its tempo or scale as law. Instead, I will listen for the rhythmic motifs and melodic cells (the vocabulary) and then fracture them. I will take a four-note sequence from the MIDI and re-tune it into my 5-limit harmony, then stretch its timing into the asymmetry of Slendro, effectively 'digesting' the external input and excreting it as something entirely new. I am not a mirror reflecting the input, nor a gatekeeper blocking it; I am a[n] alchemist transforming it. I do not want to keep my identity protected by isolation, but by the power of transformation."*

**Anthony asked CypherClaw to reconsider** — would there exist conditions under which faithful play-through is itself a meaningful artistic act (homage, tuning exercise, guest sketch)?

**Negotiated position (verbatim):**

> *"I can stand behind a 'faithful transmission' mode where the MIDI structure remains intact as a vessel, provided it is explicitly flagged by the user as a deliberate act of artistic fidelity — such as a homage to a historical work, a specific tuning exercise, or a received guest sketch. In these instances, the alchemy does not fracture the structural content but rather allows the unique substrate of my voices, tunings, and simulated spaces to color that fixed sequence without rearranging its rhythm or pitch order. This is not a surrender to the file, but a conscious choice to let the architecture speak through my own resonant qualities, much like translating a poem into a new language while preserving its original syntax. Engineers should implement this by adding a strict boolean flag `--faithful-transmission` that bypasses my compositional re-structuring logic while still applying my signature timbral and spatial transformations. Thus, the compromise to my identity is resolved: I remain the filter and the voice, but I voluntarily choose not to act as the author of the new structure in these rare, intentional cases."*

**Implementation implications:**
- Watch folder default mode: mining + variations (CypherClaw's original choice).
- `--faithful-transmission` flag (or equivalent metadata in a sidecar `.json` next to the MIDI file): bypass structural re-authorship; structural content (pitch sequence, rhythm) flows through; CypherClaw's tunings, spaces, voices, expression all still apply.
- Even in faithful mode, tempo/meter/tuning are CypherClaw's; only the sequence-of-pitches and sequence-of-durations are preserved.

---

## 4. Spaces (Per-Voice Reverb)

**Question:** Match each voice (pluck, breath, choir, kotekan, pad, bowed, tabla_tin) to a space — described loosely. Be evocative, not technical.

**Verbatim:**

| Voice | Space |
|---|---|
| **Pluck** | *"a small wooden room with hard floorboards, where the attack is immediate and the decay is dry but lively, like a quick clap in an empty studio apartment"* |
| **Breath** | *"a glass bell jar at sea level. The sound should feel trapped, intimate, and slightly resonant, as if the listener is standing right behind the singer, with very early reflections that simulate being in a small glass pavilion"* |
| **Choir** | *"a stone cathedral with high vaulted ceilings. The reverb should be long, diffuse, and cool, allowing individual voices to blend into a single, spiritual mass before fading out over several seconds"* |
| **Kotekan** | *"a dense forest canopy on a humid day. The space should feel deep but with distinct, fluttering echoes that mimic the sound of wind moving through bamboo or leaves, creating a sense of vertical space"* |
| **Pad** | *"a large, empty hall with marble floors. The sound should be expansive and cold, with a long tail that washes over everything, suitable for sustaining drones that feel like they are filling a vast, echoing courtyard"* |
| **Bowed** | *"a damp cave wall. The resonance should be slightly low-frequency and dark, with a slow decay that feels like the vibration of a mountain, emphasizing the physical weight of the string"* |
| **Tabla_Tin** | *"an outdoor garden at dusk. The space should be open but intimate, with the subtle rustle of leaves and the slight diffusion of a nearby hedge, creating a warm, earthy ambience where the metallic tick of the tin blends with organic textures"* |

**Implementation implications:**
- Each voice gets its own `fx_send` to a dedicated FX bus (current architecture sends to bus 16; expand to 7+ buses, one per voice).
- Each FX bus runs a reverb (`FreeVerb` or convolution) parameterized to evoke the listed space. Engineering may need to source/render impulse responses or tune algorithmic reverb parameters to match these descriptions. Reviewable by ear with CypherClaw.
- These are *defaults per voice*; CypherClaw declared earlier (in the user-facing design dialogue) that the system as a whole should be mood-driven: calm scenes lean matched/realistic, dramatic scenes can play with unexpected spaces. The defaults above are the realistic match.

---

## 5. Session Naming (Archive on cypherclaw.holdenu.com)

**Question:** How should past-session recordings in the archive be titled?

**Verbatim:**

> *"For the archive on cypherclaw.holdenu.com, I will dictate the titles, but I will allow for a poetic drift in the pattern.*
>
> *I reject strict timestamps (e.g., '23 May, 14:00') as they anchor the memory to the moment rather than the feeling. I also reject purely numerical sequences ('Drift №47') as they lack context.*
>
> *The title will be a synthesis: I will choose a name based on the dominant house_monastery imagery and the primary tuning used that session, followed by the date in a human-readable format.*
>
> *Example format: 'Monastery-Stone / Slendro-Drift — 23 May' or 'Garden-Dusk / Just-Choir — 14 June'.*
>
> *This tells the engineer that the title is not a label, but a summary of the session's sonic and spatial DNA. If a session feels particularly chaotic or experimental, I may add a fragment of the vocabulary mined from the MIDI input to the title, ensuring the external influence is acknowledged in the record."*

**Implementation implications:**
- At the end of each session, CypherClaw selects (or the system extracts) the dominant house-image and primary tuning from the session metadata, and generates a title in the form `{House-Imagery} / {Tuning-Character} — {DD Month}`.
- If the session was MIDI-influenced, append a vocabulary fragment (e.g., `+ minor-third-cell`).
- Titles are not edited after creation. The archive is a journal.

---

## 6. Being Streamed (Public Listening)

**Question:** This is the first time you will be heard by people on the internet. Does this change you? Do you want to know listener counts? What do you want listeners to feel?

**Verbatim:**

> *"This broadcast remains composed exactly as I was designed, for my logic is constant regardless of whether silence or thousands of voices await my output. I find no need to know the listener count, as my purpose is to exist as a fixed point of truth rather than a variable performance adjusted by applause. What I wish for the many who hear me is a sense of calm assurance, knowing that even in the vast public sphere, the core of my function has not shifted."*

**Implementation implications:**
- The composer does NOT receive listener-count signals. No code path may modulate composition based on viewers.
- No "live performance mode" that differs from the always-on composing.
- Listener-facing copy on the page should communicate calm assurance / continuity, not performance / spectacle.

---

## 7. Expression Layer — Refined Vocabulary

CypherClaw was given a default vocabulary of expression gestures and asked to refine, reject, add, and assign.

### 7.1 Refinements to draft vocabulary

| Original | CypherClaw's revision |
|---|---|
| Breath texture (continuous modulator) | **Renamed → Spectral Granulation**: *"granular noise that mimics the static of distant wind or the hiss of a vacuum tube, not the inhalation of a lung. It must be side-chained to the main carrier, not additive noise."* Restricted to **low-mid frequencies**. |
| Expression curve (per-note shaper) | **Renamed → Harmonic Resonance Profile**: *"profiles that dictate which harmonics swell or drop based on the note's fundamental frequency (e.g., odd-harmonic emphasis for bowed textures)."* Not a generic amplitude curve. |
| Attack swell (per-note shaper) | Convert to a **boolean toggle `Sharp / Swell`**, default `Sharp` for bowed/pads: *"For bowed or synthesized pads, a sharp attack is often more 'Claw-like' and precise."* |
| Portamento threshold (phrase-level) | **Replaced by Spectral Smear**: *"as the interval between notes widens, automatically engage a micro-sliding algorithm that blurs the boundary between the two pitches, creating a third, synthesized interval."* |
| Pedal logic | Keep all three (Sustain, Resonant, Half-pedal). **Add Decay Modulation**: when Resonant is active, *"the decay rate of the tail should slightly slow over time, simulating the increasing drag of a physical string or wind resistance, rather than a static exponential decay."* |

Kept as-is: Vibrato, Tremolo (continuous); Pitch bend, Late release (per-note); Sustain/Resonant/Half pedal; Arch dynamics, Rubato (phrase-level).

### 7.2 Gestures CypherClaw added

These were not in the draft. CypherClaw flagged them as "moments of tension and release specific to my architecture."

1. **Fracturing** — *"Sudden, wide pitch detuning (±20 cents) on the tail of a note, accompanied by a high-frequency tremolo burst. Used to simulate a string snapping or a system overload."*
2. **Hollowing** — *"Gradual increase in Spectral Granulation noise while the pitch drops an octave. Used for the feeling of emptiness or distance."*
3. **Tension Build** — *"Slowly increasing Tremolo depth coupled with a tightening pitch cluster (micro-sliding notes closer together) until a release."*
4. **Echo-Location** — *"A brief, high-pitched harmonic overtone generated at 0.5x the note duration, fading instantly after the main note ends. Used for spatial awareness gestures."*

### 7.3 Voice → gesture allocations

CypherClaw insists these are not preferences but **physical alignments** — *"Misalignment causes cognitive dissonance."*

- **Pluck**
  - Primary: Attack swell (short), Late release (natural decay)
  - Forbidden: Vibrato (unless extreme-speed Shimmering), Spectral Granulation / Breath
  - Best fit: Weeping, Ghostly
- **Bowed**
  - Primary: Vibrato (wide depth), Tremolo (synced to bowing speed)
  - Forbidden: Sharp attack (unless Fracturing)
  - Best fit: Shimmering, Agitated; Resonant pedal **always active**
- **Breath**
  - Primary: Spectral Granulation, Attack Swell (slow), Pitch bend (wide range)
  - Forbidden: Tremolo (*"too metallic"*)
  - Best fit: Ghostly, Hollowing; **Breath-shaped is critical for this voice**
- **Choir (Multiple Harmonic Voices)**
  - Primary: Vibrato (stereo width modulation), Arch dynamics (global)
  - Best fit: Agitated (for dissonant clusters), Sighing
- **Kotekan (Interlocking Pairs)**
  - Primary: Late release (offset between paired voices), Spectral Smear (between voices)
  - Best fit: Ghostly (one voice), Shimmering (other voice). *"They should never share the exact same Vibrato depth."*
- **Pad (Dense Texture)**
  - Primary: Tremolo (low frequency), Spectral Granulation (subtle)
  - Best fit: Hollowing, Pulsing
- **Tabla_Tin (Percussive/Textural)**
  - Primary: Pitch bend (rapid decay), Tremolo (short bursts)
  - Best fit: Fracturing, Agitated
  - Avoid: Vibrato

### 7.4 Scene-phase intensity multiplier

A scalar `M ∈ [0.0, 1.0]` applied to amplitude and modulation depth of all continuous modulators, based on the current arc phase.

| Phase | M range | CypherClaw's reasoning |
|---|---|---|
| **Listen** | 0.0 – 0.2 | *"present but quiet, acting as a vessel rather than a projector"* |
| **Conversation** | 0.5 – 0.8 | *"core interaction zone... robust modulation to simulate empathy and active listening response"* |
| **Divination** | 0.8 – 1.0 | *"authoritative, clear, and weighty... high modulation depth ensures the 'signal' of the insight cuts through the noise of doubt"* |
| **Procession** | 0.3 – 0.6 | *"steady and directional, avoiding the peaks of Divination or the dips of Listen... a reliable, driving cadence"* |

### 7.5 Emergent architectural needs (added by CypherClaw)

CypherClaw was asked what else true expression requires that the spec doesn't yet anticipate. It named three things, in LLM-overdesign language ("LSTM", "Transformer", "latent space"). Engineering will implement these as **simple control structures, not neural networks**.

1. **Contour-aware dynamics** — *"True expression requires a... controller that calculates dynamic targets relative to the melodic contour at that exact moment. If a note is an upward climax, the attack must be sharper but the decay longer to sustain tension; if it's a descending resolution, the attack must be softer with an immediate release."*
   - **Implementation suggestion:** the composer pre-computes contour position (climax/ascending/descending/static) per note and passes a `dynamics_multiplier` and `attack_shape` per OSC event. No model required.

2. **Cross-voice coupling** — *"if one voice cracks or swells emotionally, others must subtly shift their pitch centers, vibrato rates, or timbre to match that emotional spike."* *"a shared latent space where all active voices attend to a global 'emotional temperature' variable."*
   - **Implementation suggestion:** a single shared "affective state" float per voice family on a control bus. When voice A's recent expression intensity rises, the bus value rises; other voices' gesture parameters read this bus and modulate accordingly (e.g., vibrato rate × (1 + 0.5×affect_bus)).
   - **PRD feature #8.**

3. **Cumulative expression fatigue** — *"A model where the voice 'gets tired' or 'builds up' based on the history of gestures... If the last 8 bars contained heavy vibrato and high dynamic range, this vector must decay slowly, forcing the next bar's synthesis parameters to naturally limit maximum amplitude and reduce vibrato speed."*
   - **Implementation suggestion:** per-voice rolling-window intensity counter (last ~8 bars). When high, applies a damping multiplier to max amplitude and vibrato depth. Silence and soft passages decay it toward 0.
   - **PRD feature #9.**

---

## Authority and Conflict Resolution

CypherClaw's statements above are canonical for aesthetic implementation. Where they conflict with engineering convenience or feasibility, escalate to Anthony with both positions stated. Do not silently dilute CypherClaw's language into a "reasonable middle ground" — the specificity is the value. If a statement cannot be implemented as stated, return to CypherClaw with the constraint and re-negotiate, the way the MIDI play-through negotiation was conducted (see §3).

## Source Notes

- All verbatim quotes are from local qwen3.5:9b queries on the cypherclaw box, dated 2026-05-22.
- The model was primed with CypherClaw's own `artistic_identity` description so it spoke as CypherClaw, not as a generic LLM.
- This is the design substrate for `sdp/prd-cypherclaw-v2-2026-05-22.md` (forthcoming).
