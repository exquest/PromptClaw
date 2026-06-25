# Coherence

PromptClaw coherence is the runtime layer that keeps multi-agent work aligned
across runs. It records durable decisions, holds unresolved tensions visibly,
evaluates the project constitution, updates per-agent trust scoring, graduates
enforcement mode when the evidence supports it, and writes a re-entry digest for
the next session.

Start with [configuration-reference.md](configuration-reference.md#coherence)
for the `promptclaw.json` fields and [coherence-api.md](coherence-api.md) for
the external session API.

## Standing Protocol

Agent prompts get the standing protocol from
[protocol.py](../promptclaw/coherence/protocol.py). That file composes the
[Shadowland Field Guide](Shadowland2/final/field_guide.md) working protocol with
the block contract below. The protocol tells agents to separate stated facts,
inferences, assumptions, and unknowns; ask only material questions; and declare
durable decisions or unresolved contradictions only when they matter.

## Decision Blocks

Decision blocks are parsed by
[decision_capture.py](../promptclaw/coherence/decision_capture.py) and stored as
active architectural decisions. Active decisions are injected into later prompts
as constraints.

````markdown
```decision
title: Use SQLite for local coherence state
what: Store event, decision, tension, trust, and graduation state in one local SQLite database.
context: Default installs must work without external services.
rationale: SQLite keeps the default path dependency-light and inspectable.
unlocks: one-command init; local replay; portable demos
constrains: local runs must preserve .promptclaw/coherence.db; PostgreSQL remains optional
files: promptclaw/coherence/engine.py, docs/configuration-reference.md
tags: coherence, persistence
```
````

Use a block only for a durable choice that future work should honor. Routine
steps, temporary observations, and ordinary implementation notes should stay out
of the decision store.

## Tension Blocks

Tension blocks are parsed by
[tension_capture.py](../promptclaw/coherence/tension_capture.py). A tension is a
real contradiction that should remain visible instead of being silently collapsed
or prematurely resolved.

````markdown
```tension
statement: Local-first defaults vs. shared multi-host enforcement
state: Local SQLite is the default; PostgreSQL is available for coordinated hosts.
resolves: A deployment needs concurrent hosts sharing one coherence event store.
between: docs/configuration-reference.md, promptclaw/coherence/engine.py
```
````

Open tensions are injected into future prompts under the active-tensions context.
They should name what evidence or decision would resolve the contradiction.

## Re-entry Digest

[reentry.py](../promptclaw/coherence/reentry.py) renders the re-entry digest and
the engine writes it to `.promptclaw/reentry.md` on finalize. The digest is the
current "read this first" artifact: where the last run ended, which decisions
are live, which tensions remain open, and what to inspect before resuming.

## Trust And Graduation

[trust.py](../promptclaw/coherence/trust.py) keeps per-agent trust scoring in the
coherence database. A compliant action earns a small reward; soft violations and
hard violations apply penalties; agents below the restriction threshold can be
deprioritized by routing.

[graduation.py](../promptclaw/coherence/graduation.py) promotes enforcement mode
when observations show the rules are working. `monitor` records without
blocking, `soft` blocks hard violations, and `full` blocks any violation.
`auto_graduate=false` freezes the configured mode.

## Constitution Tiers

Constitution rules have two separate axes:

- `severity`: `hard` or `soft`, which controls when a violation blocks.
- `tier`: `foundation` or `formula`, which controls how load-bearing the rule is.

A `foundation` rule is fixed by deliberate human amendment. Changing one is a
"recut, don't grandfather" event: dependent decisions and generated outputs
should be rechecked against the new foundation instead of assumed valid. A
`formula` rule is adjustable operational guidance inside the foundation.
