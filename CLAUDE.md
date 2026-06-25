# PromptClaw — Claude Code Project Context

## Project Identity

```yaml
name: PromptClaw
one_liner: "Markdown-first, artifact-driven multi-agent orchestrator with coherence enforcement. Originally an OpenClaw agent clone; now a Cascadian Tech lead product."
audience: "developers / teams running multi-agent AI workflows"
status: active
business_role: lead_product
revenue_stage: pre_revenue
tags: [ct_business, ai_infra]
related_projects: [cypherclaw, CTMarketing]
license: Proprietary
```

## Notes for agents

- PromptClaw is a CT lead product. Treat work here as product work, not
  experimentation.
- It's the engine behind CTMarketing (CTMarketing is a configured PromptClaw
  instance, per CTMarketing's own CLAUDE.md).
- Coherence enforcement is core; don't bypass it.
- Two local working copies exist (`~/Programming/PromptClaw/` and
  `~/Programming/AIClassClawHelper/`) sharing the same `exquest/PromptClaw`
  remote. Anthony has confirmed these are the same project.

## Code Review (`sdp-cli review`)

The `sdp-cli` framework includes a multi-agent code-review loop. Findings are
operator-gated, and agent findings must survive cross-model adversarial
verification before they can drive a fix — nothing bypasses the test-suite gate.

- `sdp-cli review run --since main` — review changed files (static, fast). Add
  `--panel` for the cross-model agent panel (live LLM calls; bound cost with
  `--max-regions`).
- `sdp-cli review findings --status confirmed` — list tracked findings.
- `sdp-cli review approve --all --min-severity high` — batch-approve confirmed
  findings into scoped fix tasks (or pass explicit `RF-…` ids); `--dry-run` previews.
- `sdp-cli review pr-comment` — render findings as a GitHub PR comment
  (preview-only by default; `--post` to actually comment).
- `sdp-cli review loop --since main` — converge: re-review until clean.
- `sdp-cli review score` — the code_quality signal the confirmed findings produce.
