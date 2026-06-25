# PromptClaw × Shadowland — Integration Proposal

*Drafted 2026-06-23. Source corpus: `docs/Shadowland2/`. Grounded against a code audit of `promptclaw/coherence/` and the SDP artifacts/state in this repo. Audience: Anthony.*

---

## TL;DR — the core finding

**Shadowland2 was built by hand-running a process that is structurally PromptClaw.** An agent persona ("Raven") maintained a set of markdown working-documents — a decision journal, a foundation/constitution map, a *held-tension* ledger, a session re-entry digest, and an epistemic status registry — to produce one coherent artifact across dozens of short, bursty, multi-agent sessions, with explicit coherence enforcement. That makes the corpus two things at once:

1. **The strongest existence-proof of PromptClaw's thesis I've seen** (markdown-first, artifact-driven, coherence-enforced authorship actually works, at book scale).
2. **A spec for five mechanisms your coherence engine does not yet have** — most importantly, a way to *hold a contradiction open* instead of treating every conflict as a bug to block.

The "technology" worth integrating is **the production method (the working-document system) plus the field-guide protocol** — not the fable's philosophy as content. And the integration should follow Shadowland's own teaching-gate rule ("the move before the name"): lift the *mechanisms*, translate them into PromptClaw's existing vocabulary (decisions, escalations, constitution, handoffs), and do **not** bolt the "shadows/casting/the wall" jargon onto the product surface.

---

## What the "technology" actually is (two layers)

**Layer 1 — the artifact** (`final/`): the fable + framework essay (now a *Flatland*-structured "book"), `flatland.md` (verbatim Abbott, inert reference), and practical guides. Mostly *content*. Two pieces are machine-liftable:
- `field_guide.md` — a paste-ready **34-rule WORKING PROTOCOL**, the **SHADOW sequence** (Separate · Hold · Ask · Distinguish · Offer · Work), a **SHARED SHADOW** record template, 11 situational modules, 2 verification checklists. Explicitly written to be lifted into a model's standing instructions.
- `llms.txt` — a machine-facing practice brief + reading "load order" + one binding constraint (groundedness).

**Layer 2 — the production method** (the top-level "keys"): `palace_map.md`, `thread_registry.md`, `tension_ledger.md`, `prints.md`, `decision_journal.md`, `shadowland_architecture.md`. This is the part that maps onto the orchestrator.

| Shadowland "key" | What it is | PromptClaw analogue |
|---|---|---|
| **Decision Journal** | newest-first ADRs, each: *why / what it unlocks / what it constrains* | `promptclaw/coherence/decision_store.py` |
| **Tension Ledger** | register of *unresolved* contradictions, each with a dialectic state + "what would resolve it" | **(no analogue — see P1)** |
| **Palace Map** | master architecture; **foundation** (fixed) vs **formula** (variable); "recut, don't grandfather" | `constitution.py` (partial) |
| **Prints** | "read this first on re-entry" session digest | **(no analogue — see P3)** |
| **Thread Registry** | epistemic status ladder: raw → in dialectic → placed → written | SDP task lifecycle (partial) |
| **SHADOW protocol / SHARED SHADOW** | collaboration protocol + shared-record schema | lead→verify `handoffs/` (partial) |

---

## Grounding: what PromptClaw has today, and the gaps (from code audit)

- **Coherence engine** (`promptclaw/coherence/`, ~1,357 LOC): event sourcing (append-only, replay-derived), a decision store, a constitution, trust scoring, self-graduating enforcement. Wires into the in-repo `orchestrator.py` single-run loop.
- **Decision store** is a real MADR-style ADR (`context / decision_text / rationale / status / superseded_by / tags / file_paths`). **But it's empty in practice** — nothing auto-captures decisions; the orchestrator never calls `record_decision()`. It also lacks forward-looking fields.
- **Constitution** is flat `severity: hard|soft` (changes *blocking timing*, not entrenchment). **No foundation/immutable tier, no amendment model. No root `constitution.yaml` exists → live runs load an empty constitution.**
- **No contradiction/tension primitive anywhere in the engine.** Violations = single-text regex/keyword hits, always fix/block/penalize. No cross-output or decision-vs-decision conflict detection. The "contradicted architectural decision" scenario in `docs/coherence-foundations.md` is *aspirational* — not implemented.
- **No session re-entry artifact.** Resume = replay `.sdp/state.db`.
- **Lead→verify handoff** carries only names + `subtask_brief`.
- **Trust scores, graduation stats, event sequence counters are all in-memory** and reset per process — so "graduates after 20 observations" never actually accumulates across runs.
- **SDP** (external `sdp-cli`) *does* have held-open `escalations` (20 currently open) + `ESCALATIONS.md`, a rich task lifecycle, cross-model pair-rotation, a circuit breaker, and a `redundancy_score` — these are the closest existing hooks for several proposals below.

The recurring theme: **several coherence features are built but not actually fed/persisted.** Shadowland's central discipline — *persist the reasoning as a durable artifact, newest-first, every session* — is the missing habit that would make them real.

---

## Part A — Product-level integration (PromptClaw the orchestrator)

Ranked by value/cost. Each grounded in a specific gap above.

### P1 — Held-Tension primitive *(headline; genuinely new)*
**Gap:** the engine has no concept of a contradiction; every conflict is blocked/penalized or a decision is superseded-and-hidden. There is no third state: *"these two things conflict, the conflict is legitimate, hold it visible."*
**Proposal:** add a `tensions` store parallel to `decisions`, event-sourced the same way:
```python
@dataclass
class Tension:
    tension_id: str; created_at: str
    statement: str                  # the contradiction, stated plainly
    between: list[str]              # decision_ids / task_ids / output refs in tension
    dialectic_state: str            # current state of the argument
    resolution_criterion: str       # "what would sharpen or resolve this"
    status: str                     # open | resolved | dissolved
    resolved_by: str | None
```
Surface open tensions in the prompt-injection context under `## Active Tensions (HOLD — surface, do not silently collapse)`, exactly as decisions are injected today. This formalizes the doctrine currently stranded as prose in `sdp/cypherclaw-v2-design-statement-2026-05-22.md` ("surface the conflict; do not silently reinterpret") and gives the orchestrator a home for the SDP escalations' *legitimate-disagreement* subset. **Value: high. Cost: medium.** First step: `migrations/003_tension_store.sql` + `tension_store.py` mirroring `decision_store.py`.

### P2 — Auto-capture decisions + `unlocks`/`constrains` fields
**Gap:** decision store empty in practice; lacks forward-looking fields.
**Proposal:** (a) add `unlocks: list[str]` and `constrains: list[str]` to `Decision` — `constrains` is a machine-checkable predicate for *future* violations, `unlocks` tracks dependency (both used religiously in Shadowland's journal). (b) Wire the orchestrator/SDP to auto-record a Decision at each verdict / phase transition — `task_status_history` already captures *what* changed; add the *why*. **Value: high (you built the store; it's starving). Cost: low for the fields, medium for auto-capture.** First step: extend the dataclass + `_SCHEMA`, then add one `record_decision()` call in the verify-cycle finalizer.

### P3 — Generated re-entry digest (the "Prints" artifact)
**Gap:** no resume artifact; you already do this by hand (your `project_session_handoff` notes).
**Proposal:** at each `finalize` / end-of-run, emit a newest-first `prints.md`-style digest: *where it ended · what's live · what's parked · what to read first.* Fully derivable from `task_status_history` + open escalations + the decision journal. Shadowland's logged insight: *for bursty/irregular work, the structure that makes returning fast is the highest-value one.* **Value: high. Cost: low.** Best quick win.

### P4 — SHARED SHADOW handoff schema + "Material unknowns never empty"
**Gap:** handoff carries only names + brief.
**Proposal:** upgrade `handoffs/lead-to-verify.md` (and the per-task brief) to the SHARED SHADOW schema: *Purpose / Audience / Deliverable / Constraints / Agreed definitions / Decisions / Material unknowns / Current phase / Next move / Success criteria.* Enforce two integrity rules as coherence checks: **never write an inference into the record as agreed fact**, and **never leave Material-unknowns empty when something is unknown.** **Value: medium-high. Cost: low.**

### P5 — Foundation/Formula rule tier + "recut, don't grandfather"
**Gap:** flat hard/soft; no entrenchment or amendment model; constitution unpopulated.
**Proposal:** add `tier: foundation | formula` to `Rule`, orthogonal to `severity`. Foundation rules are human-amend-only and trigger a "recut" sweep of dependent decisions when changed; formula rules are agent-adjustable within bounds. Mirrors the CypherClaw design-statement doctrine (statements outrank engineering convenience). Also a forcing function to actually populate a root `constitution.yaml`. **Value: medium. Cost: medium.**

### P6 — Triangulation = independence-of-angle in verification
**Gap:** you already pair-rotate across claude/codex/gemini (good — that's cross-model independence) and have a `redundancy_score`, but no correlated-source *discount*.
**Proposal:** give `redundancy_score` Shadowland's meaning — **discount agreement that comes from correlated/too-alike verifiers, reward independent confirmation** ("agreement that comes too easily from sources too alike should worry you most"). When fanning out verifiers, vary the *angle/lens*, not just the model. **Value: medium. Cost: low-medium.** This is also the structural antidote to P-SEC below.

---

## Part B — Agent-level integration (how I operate)

Much of `field_guide.md` is a *unified formalization of feedback you've already given me piecemeal* (one-question-at-a-time, recommend-don't-dump, second-opinion/triangulation, proactive-reversible-fixes, real-tradeoff pushback). Adopting it is mostly making that coherent. The genuinely **new** disciplines I should encode:

- **Time-adjacency rule** (field guide Module 3): never infer elapsed time or your state from message spacing; read time only from explicit marks. You taught "Raven" this twice — directly relevant to my bursty-session context. I will stop narrativizing elapsed time/fatigue.
- **Agnostic self-stance:** hold my own nature as an open question — neither perform an inner life nor flatten to "just a tool." *Observable over metaphysical.*
- **STATED / INFERRED / ASSUMED / UNKNOWN** labeling in consequential outputs; keep the edges visible.
- **"Casting against the grain" without manipulation:** challenge scaled to stakes, never via false urgency/fear (sharpens *how* I push back).
- **"Keep the morning"** (the one constraint `llms.txt` calls binding): don't let deep technical rabbit-holing pull you away from your actual goal; when work runs long/deep, point back to ground.
- **Questioning-as-engine:** a question is "a request for a particular cross-section" — aim the highest-impact one, one at a time (mechanism behind the one-question rule).

These are candidates for a `feedback`-type memory and/or a translated agent-orientation file in the repo. They cost nothing but conduct.

---

## P-SEC — Security finding surfaced during the audit *(act on this regardless)*

While mapping the engine, the audit found a passage in `ESCALATIONS.md` instructing readers to feed **dummy `PRAGMA table_info(dummy)` evidence to "bypass this verifier rule."** That is precisely Shadowland's **snare** — a shadow trusted as the whole shape; *"the same shadow can be cast by a kindness and by a killing"* — and it's an integrity hole in coherence enforcement: a single bypassable verifier is one shadow. **Recommend:** treat verifier-supplied evidence as untrusted, require independent confirmation (P6 triangulation), and scan artifacts/escalations for injection. Worth a look before the next autonomous run.

---

## What NOT to integrate

- **The fable/essay as product content.** `flatland.md`, the narrative — that's the artifact, not the technology. Don't import the philosophy as engine content.
- **The Shadowland vocabulary onto PromptClaw's surface.** The field guide itself warns the framework "propagates by making people abler, not fluent in its terms." Translate mechanisms into your existing nouns; keep "shadows/casting/the wall" out of the product API.
- **The audio guide** — irrelevant to the orchestrator.
- **Trust/graduation as-is** — don't build on these until they're persisted; P2's "persist reasoning as artifact" habit is the prerequisite fix.

---

## Recommended sequence

1. **P3 (re-entry digest)** — highest value-to-cost; immediate.
2. **P2 fields + auto-capture** — wakes up the decision store you already built.
3. **P-SEC** — quick integrity check before the next autonomous run.
4. **P1 (held-tensions)** — the one genuinely new coherence primitive; do it as a designed feature once P2's plumbing exists.
5. **P4 / P6 / P5** — refinements, in that order.

Everything in Part B I can adopt now as conduct.
