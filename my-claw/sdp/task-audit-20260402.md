# Task Audit — 2026-04-02

This document reviews the current live root-task backlog against the updated PromptClaw vision:

1. sovereign installable homes
2. clone + identity + lineage
3. embodied art organism
4. federation with read-default and proposal-based writes
5. publication and bundle exchange

The goal is not to discard the whole queue. The goal is to identify what should stay, what should be rewritten, and what old framing is now weaker than the new system model.

## Keep As-Is

These tasks still fit the new direction and should remain in the active backbone:

| Task IDs | Recommendation | Why |
|---|---|---|
| `T-013`, `T-001`, `T-002`, `T-004`, `T-003`, `T-014` @ `20260331T232739Z` | keep | Home resilience and safe maintenance/recovery are still the first priority for every future home and clone |
| `T-001` … `T-006` @ `20260328T142659Z` | keep | Restructure still removes path/import debt that will poison clone/install and embodiment work otherwise |
| `T-002` … `T-009` @ `20260401T195527Z` | keep | GlyphWeave studio loop is still the right artist-runtime foundation before deeper embodiment |
| `T-007`, `T-008`, `T-009`, `T-010`, `T-011`, `T-012`, `T-013`, `T-014`, `T-015` @ `20260331T210000Z` | keep but regroup under embodiment | These are embodiment-critical SenseWeave/audio/device tasks and should be sequenced beneath embodiment instead of floating as generic sensor work |
| `T-004` … `T-016` @ `20260329T183119Z` | keep but defer until embodiment spine is stable | Narrative engine is still important, but not ahead of studio loop + embodiment core |

## Rewrite

These tasks point at real needs, but their framing is too local, too old, or too broad compared with the updated home/clone/federation model:

| Task IDs | Recommendation | Rewrite Target |
|---|---|---|
| `T-016@20260327T234426Z` | rewrite | Replace “one-command rebuild of CypherClaw on Ubuntu” with queue-ready clone/install tasks from [prd-clone-and-home-creation.md](./prd-clone-and-home-creation.md) |
| `T-001`, `T-002`, `T-003`, `T-004` @ `20260329T205115Z` | rewrite | Reframe from ad hoc federation bootstrap into clone/home creation + lineage + announcement |
| `T-004@20260329T205115Z` | rewrite | Art sharing should move under publication surfaces + bundle exchange, not “send everything to peers” |
| `T-003`, `T-004` @ `20260327T234426Z` | rewrite/defer | Private-repo backup tasks should be reframed as home export/restore and release-snapshot packaging, not only git mirroring |

## Supersede

These existing federation tasks are based on the older “networked peers with broad collaboration” framing. They should be replaced by the new clone/identity/read/proposal/publication/bundle PRD family.

| Task IDs | Recommendation | Superseded By |
|---|---|---|
| `T-005` … `T-014` @ `20260329T205115Z` | supersede | [prd-federation-read-model.md](./prd-federation-read-model.md), [prd-federation-proposal-writes.md](./prd-federation-proposal-writes.md), [prd-publication-and-gallery-surfaces.md](./prd-publication-and-gallery-surfaces.md), [prd-bundle-exchange.md](./prd-bundle-exchange.md), [prd-instance-identity-and-lineage.md](./prd-instance-identity-and-lineage.md) |
| Existing [prd-federation.md](./prd-federation.md) task framing | supersede | New home/clone/federation/publication/bundle family |

## Defer

These tasks are still useful but should not outrun the new home/runtime/embodiment spine:

| Task IDs | Recommendation | Why |
|---|---|---|
| `T-007` … `T-013` @ `20260327T233208Z` | defer | Web platform should follow stable home/runtime, clone/install, and embodiment core rather than define them |
| `T-010`, `T-013`, `T-015` @ `20260327T172236Z` | defer | Rich art repository/gallery web work is valuable, but the studio loop, embodiment core, and publication surfaces come first |
| `T-012` … `T-020` @ `20260327T234426Z` memory/cost/project-health slice | defer | Useful operator layers, but not on the critical path to cloneable embodied homes |

## New Top-Level Work Missing From The Queue

The current root backlog does not yet represent these system-defining tracks clearly enough:

1. `Clone and Home Creation`
2. `Instance Identity and Lineage`
3. `Federation Read Model`
4. `Federation Proposal and Approval Writes`
5. `Publication and Gallery Surfaces`
6. `Bundle Exchange`
7. `Embodiment Core`
8. `Embodiment Interaction Loops`

These now deserve first-class PRD-driven loading rather than being implied by older federation or art tasks.

## Rebuild Rule

When an older task family is still mostly unimplemented, do not preserve the old framing just because it already exists in the queue.

Use this rule:

1. if the old family is already substantially built, finish or narrowly rewrite it
2. if the old family is mostly conceptual or partially stubbed, supersede it with the new queue-fit PRD family
3. before loading replacement work, run the new PRD through [prd-authoring-rules.md](./prd-authoring-rules.md) and `sdp-cli analyze --validate-only`

This is especially important for:

- old federation/bootstrap tasks
- older broad art repository tasks
- any cross-cutting embodiment epic that predates the new shared-state model

## Recommended Queue Reorder

1. Finish the remaining `Home Resilience` slice.
2. Finish `Restructure`.
3. Finish `GlyphWeave Studio Loop`.
4. Pull the embodiment-critical SenseWeave/device tasks forward.
5. Load and execute `Embodiment Core`.
6. Load and execute `Embodiment Interaction Loops`.
7. Resume deeper `GlyphWeave Art Studio`, `Narrative Engine`, and `Pet System v2` work in service of the embodied organism.
8. Load `Publication and Gallery Surfaces`.
9. Load and execute `Clone and Home Creation`.
10. Load and execute `Instance Identity and Lineage`.
11. Load `Federation Read Model`.
12. Load `Federation Proposal and Approval Writes`.
13. Load `Bundle Exchange`.
14. Revisit web platform and later expansion work afterward.

## Live Queue Action

To make the art-first reorder real in the current queue:

1. keep `Home Resilience`, `Restructure`, `GlyphWeave Studio Loop`, `Embodiment`, `GlyphWeave Art Studio`, `Narrative`, `Pet System v2`, and `Publication` active
2. freeze the currently loaded `Clone and Home Creation`, `Instance Identity and Lineage`, `Federation Read Model`, `Federation Proposal and Approval Writes`, and `Bundle Exchange` batches
3. unfreeze those deferred batches only after the local organism and publication surfaces are meaningfully built

## Practical Rule

If a task helps build:
- a reproducible sovereign home
- the artist runtime
- the embodied organism
- clone/install
- federation/publication with sovereignty

then it belongs in the new active spine.

If it is a richer surface around those things, it should wait until the new spine is stable.
