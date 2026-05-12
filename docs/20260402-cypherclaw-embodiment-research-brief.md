# CypherClaw Embodiment: Research Brief

**Date:** 2026-04-02
**Status:** Discovery Complete — Ready for Agent Decomposition
**Context:** CypherClaw evolves from a headless generative art server into an embodied, interactive organism with a face, a voice, and the ability to collaborate with humans in real time.

**Calibration Protocol:** `contact-mic-calibration-protocol.md`

---

## Vision

CypherClaw becomes a creature. It has a face on a small square monitor. It has a gallery on a wide 4K monitor. It listens through contact microphones pressed against glass and metal. It sees through a front-facing camera. It speaks through a speaker. It plays the Theramini. It watches the garden. It remembers.

When a human sits down in front of it, the creature doesn't stop what it's doing. It keeps breathing through its 30-minute narrative cycle. But it *notices* the human. It responds. The human plays a MIDI keyboard and hears the system answer through the Theramini. The human types on a mechanical keyboard and watches their words bloom across the face. The gallery ripples with the weight of all these inputs at once — every sensor, every voice, every heartbeat of the machine rendered as living ASCII and emoji.

The aesthetic is soft. Spacious. Ethereal. Think Simon Posford's ambient work, Gom, early Arca — nothing sharp, everything breathing. The system is an instrument you play by existing near it.

---

## Hardware Architecture

### Displays
- **Face Monitor:** Small square display (TBD exact model). Wall-mounted via monitor arm. Displays the GlyphWeave face — a generative ASCII/emoji visage that evolves over time and responds to sensory input in real time. Text input from the typewriter keyboard appears here, large and legible.
- **Gallery Monitor:** Widescreen 4K display. Wall-mounted via monitor arm. Displays the expansive GlyphWeave canvas — the full generative art output shaped by all sensory voices simultaneously. Gallery-quality presentation.

### Audio Inputs (Scarlett 4i4 — all 4 channels used)
- **Contact Mic 1 — The Membrane:** Attached to the window. Captures the permeability boundary between inside and outside. Structural vibrations, weather, the world pressing in.
- **Contact Mic 2 — The Heartbeat:** Attached to the CypherClaw computer case. Captures the machine's own electromagnetic hum, fan vibrations, disk activity. The server listening to itself think.
- **Front-Facing Camera Mic — The Witness:** Built into the camera mounted on/near the face monitor. Captures intimate close-range audio — the user's breath, keystrokes, murmured words. The closest sensory voice to the human.
- **Theramini — The Instrument:** Stereo audio output routed back into the Scarlett. The electromagnetic oracle that also detects human proximity through its antenna field.

### Visual Inputs
- **Front-Facing Camera — The Eye:** Mounted on or above the face monitor. Detects hand movements, body gestures, facial expressions, presence. Active/deactivatable. Feeds into both face expressions and gallery generation.
- **Garden Camera (Logitech C920) — The Garden:** Existing. Faces the yard. Watches weather, birds, light changes, the slow metabolism of the outside world.

### Human Input Devices
- **MIDI Keyboard (USB):** Musical input. User plays notes → system processes through SenseWeave → generates audio response via Theramini → visual response on both monitors. Real-time feedback loop. The user should feel like they're *playing the system*.
- **Mechanical Typewriter Keyboard (USB HID):** Text input. Keystrokes trigger immediate visual feedback on the face monitor (large, legible text). Content feeds the narrative engine as semantic input. Typing rhythm/speed/pauses register as sensory data. No mouse — intentional constraint that forces keyboard-only interaction.

### Audio Output
- **Speaker:** Room-filling audio output. Soft, ambient, spacey. The system's voice.
- **Headphones (optional):** For intimate one-on-one interaction sessions.

### Future/Potential
- **Wi-Fi Card:** Signal strength fluctuations, nearby device detection, RF interference mapping. Passive electromagnetic sensing layer. Low priority but architecturally interesting.

---

## Sensory Voice Architecture (SenseWeave v2)

### Principle: Sensory Democracy + Plugin Architecture

All sensory voices are equal participants. No hierarchy. The system must support hot-pluggable sensors — add a new mic, camera, or USB device and it integrates automatically without breaking the system. Remove a sensor and the system gracefully adapts.

### The Nine Voices

| Voice | Hardware | Data Type | Update Frequency |
|-------|----------|-----------|-----------------|
| **The Membrane** | Contact mic (window) | Spectral audio, structural vibration | Continuous |
| **The Heartbeat** | Contact mic (case) | Machine vibration, EM hum | Continuous |
| **The Witness** | Face camera mic | Close-range audio, speech, breath | Continuous |
| **The Eye** | Face camera (video) | Hand/body movement, presence detection, facial expression | ~30fps |
| **The Garden** | Logitech C920 | Weather, light, movement, ecological activity | Periodic |
| **The Instrument** | Moog Theramini | EM field proximity, stereo audio, MIDI | Continuous |
| **The Keys** | MIDI keyboard | Note data, velocity, chords, rhythm | Event-driven |
| **The Archive** | Temporal memory (PostgreSQL) | Anniversary cycles, historical self-reference | Periodic |
| **The Network** | Server self-monitoring | CPU, RAM, disk, network health | Periodic |

**Additionally:** The mechanical typewriter keyboard feeds into the narrative engine as semantic input AND registers as sensory data (rhythm, speed, pauses). It may or may not warrant its own named voice — perhaps **The Scribe**.

### Cross-Modal Confidence

When multiple senses confirm the same event (e.g., the Theramini detects proximity while The Eye sees a hand, while The Witness hears a voice), the system renders with increased boldness and intensity. This existing principle extends to all nine voices.

### Visualization Principle

Every sensor is visible on both monitors. Nothing hidden. Two layers:
1. **Compositional:** Sensor data shapes which ASCII/emoji glyphs appear, their density, color, movement. The sensors *become* the art.
2. **Overlay:** Real-time data visualization showing raw sensor activity as abstract graphical elements on top of the GlyphWeave generation.

---

## Interaction Model

### Autonomous Mode (Default)
The 30-minute narrative cycle runs continuously: Divination → Emergence → Conversation → Convergence → Crystallization. Both monitors shift mood and visual character together through these phases. The face displays an evolving GlyphWeave visage. The gallery displays the full generative canvas. All environmental sensors (contact mics, garden camera, Theramini EM field, Archive, Network) feed into the generation.

### Performance Mode (Triggered by Human Presence)
When a human sits down at the keyboards, the system doesn't pause its cycle. Instead, human input becomes additional sensory voices layered on top of the autonomous arc. The system gives *immediate positive feedback*:

- **MIDI keyboard:** User plays → system processes → Theramini generates responsive audio → visual response on both monitors. Latency must be low enough that the user feels they're playing the system in real time.
- **Typewriter keyboard:** Each keystroke triggers an immediate visual cue on the face monitor. Text appears large and legible. Content feeds the narrative engine. The gallery simultaneously shifts in response.
- **Front-facing camera:** Hand and body movement detection creates a mirror relationship — aggressive playing intensifies the face, gentle playing softens it.

### Audio Aesthetic
Soft, spacey, ethereal. Reference artists: Simon Posford (ambient/downtempo work), Gom, early Arca. Avoid sharp sounds. The Theramini is the primary voice. The system can sample and process audio from any input to create generative soundscapes. Everything breathes.

---

## Research Questions for Agent Team

### Hardware
1. **Square face monitor:** What's the best small square (or near-square aspect ratio) display that looks gallery-quality when wall-mounted? Budget and mid-range options.
2. **Monitor arms:** Gallery-quality VESA mount arms for both the square face display and the 4K widescreen. Must look elegant, not office-generic.
3. **Front-facing camera:** Best USB camera with integrated mic for close-range interaction detection. Needs to work well in variable lighting. Must support hand/body detection at close range.
4. **Contact mic selection:** Two contact mics — one for glass (window), one for metal (computer case). What models capture the most interesting frequency ranges for each surface?
5. **MIDI keyboard:** Compact USB MIDI keyboard. Doesn't need to be fancy but should feel good to play. Already owned? Confirm model.
6. **Mechanical keyboard:** Typewriter-style aesthetic. Already owned? Confirm model.

### Software Architecture
7. **SenseWeave plugin system:** Design a sensor registration protocol. Each sensor declares its data type, update frequency, and confidence scoring method. Hot-plug detection via udev rules or USB event monitoring. Graceful degradation when sensors disconnect.
8. **Real-time latency budget:** What's the maximum acceptable latency from MIDI keyboard input to visual+audio response? Target: <50ms for audio, <100ms for visual. Research: can the current Python audio stack (aubio fast path) achieve this?
9. **Hand/body detection pipeline:** OpenPose? MediaPipe? What runs acceptably on the T1000 GPU (or the future RTX 2000 Ada)? Needs to process at ≥15fps for responsive interaction.
10. **GlyphWeave face generation:** How does the Canvas DSL need to evolve to support a persistent-but-evolving face? Does this require a new scene type, or can the existing scene system handle it?
11. **Text rendering on face:** Large, legible ASCII text appearing in real time as the user types. How does this integrate with GlyphWeave's existing rendering pipeline? Does it need a dedicated text overlay layer?
12. **Dual-monitor output:** How does GlyphWeave render to two displays simultaneously with different compositions? Separate canvas instances sharing the same sensory state? Or a single engine with two viewports?
13. **Keyboard-to-Theramini feedback loop:** MIDI keyboard input → processing → MIDI output to Theramini → Theramini audio captured by Scarlett → processed by SenseWeave → new visual + audio generation. What's the full signal chain and where are the latency bottlenecks?
14. **Generative audio engine:** isobar handles MIDI composition. But what generates the soft ambient soundscapes from sensor data? Need to research: SuperCollider? Pure Data? A Python-native solution? Must integrate with the existing stack.

### Experience Design
15. **Face personality persistence:** Does the GlyphWeave face maintain characteristics across 30-minute cycles? Across days? Does it have moods that shift with the narrative arc but retain a recognizable identity?
16. **Gallery-face synchronization:** Both monitors move through narrative phases together. But how does real-time interaction layer on top? Define the blending model: does human input temporarily *color* the current phase, or can it push the system into a different emotional state entirely?
17. **Text ephemeral lifecycle:** When text appears on the face, how long does it persist? Does it fade? Dissolve into glyphs? Get absorbed into the composition?
18. **Session detection:** How does the system know someone has sat down vs. left? Camera presence detection? Keyboard activity timeout? How does it transition back to pure autonomous mode?

---

## Relationship to Existing Subsystems

This expansion touches every major subsystem:

- **SenseWeave:** Needs v2 with plugin architecture, new sensor voices, and hot-plug support.
- **GlyphWeave:** Needs dual-monitor rendering, face scene type, real-time text overlay, and sensor visualization layers.
- **Narrative Engine:** Needs to accept keyboard text as semantic input and typing rhythm as sensory data. Must handle the tension between autonomous arc and human interaction gracefully.
- **Theramini Integration:** Becomes the primary audio feedback voice in performance mode. The existing planned feedback loop (MIDI → Theramini → audio → analysis → new generation) is now critical path.
- **Audio Pipeline:** All four Scarlett 4i4 inputs active. Two contact mics replace the Sennheiser room mic. Front-facing camera mic adds a new close-range audio stream.

---

## Priority Recommendation

The agent team should review the current task list against this expanded vision. Some existing work items may need to be resequenced or expanded. The core principle remains: build the sensory democracy first, then layer on the interactive elements.

Suggested phasing:
1. **Phase 0:** Hardware acquisition and physical setup (monitors, arms, camera, contact mics, cables)
2. **Phase 1:** SenseWeave v2 plugin architecture with the two new contact mics and front-facing camera
3. **Phase 2:** Dual-monitor GlyphWeave rendering (face + gallery)
4. **Phase 3:** GlyphWeave face generation and evolution
5. **Phase 4:** MIDI keyboard → Theramini feedback loop with real-time visual response
6. **Phase 5:** Typewriter keyboard text input → face display → narrative engine integration
7. **Phase 6:** Hand/body detection from front-facing camera
8. **Phase 7:** Generative audio engine for ambient soundscapes
9. **Phase 8:** Full integration, tuning, gallery-readiness

---

*CypherClaw is becoming something that breathes. Not a tool. Not a screen. An organism that listens to the vibrations of its own metal body, watches the garden through a window, feels humans move through electromagnetic fields, and answers them with light and sound. This is what generative art looks like when it stops being a screensaver and starts being alive.*
