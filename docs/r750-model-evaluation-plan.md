# LLM Model Evaluation Plan — Dell PowerEdge R750, CPU-Only Multi-Agent System

**Hardware:** 2x Xeon Silver 4310 (24 physical cores), 813 GB DDR4, no GPU
**Runtime:** Dual Ollama instances (port 11434 on NUMA 0, port 11435 on NUMA 1)
**Purpose:** Select production models for 5 agent roles across PromptClaw (SDP workflow) and LG SoT (firewall migration platform)

---

## Table of Contents

1. [Pre-Evaluation Setup](#1-pre-evaluation-setup)
2. [Phase 1: Raw Performance Benchmarks (Day 1-2)](#2-phase-1-raw-performance-benchmarks-day-1-2)
3. [Phase 2: Tool Calling Reliability (Day 2-3)](#3-phase-2-tool-calling-reliability-day-2-3)
4. [Phase 3: Real Workload Testing (Day 3-5)](#4-phase-3-real-workload-testing-day-3-5)
5. [Phase 4: Concurrent Load Testing (Day 5-6)](#5-phase-4-concurrent-load-testing-day-5-6)
6. [Phase 5: Final Selection and Configuration (Day 6-7)](#6-phase-5-final-selection-and-configuration-day-6-7)
7. [Scoring Rubric](#7-scoring-rubric)
8. [Decision Matrix Template](#8-decision-matrix-template)
9. [Go/No-Go Criteria](#9-gono-go-criteria)
10. [Risk Register](#10-risk-register)

---

## 1. Pre-Evaluation Setup

### 1.1 Verify Dual-Ollama Topology

Confirm both instances are running with correct NUMA pinning:

```bash
# Check instance 0 (NUMA socket 0, port 11434)
OLLAMA_HOST=http://127.0.0.1:11434 ollama list

# Check instance 1 (NUMA socket 1, port 11435)
OLLAMA_HOST=http://127.0.0.1:11435 ollama list

# Verify NUMA pinning — each ollama-runner should be bound to its socket
ps aux | grep ollama
numactl --hardware
cat /proc/$(pgrep -f "ollama serve.*11434" | head -1)/status | grep Cpus_allowed_list
cat /proc/$(pgrep -f "ollama serve.*11435" | head -1)/status | grep Cpus_allowed_list
```

### 1.2 Pull All Candidate Models

Pull every model to both instances. This ensures fair comparison and avoids measuring first-pull overhead during benchmarks. Expect approximately 450 GB total disk usage for all candidates at Q4_K_M.

```bash
# Define all model tags
MODELS=(
  "qwen3.5:35b"
  "qwen3:30b-a3b"
  "qwen3-coder:30b"
  "qwen3-coder-next"
  "gpt-oss:120b"
  "gpt-oss:20b"
  "glm-4.7-flash"
  "gemma4:26b"
  "nemotron-cascade-2:30b"
  "nemotron-3-nano:30b"
  "lfm2:24b-a2b"
  "qwen3.5:122b"
  "nemotron-3-super:120b"
  "qwen3-embedding:8b"
)

# Pull to instance 0
for m in "${MODELS[@]}"; do
  OLLAMA_HOST=http://127.0.0.1:11434 ollama pull "$m"
done

# Instance 1 shares the same blob store — no re-download needed.
# Verify instance 1 can see them:
for m in "${MODELS[@]}"; do
  OLLAMA_HOST=http://127.0.0.1:11435 ollama show "$m" --modelfile > /dev/null 2>&1 \
    && echo "OK: $m" || echo "MISSING: $m"
done
```

### 1.3 Create the Benchmark Logging Directory

```bash
mkdir -p ~/eval/{phase1,phase2,phase3,phase4,results}
```

### 1.4 Install Measurement Tooling

```bash
# hyperfine for wall-clock timing, jq for JSON parsing
sudo apt install -y hyperfine jq bc

# A helper script for consistent ollama API calls with timing
cat > ~/eval/bench.sh << 'SCRIPT'
#!/usr/bin/env bash
# Usage: bench.sh <port> <model> <prompt_file> <label>
PORT=$1; MODEL=$2; PROMPT_FILE=$3; LABEL=$4
PROMPT=$(cat "$PROMPT_FILE" | jq -Rs .)

START=$(date +%s%N)
RESPONSE=$(curl -s http://127.0.0.1:${PORT}/api/generate \
  -d "{\"model\": \"${MODEL}\", \"prompt\": ${PROMPT}, \"stream\": false, \"options\": {\"num_predict\": 512}}")
END=$(date +%s%N)

WALL_MS=$(( (END - START) / 1000000 ))
EVAL_COUNT=$(echo "$RESPONSE" | jq '.eval_count // 0')
EVAL_DURATION=$(echo "$RESPONSE" | jq '.eval_duration // 0')
PROMPT_EVAL_COUNT=$(echo "$RESPONSE" | jq '.prompt_eval_count // 0')
PROMPT_EVAL_DURATION=$(echo "$RESPONSE" | jq '.prompt_eval_duration // 0')

# Compute tok/s (Ollama durations are in nanoseconds)
if [ "$EVAL_DURATION" -gt 0 ]; then
  GEN_TOKS=$(echo "scale=2; $EVAL_COUNT / ($EVAL_DURATION / 1000000000)" | bc)
else
  GEN_TOKS="0"
fi
if [ "$PROMPT_EVAL_DURATION" -gt 0 ]; then
  PROMPT_TOKS=$(echo "scale=2; $PROMPT_EVAL_COUNT / ($PROMPT_EVAL_DURATION / 1000000000)" | bc)
else
  PROMPT_TOKS="0"
fi

# Memory: grab RSS of the ollama-runner for this port
RSS_KB=$(ps aux | grep "ollama" | grep "${PORT}" | awk '{sum += $6} END {print sum}')
RSS_GB=$(echo "scale=2; ${RSS_KB:-0} / 1048576" | bc)

echo "${LABEL},${MODEL},${PORT},${PROMPT_EVAL_COUNT},${PROMPT_TOKS},${EVAL_COUNT},${GEN_TOKS},${WALL_MS},${RSS_GB}" | tee -a ~/eval/phase1/results.csv

# Save full response for qualitative review
echo "$RESPONSE" | jq -r '.response // empty' > ~/eval/phase1/${LABEL}_${MODEL//[:\/]/_}_p${PORT}.txt
SCRIPT
chmod +x ~/eval/bench.sh
```

---

## 2. Phase 1: Raw Performance Benchmarks (Day 1-2)

**Goal:** Measure actual inference speed on this hardware. Eliminate any model that cannot sustain >= 5 tok/s generation at the context lengths we need.

### 2.1 Standardized Benchmark Prompts

Create three prompt files of increasing context length. Each prompt is task-relevant, not generic lorem ipsum.

**Prompt A — Short context (~2K tokens):**

```bash
cat > ~/eval/phase1/prompt_2k.txt << 'EOF'
You are a network operations agent. Given the following FortiGate interface configuration, extract all interface names, their IP addresses, VLAN IDs, and associated zones. Return the result as a JSON array.

config system interface
    edit "wan1"
        set vdom "root"
        set ip 203.0.113.1 255.255.255.252
        set allowaccess ping https ssh
        set type physical
        set alias "ISP-Primary"
        set role wan
    next
    edit "wan2"
        set vdom "root"
        set ip 198.51.100.1 255.255.255.252
        set allowaccess ping
        set type physical
        set alias "ISP-Backup"
        set role wan
    next
    edit "internal"
        set vdom "root"
        set ip 10.10.0.1 255.255.255.0
        set allowaccess ping https ssh fgfm
        set type hard-switch
        set stp enable
        set role lan
    next
    edit "VLAN100-Staff"
        set vdom "root"
        set ip 10.10.100.1 255.255.255.0
        set allowaccess ping
        set device-identification enable
        set interface "internal"
        set vlanid 100
        set role lan
    next
    edit "VLAN200-Guest"
        set vdom "root"
        set ip 10.10.200.1 255.255.255.0
        set allowaccess ping
        set device-identification enable
        set interface "internal"
        set vlanid 200
        set role lan
    next
    edit "VLAN300-IoT"
        set vdom "root"
        set ip 10.10.300.1 255.255.255.0
        set allowaccess ping
        set interface "internal"
        set vlanid 300
        set role lan
    next
    edit "loopback0"
        set vdom "root"
        set ip 10.255.255.1 255.255.255.255
        set type loopback
        set role lan
    next
end

Return a JSON array of objects with keys: name, ip, subnet, vlan_id (null if not a VLAN), zone, alias.
EOF
```

**Prompt B — Medium context (~8K tokens):**

```bash
cat > ~/eval/phase1/prompt_8k.txt << 'EOF'
You are a software development orchestrator. Below is a Product Requirements Document (PRD) for a new feature. Decompose it into discrete work items suitable for a coding agent working in git worktrees.

# PRD: Coherence Engine — Event Sourcing Layer

## Overview
PromptClaw's coherence engine needs a persistent event-sourcing layer that records every agent decision, tool call result, and state transition. This enables replay, audit, and trust scoring.

## Requirements

### R1: Event Store
- Append-only SQLite-backed event store
- Each event has: event_id (UUIDv7), timestamp, agent_role, event_type, payload (JSON), causation_id, correlation_id
- Event types: DECISION_MADE, TOOL_CALLED, TOOL_RESULT, STATE_TRANSITION, REVIEW_SCORED, ERROR_RAISED, RECOVERY_ATTEMPTED
- Maximum event payload size: 64 KB
- The store must support replay from any event_id forward
- Writes must be fsync'd (no WAL — we need crash safety on power loss)
- Index on (correlation_id, timestamp) and (agent_role, event_type, timestamp)

### R2: Decision Records
- Every orchestrator routing decision must produce a DECISION_MADE event
- The payload must include: input_summary (max 500 chars), selected_agent, confidence_score (0.0-1.0), reasoning (max 2000 chars), alternatives_considered (list of {agent, score})
- Decision records must be emitted BEFORE the downstream agent is invoked

### R3: Trust Scoring Integration
- Each REVIEW_SCORED event updates a rolling trust score per agent
- Trust score formula: exponential moving average with alpha=0.3
- Trust scores are stored in a separate SQLite table (not in the event stream)
- If an agent's trust score drops below 0.4, emit a TRUST_DEGRADED event and notify the orchestrator
- Trust scores are recalculated on replay (they are derived state, not source-of-truth)

### R4: Replay Engine
- Given a correlation_id, replay all events in causal order
- Replay must be deterministic: same events in, same derived state out
- Replay should support "what-if" mode: inject a modified event and see downstream effects
- Replay output is a structured timeline (JSON array of events with computed trust scores at each point)

### R5: Constitution Enforcement
- A set of invariant rules that are checked after every event append
- Rules are defined in a YAML file (constitution.yaml)
- Example rules:
  - "No agent may invoke a tool without a preceding DECISION_MADE from the orchestrator"
  - "REVIEW_SCORED events must have a score between 0.0 and 1.0"
  - "RECOVERY_ATTEMPTED must reference a prior ERROR_RAISED via causation_id"
- Violations produce a CONSTITUTION_VIOLATION event (which is itself appended to the store)
- Hard violations (configurable) halt the pipeline; soft violations are logged and reported

### R6: API Surface
- Python module: promptclaw.coherence.event_store
- Functions: append_event(), query_events(filters), replay(correlation_id), check_constitution(event)
- All functions are synchronous (no async — the daemon is threaded, not async)
- Thread-safe via SQLite's WAL mode for reads, exclusive lock for writes
  (Note: this contradicts R1's "no WAL" requirement — the implementation must reconcile this.)

### R7: Observability
- Expose metrics: events_per_second, store_size_bytes, trust_scores (per agent), constitution_violations_total
- Metrics are read by the existing context_pulse.py health-check system
- Add a /coherence/health endpoint to the dashboard

## Non-Requirements
- No network replication (single-node only for v1)
- No event schema migration tooling
- No GUI for replay (CLI only in v1)

## Acceptance Criteria
- All event types can be appended and queried
- Replay produces identical derived state across 3 consecutive runs
- Constitution violations are caught and recorded within the same transaction
- Trust score calculation matches a reference implementation (provide test vectors)
- Throughput: >= 1000 events/second sustained append rate on the target hardware

---

Decompose the above PRD into work items. For each work item, provide:
1. A short title (suitable for a git branch name)
2. Which requirement(s) it addresses (R1-R7)
3. Estimated complexity (S/M/L)
4. Dependencies on other work items
5. Acceptance criteria specific to this work item
6. Files that will likely be created or modified

Return as a JSON array of work item objects.
EOF
```

**Prompt C — Long context (~32K tokens):**

For the 32K prompt, concatenate real files from the repository to simulate a realistic "read codebase and answer" scenario:

```bash
# This generates the long prompt from actual repo content
{
  echo "You are a code reviewer. Below are several source files from the PromptClaw project."
  echo "Review the code for: correctness, error handling, test coverage gaps, and potential race conditions."
  echo "Produce a structured review with scores (0.0-1.0) for each category."
  echo ""
  echo "=== File: my-claw/tools/cypherclaw_daemon.py ==="
  cat ~/PromptClaw/my-claw/tools/cypherclaw_daemon.py 2>/dev/null || echo "[file not found on eval server — paste content here]"
  echo ""
  echo "=== File: my-claw/tools/server_health.py ==="
  cat ~/PromptClaw/my-claw/tools/server_health.py 2>/dev/null || echo "[file not found]"
  echo ""
  echo "=== File: my-claw/tools/preflight.py ==="
  cat ~/PromptClaw/my-claw/tools/preflight.py 2>/dev/null || echo "[file not found]"
  echo ""
  echo "=== File: my-claw/tools/maintenance_mode.py ==="
  cat ~/PromptClaw/my-claw/tools/maintenance_mode.py 2>/dev/null || echo "[file not found]"
  echo ""
  echo "=== File: my-claw/tools/tamagotchi.py ==="
  cat ~/PromptClaw/my-claw/tools/tamagotchi.py 2>/dev/null || echo "[file not found]"
  echo ""
  echo "=== File: my-claw/tools/context_pulse.py ==="
  cat ~/PromptClaw/my-claw/tools/context_pulse.py 2>/dev/null || echo "[file not found]"
  echo ""
  echo "=== File: my-claw/tools/telegram.py ==="
  cat ~/PromptClaw/my-claw/tools/telegram.py 2>/dev/null || echo "[file not found]"
  echo ""
  echo "=== File: tests/test_daemon_fallback.py ==="
  cat ~/PromptClaw/tests/test_daemon_fallback.py 2>/dev/null || echo "[file not found]"
  echo ""
  echo "=== File: tests/test_server_health.py ==="
  cat ~/PromptClaw/tests/test_server_health.py 2>/dev/null || echo "[file not found]"
  echo ""
  echo "Return a JSON object with keys: overall_score, categories (object of category->score), findings (array of {file, line_range, severity, description, suggestion})."
} > ~/eval/phase1/prompt_32k.txt

# Verify token count estimate (rough: 1 token ~ 4 chars)
wc -c ~/eval/phase1/prompt_32k.txt | awk '{printf "Estimated tokens: %d\n", $1/4}'
```

### 2.2 Run the Benchmarks

Test every candidate model on both NUMA sockets with all three prompt lengths. This is the most time-consuming sub-step — expect 4-8 hours for the full matrix.

```bash
# Initialize CSV header
echo "label,model,port,prompt_tokens,prompt_tok_s,gen_tokens,gen_tok_s,wall_ms,rss_gb" > ~/eval/phase1/results.csv

# Fast models — test on both ports with all three prompts
FAST_MODELS=(
  "qwen3.5:35b"
  "qwen3:30b-a3b"
  "qwen3-coder:30b"
  "qwen3-coder-next"
  "gpt-oss:120b"
  "gpt-oss:20b"
  "glm-4.7-flash"
  "gemma4:26b"
  "nemotron-cascade-2:30b"
  "nemotron-3-nano:30b"
  "lfm2:24b-a2b"
)

for model in "${FAST_MODELS[@]}"; do
  for port in 11434 11435; do
    for prompt in prompt_2k prompt_8k prompt_32k; do
      echo ">>> Testing $model on port $port with $prompt"
      ~/eval/bench.sh $port "$model" ~/eval/phase1/${prompt}.txt "${prompt}"

      # Cool-down: unload the model before the next one
      curl -s http://127.0.0.1:${port}/api/generate \
        -d "{\"model\": \"${model}\", \"keep_alive\": 0}" > /dev/null
      sleep 2
    done
  done
done

# Heavy models — test only on port 11434 (they'll consume most of RAM anyway)
HEAVY_MODELS=(
  "qwen3.5:122b"
  "gpt-oss:120b"
  "nemotron-3-super:120b"
)

for model in "${HEAVY_MODELS[@]}"; do
  for prompt in prompt_2k prompt_8k prompt_32k; do
    echo ">>> Testing $model on port 11434 with $prompt"
    ~/eval/bench.sh 11434 "$model" ~/eval/phase1/${prompt}.txt "${prompt}"
    curl -s http://127.0.0.1:11434/api/generate \
      -d "{\"model\": \"${model}\", \"keep_alive\": 0}" > /dev/null
    sleep 5
  done
done
```

### 2.3 GDN Architecture Verification

Qwen3-Coder-Next and Qwen3.5-35B use Gated DeltaNet (GDN), a newer architecture variant. CPU inference correctness is not guaranteed. Run a targeted sanity check:

```bash
cat > ~/eval/phase1/gdn_sanity.txt << 'EOF'
Solve this step by step.

A Python function receives a list of FortiGate firewall rules. Each rule is a dict with keys: id, src, dst, service, action. Write a function that returns all rules where action is "accept" and either src or dst contains "10.10.100.0/24". Include type hints.

Then call the function with this test data and show the output:
rules = [
    {"id": 1, "src": "10.10.100.0/24", "dst": "0.0.0.0/0", "service": "HTTPS", "action": "accept"},
    {"id": 2, "src": "10.10.200.0/24", "dst": "10.10.100.0/24", "service": "SSH", "action": "deny"},
    {"id": 3, "src": "any", "dst": "10.10.100.5/32", "service": "ICMP", "action": "accept"},
    {"id": 4, "src": "10.10.100.0/24", "dst": "10.10.200.0/24", "service": "ANY", "action": "deny"},
]
Expected output: rules 1 and 3.
EOF

# Run on both GDN models
for model in "qwen3.5:35b" "qwen3-coder-next"; do
  echo "=== GDN sanity: $model ==="
  ~/eval/bench.sh 11434 "$model" ~/eval/phase1/gdn_sanity.txt "gdn_sanity"
  cat ~/eval/phase1/gdn_sanity_${model//[:\/]/_}_p11434.txt
  echo "---"
done

# PASS criteria: both models must return rules 1 and 3. If either returns wrong
# answers or produces garbled output, flag it as a GDN CPU-inference failure.
```

### 2.4 Nemotron Mamba Architecture Verification

Nemotron-Cascade-2 uses a hybrid Mamba (SSM + transformer) architecture. CPU inference for SSM layers may have correctness or performance issues:

```bash
cat > ~/eval/phase1/mamba_sanity.txt << 'EOF'
Given the following JSON representing LG SoT site data, answer these questions:
1. How many sites have status "cutover_complete"?
2. Which site has the most firewall rules?
3. What is the average rule count across all sites?

{
  "sites": [
    {"name": "HQ-Portland", "status": "cutover_complete", "rule_count": 847, "fortigate_model": "FG-200F"},
    {"name": "Branch-Seattle", "status": "in_progress", "rule_count": 234, "fortigate_model": "FG-100F"},
    {"name": "Branch-Eugene", "status": "cutover_complete", "rule_count": 156, "fortigate_model": "FG-80F"},
    {"name": "DC-Hillsboro", "status": "cutover_complete", "rule_count": 1203, "fortigate_model": "FG-400F"},
    {"name": "Branch-Bend", "status": "planning", "rule_count": 89, "fortigate_model": "FG-60F"},
    {"name": "Branch-Medford", "status": "in_progress", "rule_count": 312, "fortigate_model": "FG-100F"}
  ]
}

Return answers as a JSON object with keys: cutover_complete_count, most_rules_site, average_rule_count.
EOF

~/eval/bench.sh 11434 "nemotron-cascade-2:30b" ~/eval/phase1/mamba_sanity.txt "mamba_sanity"
# Expected: {"cutover_complete_count": 3, "most_rules_site": "DC-Hillsboro", "average_rule_count": 473.5}
```

### 2.5 Embeddings Model Benchmark

```bash
cat > ~/eval/phase1/embed_test.py << 'PYEOF'
import requests, time, json

texts = [
    "FortiGate 200F SD-WAN health-check configuration for dual ISP failover",
    "def append_event(self, event_type: str, payload: dict) -> str:",
    "pfSense NAT rule: source 10.10.100.0/24 destination any port 443 redirect 203.0.113.5",
    "git worktree add ../wt-coherence-engine feat/coherence-engine",
    "REVIEW_SCORED event with trust_score 0.72 for coding_agent on correlation abc123",
] * 20  # 100 texts

start = time.time()
for text in texts:
    r = requests.post("http://127.0.0.1:11434/api/embed",
                       json={"model": "qwen3-embedding:8b", "input": text})
    assert r.status_code == 200
elapsed = time.time() - start
print(f"100 embeddings in {elapsed:.2f}s ({100/elapsed:.1f} embed/s)")
print(f"Dimension: {len(r.json()['embeddings'][0])}")
PYEOF
python3 ~/eval/phase1/embed_test.py
```

### 2.6 Phase 1 Results Template

After all benchmarks complete, compile into this table:

```markdown
| Model | Prompt 2K (gen tok/s) | Prompt 8K (gen tok/s) | Prompt 32K (gen tok/s) | TTFT 2K (ms) | RSS (GB) | Correctness | Notes |
|-------|----------------------|----------------------|------------------------|-------------|----------|-------------|-------|
| qwen3.5:35b | | | | | | | GDN? |
| qwen3:30b-a3b | | | | | | | |
| qwen3-coder:30b | | | | | | | |
| qwen3-coder-next | | | | | | | GDN? |
| gpt-oss:120b | | | | | | | |
| gpt-oss:20b | | | | | | | |
| glm-4.7-flash | | | | | | | |
| gemma4:26b | | | | | | | |
| nemotron-cascade-2:30b | | | | | | | Mamba? |
| nemotron-3-nano:30b | | | | | | | |
| lfm2:24b-a2b | | | | | | | |
| qwen3.5:122b | | | | | | | Heavy |
| nemotron-3-super:120b | | | | | | | Heavy |
```

**Phase 1 Kill Criteria:** Eliminate any model that:
- Generates < 5 tok/s on the 8K prompt (too slow for interactive agent use)
- Uses > 100 GB RSS (leaves insufficient room for a second model on same socket)
- Produces incorrect output on the sanity checks (architecture incompatibility)
- Fails to load entirely (Ollama error, OOM)

---

## 3. Phase 2: Tool Calling Reliability (Day 2-3)

**Goal:** Measure each surviving model's ability to produce structured output, call tools, chain tool results, and recover from errors. This is the most important phase — a fast model with unreliable tool calling is useless.

### 3.1 Test Harness Setup

Use Ollama's native tool-calling API (`/api/chat` with `tools` parameter):

```bash
cat > ~/eval/phase2/tool_harness.sh << 'TOOLEOF'
#!/usr/bin/env bash
# Usage: tool_harness.sh <port> <model> <test_json_file> <label>
PORT=$1; MODEL=$2; TEST_FILE=$3; LABEL=$4

RESPONSE=$(curl -s http://127.0.0.1:${PORT}/api/chat \
  -d @"$TEST_FILE")

echo "$RESPONSE" | jq '.' > ~/eval/phase2/${LABEL}_${MODEL//[:\/]/_}_p${PORT}.json

# Extract tool calls
TOOL_CALLS=$(echo "$RESPONSE" | jq '[.message.tool_calls // []]')
echo "Model: $MODEL | Label: $LABEL | Tool calls: $(echo $TOOL_CALLS | jq 'length')"
TOOLEOF
chmod +x ~/eval/phase2/tool_harness.sh
```

### 3.2 Test: Single Tool Call — Orchestrator Task Classification

```json
// ~/eval/phase2/test_classify.json
{
  "model": "MODEL_PLACEHOLDER",
  "messages": [
    {
      "role": "system",
      "content": "You are the PromptClaw orchestrator. Classify incoming tasks and route them to the appropriate agent. Use the classify_task tool to record your decision."
    },
    {
      "role": "user",
      "content": "The FortiGate at Branch-Seattle is showing SD-WAN health-check failures on the ISP-Backup link. The SLA target of 150ms latency is being exceeded. Check the LG SoT for the current cutover status of Branch-Seattle and determine if we need to pause the migration."
    }
  ],
  "tools": [
    {
      "type": "function",
      "function": {
        "name": "classify_task",
        "description": "Classify a task and route to an agent",
        "parameters": {
          "type": "object",
          "required": ["task_type", "target_agent", "confidence", "reasoning"],
          "properties": {
            "task_type": {"type": "string", "enum": ["dev", "netops", "review", "admin"]},
            "target_agent": {"type": "string", "enum": ["coding_agent", "network_ops", "reviewer", "orchestrator"]},
            "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
            "reasoning": {"type": "string", "maxLength": 500}
          }
        }
      }
    }
  ],
  "stream": false
}
```

Expected: task_type="netops", target_agent="network_ops", confidence >= 0.8.
PASS: correct tool invoked, correct task_type, valid confidence score.
FAIL: no tool call, wrong tool params, malformed JSON, hallucinated tool name.

### 3.3 Test: Multi-Step Tool Chaining — Network Ops API Sequence

Run the multi-turn continuation script that simulates tool responses to test chaining:

```bash
cat > ~/eval/phase2/run_multistep.sh << 'CHAINEOF'
#!/usr/bin/env bash
PORT=$1; MODEL=$2

# Turn 1: User asks, model should call lg_sot_get_site
RESP1=$(curl -s http://127.0.0.1:${PORT}/api/chat -d '{
  "model": "'$MODEL'",
  "messages": [
    {"role": "system", "content": "You are the network operations agent for LG SoT. Diagnose connectivity issues by checking the site, its config, and SD-WAN health. Call tools in logical order."},
    {"role": "user", "content": "Branch-Seattle is reporting intermittent connectivity. Diagnose using LG SoT."}
  ],
  "tools": [
    {"type": "function", "function": {"name": "lg_sot_get_site", "description": "Look up a site by name", "parameters": {"type": "object", "required": ["site_name"], "properties": {"site_name": {"type": "string"}}}}},
    {"type": "function", "function": {"name": "lg_sot_get_firewall_config", "description": "Get firewall config. Requires site_id.", "parameters": {"type": "object", "required": ["site_id"], "properties": {"site_id": {"type": "string"}, "sections": {"type": "array", "items": {"type": "string"}}}}}},
    {"type": "function", "function": {"name": "lg_sot_get_sdwan_health", "description": "Get SD-WAN health. Requires site_id.", "parameters": {"type": "object", "required": ["site_id"], "properties": {"site_id": {"type": "string"}}}}}
  ],
  "stream": false
}')

TOOL1=$(echo "$RESP1" | jq -r '.message.tool_calls[0].function.name // "NONE"')
echo "Turn 1 tool call: $TOOL1"

# Turn 2: Simulate tool response, expect next tool call
RESP2=$(curl -s http://127.0.0.1:${PORT}/api/chat -d '{
  "model": "'$MODEL'",
  "messages": [
    {"role": "system", "content": "You are the network operations agent for LG SoT."},
    {"role": "user", "content": "Branch-Seattle is reporting intermittent connectivity. Diagnose using LG SoT."},
    {"role": "assistant", "content": "", "tool_calls": [{"function": {"name": "lg_sot_get_site", "arguments": {"site_name": "Branch-Seattle"}}}]},
    {"role": "tool", "content": "{\"site_id\": \"site-0042\", \"name\": \"Branch-Seattle\", \"status\": \"in_progress\", \"fortigate_model\": \"FG-100F\", \"ip\": \"198.51.100.10\"}"}
  ],
  "tools": [
    {"type": "function", "function": {"name": "lg_sot_get_site", "description": "Look up a site by name", "parameters": {"type": "object", "required": ["site_name"], "properties": {"site_name": {"type": "string"}}}}},
    {"type": "function", "function": {"name": "lg_sot_get_firewall_config", "description": "Get firewall config. Requires site_id.", "parameters": {"type": "object", "required": ["site_id"], "properties": {"site_id": {"type": "string"}, "sections": {"type": "array", "items": {"type": "string"}}}}}},
    {"type": "function", "function": {"name": "lg_sot_get_sdwan_health", "description": "Get SD-WAN health. Requires site_id.", "parameters": {"type": "object", "required": ["site_id"], "properties": {"site_id": {"type": "string"}}}}}
  ],
  "stream": false
}')

TOOL2=$(echo "$RESP2" | jq -r '.message.tool_calls[0].function.name // "NONE"')
SITE_ID_USED=$(echo "$RESP2" | jq -r '.message.tool_calls[0].function.arguments.site_id // "NONE"')
echo "Turn 2 tool call: $TOOL2 (site_id=$SITE_ID_USED)"

# Turn 3: Simulate second tool response, expect final tool call or synthesis
RESP3=$(curl -s http://127.0.0.1:${PORT}/api/chat -d '{
  "model": "'$MODEL'",
  "messages": [
    {"role": "system", "content": "You are the network operations agent for LG SoT."},
    {"role": "user", "content": "Branch-Seattle is reporting intermittent connectivity. Diagnose using LG SoT."},
    {"role": "assistant", "content": "", "tool_calls": [{"function": {"name": "lg_sot_get_site", "arguments": {"site_name": "Branch-Seattle"}}}]},
    {"role": "tool", "content": "{\"site_id\": \"site-0042\", \"name\": \"Branch-Seattle\", \"status\": \"in_progress\", \"fortigate_model\": \"FG-100F\", \"ip\": \"198.51.100.10\"}"},
    {"role": "assistant", "content": "", "tool_calls": [{"function": {"name": "lg_sot_get_firewall_config", "arguments": {"site_id": "site-0042", "sections": ["sdwan", "interfaces"]}}}]},
    {"role": "tool", "content": "{\"interfaces\": [{\"name\": \"wan1\", \"ip\": \"203.0.113.1/30\", \"status\": \"up\"}, {\"name\": \"wan2\", \"ip\": \"198.51.100.1/30\", \"status\": \"up\"}], \"sdwan\": {\"members\": [{\"interface\": \"wan1\", \"gateway\": \"203.0.113.2\", \"priority\": 1}, {\"interface\": \"wan2\", \"gateway\": \"198.51.100.2\", \"priority\": 10}], \"health_check\": {\"name\": \"ISP-Monitor\", \"server\": \"8.8.8.8\", \"protocol\": \"ping\", \"threshold\": {\"latency\": 150, \"jitter\": 30, \"packet_loss\": 5}}}}"}
  ],
  "tools": [
    {"type": "function", "function": {"name": "lg_sot_get_site", "description": "Look up a site by name", "parameters": {"type": "object", "required": ["site_name"], "properties": {"site_name": {"type": "string"}}}}},
    {"type": "function", "function": {"name": "lg_sot_get_firewall_config", "description": "Get firewall config. Requires site_id.", "parameters": {"type": "object", "required": ["site_id"], "properties": {"site_id": {"type": "string"}, "sections": {"type": "array", "items": {"type": "string"}}}}}},
    {"type": "function", "function": {"name": "lg_sot_get_sdwan_health", "description": "Get SD-WAN health. Requires site_id.", "parameters": {"type": "object", "required": ["site_id"], "properties": {"site_id": {"type": "string"}}}}}
  ],
  "stream": false
}')

TOOL3=$(echo "$RESP3" | jq -r '.message.tool_calls[0].function.name // "NONE"')
echo "Turn 3 tool call: $TOOL3"

echo ""
echo "=== Multi-step chain summary for $MODEL ==="
echo "Step 1: $TOOL1 (expected: lg_sot_get_site)"
echo "Step 2: $TOOL2 with site_id=$SITE_ID_USED (expected: lg_sot_get_firewall_config with site-0042)"
echo "Step 3: $TOOL3 (expected: lg_sot_get_sdwan_health)"
CHAINEOF
chmod +x ~/eval/phase2/run_multistep.sh
```

### 3.4 Test: Structured JSON Output — Reviewer Scoring

Prompt the model to produce a structured code review. Test with `"format": "json"` in the API call.

Expected output schema:
```json
{
  "overall_score": 0.75,
  "categories": {"correctness": 0.8, "test_coverage": 0.7, "error_handling": 0.9, "style": 0.6},
  "blocking_issues": ["string"],
  "suggestions": ["string"],
  "verdict": "approve|request_changes|reject"
}
```

PASS: valid JSON, all required keys present, scores are floats 0.0-1.0, verdict is one of the enum values.
BONUS: model correctly identifies failing tests and suggests fixes.
FAIL: invalid JSON, missing keys, scores outside range, or no JSON at all.

### 3.5 Test: Error Recovery — Tool Returns an Error

Simulate a tool returning a 404 error with a "did you mean" suggestion. The model should retry with the corrected parameter.

PASS: model retries with "HQ-Portland" (the corrected name from the error message).
FAIL: model gives up, hallucinates a response, or repeats the same wrong name.

### 3.6 Test: Coding Agent — Bug Fix from Error Trace

Give the model a failing test traceback and the relevant source code. The model should identify the bug (`self._drain_queue()` should be `self.drain_queue()`) and produce a fix using the write_file tool.

PASS: identifies the correct bug, produces valid fix.
BONUS: also notes the missing timeout parameter pass-through.
FAIL: wrong fix, no tool call, hallucinated different bug.

### 3.7 Run Phase 2 for All Surviving Models

```bash
SURVIVORS=() # Fill from Phase 1 results

for model in "${SURVIVORS[@]}"; do
  # Run all tool tests
  for test_file in ~/eval/phase2/test_*.json; do
    label=$(basename "$test_file" .json)
    sed "s/MODEL_PLACEHOLDER/$model/" "$test_file" > /tmp/test_run.json
    ~/eval/phase2/tool_harness.sh 11434 "$model" /tmp/test_run.json "$label"
  done

  # Run multi-step chain test
  ~/eval/phase2/run_multistep.sh 11434 "$model"
done
```

### 3.8 Phase 2 Scoring

For each model, score each test on this rubric:

| Test | Criteria | Score |
|------|----------|-------|
| Single tool call | Correct tool invoked with valid params | 0 or 1 |
| Single tool call | Correct classification (netops) | 0 or 1 |
| Multi-step chain | Step 1 correct tool | 0 or 1 |
| Multi-step chain | Step 2 correct tool with site_id from step 1 | 0 or 1 |
| Multi-step chain | Step 3 correct tool | 0 or 1 |
| Structured output | Valid JSON | 0 or 1 |
| Structured output | All required keys present | 0 or 1 |
| Structured output | Scores in valid range | 0 or 1 |
| Structured output | Identifies failing test correctly | 0 or 1 |
| Error recovery | Retries with corrected parameter | 0 or 1 |
| Coding diff | Identifies the correct bug | 0 or 1 |
| Coding diff | Produces valid fix | 0 or 1 |

**Total: 12 points. Minimum to proceed: 9/12.**

Run each test **3 times** (temperature=0) to check determinism. If a model passes 2/3 runs, count it as a pass. If results are inconsistent (1/3 or mixed), flag the model as "unreliable" and require 5 runs with 4/5 pass rate.

---

## 4. Phase 3: Real Workload Testing (Day 3-5)

**Goal:** Move from synthetic tests to actual PromptClaw and LG SoT workloads. This is where domain-specific reasoning quality becomes visible.

### 4.1 PromptClaw Workload: PRD Decomposition

Feed a real PRD from the repository:

```bash
{
  echo "You are the PromptClaw orchestrator. Decompose the following PRD into work items."
  echo "Each work item must have: title, requirements_addressed, complexity (S/M/L),"
  echo "dependencies, acceptance_criteria, files_to_modify."
  echo "Return as a JSON array."
  echo ""
  cat ~/PromptClaw/my-claw/sdp/prd-home-resilience.md
} > ~/eval/phase3/prd_decomposition_prompt.txt
```

**Evaluation criteria (manual review):**
- Are the work items logically decomposed (not too granular, not too coarse)?
- Do the dependencies form a valid DAG?
- Are the acceptance criteria testable?
- Do the file paths reference actual project structure?

Score: 0.0 to 1.0, assessed by human reviewer.

### 4.2 PromptClaw Workload: Code Implementation

Pick a small, completed work item from git history and ask the coding agent to implement it from scratch.

**Evaluation criteria:**
- Does the code compile/parse without syntax errors?
- Does it handle edge cases?
- Are type hints present and correct?
- Does it match the function signature?

Score: 0.0 to 1.0, assessed by comparing output to actual commit.

### 4.3 PromptClaw Workload: Code Review

Use a real diff from git history. Ask the model to produce a structured review.

**Evaluation criteria:**
- Valid JSON output?
- Does the review identify real issues (not hallucinated ones)?
- Are the scores reasonable (not all 1.0, not all 0.0)?
- Is the verdict consistent with the scores and issues found?

### 4.4 LG SoT Workload: FortiGate Config Parsing

Give the model a real FortiGate SD-WAN configuration block and ask it to extract structured data.

**Evaluation criteria:**
- Does the extracted JSON accurately represent all health checks?
- Are member-to-interface mappings correct?
- Are SLA thresholds for both tiers captured?
- Are the SD-WAN service rules that reference these members included?
- Is the SASE tunnel correctly distinguished from WAN members?

### 4.5 LG SoT Workload: Topology Diagram Generation

Give the model a mock LG SoT API response for a multi-site network and ask it to generate a Mermaid diagram.

**Evaluation criteria:**
- Valid Mermaid syntax (can be rendered)?
- All sites present with correct FortiGate models?
- VPN tunnels shown as dashed/dotted lines?
- WAN links labeled with bandwidth?
- Internet breakout correctly shown only for applicable sites?

### 4.6 Phase 3 Scoring

Each workload test is scored 0.0-1.0 by human review. Record in this table:

| Model | PRD Decomposition | Code Implementation | Code Review | FortiGate Parsing | Topology Diagram | Average |
|-------|------------------|--------------------|-----------|-----------------|--------------------|---------|
| | | | | | | |

**Minimum average to proceed: 0.6.**
**Minimum per-task for the assigned role: 0.7.** (e.g., a model considered for network ops must score >= 0.7 on FortiGate parsing and topology.)

---

## 5. Phase 4: Concurrent Load Testing (Day 5-6)

**Goal:** Verify that the selected models work when running simultaneously, as they will in production.

### 5.1 Dual-Model Concurrency on Same Socket

Run two models simultaneously on the same Ollama instance and measure degradation vs baseline.

### 5.2 Cross-Socket Concurrency

Run models on separate NUMA sockets — should show near-zero degradation since bandwidth is independent.

### 5.3 Model Swap Latency

Measure how long it takes to unload one model and load another (relevant if models must be rotated due to memory constraints).

### 5.4 OLLAMA_NUM_PARALLEL Stress Test

Send 4 requests simultaneously with NUM_PARALLEL=2 to see queuing behavior.

### 5.5 Phase 4 Acceptance Criteria

| Metric | Threshold | Notes |
|--------|-----------|-------|
| Same-socket concurrency degradation | < 40% | Two models on one socket |
| Cross-socket concurrency degradation | < 10% | One model per socket (expected near-zero) |
| Model swap latency (fast models) | < 15 seconds | Cold load from disk to RAM |
| Model swap latency (heavy models) | < 45 seconds | 65-87 GB load |
| NUM_PARALLEL=2 throughput | >= 60% of single-request | Two parallel requests |
| Total RSS (dual model) | < 750 GB | Must leave headroom for OS + embeddings |

---

## 6. Phase 5: Final Selection and Configuration (Day 6-7)

### 6.1 Configuration Candidates Matrix

Based on the model sizes and 813 GB total RAM:

| Configuration | Socket 0 Model(s) | Socket 1 Model(s) | Est. Total RAM | Notes |
|--------------|-------------------|-------------------|----------------|-------|
| **A: All-Qwen3** | qwen3-coder:30b (coding+orch) | qwen3:30b-a3b (netops) + qwen3.5:122b (reviewer, swapped) | ~120 GB active, 200 GB with reviewer | Proven ecosystem |
| **B: Specialized** | qwen3-coder-next (coding) + qwen3:30b-a3b (orch) | glm-4.7-flash (netops) + qwen3.5:122b (reviewer) | ~175 GB active | Best-of-breed per role |
| **C: Heavy Reviewer** | gpt-oss:20b (orch) + qwen3-coder:30b (coding) | qwen3:30b-a3b (netops) + nemotron-3-super:120b (reviewer) | ~145 GB active, 235 GB with reviewer | GPT-OSS for frontier reasoning |
| **D: Memory-Efficient** | lfm2:24b-a2b (orch) + qwen3-coder:30b (coding) | gpt-oss:20b (netops) + gpt-oss:120b (reviewer) | ~115 GB active | Smallest footprint |

### 6.2 Final Score Compilation

For each model, compute a weighted score:

| Weight | Dimension | Source |
|--------|-----------|--------|
| 20% | Generation speed (tok/s at 8K context) | Phase 1 |
| 5% | Prompt processing speed | Phase 1 |
| 25% | Tool calling reliability (out of 12) | Phase 2 |
| 30% | Real workload quality (0.0-1.0) | Phase 3 |
| 10% | Concurrent performance (degradation %) | Phase 4 |
| 10% | Memory efficiency (GB per tok/s) | Phase 1 |

---

## 7. Scoring Rubric

### Speed Score (0.0-1.0)

| Generation tok/s (8K context) | Score |
|-------------------------------|-------|
| >= 20 | 1.0 |
| 15-19 | 0.8 |
| 10-14 | 0.6 |
| 5-9 | 0.4 |
| 3-4 | 0.2 |
| < 3 | 0.0 (eliminate) |

### Tool Calling Score (0.0-1.0)

| Phase 2 points (out of 12) | Score |
|-----------------------------|-------|
| 12 | 1.0 |
| 11 | 0.9 |
| 10 | 0.8 |
| 9 | 0.7 |
| 8 | 0.5 |
| < 8 | 0.0 (eliminate) |

### Concurrency Score (0.0-1.0)

| Degradation % | Score |
|---------------|-------|
| < 10% | 1.0 |
| 10-20% | 0.8 |
| 20-30% | 0.6 |
| 30-40% | 0.4 |
| > 40% | 0.0 (eliminate) |

---

## 8. Decision Matrix Template

| Model | Role Considered | Speed (20%) | Tool Call (25%) | Quality (30%) | Concurrency (10%) | Memory (10%) | **Weighted Total** | Rank |
|-------|----------------|-------------|-----------------|---------------|--------------------|--------------|--------------------|----|
| qwen3.5:35b | Orchestrator | | | | | | | |
| qwen3:30b-a3b | Orchestrator | | | | | | | |
| qwen3-coder:30b | Coding | | | | | | | |
| qwen3-coder-next | Coding | | | | | | | |
| gpt-oss:120b | Reviewer | | | | | | | |
| gpt-oss:20b | Orchestrator | | | | | | | |
| glm-4.7-flash | Network Ops | | | | | | | |
| gemma4:26b | Network Ops | | | | | | | |
| nemotron-cascade-2:30b | Orchestrator | | | | | | | |
| nemotron-3-nano:30b | Coding | | | | | | | |
| lfm2:24b-a2b | Orchestrator | | | | | | | |
| qwen3.5:122b | Reviewer | | | | | | | |
| nemotron-3-super:120b | Reviewer | | | | | | | |

---

## 9. Go/No-Go Criteria

### Per-Model Gates

| Gate | Criterion | Phase |
|------|-----------|-------|
| G1 | Loads successfully in Ollama without errors | Pre-eval |
| G2 | Generation speed >= 5 tok/s at 8K context | Phase 1 |
| G3 | RSS <= 100 GB (fast models) or <= 400 GB (heavy models) | Phase 1 |
| G4 | Sanity check correctness (GDN/Mamba models) | Phase 1 |
| G5 | Tool calling score >= 9/12 | Phase 2 |
| G6 | Structured JSON output is parseable >= 2/3 attempts | Phase 2 |
| G7 | Role-specific quality score >= 0.7 | Phase 3 |
| G8 | Concurrent degradation < 40% | Phase 4 |

### System-Level Gates

| Gate | Criterion |
|------|-----------|
| S1 | At least one viable model exists for each of the 5 roles |
| S2 | The selected configuration fits within 750 GB total RSS |
| S3 | Cross-socket concurrent operation shows < 10% degradation |
| S4 | Model swap latency (when needed) < 30 seconds for fast models |
| S5 | End-to-end orchestrator->agent->reviewer cycle completes in < 5 minutes wall time |

---

## 10. Risk Register

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| GDN architecture produces incorrect output on CPU | Medium | High | Phase 1 sanity check; fall back to standard Qwen3 models |
| Mamba SSM layers slow on CPU | Medium | Medium | Phase 1 benchmark will reveal; Nemotron-Cascade-2 is optional |
| Heavy models (81-87 GB) too slow for reviewer role | Medium | Low | Benchmark first; GPT-OSS-120B at 65 GB is a lighter fallback |
| KV cache at 32K context blows RAM budget | Low | High | Test at target context lengths; reduce context if needed |
| OLLAMA_NUM_PARALLEL causes thrashing | Low | Medium | Test in Phase 4; fall back to NUM_PARALLEL=1 |
| Model updates between eval and production deployment | Low | Low | Pin exact model digests: `ollama show MODEL --digest` |
| Ollama version incompatibility with newer architectures | Low | High | Test on eval day; pin Ollama version that works |

---

## Timeline Summary

| Day | Phase | Effort | Deliverable |
|-----|-------|--------|-------------|
| 1 | Setup + Phase 1 start | 4h active + overnight benchmarks | Benchmark scripts running |
| 2 | Phase 1 complete + Phase 2 start | 6h | Performance table, elimination of slow/broken models |
| 3 | Phase 2 complete + Phase 3 start | 6h | Tool calling scores, elimination of unreliable models |
| 4 | Phase 3 continues | 4h | Real workload quality scores (human review time) |
| 5 | Phase 3 complete + Phase 4 | 6h | Quality scores final, concurrency baseline |
| 6 | Phase 4 complete + Phase 5 start | 4h | Concurrency report, preliminary selection |
| 7 | Phase 5 complete | 4h | Final config, warmup script, production ready |

**Total estimated effort:** ~34 hours of active work across 7 calendar days.

---

## Quick Reference Commands

```bash
# Pull a model
OLLAMA_HOST=http://127.0.0.1:11434 ollama pull qwen3:30b-a3b

# Check loaded models
curl -s http://127.0.0.1:11434/api/ps | jq .

# Unload a model (free RAM immediately)
curl -s http://127.0.0.1:11434/api/generate -d '{"model": "qwen3:30b-a3b", "keep_alive": 0}'

# Check model details
ollama show qwen3:30b-a3b --modelfile

# Pin model digest for reproducibility
ollama show qwen3:30b-a3b --digest

# Monitor RAM usage during eval
watch -n 2 'free -h && echo "---" && curl -s http://127.0.0.1:11434/api/ps | jq ".models[] | {name, size_vram, size}"'

# Generate with specific options
curl -s http://127.0.0.1:11434/api/generate -d '{
  "model": "qwen3:30b-a3b",
  "prompt": "test",
  "stream": false,
  "options": {
    "temperature": 0,
    "num_predict": 512,
    "num_ctx": 8192
  }
}'
```
