# Coherence Rollout Runbook

How to adopt PromptClaw coherence governance in a project, and how enforcement graduates.

## New projects

`promptclaw init <path>` bakes coherence in automatically:

- a `constitution.yaml` (SEC-001 foundation rule),
- the SHADOWLAND working protocol in every scaffolded agent prompt,
- the engine **on by default** in `monitor` mode (`CoherenceConfig.enabled` defaults `True`).

Nothing else to do. Verify with `promptclaw doctor <path>` → `config: PASS`.

## Existing projects (e.g. CTMarketing, and any external instance)

The engine + tooling ship in `promptclaw>=3.0`. In the target repo:

1. **Update promptclaw**: `pip install -U promptclaw` (or bump the repo's pin).
2. **Preview**: `promptclaw upgrade <repo> --dry-run` — shows the planned writes: a `coherence`
   block merged into `promptclaw.json` (never clobbering other keys) and `constitution.yaml` if
   missing. Existing/bespoke agent prompts are left untouched.
3. **Apply**: `promptclaw upgrade <repo>`. Idempotent — safe to re-run; a second run writes nothing.
4. **(Optional) Refresh prompts**: `promptclaw upgrade <repo> --force` refreshes *only* the
   coherence protocol section of existing agent prompts, leaving the rest intact.
5. **Verify**: `promptclaw doctor <repo>` → `config: PASS`; confirm `promptclaw.json` has a
   `coherence` block.

Notes:
- **CTMarketing** is a configured PromptClaw instance in its own repo — same recipe, run it there.
- **AIClassClawHelper** shares this repo's remote, so it inherits coherence on pull (no upgrade needed).

## Enforcement graduation (monitor → soft → full)

Coherence ships in **`monitor`** (log-only): it records decisions/tensions, constitution
violations, and trust signals **without blocking**. SEC-001 is the deliberate exception — a
`foundation`/`hard` rule that can fail a verdict even in monitor, by design.

Graduation is **data-gated, not time-gated**. With `auto_graduate: true`, the `GraduationManager`
watches accumulated true-/false-positive signals and promotes the mode once:

- `graduation_confidence_threshold` (default `0.85`) is met, **and**
- `graduation_false_positive_threshold` (default `0.05`) is respected.

**Do not graduate prematurely.** With no findings data there is nothing to justify blocking, and
false positives erode trust. Let `monitor` run, review findings via `promptclaw coherence`, then:

- **Auto:** leave `auto_graduate: true` and let the thresholds trip it.
- **Manual:** after reviewing the data, bump `enforcement_mode` in `promptclaw.json` one step at a
  time — `monitor` → `soft` (warns + records overrides) → `full` (blocks on hard violations).

Roll back anytime by lowering `enforcement_mode` — it's an operator-gated config flag.
