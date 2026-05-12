# SDP Telemetry Cost Model

## Scope

This reference is the operator-facing cost model for PromptClaw SDP telemetry. It covers two active cost surfaces:

- SDP agent token accounting: historical telemetry, static per-million-token pricing, p50/p90 prediction, admission rejection, and safe worker concurrency.
- CypherClaw external generation accounting: per-call audio generation estimates, daily/monthly USD caps, and realized spend recording.

It does not define provider secrets, billing credentials, migrations, or live provider price discovery.

## Source Of Truth

| Surface | Source |
| --- | --- |
| Token cost summary | `sdp.pipeline.cost_summary` |
| Token p50/p90 prediction | `sdp.pipeline.token_cost` |
| Project capacity and safe concurrency | `sdp.pipeline.capacity` |
| Quota admission behavior | `sdp.pipeline.admission` |
| Generation budget gate | `my-claw/tools/senseweave/generation/budget.py` |
| Modal generation runtime cost | `my-claw/tools/senseweave/generation/client_modal.py` |
| Local runtime state | `.sdp/state.db` |
| Historical token rows | `telemetry` |
| Optional model registry pricing | `model_registry` |
| Provider usage windows | `agent_usage_snapshots` |
| Provider quota snapshots | `quota_snapshots` |

The telemetry table records `input_tokens`, `output_tokens`, `thinking_tokens`, `cache_creation_tokens`, and `cache_read_tokens`. The current summary cost formula prices only input and output tokens.

## Token Pricing

`sdp.pipeline.cost_summary` resolves token pricing by case-insensitive substring match against the model profile. Prices are USD per 1 million tokens.

| Model pattern | Input price per 1M tokens | Output price per 1M tokens |
| --- | ---: | ---: |
| claude-opus-4 | $15.00 | $75.00 |
| claude-sonnet-4 | $3.00 | $15.00 |
| claude-haiku | $0.80 | $4.00 |
| gpt-4o | $2.50 | $10.00 |
| o3 | $10.00 | $40.00 |
| codex-mini | $1.50 | $6.00 |
| fallback | $3.00 | $15.00 |

Per-call token cost:

```text
call_cost_usd = (input_tokens / 1_000_000 * input_price_per_m) + (output_tokens / 1_000_000 * output_price_per_m)
```

Example: 10,000 input tokens and 5,000 output tokens on `claude-sonnet-4` estimate to `(10_000 / 1_000_000 * 3.00) + (5_000 / 1_000_000 * 15.00) = $0.105`.

## Per-Call Generation Costs

CypherClaw generation budget estimates request cost from requested duration and model rate. The Replicate-style budget rate is per requested audio second. The Modal rate is per compute second from prediction metadata, with local latency as fallback metadata.

| Model/backend | Rate | Unit |
| --- | ---: | --- |
| musicgen-medium | $0.0050 | audio-second |
| stable-audio-open | $0.0035 | audio-second |
| modal-a10g | $0.0003056 | compute-second |

Generation budget estimate:

```text
generation_estimate_usd = per_second_usd[model] * duration_sec * 1.5
```

Default generation caps are `$5.00` daily and `$100.00` monthly. Operators can override them with `CYPHERCLAW_GENERATION_DAILY_CAP_USD` and `CYPHERCLAW_GENERATION_MONTHLY_CAP_USD`.

Generation budget admission:

```text
today_after = today_spent_usd + generation_estimate_usd
month_after = month_spent_usd + generation_estimate_usd
allow = today_after <= daily_cap_usd and month_after <= monthly_cap_usd
```

Realized generation spend is recorded from `cost_usd` on the generation result. Missing, zero, or negative realized costs do not increment counters.

## Fixed Overhead

No fixed per-call USD charge is added to SDP token calls. SDP token cost is variable-only: input tokens plus output tokens priced by model.

SDP capacity planning keeps a token reserve before estimating worker capacity. The default `selector_reserve_fraction` is `0.20`, meaning 20 percent of the provider token limit is held back from concurrency calculations.

Generation budget estimates include a fixed multiplier rather than a fixed dollar fee. `GenerationBudget` applies the 1.5 overhead factor to requested audio-second rates to cover provider variance and queue/runtime uncertainty.

Cache and reasoning fields are telemetry-only in the current summary model: `cache_creation_tokens`, `cache_read_tokens`, and `thinking_tokens` are tracked for future accounting but are not billed by the current `call_cost_usd` formula unless a future provider-specific formula adds them.

## Cap Formula

Token p50/p90 prediction uses valid historical telemetry samples and nearest-rank percentiles. Segments are keyed by tier, task type, and model profile; segments smaller than 5 samples use the global fallback set.

Project token projection:

```text
projected_tokens_per_project = task_p90_cost * avg_tasks_per_project
```

Provider reserve:

```text
reserve_tokens = token_limit * reserve_fraction
remaining_after_reserve = remaining_tokens - reserve_tokens
```

Per-provider maximum simultaneous projects:

```text
max_simultaneous_projects = floor(remaining_after_reserve / projected_tokens_per_project)
```

Global safe concurrency across providers and configured worker cap:

```text
safe_concurrency = min(provider_max_projects..., configured_worker_bound)
```

Providers with invalid inputs or no projection degrade to capacity 0 for the global safe-concurrency calculation.

## Edge Cases

- No telemetry: p50/p90 are 0.0 with no_data confidence.
- Fewer than 5 matching samples: fall back to global telemetry.
- Unknown token model: use fallback pricing.
- Unknown generation model: use the highest configured generation rate.
- Cost rejection is strict: predicted_p90_cost > remaining_tokens.
- A predicted p90 cost that is zero, negative, missing, or non-finite is treated as no cost data and should not reject a model by itself.
- Estimated quota data does not hard-deny admission.
- Authoritative or observed quota data can hard-deny only when all eligible providers are exhausted by the admission policy.
- Generation caps reject only when existing spend plus estimated request cost is greater than the daily or monthly cap.
- Date and month boundaries roll the generation budget counters before admission or recording.
