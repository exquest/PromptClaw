# PRD: Cost Tracking — Budget-Aware Agent Operations

## Overview

CypherClaw runs multiple AI agents (Claude, Gemini, Codex) across dozens of daily tasks. Without cost visibility, a single runaway pipeline can burn through an entire month's API budget in hours. This PRD introduces end-to-end cost tracking: estimate costs before invocation, record actuals after, enforce daily/weekly budgets per provider, alert Anthony via Telegram at thresholds, and automatically degrade to cheaper models when budgets are tight. The goal is zero-surprise bills and maximum value per dollar spent.

**Key capabilities:**
- Per-invocation cost estimation using token counts and per-model pricing tables
- PostgreSQL-backed cost event storage with full attribution (task, agent, model, tokens)
- Configurable daily and weekly budgets per provider with Telegram alerts at 80%
- Automatic model degradation (opus -> sonnet -> haiku, pro -> flash) when approaching limits
- Local model preference (Ollama) as a free-tier fallback when budget is exhausted
- Cost dashboard on the web platform and /cost Telegram command for instant visibility

## Architecture

```
                           +-------------------+
                           |   Agent Request    |
                           +--------+----------+
                                    |
                                    v
                      +-------------+-------------+
                      |   Cost Estimator (CT-001) |
                      |   token count x pricing   |
                      +-------------+-------------+
                                    |
                         estimated cost + model
                                    |
                    +---------------v----------------+
                    | Cost-Aware Selector (CT-010)   |
                    | budget remaining > est cost?   |
                    +---+-------------------+--------+
                        |                   |
                   yes  |                   | no
                        v                   v
              +---------+-------+  +--------+---------+
              | Use Requested   |  | Auto-Degrade     |
              | Model           |  | (CT-005/CT-006)  |
              +---------+-------+  +--------+---------+
                        |                   |
                        +-------+-----------+
                                |
                                v
                    +-----------+-----------+
                    |   Agent Invocation    |
                    +-----------+-----------+
                                |
                         actual tokens used
                                |
                                v
                    +-----------+-----------+
                    | Cost Storage (CT-002) |
                    | PostgreSQL cost_events|
                    +-----------+-----------+
                                |
               +----------------+----------------+
               |                |                |
               v                v                v
      +--------+---+  +--------+----+  +---------+------+
      | Budget     |  | Telegram    |  | Web Dashboard  |
      | Alerting   |  | /cost cmd   |  | (CT-008)       |
      | (CT-004)   |  | (CT-007)    |  |                |
      +------------+  +-------------+  +----------------+
```

## Requirements

| ID | Description | Priority | Tier | Acceptance Criteria |
|---|---|---|---|---|
| CT-001 | **Cost estimator.** Estimate cost before each agent invocation by counting input/output tokens and multiplying by per-model pricing. Maintain a `MODEL_PRICING` table with $/1K-token rates for all supported models (Claude Opus, Sonnet, Haiku; Gemini Pro, Flash; GPT-4o, 4o-mini; local models at $0). Update pricing table via config file, not hardcoded. Include prompt caching discount calculation. | MUST | T1 | - Estimates within 20% of actual cost for 90% of invocations<br/>- Pricing table covers all active models<br/>- Pricing config reloadable without restart<br/>- Prompt caching discounts applied correctly |
| CT-002 | **Cost storage in PostgreSQL.** Create a `cost_events` table: `id`, `timestamp`, `task_id`, `agent_name`, `model`, `provider`, `input_tokens`, `output_tokens`, `cached_tokens`, `estimated_cost`, `actual_cost`, `budget_period` (daily/weekly). Insert a row after every agent invocation. Include indexes on `timestamp`, `provider`, and `budget_period` for fast aggregation queries. | MUST | T1 | - Table created via migration script<br/>- Row inserted for every invocation<br/>- Queries for daily/weekly totals return in <50ms<br/>- No data loss on daemon restart |
| CT-003 | **Daily/weekly budget configuration per provider.** Allow setting budget caps in `promptclaw.json` or a dedicated `budgets.toml`: per-provider daily limit (e.g., Anthropic: $5/day, Google: $2/day) and weekly limit. Support a global daily cap as well. Budget periods reset at midnight UTC (daily) and Monday 00:00 UTC (weekly). Allow runtime override via Telegram command. | MUST | T1 | - Budgets configurable per provider + global<br/>- Daily reset at midnight UTC<br/>- Weekly reset at Monday 00:00 UTC<br/>- Telegram override persists until next reset<br/>- Config changes applied without restart |
| CT-004 | **Budget alert via Telegram at 80% threshold.** When spending for any provider reaches 80% of its daily or weekly budget, send a Telegram alert to Anthony with: provider name, amount spent, budget limit, top 3 cost contributors, and time until reset. Send a second alert at 95%. Do not send more than one alert per threshold per period to avoid spam. | MUST | T1 | - Alert at 80% and 95% thresholds<br/>- No duplicate alerts per threshold per period<br/>- Alert includes provider, spend, limit, top tasks<br/>- Alert includes time-to-reset<br/>- Delivered within 60s of threshold crossing |
| CT-005 | **Auto-degradation.** When a provider's budget hits 90%, automatically switch to cheaper models: Claude Opus -> Sonnet -> Haiku, Gemini Pro -> Flash. The degradation is per-provider and resets when the budget period resets. Log every degradation event to Observatory and notify via Telegram. Allow Anthony to override degradation for specific tasks via Telegram command. | MUST | T1 | - Degradation triggers at 90% budget<br/>- Correct model fallback chains<br/>- Resets with budget period<br/>- Override via Telegram works<br/>- All degradations logged to Observatory |
| CT-006 | **Local model preference when budget tight.** When all cloud provider budgets are above 80%, prefer local Ollama models for non-critical tasks (sdp-cli pipeline, code review, summarization). Critical tasks (user-facing Telegram responses, complex reasoning) still use cloud models. Define task criticality in agent_selector config. | SHOULD | T2 | - Local models used for non-critical tasks above 80%<br/>- Critical tasks still get cloud models<br/>- Task criticality configurable<br/>- Smooth fallback with no user-visible quality cliff |
| CT-007 | **/cost Telegram command.** Respond with a formatted summary: today's spend per provider, weekly spend per provider, budget remaining per provider, top 5 most expensive tasks today, current degradation status, estimated days until weekly budget exhaustion at current burn rate. Support `/cost weekly` for the weekly view and `/cost task <name>` for per-task breakdown. | MUST | T2 | - `/cost` returns daily summary<br/>- `/cost weekly` returns weekly summary<br/>- `/cost task <name>` returns per-task breakdown<br/>- Response formatted cleanly in Telegram<br/>- Data accurate within last 60 seconds |
| CT-008 | **Cost dashboard on web platform.** Add a `/costs` page to the web dashboard showing: daily spend chart (bar chart by provider, last 30 days), budget utilization gauges, cost breakdown by agent and task type, model usage distribution pie chart, trend line with projected monthly total. Auto-refreshes every 5 minutes. | SHOULD | T2 | - Dashboard renders correctly<br/>- Charts show last 30 days<br/>- Budget gauges update in real-time<br/>- Projected monthly total displayed<br/>- Auto-refresh every 5 minutes |
| CT-009 | **Per-task cost attribution.** Tag every cost event with the originating task (sdp-cli task name, Telegram command, scheduled job, etc.). Aggregate costs per task over time. Identify the most and least cost-efficient tasks by comparing cost to completion success rate. Surface task-level costs in the daily briefing. | MUST | T1 | - Every cost event tagged with task ID<br/>- Aggregation queries by task available<br/>- Cost-efficiency metric calculated<br/>- Top/bottom tasks shown in daily briefing |
| CT-010 | **Cost-aware model selection in agent_selector.** Modify `agent_selector.py` to factor in remaining budget when choosing a model. If estimated cost would exceed remaining daily budget, select a cheaper alternative. If no cloud model fits the budget, route to local. Log the selection reasoning to Observatory. | MUST | T1 | - Agent selector checks budget before selection<br/>- Cheaper alternative selected when over budget<br/>- Falls back to local when no cloud budget<br/>- Selection reasoning logged<br/>- No increase in selection latency >50ms |
| CT-011 | **Weekly cost report in morning briefing.** Add a cost section to the existing daily/weekly briefing: total spend vs. budget, per-provider breakdown, most expensive day, cost trend (up/down/flat vs. prior week), optimization recommendations. For weekly briefings, include a 4-week trend chart rendered as ASCII art for Telegram compatibility. | SHOULD | T2 | - Cost section added to daily briefing<br/>- Weekly briefing includes 4-week trend<br/>- ASCII chart renders correctly in Telegram<br/>- Recommendations based on actual patterns |
| CT-012 | **Budget reset scheduling.** Implement reliable budget period resets: daily at midnight UTC, weekly at Monday 00:00 UTC. Clear degradation flags, reset spend counters in Redis, archive the completed period's totals to PostgreSQL. Handle edge cases: missed resets (server was down), timezone changes, leap seconds. Send a "budget reset" confirmation to Telegram. | MUST | T1 | - Daily reset at midnight UTC<br/>- Weekly reset at Monday 00:00 UTC<br/>- Missed resets caught up on next run<br/>- Degradation flags cleared on reset<br/>- Confirmation sent to Telegram |
| CT-013 | **Cost estimation for sdp-cli pipeline tasks.** Before the sdp-cli pipeline starts a task, estimate its total cost based on historical data for similar tasks (same type, same agent). If the estimated cost would push the daily budget over limit, skip the task and log the reason. Provide a `/pipeline-budget` command to see queued task costs. | SHOULD | T2 | - Pre-task cost estimation from historical data<br/>- Tasks skipped when over budget<br/>- Skip reason logged to Observatory<br/>- `/pipeline-budget` shows queue with estimates<br/>- Estimation improves with more historical data |
| CT-014 | **Historical cost trend tracking.** Store daily and weekly cost summaries in a `cost_summaries` table: period_type, period_start, period_end, provider, total_cost, total_tokens, invocation_count, avg_cost_per_invocation. Query support for: last N days, month-over-month comparison, provider-level trends. Used by the dashboard and weekly reports. | SHOULD | T2 | - Daily summaries generated at period close<br/>- Weekly summaries generated at period close<br/>- Month-over-month comparison queries work<br/>- Data retained for at least 90 days<br/>- Summary generation does not impact live operations |
| CT-015 | **Cost optimization recommendations.** Analyze cost patterns and generate actionable recommendations: (a) tasks that could use cheaper models without quality loss (based on Observatory skill scores), (b) tasks with high cache-miss rates that would benefit from prompt caching, (c) tasks that run too frequently and could be batched, (d) providers where we are consistently under-budget (waste of allocation). Surface recommendations weekly in the briefing and on the dashboard. | SHOULD | T3 | - At least 4 recommendation categories<br/>- Recommendations based on actual data (not generic)<br/>- Surfaced in weekly briefing<br/>- Visible on dashboard<br/>- Each recommendation includes estimated savings |

## Implementation Phases

### Phase 1: Foundation (T1) — CT-001, CT-002, CT-003, CT-004, CT-005, CT-009, CT-010, CT-012

Build the core cost tracking loop: estimate before invocation, record after, enforce budgets, degrade when necessary. This phase alone prevents runaway spending and gives basic visibility. All cost events are stored with full attribution. Budget resets run reliably. The agent selector is cost-aware. This is the minimum viable cost system.

### Phase 2: Visibility (T2) — CT-006, CT-007, CT-008, CT-011, CT-013, CT-014

Add user-facing interfaces: Telegram commands for instant cost checks, web dashboard for historical analysis, cost sections in briefings, pipeline budget awareness. Local model preference kicks in to save money on non-critical tasks. Historical summaries enable trend analysis. Anthony can see exactly where money is going without querying the database.

### Phase 3: Intelligence (T3) — CT-015

The system starts making recommendations: which tasks could be cheaper, which prompts should use caching, which tasks could be batched. This turns cost tracking from a reporting tool into an optimization engine. Requires at least 2 weeks of historical data to generate meaningful recommendations.

## Success Metrics

| Metric | Target |
|--------|--------|
| Cost estimation accuracy | Within 20% of actual for 90% of invocations |
| Budget overshoot prevention | Zero days exceeding daily budget by >10% |
| Alert delivery latency | <60 seconds from threshold crossing to Telegram delivery |
| Auto-degradation response time | <5 seconds from budget check to model switch |
| Cost visibility | Anthony can answer "how much did I spend today?" in <10 seconds |
| Monthly cost reduction | 15% reduction within first month of optimization recommendations |
| Cost event recording | 100% of agent invocations have a cost_events row |
| Dashboard uptime | 99.5% availability during server uptime |
| Budget reset reliability | 100% of resets execute within 5 minutes of scheduled time |
