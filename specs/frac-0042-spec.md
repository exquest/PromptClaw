# Task frac-0042 Specification: PromptClaw SDP Cost Depth 2

## Problem Statement

`promptclaw/sdp_cost.py` is the steady-state cost extractor: it reads SDP
telemetry rows from `.sdp/state.db`, applies the `sdp/telemetry/cost-model.md`
pricing table, and rolls per-call token usage into one `DailyCostRow` per
active UTC day, plus an optional Markdown cap summary.

The module currently classifies at fractal depth 1. Most of its surface is
short single-return helpers (`call_cost_usd`, `check_daily_caps`,
`summarize_daily_cap`) plus seven dataclass properties on `DailyCapCheck`
and `CostCapSummary`, all of which the AST classifier scores as trivial.
Even though the extract / write / render path already has substantial
logic, the trivial-vs-real ratio sits at 11 trivial / 8 real, which keeps
the module pinned at depth 1.

This task deepens the module to a simple depth-2 implementation by adding
three end-to-end roll-up helpers and one orchestrator that ties extraction,
CSV write, and cap summary together. Every existing public function and
signature is preserved so all current callers (extractor tests, CLI,
committed cap summary) keep working.

## Technical Approach

- Add `total_cost_usd(rows: list[DailyCostRow]) -> float` that explicitly
  loops over the rows and accumulates the per-row USD totals.
- Add `cost_by_model(rows: list[DailyCostRow]) -> dict[str, float]` that
  loops over rows and partitions each row's `total_cost_usd` evenly across
  its declared `models` tiers, returning a sorted dict keyed by tier. Rows
  with an empty `models` list contribute their cost to the `fallback`
  bucket — the same sentinel `match_pricing` already uses.
- Add `aggregate_rows(rows: list[DailyCostRow]) -> DailyCostRow` that loops
  once and sums `runs`, the four token columns, and `total_cost_usd` into
  a single `DailyCostRow`. The `date` field on the aggregate row is the
  earliest input date (or `""` for an empty input). The `models` field is
  the sorted union of all per-row models.
- Add a `CostRunSummary` dataclass and `summarize_cost_run(...)` that ties
  `extract_steady_state_cost`, `write_csv`, and `write_cap_summary` together
  in one call. It returns the rows, the total, the by-model breakdown, the
  written CSV path, and the optional `CostCapSummary` (or `None` when no
  summary path is provided).
- Preserve `match_pricing`, `call_cost_usd`, `extract_steady_state_cost`,
  `write_csv`, `read_csv`, `check_daily_caps`, `summarize_daily_cap`,
  `_cost_model_link`, `render_cap_summary`, `write_cap_summary`,
  `_parse_args`, and `main` exactly as they are.
- No new dependencies, migrations, database columns, secrets, runtime
  state files, or CLI flags.

## Edge Cases

- Empty `rows` → `total_cost_usd` returns `0.0`; `cost_by_model` returns
  `{}`; `aggregate_rows` returns a zero-filled `DailyCostRow` with
  `date=""` and `models=[]`.
- `cost_by_model` with a row whose `models` list is empty buckets that
  row's full cost under `"fallback"`.
- `summarize_cost_run` with `summary_out=None` skips the cap summary and
  sets `CostRunSummary.cap` to `None`; the CSV is still written.
- Existing CLI behavior, on-disk CSV header, and Markdown summary output
  are unchanged.

## Acceptance Criteria

1. Existing extractor and CLI behavior remains unchanged.
   VERIFY: `pytest tests/test_sdp_cost_extractor.py tests/test_sdp_telemetry_cost_model.py -q`

2. `total_cost_usd` produces meaningful USD totals over a row list.
   VERIFY: `pytest tests/test_promptclaw_sdp_cost_depth.py::test_total_cost_usd_sums_rows -q`

3. `cost_by_model` partitions each row's cost across its declared tiers
   and falls back to the `fallback` bucket when a row has no models.
   VERIFY: `pytest tests/test_promptclaw_sdp_cost_depth.py::test_cost_by_model_partitions_rows_across_tiers -q`

4. `aggregate_rows` sums runs, tokens, and cost across rows and unions
   the model tiers.
   VERIFY: `pytest tests/test_promptclaw_sdp_cost_depth.py::test_aggregate_rows_sums_runs_tokens_and_cost -q`

5. `summarize_cost_run` produces an end-to-end summary, writing CSV and
   the optional cap summary in one call.
   VERIFY: `pytest tests/test_promptclaw_sdp_cost_depth.py::test_summarize_cost_run_writes_csv_and_cap -q`

6. `summarize_cost_run` skips the cap summary when no summary path is
   provided.
   VERIFY: `pytest tests/test_promptclaw_sdp_cost_depth.py::test_summarize_cost_run_without_cap_path -q`

7. Fractal depth for `promptclaw/sdp_cost.py` reaches at least depth 2.
   VERIFY: `pytest tests/test_promptclaw_sdp_cost_depth.py::test_sdp_cost_module_reaches_depth_two -q`

8. Full project validation remains clean.
   VERIFY: `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/`
