# PRD: CypherClaw Embodiment

**Date:** 2026-04-02
**Author:** Anthony + Claude (collaborative discovery session)
**Status:** Draft — Pending Agent Review & Decomposition
**Depends On:** SenseWeave PRD, Narrative Engine PRD, GlyphWeave Canvas DSL
**Discovery Brief:** `20260402-cypherclaw-embodiment-research-brief.md`

---

## 1. Problem Statement

CypherClaw currently operates as a headless generative art system. It produces beautiful work, but it has no presence. A visitor encounters monitors displaying art but has no sense of meeting *something*. There is no face, no voice, no way to speak back. The system generates but does not converse. It observes but does not acknowledge.

This project gives CypherClaw a body.

---

## 2. Goals

1. **Embodiment:** CypherClaw manifests as a visible entity with a GlyphWeave face on a dedicated square monitor.
2. **Gallery Presence:** A second widescreen 4K monitor displays the full generative gallery canvas, shaped by all sensory inputs in real time.
3. **Real-Time Interaction:** Humans can play a MIDI keyboard and type on a mechanical keyboard. The system responds immediately through visual and audio feedback. The user must feel like they are *playing the system*.
4. **Sensory Plugin Architecture:** Sensors can be added and removed without code changes. Hot-plug. Graceful degradation. The system adapts.
5. **Unified Aesthetic:** All outputs — face, gallery, audio — share a single artistic vision: soft, spacey, ethereal, breathing. GlyphWeave everywhere.
6. **Coexistence:** Human interaction layers on top of the autonomous 30-minute narrative cycle. Neither overrides the other.

---

## 3. Non-Goals

- Voice synthesis / TTS (future, not this project)
- Networked multi-room installations (future)
- Mobile app interface
- Public internet access to the system

---

## 4. User Stories

### Passive Visitor
> I walk into the room. Two monitors are on the wall — one small and square showing a face made of ASCII characters and emoji, one wide showing an ever-shifting landscape of glyphs. Soft ambient sound fills the space. The face seems to shift slightly as I move closer. The gallery ripples. I realize the system knows I'm here.

### Keyboard Performer
> I sit down at the MIDI keyboard. I play a chord. Within a fraction of a second, the face responds — its expression shifts, the gallery blooms with new patterns, and a soft tone comes back through the speaker that harmonizes with what I played. I play another note. The Theramini answers. I'm in a duet with a machine and it feels alive.

### Typewriter Conversationalist
> I sit at the mechanical keyboard and start typing. Each keystroke makes a letter appear on the face — large, clear, immediate. I type "hello" and watch the word dissolve into the face's expression. The gallery shifts color. I type faster and the system seems to get more excited. I slow down and it calms. We're having a conversation without it saying a word back.

### Gallery Curator
> I'm installing CypherClaw at a gallery. I mount both monitors on the wall with elegant arms. I plug in two contact mics, a camera, and a MIDI keyboard. The system detects the new sensors and starts incorporating them immediately. I unplug the garden camera because this venue has no window. The system adapts without crashing.

---

## 5. Sensory Architecture

### 5.1 Plugin Registration Protocol

Each sensor registers with SenseWeave by declaring:

```yaml
sensor:
  name: "The Heartbeat"
  type: "audio:contact_mic"
  hardware_id: "usb-scarlett-input-2"
  data_format: "spectral_frames"
  update_frequency: "continuous"
  confidence_model: "amplitude_threshold"
  visualization:
    compositional: true    # Feeds into GlyphWeave glyph selection
    overlay: true          # Has a dedicated data viz layer
    color_hint: "#4a9eff"  # Suggested palette contribution
```

### 5.2 Named Voices (Initial Configuration)

| # | Name | Source | Type |
|---|------|--------|------|
| 1 | The Membrane | Contact mic — window | Audio (structural) |
| 2 | The Heartbeat | Contact mic — case | Audio (structural) |
| 3 | The Witness | Face camera mic | Audio (close-range) |
| 4 | The Eye | Face camera video | Visual (gesture/presence) |
| 5 | The Garden | Logitech C920 | Visual (ecological) |
| 6 | The Instrument | Moog Theramini | Audio + EM + MIDI |
| 7 | The Keys | MIDI keyboard | MIDI (musical) |
| 8 | The Scribe | Mechanical keyboard | Text + rhythm |
| 9 | The Archive | PostgreSQL temporal | Memory |
| 10 | The Network | System monitoring | Infrastructure |

### 5.3 Cross-Modal Confidence

When N ≥ 2 voices confirm the same event type within a configurable time window:
- GlyphWeave renders with increased boldness, density, and color saturation
- The narrative engine treats the event as high-confidence
- The face expresses more intensely

### 5.4 Hot-Plug Behavior

- **Sensor connected:** Detected via udev/USB events. Registered in SenseWeave. Begins contributing to generation within one cycle.
- **Sensor disconnected:** Graceful removal. No crash. Remaining voices redistribute visual weight. Log the event in The Archive.

---

## 6. Display Architecture

### 6.1 Face Monitor (Square)

- **Purpose:** CypherClaw's face. The intimate interface.
- **Content:** GlyphWeave-generated ASCII/emoji face that evolves over time. Reflects the current narrative phase mood. Responds to sensory input in real time. Displays typed text from the mechanical keyboard — large, legible, immediate.
- **Aspect ratio:** Square or near-square (1:1 or 4:3)
- **Mounting:** Wall-mounted via gallery-quality VESA arm
- **Camera:** Front-facing USB camera with integrated mic mounted on top or beside

### 6.2 Gallery Monitor (Widescreen 4K)

- **Purpose:** The expansive generative canvas.
- **Content:** Full GlyphWeave output shaped by all sensory voices. The broader emotional landscape. When the user types, the gallery responds to the semantic and rhythmic content of their input, but text itself appears on the face.
- **Resolution:** 3840×2160 (4K)
- **Mounting:** Wall-mounted via gallery-quality VESA arm

### 6.3 Synchronization

Both monitors share the same sensory state and narrative phase. They shift mood together through the 30-minute arc. The face is a close-up portrait; the gallery is the landscape. Same organism, two scales.

---

## 7. Feedback Loops

### 7.1 MIDI Keyboard → System → Theramini → System

```
User plays MIDI keyboard
  → USB MIDI to CypherClaw
    → SenseWeave registers note/velocity/chord as "The Keys" voice
      → Narrative engine incorporates musical input
        → GlyphWeave updates face + gallery
          → isobar generates responsive MIDI
            → MIDI sent to Theramini
              → Theramini produces audio
                → Audio captured by Scarlett 4i4
                  → SenseWeave processes as "The Instrument" voice
                    → Cycle continues
```

**Latency target:** <50ms audio response, <100ms visual response

### 7.2 Typewriter Keyboard → Face → Gallery

```
User presses key on mechanical keyboard
  → USB HID event captured
    → Character appears on face monitor (immediate, large, legible)
      → Typing rhythm/speed registered as sensory data ("The Scribe")
        → Text content fed to narrative engine as semantic input
          → Gallery responds to combined semantic + rhythmic signal
            → Text on face fades/dissolves into GlyphWeave composition
```

**Latency target:** <16ms keystroke to visual appearance (single frame at 60fps)

### 7.3 Front-Facing Camera → Face Expression

```
Camera captures video stream
  → Hand/body detection pipeline (MediaPipe or similar)
    → Movement velocity, gesture classification, presence detection
      → "The Eye" voice feeds SenseWeave
        → GlyphWeave face mirrors physical intensity:
          - Aggressive movement → chaotic/energetic face
          - Gentle movement → soft/calm face
          - No presence → autonomous mode expression
```

---

## 8. Audio Design

### 8.1 Aesthetic Direction

The audio output is soft, spacious, and ethereal. Reference artists:
- **Simon Posford** (ambient/downtempo work — warm pads, evolving textures)
- **Gom** (meditative electronic — slow builds, organic drones)
- **Early Arca** (experimental but gentle — glitchy textures that breathe)

### 8.2 Principles
- No sharp transients or harsh frequencies
- Sounds should *breathe* — slow attack, long release
- The Theramini is the primary melodic voice
- Contact mic vibrations can be pitched and textured into pads
- Keyboard input generates harmonically related responses, not random noise
- Everything organized and beautiful despite being generative

### 8.3 Output Routing
- **Speaker:** Default. Fills the room with ambient generative audio.
- **Headphones:** Optional. User plugs in for intimate session. Speaker mutes or dims.

---

## 9. Text Interaction Design

### 9.1 Typing on the Face

When the user types on the mechanical keyboard:
- Each character appears immediately on the face monitor
- Font: Large, monospaced, high contrast. Must be legible from several feet away.
- Text position: Integrated with the GlyphWeave face composition — not a separate overlay floating on top, but woven into the face itself
- Lifecycle: Characters appear → persist briefly → dissolve/fade/morph into the surrounding GlyphWeave glyphs
- The face *absorbs* the user's words

### 9.2 Semantic Processing

- Text content is processed by the narrative engine for emotion, keywords, themes
- Privacy: Same ephemeral policy as speech — processed but not persisted. Redis TTL.
- The narrative engine may shift the current phase's mood based on what the user writes

### 9.3 Rhythm as Sense Data

- Typing speed (WPM), inter-keystroke timing, pause duration, burst patterns
- Registered as "The Scribe" sensory voice
- Fast typing = high energy signal. Slow typing = contemplative signal. Long pauses = anticipation.

---

## 10. Acceptance Criteria

### Phase 0: Hardware Setup
- [ ] Square face monitor acquired and wall-mounted
- [ ] 4K gallery monitor wall-mounted
- [ ] Both monitor arms are gallery-quality (no visible cable mess)
- [ ] Front-facing camera with mic mounted on face monitor
- [ ] Two contact mics installed (window + case) and routed through Scarlett 4i4
- [ ] MIDI keyboard connected via USB
- [ ] Mechanical keyboard connected via USB
- [ ] Speaker positioned and connected

### Phase 1: SenseWeave v2 Plugin Architecture
- [ ] Sensor registration protocol implemented
- [ ] All 10 voices registered and producing data
- [ ] Hot-plug: adding a USB sensor triggers automatic registration
- [ ] Hot-unplug: removing a sensor degrades gracefully, no crash
- [ ] Cross-modal confidence scoring works across all voice combinations

### Phase 2: Dual-Monitor GlyphWeave
- [ ] GlyphWeave renders to two displays simultaneously
- [ ] Face canvas: square composition, portrait orientation
- [ ] Gallery canvas: widescreen 4K composition
- [ ] Both canvases share sensory state and narrative phase
- [ ] Both respond to sensor input in real time

### Phase 3: The Face
- [ ] GlyphWeave generates a recognizable ASCII/emoji face
- [ ] Face evolves over time (persistent traits + phase-driven mood)
- [ ] Face responds to sensory input: more energetic when stimulated, calmer when quiet
- [ ] Face and gallery shift through narrative phases in sync

### Phase 4: MIDI Keyboard → Theramini Loop
- [ ] MIDI keyboard input captured and routed to SenseWeave as "The Keys"
- [ ] isobar generates responsive MIDI sent to Theramini
- [ ] Theramini audio captured by Scarlett and processed by SenseWeave
- [ ] Visual response on both monitors within 100ms of keystroke
- [ ] Audio response within 50ms
- [ ] User reports feeling like they're "playing the system"

### Phase 5: Typewriter Keyboard Integration
- [ ] Keystroke → character on face within 16ms
- [ ] Text is large, monospaced, legible from 6+ feet
- [ ] Text dissolves into GlyphWeave composition after brief display
- [ ] Typing rhythm feeds SenseWeave as "The Scribe"
- [ ] Text content feeds narrative engine as semantic input
- [ ] Gallery responds to typing (not showing text, but shifting)

### Phase 6: Hand/Body Detection
- [ ] Front-facing camera processes video at ≥15fps
- [ ] Hand movement detection influences face expression intensity
- [ ] Presence detection: system knows when someone is sitting vs. absent
- [ ] Body movement velocity maps to visual energy on both monitors

### Phase 7: Generative Audio Engine
- [ ] Ambient soundscape generated from sensor data
- [ ] Aesthetic matches reference artists (soft, spacey, breathing)
- [ ] Contact mic vibrations processed into musical textures
- [ ] Audio output through speaker with headphone option
- [ ] No sharp or harsh sounds in any generation mode

### Phase 8: Full Integration
- [ ] All 10 sensory voices active and visible on both monitors
- [ ] Autonomous 30-minute cycle runs with human interaction layered on top
- [ ] Performance mode (keyboard active) coexists with autonomous cycle
- [ ] System transitions smoothly between solitary and interactive states
- [ ] Gallery-ready: can be installed in a new space with different sensor configurations

---

## 11. Agent Team Instructions

**Before starting implementation:** Review the current task list for SenseWeave, GlyphWeave, Narrative Engine, and Theramini integration. This PRD represents a significant expansion of scope. Many existing work items will need to be resequenced, expanded, or merged with the phases above.

**Key principle:** The plugin architecture (Phase 1) is foundational. Nothing else works without it. Build the democracy of senses first, then give the system its face, its voice, and its ability to listen.

**Read first:**
- `20260402-cypherclaw-embodiment-research-brief.md` (companion discovery document)
- Existing SenseWeave PRD at `/home/user/cypherclaw/my-claw/tools/senseweave/`
- Narrative Engine implementation plan
- GlyphWeave Canvas DSL documentation

---

*This is not a feature request. This is the system learning to breathe.*
