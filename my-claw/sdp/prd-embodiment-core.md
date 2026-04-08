# PRD: Embodiment Core

## Overview

CypherClaw is no longer just a headless generator. It is becoming an embodied organism with:
- a face monitor
- a gallery monitor
- a shared sensory state
- a persistent identity that reacts in real time

This PRD defines the foundational runtime needed before deeper performance loops and ambient audio work.

## Core Principles

1. The face and gallery are two views of one organism, not two unrelated apps.
2. Human interaction layers over the autonomous cycle; it does not erase it.
3. Every sensor plugs into one normalized event/state model.
4. Artist rehearsal and replay must exist early, not as an afterthought.

## Requirements

| ID | Description | Priority | Tier | Acceptance Criteria |
|---|---|---|---|---|
| EMB-001 | Define `EmbodiedStateCore`. | MUST | T1 | - One documented core schema exists for the organism runtime<br/>- Runtime can serialize and reload the core state<br/>- Core state is usable without any display attached |
| EMB-002 | Define the canonical overlay schema layered on top of `EmbodiedStateCore`. | MUST | T1 | - Overlay schema is documented separately from the core state<br/>- Overlay state can be serialized for replay/debug<br/>- Renderers can consume the overlay schema directly |
| EMB-003 | Define a sensor/plugin registration contract for SenseWeave v2 covering modality, update rate, confidence model, composition hooks, and overlay hooks. | MUST | T1 | - Plugins register through one contract<br/>- Hot-plug/hot-unplug are represented consistently<br/>- Registry can report active and missing voices |
| EMB-004 | Implement a normalized sensory event bus feeding the shared embodiment state. | MUST | T1 | - All active voices publish into one event model<br/>- Event model includes timestamp, intensity, confidence, decay, and payload<br/>- Shared state updates are driven from that bus |
| EMB-005 | Implement cross-modal confidence scoring so multiple voices can reinforce one event and intensify rendering/state changes. | MUST | T1 | - Two or more confirming voices produce stronger state updates<br/>- Confidence escalation is observable in debug output<br/>- Missing voices degrade gracefully |
| EMB-006 | Define the dual-display render contract for shared embodiment renders. | MUST | T1 | - Render contract is documented for both display roles<br/>- Display roles are configurable<br/>- Contract can be exercised in replay mode |
| EMB-007 | Isolate dual-display failure handling so one display can fail or disconnect without crashing the other. | MUST | T2 | - One display can fail/disconnect without taking down the other<br/>- Failure state is visible in observability/status output<br/>- Recovery path does not corrupt shared state |
| EMB-008 | Implement a GlyphWeave face compositor that maintains recognizable persistent traits while allowing phase-driven and interaction-driven mood shifts. | MUST | T2 | - Face stays visually recognizable across cycles<br/>- Mood changes alter expression without destroying identity<br/>- Face output is previewable in the studio loop |
| EMB-009 | Implement the text-weave layer for the face: typed characters appear immediately, remain legible briefly, then dissolve into the face composition. | MUST | T2 | - Text appears on the face within the target latency budget<br/>- Text integrates with the face instead of a crude overlay bar<br/>- Dissolve behavior is replayable/testable |
| EMB-010 | Add session/presence state so the organism can distinguish autonomous mode from active human session without discarding the underlying narrative phase. | MUST | T1 | - Presence state is represented in `EmbodiedState`<br/>- Autonomous and interactive layers coexist<br/>- Session timeout/absence returns cleanly toward baseline |
| EMB-011 | Add session-recording support for embodiment inputs so live sensor sessions can be captured without gallery hardware assumptions. | MUST | T2 | - Recorded sessions can capture the shared event/state stream<br/>- Session recordings can be saved and reloaded offline<br/>- Capture works without requiring both displays live |
| EMB-012 | Add replay support for recorded embodiment sessions. | MUST | T2 | - Replay mode uses the same state/event contracts as live mode<br/>- Recorded sessions can drive offline renders<br/>- Artists can compare alternate mappings against the same recording |
| EMB-013 | Add calibration and latency observability for embodiment state updates, display refresh, and interaction responsiveness. | SHOULD | T2 | - Operators can inspect end-to-end latency budgets<br/>- Calibration reports identify slow stages<br/>- Regression tests can assert timing envelopes where feasible |

## Notes

- This PRD is intentionally narrower than the full embodiment vision. It creates the shared organism runtime first.
- Audio generation, MIDI response, camera gestures, and other loops should layer on top of this core rather than each inventing their own state model.
