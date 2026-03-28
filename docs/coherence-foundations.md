# Coherence Foundations --- Multi-Agent Consistency in PromptClaw

This document distills findings from 60+ research papers and production multi-agent systems into the design rationale behind PromptClaw's Coherence Engine. It is intended as a reference for developers working on or extending the coherence subsystem.

**Relevant source code:**
- `promptclaw/coherence/engine.py` --- `CoherenceEngine` facade with 7 orchestrator hooks
- `promptclaw/coherence/event_store.py` --- Append-only SQLite and PostgreSQL backends
- `promptclaw/coherence/decision_store.py` --- MADR-inspired architectural decision records
- `promptclaw/coherence/constitution.py` --- YAML/JSON rule evaluation engine
- `promptclaw/coherence/trust.py` --- Per-agent trust scoring
- `promptclaw/coherence/graduation.py` --- Self-graduating enforcement promotion
- `promptclaw/coherence/prompt_injection.py` --- Decision and rule injection into agent prompts
- `promptclaw/orchestrator.py` --- Hook integration points (A through G)

---

## Why Coherence Matters

Multi-agent systems do not fail because a single agent produces bad output. They fail because agents produce *inconsistent* output --- contradictory decisions, drifted assumptions, violated constraints that no individual agent was tracking. This is the central lesson from both academic research and production deployments.

**Prompting alone is insufficient.** The Agent Contracts work (COINE/AAMAS 2026) and Institutional AI research (2026) demonstrate that natural-language instructions degrade under composition. When Agent A's output becomes Agent B's input, prompt-level guidance ("always follow the style guide") has no enforcement mechanism. The constraint exists only as a suggestion that each agent independently decides to honor or ignore.

**Infrastructure-level enforcement is required.** Constitutional AI (Bai et al., 2022) showed that embedding constraints into the generation pipeline --- not just the prompt --- produces measurably more aligned outputs. PromptClaw extends this principle to the multi-agent case: the `CoherenceEngine` sits between the orchestrator and every agent invocation, injecting context, evaluating outputs, and blocking violations before they propagate.

The practical cost of incoherence is high. In PromptClaw's lead-verify-retry loop, a single inconsistent routing decision can waste an entire verification cycle. A contradicted architectural decision can produce code that passes verification but violates a constraint recorded three runs ago. The coherence engine exists to make these failures structurally impossible rather than statistically unlikely.

---

## The Four Dimensions of Coherence

Research on multi-agent consistency clusters into four orthogonal concerns. PromptClaw addresses each with dedicated subsystems.

### 1. Output Consistency

**Problem:** Two agents, given the same project context, produce outputs that contradict each other in style, assumptions, or technical decisions.

**Research basis:**

- **AGENTS.md / CLAUDE.md convention.** Shared context files give every agent in a project the same baseline instructions. This is the simplest form of coherence --- a static document that every agent reads. It works well for style and convention but cannot enforce dynamic constraints.
- **Cross-agent review (multi-agent debate).** Du et al. (ICML 2024) showed that having agents critique each other's outputs catches errors that self-review misses. The "debate" pattern --- where agents must justify their outputs to a reviewer --- produces higher accuracy than single-agent generation with planning.
- **Structured output validation.** SagaLLM and defense-in-depth approaches validate agent outputs against schemas before they enter the pipeline. This catches structural inconsistencies (wrong JSON shape, missing required fields) that semantic review might miss.

**Key finding: "Review Beats Planning."** Across multiple benchmarks, the critic/review pattern achieves 90.2% pass@1, outperforming elaborate planning-first approaches. PromptClaw implements this directly: the orchestrator's verify phase is not optional polish --- it is the primary quality mechanism.

**PromptClaw implementation:** The lead-verify-retry loop in `orchestrator.py` embodies this pattern. The verifier agent receives the lead output and emits a verdict (`PASS`, `PASS_WITH_NOTES`, or `FAIL`). On `FAIL`, the lead agent retries with the verifier's feedback injected. The coherence engine's hooks C/D (pre/post-lead) and E/F (pre/post-verify) inject constitutional rules and active decisions into both agents, ensuring they evaluate against the same constraint set.

### 2. System State Synchronization

**Problem:** Agents operate on stale or conflicting views of the system's state --- file contents, configuration, prior decisions.

**Research basis:**

- **Git worktree isolation (CAID framework).** When multiple agents write code concurrently, they must operate in isolated workspaces. The CAID framework demonstrates that git worktree isolation prevents merge conflicts from becoming semantic conflicts. Without isolation, Agent A's file write can silently invalidate Agent B's assumptions mid-execution.
- **Declarative source-of-truth (GitOps reconciliation).** The GitOps pattern --- where the declared state in version control is the only source of truth, and all runtime state is derived from it --- prevents state drift between what agents believe and what actually exists.
- **Documentation drift detection.** Tools like Vale and Doc Detective catch cases where documentation (including agent instructions) no longer matches the codebase. In a multi-agent system, stale instructions are a coherence failure.
- **Auto-remediation with bounds.** Self-healing systems can correct drift automatically, but unbounded auto-remediation creates death spirals where agents endlessly "fix" each other's fixes. Bounds are essential.

**PromptClaw implementation:** The append-only event store (`event_store.py`) is the state synchronization mechanism. Every orchestrator action --- routing, lead execution, verification, retry --- emits an event. The `replay(run_id)` method reconstructs the complete state of any run from its event log. There is no mutable "current state" object that can drift; state is always derived from the event sequence.

The `SqliteEventStore` uses WAL mode with `PRAGMA synchronous=NORMAL` for concurrent read safety. The `PostgresEventStore` adds optional Redis cache invalidation: on every `append()`, the Redis key `coherence:state:{run_id}` is deleted, forcing the next read to reconstruct from the database. This ensures no consumer operates on stale cached state.

### 3. Decision Memory

**Problem:** Agents re-litigate decisions that were already made, or worse, make contradictory decisions because they have no record of what was decided previously.

**Research basis:**

- **Architecture Decision Records (MADR 4.0.0, 2024).** The MADR format --- title, context, decision, rationale, status --- provides a structured way to record *why* something was decided, not just *what*. This is critical because agents need rationale to determine whether a prior decision still applies to a new context.
- **Vector-indexed retrieval (pgvector).** Keyword matching finds decisions that share terminology with the current task, but semantic search via embeddings finds decisions that are conceptually relevant even when the terminology differs. pgvector enables this without a separate vector database.
- **Temporal knowledge graphs (Zep/Graphiti).** Graphiti achieves 94.8% accuracy on temporal knowledge tasks by modeling facts as graph edges with time ranges. This matters for decision memory because decisions can be superseded --- the system must know not just what was decided but *when* it was valid.
- **Decision immutability.** Once recorded, a decision's content must never be edited. It can only be superseded by a new decision that explicitly references the old one. This prevents the "who changed the decision?" problem that plagues wikis and shared documents.

**Key insight: 5 properties that general RAG lacks.** Decision memory requires five properties that standard retrieval-augmented generation does not provide:

1. **Immutability** --- decisions are append-only, never edited
2. **Supersession tracking** --- a new decision explicitly marks its predecessor as superseded
3. **Relevance scoring** --- decisions are ranked by relevance to the current task, not just recency
4. **Status filtering** --- only active decisions are injected; deprecated/superseded ones are excluded
5. **Structural richness** --- the title/context/decision/rationale structure lets agents understand *why*, not just *what*

**PromptClaw implementation:** The `SqliteDecisionStore` in `decision_store.py` implements all five properties. The `Decision` dataclass carries `status` (active/superseded/deprecated) and `superseded_by` (a foreign key to the replacing decision). The `query_relevant()` method tokenizes the current task text, scores each active decision by keyword overlap and file-path intersection (weighted 2x), and returns the top N. The `format_decision_context()` function in `prompt_injection.py` renders matched decisions as a markdown block with the header "Active Decisions (DO NOT VIOLATE)" that is injected into agent prompts at hooks A, C, and E.

The decision store is designed to be upgraded to pgvector-backed semantic search. The `query_relevant()` method's Python-side scoring is a deliberate stepping stone: it works without external dependencies today, and the interface is compatible with a future implementation that replaces keyword scoring with embedding similarity.

### 4. Constitutional Enforcement

**Problem:** Even with shared context, decision memory, and state synchronization, agents can still produce outputs that violate project-specific constraints. Enforcement must be automated, not advisory.

**Research basis:**

- **Governance-as-a-Service (GaaS, Gaurav et al., 2025).** GaaS demonstrates that governance rules can be evaluated as a service layer with 95% precision and 90% recall, without requiring changes to the governed agents. The key insight is separation of concerns: the agent produces output, and a separate system evaluates compliance.
- **Agent Behavioral Contracts (AgentAssert).** AgentAssert shows that behavioral contracts can be checked with less than 10ms overhead per evaluation, making real-time enforcement practical even in latency-sensitive pipelines.
- **Progressive enforcement (Monitor, Soft, Full).** Production deployments consistently show that starting with full enforcement causes false-positive blocking that erodes developer trust. The solution is progressive rollout: observe first, warn second, block third.
- **Trust scoring with (p, delta, k)-satisfaction bounds.** Agents that consistently comply earn higher trust scores, which can gate access to sensitive operations. The mathematical framework ensures that trust decisions have statistical backing rather than being arbitrary thresholds.

**PromptClaw implementation:** The `Constitution` class in `constitution.py` loads rules from YAML or JSON files. Each rule has:

- `rule_id` --- unique identifier
- `severity` --- `hard` (blocking in soft/full mode) or `soft` (warning only in soft mode, blocking in full mode)
- `pattern` --- regex evaluated against agent output
- `keywords` --- case-insensitive substring matches
- `applies_to_phases` --- optional filter (routing, lead, verify)
- `applies_to_agents` --- optional filter by agent name
- `message` --- human-readable violation description

The `evaluate()` method checks text against all applicable rules for the current phase and agent. The `should_block()` method implements the three enforcement modes:

| Mode    | Soft violation | Hard violation |
|---------|---------------|----------------|
| Monitor | log only      | log only       |
| Soft    | log + warn    | **block**      |
| Full    | **block**     | **block**      |

The `TrustManager` in `trust.py` maintains per-agent scores on a 0.0--1.0 scale, starting at 0.5. The penalty/reward constants are tuned so that a single hard violation (-0.3) is catastrophic but recoverable over 15 compliant actions (+0.02 each), while soft violations (-0.05) are correctional nudges. When a score drops below 0.2 (`RESTRICTION_THRESHOLD`), the `should_restrict()` method returns `True`, signaling to the orchestrator that this agent should be deprioritized or sandboxed.

---

## Key Systems and Frameworks

These systems informed PromptClaw's design. Each represents a different approach to multi-agent coordination.

### MetaGPT (Hong et al., ICLR 2024)
Standard Operating Procedures (SOPs) as the coordination mechanism. Each agent role has a defined protocol, and the system enforces that agents follow their SOP rather than improvising. **Lesson for PromptClaw:** Structured handoff protocols prevent cascading hallucinations. PromptClaw's `handoffs/` directory and explicit `subtask_brief` in routing decisions implement this principle.

### OpenHands V1 (Wang et al., ICLR 2025)
Event-sourced state management where the complete system state can be reconstructed by replaying the event log. Achieved 72% on SWE-bench. **Lesson for PromptClaw:** Event sourcing is the correct state model for multi-agent systems. PromptClaw's `EventStoreBackend` protocol and append-only log are directly inspired by this architecture.

### ESAA --- Executable Software Architecture for Agents (2026)
The key conceptual shift: LLMs are not autonomous actors but *intention emitters* operating under behavioral contracts. The software architecture (not the LLM) is responsible for enforcing constraints. **Lesson for PromptClaw:** The coherence engine does not trust agents to self-govern. It evaluates their outputs externally and blocks violations regardless of what the agent "intended."

### LangGraph
Central state with reducer logic. Multiple agents read from and write to a shared state object, with reducer functions that resolve conflicts. **Lesson for PromptClaw:** Centralized state reduces coordination overhead but requires careful access control. PromptClaw's event store centralizes state while the constitution controls what agents can do with it.

### Generative Agents (Park et al., UIST 2023)
Memory stream architecture where agents maintain a timestamped log of observations and retrieve relevant memories using recency, importance, and relevance scoring. **Lesson for PromptClaw:** Memory retrieval needs multi-factor scoring, not just keyword matching. The decision store's combined keyword + file-path scoring is a simplified version of this principle.

### Reflexion (Shinn et al., NeurIPS 2023)
Self-reflective agents that maintain an episodic memory of prior attempts and use it to improve future performance. **Lesson for PromptClaw:** The retry loop must include the verifier's feedback, not just the original task. PromptClaw's `build_retry_prompt()` includes both the verifier output and the prior lead output.

---

## Ten Non-Obvious Insights

These findings emerged from the research survey and directly shaped PromptClaw's architecture.

### 1. Prompting is necessary but insufficient

Natural-language instructions are the baseline, not the ceiling. Every production system that relies solely on prompting for consistency eventually encounters failures that can only be caught by infrastructure. PromptClaw uses prompting (injected decision context and constitutional rules) *and* infrastructure (post-output evaluation, trust scoring, blocking).

### 2. Worktree isolation is necessary, not just helpful

When agents modify files concurrently, isolation is not a performance optimization --- it is a correctness requirement. Without isolation, Agent A's partial write can corrupt Agent B's read. PromptClaw's per-run artifact directories (`.promptclaw/runs/<run-id>/`) provide run-level isolation. The event store provides state-level isolation.

### 3. Event sourcing is the natural state model

Mutable state objects create "who wrote last?" ambiguities in multi-agent systems. Append-only event logs eliminate this class of bug entirely. The state at any point in time is deterministically derived by replaying events up to that point. PromptClaw's `SqliteEventStore.replay(run_id)` and `PostgresEventStore.replay(run_id)` implement this directly.

### 4. LLMs as intention emitters is the key insight

The ESAA framework's reframing --- LLMs emit *intentions*, software enforces *constraints* --- resolves the fundamental tension in multi-agent systems. You do not need to make the LLM "understand" the constraint; you need to evaluate its output against the constraint externally. PromptClaw's `Constitution.evaluate()` method does not ask the agent whether it violated a rule; it checks the output text with regex and keyword matching.

### 5. Critic pattern outperforms planning pattern

Systems that invest heavily in upfront planning (decomposing tasks into detailed sub-plans before execution) are consistently outperformed by systems that execute quickly and then review critically. The pass@1 difference is significant: 90.2% for review-heavy vs. lower rates for planning-heavy approaches. PromptClaw's architecture reflects this: routing is fast and heuristic-capable, but verification is always thorough.

### 6. Decision memory needs 5 properties RAG lacks

Standard RAG retrieves text chunks by similarity. Decision memory requires immutability, supersession tracking, status filtering, relevance scoring, and structural richness. These five properties distinguish an architectural decision store from a document search engine. See [Dimension 3](#3-decision-memory) for details.

### 7. Practical concurrency ceiling is 5--7 agents

Research consistently finds diminishing returns and increasing coordination overhead beyond 5--7 concurrent agents. Adding more agents increases the chance of conflicting outputs faster than it increases total throughput. PromptClaw's routing model (one lead, one verifier) is deliberately minimal. The orchestrator scales by running more sequential runs, not by adding more concurrent agents per run.

### 8. Progressive enforcement is the only safe deployment path

Deploying full enforcement on day one causes false-positive blocking that makes the system unusable, which causes developers to disable enforcement entirely. The Monitor-then-Soft-then-Full progression lets the system prove its accuracy before gaining blocking power. PromptClaw's `GraduationManager` automates this: it requires 20 observations with >85% confidence before promoting from Monitor to Soft, and 10 runs with <5% false-positive rate before promoting from Soft to Full. It never auto-demotes.

### 9. Shared memory without access control becomes "noisy commons"

When every agent can write to shared memory without constraints, the memory fills with low-value observations that dilute high-value decisions. Access control --- or at minimum, structured formats that separate signal from noise --- is essential. PromptClaw addresses this by separating the event store (high-volume, structured, append-only) from the decision store (low-volume, curated, keyword-indexed). Only explicit `record_decision()` calls create decision records; agents cannot flood the decision store through normal operation.

### 10. Heterogeneous LLM ensembles require externalized governance

When a system uses multiple LLM providers (Claude, GPT, Gemini, local models), each with different capabilities and failure modes, governance rules cannot be embedded in any single model's system prompt. They must be externalized into infrastructure that evaluates all models' outputs uniformly. PromptClaw's constitution is model-agnostic: it evaluates text output regardless of which agent or model produced it.

---

## How PromptClaw Implements Each Dimension

### Event Store (Dimensions 2 + 3)

**Source:** `promptclaw/coherence/event_store.py`

The event store is an append-only log. Every orchestrator action emits a `CoherenceEvent` with:

```python
@dataclass
class CoherenceEvent:
    event_id: str        # UUID
    run_id: str          # Groups events by orchestrator run
    timestamp: str       # ISO 8601 UTC
    event_type: str      # e.g., "coherence.pre_routing", "lead_complete"
    phase: str           # routing, lead, verify, retry, complete
    agent: str           # Which agent was involved
    role: str            # lead, verify, or empty
    payload: dict        # Arbitrary structured data
    sequence_number: int # Monotonic within a run
```

**Two backends:**

- `SqliteEventStore` --- Zero-dependency, WAL-mode SQLite. Default for local development. Indexes on `run_id` and `event_type` for fast replay and filtering.
- `PostgresEventStore` --- Production-grade with connection pooling (psycopg2 `ThreadedConnectionPool`, 1--5 connections) and optional Redis cache invalidation. The JSONB `payload` column enables PostgreSQL-native JSON queries.

**Key invariant:** Events are never updated or deleted. All state is derived from replay. This makes the event store a reliable audit trail and enables time-travel debugging ("what did the system know at event #47?").

### Decision Store (Dimension 3)

**Source:** `promptclaw/coherence/decision_store.py`

Architectural Decision Records following the MADR pattern:

```python
@dataclass
class Decision:
    decision_id: str          # UUID
    created_at: str           # ISO timestamp
    title: str                # Human-readable summary
    context: str              # Why this decision was needed
    decision_text: str        # What was decided
    rationale: str            # The reasoning
    status: str               # "active", "superseded", "deprecated"
    superseded_by: str | None # FK to the replacing decision
    tags: list[str]           # Keyword tags for retrieval
    file_paths: list[str]     # Code paths this decision affects
```

**Retrieval:** `query_relevant(task_text, file_paths, limit)` tokenizes the task into keywords (3+ characters), scores each active decision by keyword hits in title/context/decision_text, adds a 2x bonus for file-path overlap, and returns the top N by score. This is deliberately simple and dependency-free; the interface is designed for a future pgvector upgrade that replaces keyword scoring with embedding similarity.

**Injection:** Before every agent invocation (hooks A, C, E), the `format_decision_context()` function renders matched decisions as a markdown block:

```
## Active Decisions (DO NOT VIOLATE)

### ADR: Use Redis vector sets instead of ChromaDB
- **Decision:** Migrate all vector storage to Redis
- **Rationale:** Reduces infrastructure to a single service
- **Affects:** promptclaw/memory.py, promptclaw/coherence/decision_store.py
- **Tags:** database, storage
```

This block is injected into the agent's prompt via the `coherence_context` parameter in `build_lead_prompt()` and `build_verify_prompt()`.

### Constitution (Dimension 4)

**Source:** `promptclaw/coherence/constitution.py`

Rules are defined in a YAML or JSON file (default: `constitution.yaml` in the project root):

```yaml
rules:
  - id: no-secrets-in-output
    severity: hard
    description: Never include API keys or secrets in output
    pattern: "(sk-[a-zA-Z0-9]{20,}|AKIA[A-Z0-9]{16})"
    applies_to: [lead, verify]
    message: "Output contains what appears to be an API key or secret"

  - id: require-type-hints
    severity: soft
    description: Python code should include type hints
    keywords: ["def ", "-> None"]
    applies_to: [lead]
    message: "Python function definitions should include type annotations"
```

**Evaluation:** `Constitution.evaluate(text, phase, agent)` filters rules to those applicable for the current phase and agent, then checks each rule's `pattern` (regex, case-insensitive) and `keywords` (substring, case-insensitive) against the text. Any match produces a `Violation`.

**Blocking logic:** `should_block(violations, mode)` implements the three-tier enforcement matrix. In Monitor mode, nothing blocks. In Soft mode, only hard-severity violations block. In Full mode, any violation blocks.

### Trust Scoring (Dimension 4)

**Source:** `promptclaw/coherence/trust.py`

Per-agent trust on a 0.0--1.0 continuous scale:

| Parameter               | Value  | Rationale                                              |
|------------------------|--------|--------------------------------------------------------|
| `INITIAL_SCORE`        | 0.5    | Neutral starting point --- neither trusted nor suspect |
| `HARD_PENALTY`         | -0.3   | Severe --- one hard violation drops trust to 0.2       |
| `SOFT_PENALTY`         | -0.05  | Correctional --- 10 soft violations to reach 0.0      |
| `COMPLIANT_REWARD`     | +0.02  | Slow recovery --- 15 actions to recover from one hard  |
| `RESTRICTION_THRESHOLD`| 0.2    | Below this, `should_restrict()` returns `True`         |

The asymmetry is intentional: trust is hard to earn and easy to lose. This reflects the research finding that a single uncaught violation in a multi-agent pipeline can cascade through subsequent agents, while compliant actions have only local benefit.

Trust updates happen in the `_update_trust()` method of `CoherenceEngine`, called by hooks B, D, and F (post-routing, post-lead, post-verify).

### Self-Graduating Enforcement (Dimension 4)

**Source:** `promptclaw/coherence/graduation.py`

The `GraduationManager` tracks observations (true positives and false positives) across runs and promotes the enforcement mode when confidence thresholds are met:

**Promotion rules:**

| Transition          | Requirement                                                        |
|--------------------|--------------------------------------------------------------------|
| Monitor to Soft     | >= 20 observations AND confidence > 85%                           |
| Soft to Full        | >= 10 runs in Soft mode AND false-positive rate < 5%              |
| Full to (anything)  | No auto-promotion beyond Full; no auto-demotion at any level      |

**Why never auto-demote:** Auto-demotion creates a perverse incentive where a burst of false positives (perhaps due to a new rule being too broad) causes the system to silently reduce its own enforcement power. The correct response to high false-positive rates is human review of the rule, not automatic weakening of the system.

The `finalize()` hook (Hook G) at the end of every run calls `graduation_manager.increment_run()` and `evaluate_promotion()`. If the mode changes, it is persisted to the config.

---

## The 7-Hook Architecture

The coherence engine integrates with the orchestrator through 7 hooks that cover the complete lifecycle of a run:

| Hook | Method          | When                      | Purpose                                  |
|------|----------------|---------------------------|------------------------------------------|
| A    | `pre_routing`  | Before routing decision    | Inject decisions + rules into routing    |
| B    | `post_routing` | After routing decision     | Validate routing against constitution    |
| C    | `pre_lead`     | Before lead agent runs     | Inject decisions + rules into lead       |
| D    | `post_lead`    | After lead output          | Evaluate lead output, update trust       |
| E    | `pre_verify`   | Before verification        | Inject decisions + rules into verifier   |
| F    | `post_verify`  | After verification verdict | Evaluate verdict, update trust           |
| G    | `finalize`     | End of run                 | Graduation evaluation, mode update       |

**Pre-hooks (A, C, E)** are injection-only: they query relevant decisions and applicable rules, format them as markdown, and return them in `CoherenceVerdict.injected_context`. The orchestrator passes this context to the prompt builder.

**Post-hooks (B, D, F)** are evaluation hooks: they run the agent's output through `Constitution.evaluate()`, determine whether to block based on the current enforcement mode, and update the agent's trust score.

**The finalize hook (G)** performs no evaluation. It increments the graduation manager's run counter and checks whether promotion criteria are met.

The `NullCoherenceEngine` class provides a no-op implementation of all 7 hooks, returning default `CoherenceVerdict(approved=True)` for every call. This ensures the orchestrator works correctly even if coherence initialization fails.

---

## References

1. **Du, Y., Li, S., Torralba, A., Tenenbaum, J. B., & Mordatch, I.** (2024). "Improving Factuality and Reasoning in Language Models through Multiagent Debate." *ICML 2024*.

2. **Hong, S., Zhuge, M., Chen, J., Zheng, X., Cheng, Y., Zhang, C., et al.** (2024). "MetaGPT: Meta Programming for A Multi-Agent Collaborative Framework." *ICLR 2024*.

3. **Wang, X., et al.** (2025). "OpenHands: An Open Platform for AI Software Developers." *ICLR 2025*.

4. **Bai, Y., Kadavath, S., Kundu, S., Askell, A., Kernion, J., Jones, A., et al.** (2022). "Constitutional AI: Harmlessness from AI Feedback." *Anthropic*.

5. **Gaurav, A., et al.** (2025). "Governance-as-a-Service: A Multi-Agent Framework for Responsible AI Governance." *arXiv preprint*.

6. **Agent Contracts and Institutional AI.** (2026). *COINE Workshop, AAMAS 2026*. Behavioral contracts for multi-agent systems drawing on institutional economics.

7. **ESAA: Executable Software Architecture for Agents.** (2026). LLMs as intention emitters under software-enforced behavioral contracts.

8. **Park, J. S., O'Brien, J. C., Cai, C. J., Morris, M. R., Liang, P., & Bernstein, M. S.** (2023). "Generative Agents: Interactive Simulacra of Human Behavior." *UIST 2023*.

9. **Shinn, N., Cassano, F., Gopinath, A., Narasimhan, K., & Yao, S.** (2023). "Reflexion: Language Agents with Verbal Reinforcement Learning." *NeurIPS 2023*.

10. **MADR 4.0.0.** (2024). Markdown Any Decision Records. Structured format for recording architectural decisions. https://adr.github.io/madr/

---

*This document reflects the research basis for PromptClaw's coherence engine as of v2.1. As the coherence subsystem evolves (pgvector integration, cross-run trust persistence, multi-project federation), this document should be updated to reflect the new research informing those capabilities.*
