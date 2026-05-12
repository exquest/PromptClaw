# PRD: CypherClaw Model Awareness System

## Overview
Make CypherClaw model-aware — selecting the right model for every task based on capability, speed, cost, and learned performance. Currently CypherClaw treats agents as monoliths. This PRD decomposes the system into specific models with distinct strengths.

**Depends on:** `prd-home-resilience.md` (durable runner and quota-aware continuity), `prd-restructure.md` (stable package/import layout)

## Execution Role

This is **Stage 3** of the execution spine.

Only the core routing/runtime pieces should be treated as immediate foundation work:

- model registry
- complexity classifier
- model selector
- runtime command/model flag handling
- observatory logging for model usage
- quota-aware/provider-aware selection behavior

Later visibility features such as `/models` and `/model-stats` are valuable, but they should follow the core routing work rather than compete with it.

## Requirements

| ID | Requirement | Priority | Tier | Acceptance Criteria |
|---|---|---|---|---|
| REQ-001 | Create model registry module at tools/model_registry.py with definitions for all available models (claude-opus, claude-sonnet, claude-haiku, gpt-5.4, gemini-pro, gemini-flash, gemini-image) including provider, CLI command, model flag, effort level, context window, strengths list, cost tier, and speed rating | MUST | T2 | Module loads without errors, all 7 models defined with correct CLI invocation commands |
| REQ-002 | Create task complexity classifier that categorizes incoming messages as simple (quick Q&A, greetings), standard (single-step tasks, questions requiring reasoning), or complex (multi-step, architecture, implementation) using keyword heuristics — no AI call needed | MUST | T1 | Classifier returns simple/standard/complex for test inputs with >85% accuracy on common patterns |
| REQ-003 | Create model selector function that maps (task_category, complexity) to the best model, considering strengths, speed, and cost. Routing tasks use haiku/flash, coding uses codex, research uses gemini-pro, architecture uses opus | MUST | T2 | Selector returns appropriate model for 10+ test cases covering routing, coding, research, review, simple Q&A |
| REQ-004 | Modify run_agent() in cypherclaw_daemon.py to accept a model parameter and construct the correct CLI command with --model flag for claude, -m flag for gemini, and -c flag for codex | MUST | T2 | run_agent("claude", prompt, model="claude-haiku-4-5") produces correct CLI: claude --model claude-haiku-4-5 --effort low --print -p - |
| REQ-005 | Replace the routing call in route_message() to use claude-haiku or gemini-flash instead of the default model. Route with --effort low and --model claude-haiku-4-5 for fastest possible routing | MUST | T1 | Routing latency drops from 10-40s to 2-8s measured by log timestamps |
| REQ-006 | Add model selection to the fast_route() function — simple messages (ping, status, help) bypass routing entirely (already done), but questions that need a quick AI answer should use gemini-flash directly instead of full routing | SHOULD | T1 | Simple questions like "what time is it" get answered in <5s via gemini-flash |
| REQ-007 | Record which model was used for each task in Observatory with fields: model_id, provider, effort_level, response_time_ms, success. Update observatory.record_task_result() to accept model parameter | MUST | T1 | Observatory events include model_id field, queryable by model |
| REQ-008 | Create per-model fitness scoring in Observatory — compute success_rate, avg_response_time, and cost_efficiency per model per task_category. Use exponential decay (recent results weighted more) | SHOULD | T2 | observatory.get_model_fitness("claude-haiku", "routing") returns meaningful score after 10+ tasks |
| REQ-009 | Update agent_selector.py to use model-level selection instead of agent-level. The selector should pick the best MODEL (not just agent) based on fitness scores and task category | SHOULD | T2 | Selector picks claude-haiku for routing, codex for coding, gemini-pro for research based on fitness data |
| REQ-010 | Implement effort-based degradation — when a complex task fails or times out with a standard model, automatically retry with a higher-effort model. When budget is tight, downgrade to cheaper models | COULD | T2 | Failed task with sonnet auto-retries with opus. Low budget scenario uses haiku/flash instead of opus |
| REQ-011 | Add /models command to the daemon showing all available models, their fitness scores, recent usage counts, and current selection weights | SHOULD | T1 | /models on Telegram displays a table of models with scores |
| REQ-012 | Wrap all agent CLI invocations with ionice -c3 and nice -n19 to prevent disk I/O saturation that causes jbd2 journal freezes | MUST | T1 | All subprocess.Popen/run calls for agents include ionice and nice prefixes |
| REQ-013 | Ensure the agent semaphore (max 1 concurrent) is respected across all code paths including dev_task, research, and direct agent calls | MUST | T1 | No more than 1 agent process runs at any time, verified by ps output during stress test |
| REQ-014 | Set TMPDIR and Claude cache paths to tmpfs (/run/cypherclaw-tmp) in the systemd service environment so agent disk writes go to RAM | MUST | T1 | Agent processes write temp files to tmpfs, verified by lsof during agent execution |
| REQ-015 | Add a /model-stats command showing per-model performance history from Observatory — response times, success rates, task counts, last used | COULD | T1 | /model-stats on Telegram shows meaningful performance data after a day of usage |
