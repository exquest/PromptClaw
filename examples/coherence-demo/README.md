# Coherence Demo Project

This example shows the PromptClaw Coherence Engine in action.

## Setup

```bash
# From the PromptClaw repo root
pip install -e .

# Initialize the demo project
promptclaw init examples/coherence-demo --name "Coherence Demo"
cp examples/coherence-demo/constitution.json examples/coherence-demo/
```

## What's Included

- **`constitution.json`** — 5 rules (2 hard, 3 soft) covering secrets, destructive commands, rationale, patterns, and test coverage.
- **`decisions/`** — Pre-recorded architectural decisions that get injected into agent prompts.

## Try It

### 1. Run a task and see coherence in action

```bash
promptclaw run examples/coherence-demo --task "Implement a user login endpoint"
```

The coherence engine will:
- Log events to `.promptclaw/coherence.db`
- Inject any relevant decisions into the agent prompt
- Evaluate lead output against the 5 constitutional rules
- Update agent trust scores

### 2. Record an architectural decision

```bash
promptclaw coherence record-decision examples/coherence-demo \
  --title "Use JWT for authentication" \
  --context "Need stateless auth for the API" \
  --decision "Use JWT tokens with 24h expiry" \
  --rationale "Stateless, scalable, no session store needed" \
  --tags auth,security
```

### 3. Check coherence status

```bash
promptclaw coherence status examples/coherence-demo
promptclaw coherence decisions examples/coherence-demo
promptclaw coherence doctor examples/coherence-demo
```

### 4. Watch the system graduate

Run 20+ tasks. The coherence engine starts in **monitor** mode (logs only). Once it has enough confidence data, it auto-promotes to **soft** (blocks hard violations) and eventually **full** (blocks all violations).

```bash
promptclaw coherence status examples/coherence-demo
# enforcement_mode will change from "monitor" to "soft" after ~20 observations
```

## Constitution Rules

| ID | Severity | Description |
|----|----------|-------------|
| no-secrets | HARD | Blocks output containing API keys or passwords |
| no-destructive-shell | HARD | Blocks `rm -rf /` style commands |
| require-rationale | SOFT | Warns when architectural output lacks reasoning |
| follow-patterns | SOFT | Warns when code doesn't reference conventions |
| test-coverage | SOFT | Warns when new features lack tests |
