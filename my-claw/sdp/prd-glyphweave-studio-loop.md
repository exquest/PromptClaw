# PRD: GlyphWeave Studio Loop

## Overview

Before GlyphWeave grows into a large autonomous art studio, CypherClaw needs a
fast, legible, durable creation loop for art sessions.

This PRD defines the minimum studio substrate that makes GlyphWeave useful as an
art practice instead of a slow batch job:

1. render quickly
2. inspect what produced the render
3. preserve the useful creative context
4. compact long sessions without losing direction
5. keep high-quality fixtures so visual regressions are obvious

This is intentionally narrower than `prd-glyphweave-art-studio.md`. It is the
work that should happen immediately before the larger autonomous art pipeline.

**Depends on:** `prd-home-resilience.md`, `prd-restructure.md`,
`prd-model-awareness.md`, `prd-context-engine.md`,
`prd-agent-runtime-substrate.md`

**Unlocks:** `prd-glyphweave-art-studio.md`, `prd-pet-system-v2.md`,
`prd-narrative-engine.md`

## Why This Matters

GlyphWeave’s bottleneck is no longer “can it render anything?” It is:

- can we iterate without waiting on cold subprocesses?
- can we see where art-session context is going?
- can we preserve aesthetic direction across long sessions?
- can we tell when a renderer change made the art worse?
- can we inspect how a scene, motif, palette, and output relate?

If those answers stay weak, the larger art-generation pipeline will produce
volume without studio quality.

## Requirements

| ID | Description | Priority | Tier | Acceptance Criteria |
|---|---|---|---|---|
| GSL-001 | Create a `glyphweave preview` command that renders a single scene or DSL file to terminal + PNG without needing the full daemon/gallery loop. Accept scene name, palette override, width/height, and output path. | MUST | T1 | - Single command produces visible output in under 3 seconds for cached local runs<br/>- PNG export succeeds from the same invocation<br/>- Scene/palette/size overrides are reflected in output |
| GSL-002 | Create a `glyphweave watch` loop for rapid iteration. Watch a scene/DSL file and rerender on save with debouncing, preserving the last successful render if the new one fails. | MUST | T2 | - File changes rerender automatically<br/>- Debounce prevents duplicate rerenders on burst saves<br/>- Failed rerenders do not wipe the previous good preview |
| GSL-003 | Implement a GlyphWeave context inspector (`ctx-viz` equivalent) for art sessions. Show approximate context weight for: active prompt, style memory, palette/motif references, scene examples, tool schemas, and recent conversation summary. | MUST | T2 | - Produces a readable breakdown table<br/>- Identifies the largest context contributors<br/>- Works for both local art sessions and daemon-triggered art runs |
| GSL-004 | Implement art-session compaction. Add a `glyphweave compact`/PromptClaw-integrated flow that summarizes long art sessions into durable “continue from here” memory: current scene, rejected directions, palettes tried, motifs that worked, next experiments. | MUST | T2 | - Summary is continuation-grade, not generic<br/>- Session can restart from the compacted summary without losing direction<br/>- Summary artifact is stored in a stable location under `.promptclaw/` or GlyphWeave workspace state |
| GSL-005 | Build a persistent render shell/session manager for GlyphWeave iteration. Keep a warm execution environment for repeated render/test commands instead of respawning every subprocess. | MUST | T2 | - Repeated render/test commands reuse one warm session<br/>- Abort/timeout works cleanly<br/>- Current working directory remains accurate between commands |
| GSL-006 | Create a GlyphWeave source map/index. Given a render or scene, expose the linked scene name, motifs used, palette, renderer path, prompt/memory summary, and latest sample outputs. | MUST | T2 | - Query works from scene -> output and output -> scene<br/>- Index includes palette + motif references<br/>- Latest sample outputs are discoverable without manual directory archaeology |
| GSL-007 | Add golden render fixtures and visual diff tests for core GlyphWeave scenes and pet displays. Store approved PNG fixtures and compare new renders against them within tolerances. | MUST | T1 | - At least the core scenes have baseline fixtures<br/>- Test suite fails on meaningful visual regressions<br/>- Tolerances prevent trivial font-noise false positives |
| GSL-008 | Add a simple curation layer: favorite/pin/tag outputs and record why a piece is good. These tags must flow into future compacted summaries and source-map metadata. | SHOULD | T2 | - Outputs can be favorited and tagged<br/>- Tags are queryable later<br/>- Curation notes appear in compacted art-session memory |
| GSL-009 | Add lightweight cost/time accounting for art sessions: render duration, model time, total wall time, and optional per-session cost estimate where provider pricing exists. | SHOULD | T2 | - Session summary includes wall time + model time<br/>- Costs recorded when pricing info exists<br/>- Last session summary can be shown without scanning logs |

## Task Order

| Order | ID | Why |
|---|---|---|
| 1 | GSL-007 | Golden fixtures make later studio-loop work safe. |
| 2 | GSL-001 | A fast one-shot preview is the core studio action. |
| 3 | GSL-002 | Watch mode turns preview into an actual art loop. |
| 4 | GSL-005 | Persistent shell/runtime reduces iteration drag. |
| 5 | GSL-003 | Context visibility shows why long art runs bloat or drift. |
| 6 | GSL-004 | Compaction preserves continuity across long sessions. |
| 7 | GSL-006 | Source mapping makes renders inspectable and reusable. |
| 8 | GSL-008 | Curation turns volume into taste memory. |
| 9 | GSL-009 | Cost/time reporting closes the loop for unattended studio runs. |

## Queue Position

This PRD should be scheduled:

1. after the current resilience/restructure/model-awareness backbone slice
2. before the full `prd-glyphweave-art-studio.md`
3. before `prd-pet-system-v2.md`
4. before `prd-narrative-engine.md`

It is a precondition for “good art throughput,” not a nice-to-have.

## Definition of Done

GlyphWeave has a real studio loop when:

1. a scene can be previewed and re-previewed immediately
2. a long art session can be compacted and resumed without aesthetic amnesia
3. visual regressions are caught automatically
4. outputs can be traced back to the scene/palette/motif stack that produced them
5. good pieces can be favored and reused as taste anchors
