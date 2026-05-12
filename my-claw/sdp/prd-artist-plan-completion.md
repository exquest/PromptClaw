# PRD: Artist's Plan Completion

## Overview

The Artist's Plan defines CypherClaw's artistic vision in 7 phases. After Day 4 of building, Phases 1 and 5 are nearly complete, but five specific gaps remain uncovered by any existing PRD. This PRD closes those gaps to complete the local organism before deeper synthesis, narrative, and federation work begins.

**Depends on:** `prd-embodiment-core.md` (shared state), `prd-embodiment-interaction-loops.md` (sensor wiring)

**Does not duplicate:** `prd-synthesis-and-orchestration.md` (leitmotifs, coprime timing, spectral resonance, harmonic navigation, advanced SynthDefs, deep practice mode), `prd-narrative-engine.md` (story generation, art cycle), `prd-publication-and-gallery-surfaces.md` (web gallery, publication controls)

## Requirements

| ID | Description | Priority | Tier | Acceptance Criteria |
|---|---|---|---|---|
| APC-001 | Install a lightweight face recognition model (insightface buffalo_l or equivalent) on the T1000 GPU for face embedding extraction. | MUST | T1 | - Model loads and initializes without error<br/>- Generates face embeddings from a test image in under 2 seconds<br/>- Runs in fp32 on T1000 without OOM alongside Ollama idle |
| APC-002 | Define a person registry schema storing name, face embedding vector, household role, and greeting preferences. Implement add, match (cosine similarity), and list operations. | MUST | T1 | - Schema is documented and round-trips to JSON<br/>- Match returns closest registered person above confidence threshold<br/>- Unknown faces return a distinct "visitor" result |
| APC-003 | Implement visitor identification by running face detection and embedding match against the observer camera frame at a configurable interval. | MUST | T2 | - Reads `/tmp/observer_frame.jpg` on schedule<br/>- Publishes identity result to `/tmp/visitor_identity.json`<br/>- Handles missing frame, no faces, and multiple faces gracefully |
| APC-004 | Amend `inner_life/world_model.py` to read `/tmp/visitor_identity.json` and populate `visitor_name` and `visitor_confidence` fields on WorldModel. | MUST | T2 | - WorldModel exposes visitor identity with staleness tracking<br/>- Falls back to `someone_here` boolean when identity unavailable<br/>- Tests cover known person, unknown visitor, and stale/missing file |
| APC-005 | Add a greeting rule to `inner_life/decision_engine.py` that triggers a personalized face message and mood shift when a registered person is newly identified. | MUST | T2 | - Greeting fires once per arrival (cooldown prevents spam)<br/>- Message includes visitor name<br/>- Music influence shifts toward warmer mood on recognized arrival |
| APC-006 | Debug and fix the NS8360 thermal printer ESC/POS driver so that text output prints reliably via USB. | MUST | T1 | - `thermal_printer.py` sends ESC/POS commands that produce legible text<br/>- Test print function produces visible output on paper<br/>- Driver handles printer-off and USB-disconnect gracefully |
| APC-007 | Implement a sound postcard sticker generator that captures current musical state, generates a haiku, and renders a waveform landscape for thermal printing. | SHOULD | T2 | - Reads current key, amplitude, and mood from state files<br/>- Generates a context-aware haiku (local LLM or template fallback)<br/>- Renders printable bitmap with waveform visualization and haiku text |
| APC-008 | Implement a daily digest sticker generator that summarizes the day's mood trajectory, art count, music hours, and visitor events. | SHOULD | T2 | - Reads from archive and inner life state for the current day<br/>- Generates a printable bitmap with mood graph and stats<br/>- Triggers at configurable time (default: midnight) |
| APC-009 | Implement a welcome sticker that prints when a registered visitor is first identified in a session. | SHOULD | T2 | - Triggers on first APC-003 identification per visitor per day<br/>- Includes visitor name and a brief personalized message<br/>- Respects cooldown (one welcome per person per 4 hours) |
| APC-010 | Define a gallery exhibition sequence schema in `tools/gallery/exhibition.py` with ordered image paths, per-item display duration, and optional caption text. | MUST | T1 | - Schema round-trips to JSON<br/>- Validates image paths exist on load<br/>- Tests cover valid and invalid sequence files |
| APC-011 | Add exhibition playback to `tools/gallery/gallery_display.py` that reads an active exhibition sequence file and displays items in order instead of random cycling. | MUST | T2 | - Gallery plays curated sequence when exhibition file present<br/>- Falls back to random cycle when no exhibition active<br/>- Transition timing respects per-item duration from schema |
| APC-012 | Measure the room impulse response by generating a swept sine through SuperCollider, recording the response via contact mics, and extracting the IR as a WAV file. | SHOULD | T1 | - Generates logarithmic swept sine (20Hz-20kHz) at controlled amplitude<br/>- Records response on contact mic channels<br/>- Extracts IR via deconvolution and saves as WAV<br/>- Runs only when house is empty (solitary mode) |
| APC-013 | Implement a convolution reverb SynthDef (`sw_conv_verb`) that loads the measured room IR buffer and applies convolution to replace or augment per-voice FreeVerb. | SHOULD | T2 | - SynthDef compiles and loads in scsynth<br/>- Accepts room IR buffer number as parameter<br/>- Can be used alongside or instead of existing FreeVerb per voice<br/>- Wet/dry mix is controllable |
| APC-014 | Generate color cover art for B&P stories by extracting a scene description from the story text and running it through the DreamShaper diffusion pipeline. | SHOULD | T2 | - Extracts visual scene prompt from B&P story text<br/>- Generates cover image via existing DreamShaper fp32 pipeline<br/>- Saves cover alongside story output in archive<br/>- Falls back to Pareidolia PIL sketch on GPU contention |

## Dependency Map

```
APC-001 → APC-002 → APC-003 → APC-004 → APC-005 → APC-009
APC-006 → APC-007, APC-008, APC-009
APC-010 → APC-011
APC-012 → APC-013
APC-014 (independent)
```

## Notes

- APC-001 through APC-005 form a chain — face recognition must be installed before visitor identity can work, and visitor identity must work before personalized greetings or welcome stickers.
- APC-006 (printer fix) unblocks three sticker types. This is a debugging task, not a feature build — the driver exists but produces no output.
- APC-012 should only run when the house is empty and quiet. The inner life loop's solitary mode is the natural trigger.
- APC-014 reuses the existing DreamShaper pipeline built for Pareidolia diffusion art. No new model installation needed.
