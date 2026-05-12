# CypherClaw Execution Roadmap

This roadmap reframes PromptClaw around the system it is actually becoming:

1. a reproducible sovereign home
2. an artist runtime
3. an embodied art organism
4. a cloneable descendant system
5. a federation of read-visible, write-sovereign homes
6. a private-by-default gallery/publication layer

## Non-Negotiable Rules

1. Do not schedule surface polish ahead of home/runtime authority.
2. Do not let clone/install outrun resilience and restructure.
3. Do not let federation outrun identity, sovereignty, and explicit approval.
4. Do not build embodiment loops on top of ad hoc state models.
5. Do not let publication leak private memory, raw logs, or secrets.

## Execution Spine

| Stage | PRD | Why it is here | Unlocks |
|---|---|---|---|
| 1 | [prd-home-resilience.md](./prd-home-resilience.md) | Durable state, safe maintenance, safe reboot, continuous queue | Every future home |
| 2 | [prd-restructure.md](./prd-restructure.md) | Stable imports, packaging, service paths | Reliable installs, cloneability, reusable services |
| 3 | [prd-glyphweave-studio-loop.md](./prd-glyphweave-studio-loop.md) | Fast artist iteration, context, compaction, source maps, fixtures | Better art, better embodiment iteration |
| 4 | [prd-embodiment-core.md](./prd-embodiment-core.md) | Shared organism state, sensor contract, dual-display runtime, rehearsal | Face + gallery organism |
| 5 | [prd-embodiment-interaction-loops.md](./prd-embodiment-interaction-loops.md) | MIDI, typewriter, camera, Theramini, ambient response loops | Playable embodied interaction |
| 5.5 | [prd-artist-plan-completion.md](./prd-artist-plan-completion.md) | Visitor identity, physical output, gallery exhibition, room acoustics, story covers | Complete local organism |
| 6 | [prd-glyphweave-art-studio.md](./prd-glyphweave-art-studio.md) | Larger autonomous art pipeline on top of a better studio/runtime | Volume art generation |
| 7 | [prd-narrative-engine.md](./prd-narrative-engine.md) | Story and symbolic continuity for the embodied organism | Richer long-cycle identity |
| 8 | [prd-pet-system-v2.md](./prd-pet-system-v2.md) | Pet/personality depth in service of the organism | Stronger identity continuity |
| 9 | [prd-publication-and-gallery-surfaces.md](./prd-publication-and-gallery-surfaces.md) | Private-by-default gallery surfaces, explicit publish, read-only public mode | Shareable home galleries |
| 10 | [prd-clone-and-home-creation.md](./prd-clone-and-home-creation.md) | Reproducible home creation, unattended install, clone flow | New homes, remote installs, clean bootstrap |
| 11 | [prd-instance-identity-and-lineage.md](./prd-instance-identity-and-lineage.md) | Unique identity, naming, clone inheritance, divergence semantics | Clone continuity, provenance, federation trust |
| 12 | [prd-federation-read-model.md](./prd-federation-read-model.md) | Read-visible descendants/peers, announcements, revocable read trust | Safe network presence |
| 13 | [prd-federation-proposal-writes.md](./prd-federation-proposal-writes.md) | Cross-home mutation as proposal + target approval | Sovereign cooperation |
| 14 | [prd-bundle-exchange.md](./prd-bundle-exchange.md) | Gift bundles, mounted-first imports, provenance | Artistic exchange between homes |

## Immediate Priority Slice

These items are the current P0/P1:

1. Finish the remaining `Home Resilience` slice.
2. Finish `Restructure`.
3. Finish the `GlyphWeave Studio Loop`.
4. Pull the embodiment-critical SenseWeave/device tasks under `Embodiment Core`.
5. Execute `Embodiment Core` and `Embodiment Interaction Loops`.
6. Resume deeper art/narrative/pet work before clone and federation.

## Existing PRDs That Should Be Deferred

These remain important, but they should not outrun the new spine:

- [prd-web-platform.md](./prd-web-platform.md)
- [prd-proactive-intelligence.md](./prd-proactive-intelligence.md)
- [prd-local-llm-integration.md](./prd-local-llm-integration.md)
- [prd-federation.md](./prd-federation.md) as a primary loading source

## Relationship to the Current Queue

The live root-task backlog still contains useful work, but it was authored against an older model:

- home resilience work largely still stands
- restructure work still stands
- GlyphWeave studio-loop work still stands
- old federation tasks need to be superseded by clone/identity/read/proposal/publication/bundle work
- embodiment-critical SenseWeave/device tasks need to be regrouped under the new embodiment spine

Use [task-audit-20260402.md](./task-audit-20260402.md) as the migration guide from the current backlog to the revised one.

## Task Loading Guidance

When turning this roadmap into `sdp-cli` work:

1. keep art-runtime and embodiment work ahead of clone/federation work once resilience and restructure are stable
2. load embodiment core before deeper interaction loops
3. keep publication separate from federation write logic
4. defer clone/install, identity, and federation until the local art organism is strong enough to justify replication
5. keep bundle exchange separate from core federation transport
6. author every requirement as one surface, one primary verb, one measurable outcome

Use [prd-authoring-rules.md](./prd-authoring-rules.md) as the PromptClaw-specific queue-fit guide before loading any new PRD.

## Definition of Success

The roadmap is succeeding when:

1. A new PromptClaw home can be installed or cloned reproducibly.
2. Every home has a unique identity and clear lineage.
3. The artist runtime makes iteration, replay, and calibration easy.
4. The embodied organism feels coherent across face, gallery, text, sound, and motion.
5. Federation gives visibility by default but preserves sovereignty for every write.
6. Public sharing is deliberate, private-by-default, and aesthetically strong.
