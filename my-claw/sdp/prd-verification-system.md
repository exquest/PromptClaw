# PRD: Universal Verification System — Lead/Verify Everything

## Overview

Extend the sdp-cli lead/verify pattern to ALL meaningful CypherClaw operations — not just pipeline tasks. Every code change, risky action, and significant response goes through a verification cycle with cross-provider agents. Risk-tiered: low-risk actions skip verification, medium-risk get async background checks, high-risk get full lead/verify/fix cycles. When verification fails after 3 rounds, the self-healing system takes over. If self-healing fails, escalate to Anthony.

**Depends on:** `prd-model-awareness.md` (model selector for provider rotation), `prd-agent-runtime-substrate.md` (shared execution and streaming layer), `prd-capability-approval-framework.md` (explicit action classes and approval gates), `prd-server-optimization.md` (auto-recovery)

## Execution Role

This is **Stage 6** of the execution spine.

Its immediate scope is not "verify everything on day one." The foundation slice is:

1. local risk classification
2. cross-provider verifier selection
3. code-change gates
4. emergency bypass rules
5. self-healing handoff

Broader async correction flows and approval UX should be scheduled after those basics are stable.

## Design Principles

1. **Different provider verifies** — if Claude leads, Codex or Gemini verifies. Same provider acceptable only as fallback (different model: opus leads, sonnet verifies).
2. **Risk-tiered** — not everything needs verification. Classify first, verify proportionally.
3. **Async for medium-risk** — send the response immediately, verify in background, correct if needed.
4. **Fix until it works** — code changes must pass syntax, tests, lint, AND runtime validation before committing.
5. **Self-healing before escalation** — verification failure → auto-fix cycle (3 rounds) → self-healer → escalate to Anthony as last resort.

## Risk Classification

| Risk Level | Examples | Verification | Speed |
|-----------|----------|-------------|-------|
| **None** | Pet interactions (/feed, /play), status checks (/health, /status, /pets), simple acknowledgments | Skip | Instant |
| **Low** | Casual chat responses, short answers, informational queries | Skip | Instant |
| **Medium** | Technical advice, code snippets in chat, architecture recommendations, responses referencing files/commands, anything where lead self-rates low/medium confidence | Async background verify — send response, check after, correct if wrong | Immediate response, correction within 30s |
| **High** | Code commits, file modifications, config changes, PR creation, service restarts, deployments, database modifications | Full lead/verify/fix cycle BEFORE action | 1-5 minutes |
| **Critical** | Production deployments, data deletion, security changes, changes to other people's projects, spending above budget | Lead/verify + Anthony approval | Minutes + human approval |

## Requirements

| ID | Description | Priority | Tier | Acceptance Criteria |
|---|---|---|---|---|
| VER-001 | Create `tools/risk_classifier.py` that classifies every action into risk levels (none/low/medium/high/critical). Classification uses: (a) action type (reply, code_change, shell_command, deployment, config_change), (b) target (own codebase, production server, external service, other people's repos), (c) lead agent's self-rated confidence (parsed from response metadata or estimated from response length/complexity), (d) category matching (technical advice, code snippets, and file references → medium; commits and restarts → high). Classification is local (no LLM call) using keyword matching and rule engine. | MUST | T2 | - All 5 risk levels assignable<br/>- Classification runs in <10ms (no LLM call)<br/>- Action type detection works for all daemon step types<br/>- Confidence estimation from response characteristics<br/>- Category matching for technical content<br/>- Classification logged to Observatory |
| VER-002 | Create `tools/verification_engine.py` — the core verify/fix loop. Interface: `verify(action, lead_output, risk_level) -> VerifyResult`. For medium-risk: spawns async background verification, returns immediately. For high-risk: blocks until verification completes. Verify process: (a) select verifier agent (different provider preferred, same provider different model acceptable), (b) send lead output + action context to verifier with structured prompt, (c) verifier returns: PASS, PASS_WITH_NOTES, or FAIL with specific issues, (d) on FAIL: send issues back to lead for fix, re-verify. Max 3 rounds. | MUST | T3 | - Async verification for medium-risk<br/>- Blocking verification for high-risk<br/>- Cross-provider verifier selection<br/>- 3-round fix cycle<br/>- PASS/PASS_WITH_NOTES/FAIL verdicts<br/>- Round history preserved for debugging |
| VER-003 | Integrate verification into daemon step execution. Modify the step execution loop in `cypherclaw_daemon.py`: after each step completes, classify risk. For medium-risk reply steps: send response to user immediately, start async verify. If verifier flags issues, send a follow-up correction message ("Actually, let me correct that — ..."). For high-risk steps (agent code changes, shell commands, dev_tasks): run lead/verify/fix BEFORE executing/sending. | MUST | T3 | - All daemon steps classified before/after execution<br/>- Medium-risk replies get async background verify<br/>- Corrections sent as follow-up messages<br/>- High-risk steps blocked until verified<br/>- None/low risk steps execute unchanged<br/>- No noticeable latency for low-risk actions |
| VER-004 | Implement the code change verification pipeline. When any agent produces code changes (detected by git diff in the working directory): (a) syntax check — `python3 -c "import ast; ast.parse(code)"`, (b) test run — `.venv/bin/pytest tests/ -x` if tests exist, (c) lint — `.venv/bin/ruff check` on changed files, (d) runtime validation — import the changed module to verify no runtime errors, for art generation verify Canvas renders, for daemon changes verify the daemon can start. ALL gates must pass. On failure: feed specific error back to lead, lead fixes, re-run gates. Max 3 fix rounds. | MUST | T2 | - Syntax check catches parse errors<br/>- Tests run and must pass<br/>- Lint check runs on changed files<br/>- Runtime import check for Python modules<br/>- Canvas render validation for art code<br/>- Daemon import check for daemon changes<br/>- 3-round fix cycle on failure<br/>- Gate results logged |
| VER-005 | Implement async correction for medium-risk responses. When background verification flags an issue with a response already sent: (a) generate a correction using the verifier's feedback, (b) send it as a follow-up message: "🔍 *Correction*: [corrected information]", (c) log the correction event to Observatory (tracks how often corrections happen per agent/topic). If the original response was fine, do nothing (no "verified" confirmation to avoid noise). | MUST | T2 | - Corrections sent within 30s of original response<br/>- Only sent when verifier flags actual issues<br/>- No noise for verified-correct responses<br/>- Correction rate tracked in Observatory<br/>- Works for both Telegram and web platform |
| VER-006 | Integrate with self-healing on verification failure. When the 3-round fix cycle exhausts without passing: (a) pass the failure context to `healer.py` with severity NOTIFY, (b) healer attempts: retry with a different lead agent, try a simpler approach, or decompose the task. (c) If healer succeeds, proceed. (d) If healer fails, escalate to Anthony via Telegram/web with: what was attempted, what failed, what the agents disagree on, and a recommended action. | MUST | T2 | - Failed verifications route to healer<br/>- Healer tries alternate approaches<br/>- Successful heal proceeds normally<br/>- Failed heal escalates to Anthony<br/>- Escalation includes full context and recommendation<br/>- Escalation visible on web platform |
| VER-007 | Implement critical-risk approval flow. For critical actions (production deployments, deletions, security changes, cross-project changes): after lead/verify passes, STILL require Anthony's explicit approval. Send approval request to Telegram with inline buttons (Approve/Reject) and web platform with approval UI. Timeout after 24 hours with reminder at 4h and 12h. If rejected, log reason and do not proceed. | SHOULD | T2 | - Critical actions blocked until approved<br/>- Approval request sent to Telegram + web<br/>- Inline approve/reject buttons in Telegram<br/>- 24h timeout with reminders<br/>- Rejection logged with reason<br/>- Approval audit trail in Observatory |
| VER-008 | Create verification prompts optimized for each risk tier. Medium-risk verify prompt: concise, focused on factual accuracy and safety ("Is this advice correct? Any dangerous recommendations?"). High-risk verify prompt: thorough, checks correctness, completeness, security, and unintended side effects ("Review this code change for bugs, security issues, and regression risk"). Critical verify prompt: adversarial, explicitly tries to find problems ("What could go wrong? What edge cases are missed? Is this safe for production?"). Store prompts in `tools/verification_prompts/`. | MUST | T1 | - 3 verification prompt templates (medium/high/critical)<br/>- Medium: concise factual check<br/>- High: thorough code/action review<br/>- Critical: adversarial fault-finding<br/>- Prompts include context injection points<br/>- Prompts tested with sample inputs |
| VER-009 | Add verification metrics to Observatory and web dashboard. Track: verification rate (% of actions verified), pass rate (% that pass first try), correction rate (% of medium-risk responses corrected), fix cycle count (avg rounds to pass), escalation rate (% that reach Anthony), provider agreement rate (how often lead and verify agree). Display on web platform as a "Quality" section. | SHOULD | T2 | - All 6 metrics tracked in Observatory<br/>- Queryable by time period and agent<br/>- Web dashboard Quality section<br/>- Daily/weekly trends visible<br/>- Per-agent verification performance |
| VER-010 | Add confidence self-rating to agent responses. Modify the agent prompt (AGENT_CONTEXT) to instruct agents to end responses with a confidence tag: `[confidence: high/medium/low]`. Parse this from agent output to feed into risk classification. If agent doesn't include the tag, estimate confidence from: response length (shorter = lower for complex questions), hedging language ("I think", "probably", "I'm not sure"), and whether the response includes code/commands (higher risk = lower default confidence). | SHOULD | T2 | - AGENT_CONTEXT instructs confidence tagging<br/>- Parser extracts confidence from output<br/>- Fallback estimation when tag missing<br/>- Confidence feeds into risk_classifier<br/>- Confidence logged per response |
| VER-011 | Implement verification bypass for time-sensitive actions. Some actions can't wait for verification: I/O guard kills, health check auto-maintenance, emergency restarts. Create a whitelist of action types that bypass verification entirely. These still get logged to Observatory for post-hoc review but execute immediately. | MUST | T1 | - Whitelist of bypass-able actions defined<br/>- Emergency actions execute immediately<br/>- Bypassed actions logged for post-hoc review<br/>- Whitelist is configurable<br/>- Self-healing actions always bypass |

## Verification Flow

```
Action triggered
    │
    ▼
Risk Classifier (VER-001)
    │
    ├─ None/Low → Execute immediately, no verification
    │
    ├─ Medium → Execute immediately
    │           └─ Async: Verify in background (VER-002)
    │               ├─ PASS → Done (no message)
    │               └─ FAIL → Send correction (VER-005)
    │
    ├─ High → Lead produces output
    │         └─ Verify (different provider) (VER-002)
    │             ├─ PASS → Execute
    │             └─ FAIL → Fix cycle (max 3 rounds) (VER-004)
    │                 ├─ Fixed → Execute
    │                 └─ Exhausted → Self-healer (VER-006)
    │                     ├─ Healed → Execute
    │                     └─ Failed → Escalate to Anthony
    │
    └─ Critical → Lead produces output
                  └─ Verify (different provider)
                      ├─ PASS → Request Anthony approval (VER-007)
                      │         ├─ Approved → Execute
                      │         └─ Rejected → Cancel + log
                      └─ FAIL → Fix cycle → Self-heal → Escalate
```

## Verifier Selection Logic

```python
def select_verifier(lead_agent: str, lead_provider: str) -> str:
    """Select verification agent — different provider preferred."""
    providers = {
        "anthropic": ["claude"],
        "openai": ["codex"],
        "google": ["gemini"],
        "local": ["local-qwen", "local-gemma"],
    }

    # Prefer different provider
    other_providers = [p for p in providers if p != lead_provider]
    for provider in other_providers:
        agents = providers[provider]
        # Pick agent with highest verify fitness
        best = max(agents, key=lambda a: get_verify_fitness(a))
        if is_available(best):
            return best

    # Fallback: same provider, different model
    if lead_agent == "claude":
        return "claude-sonnet"  # opus led, sonnet verifies
    if lead_agent == "codex":
        return "codex-spark"    # gpt-5.4 led, spark verifies

    # Last resort: same agent (should never happen with 3+ providers)
    return lead_agent
```

## Success Metrics

| Metric | Target |
|--------|--------|
| Verification coverage | >95% of high/critical actions verified |
| First-pass rate | >70% of verified actions pass on first try |
| Correction rate | <10% of medium-risk responses need correction |
| Fix cycle efficiency | Avg <2 rounds to pass (of 3 max) |
| Escalation rate | <5% of verified actions reach Anthony |
| Verification latency (medium) | <30s for async correction |
| Verification latency (high) | <3 min for full cycle |
| False positive rate | <5% of corrections are unnecessary |
| Emergency bypass accuracy | 100% of emergencies execute without delay |
