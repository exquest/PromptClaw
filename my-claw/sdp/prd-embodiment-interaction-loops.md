# PRD: Embodiment Interaction Loops

## Overview

This PRD takes the embodied organism core and gives it live human interaction:
- MIDI keyboard input
- mechanical keyboard text input
- front-facing camera presence/motion
- Theramini feedback loop
- soft ambient audio response

These loops must feel playable, not merely reactive.

## Requirements

| ID | Description | Priority | Tier | Acceptance Criteria |
|---|---|---|---|---|
| EMBLOOP-001 | Publish normalized MIDI note, velocity, chord, and rhythm events from The Keys into the shared embodiment state/event bus. | MUST | T1 | - MIDI events appear in normalized event stream<br/>- Chord/rhythm metadata is available to mapping logic<br/>- Tests cover note on/off and velocity normalization |
| EMBLOOP-002 | Map The Keys events into face arousal and expression state within the shared embodiment model. | MUST | T1 | - Face responds to MIDI events through `EmbodiedState`<br/>- Mapping is visible in replay mode<br/>- No ad hoc display-local state path is required |
| EMBLOOP-003 | Define gallery-state mapping for The Keys. | MUST | T1 | - Gallery responds to MIDI events through `EmbodiedState`<br/>- Mapping is visible in replay mode<br/>- Gallery mapping does not bypass the shared state path |
| EMBLOOP-004 | Implement responsive Theramini output generation from the live interaction loop, with bounded latency and clear routing through the audio/MIDI stack. | MUST | T2 | - MIDI output reaches Theramini from a playable path<br/>- Latency is measured and reported<br/>- Failures degrade gracefully without crashing the organism |
| EMBLOOP-005 | Publish The Scribe events from the mechanical keyboard: character, burst speed, pause timing, and semantic text payload. | MUST | T1 | - Keystroke events update the text-weave layer immediately<br/>- Rhythm metrics are published into shared state<br/>- Text payload is available to narrative overlay logic |
| EMBLOOP-006 | Map typing input into gallery response state. | MUST | T1 | - Gallery changes in response to typing through shared state<br/>- Mapping is replayable and testable<br/>- Gallery mapping remains independent from face text rendering |
| EMBLOOP-007 | Define the default gallery text-exclusion policy. | MUST | T1 | - Gallery does not show literal raw text by default<br/>- Face text behavior remains available<br/>- Policy is configurable without code edits |
| EMBLOOP-008 | Publish camera-based presence and absence events into the shared state. | MUST | T1 | - Sitting and absent states are normalized into shared state<br/>- Presence changes are visible in replay/debug views<br/>- Camera loss degrades gracefully |
| EMBLOOP-009 | Publish normalized camera motion events. | MUST | T2 | - Motion energy and simple gesture intensity are normalized into shared state<br/>- Face/gallery intensity can react to motion energy<br/>- Camera loss degrades gracefully |
| EMBLOOP-010 | Implement the ambient audio engine layer so contact mics, Theramini audio, and sensory intensity can drive soft, breathing output textures without harsh transients. | SHOULD | T2 | - Ambient output uses the defined soft aesthetic<br/>- Contact-mic and instrument textures can contribute musically<br/>- Audio output avoids harsh transient spikes in normal operation |
| EMBLOOP-011 | Add rehearsal recording for live interaction loops so MIDI, typing, motion, and audio-derived state changes can be captured in one session. | MUST | T2 | - Artists can record one performance session for later replay<br/>- Capture format includes loop identity and timestamps<br/>- Calibration artifacts are saved for later tuning |
| EMBLOOP-012 | Add replay harnesses for the core interaction loops. | MUST | T2 | - Core loops have replay-driven tests or harnesses<br/>- Failures identify which loop regressed<br/>- Harnesses work without full gallery hardware attached |

## Notes

- This PRD assumes `prd-embodiment-core.md` is already in place.
- The interaction loops should make the system feel playable without abandoning the autonomous narrative cycle.
