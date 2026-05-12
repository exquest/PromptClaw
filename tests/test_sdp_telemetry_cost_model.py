from pathlib import Path


COST_MODEL_DOC = Path("sdp/telemetry/cost-model.md")


def _doc_text() -> str:
    assert COST_MODEL_DOC.exists(), "missing SDP telemetry cost model reference"
    return COST_MODEL_DOC.read_text(encoding="utf-8")


def test_cost_model_reference_exists_with_required_sections() -> None:
    text = _doc_text()

    assert text.startswith("# SDP Telemetry Cost Model")
    for heading in (
        "## Scope",
        "## Source Of Truth",
        "## Token Pricing",
        "## Per-Call Generation Costs",
        "## Fixed Overhead",
        "## Cap Formula",
        "## Edge Cases",
    ):
        assert heading in text

    for source_path in (
        "sdp.pipeline.cost_summary",
        "sdp.pipeline.token_cost",
        "sdp.pipeline.capacity",
        "sdp.pipeline.admission",
        "my-claw/tools/senseweave/generation/budget.py",
        ".sdp/state.db",
        "telemetry",
        "model_registry",
        "agent_usage_snapshots",
        "quota_snapshots",
    ):
        assert source_path in text


def test_cost_model_documents_token_pricing() -> None:
    text = _doc_text()

    for row in (
        "| claude-opus-4 | $15.00 | $75.00 |",
        "| claude-sonnet-4 | $3.00 | $15.00 |",
        "| claude-haiku | $0.80 | $4.00 |",
        "| gpt-4o | $2.50 | $10.00 |",
        "| o3 | $10.00 | $40.00 |",
        "| codex-mini | $1.50 | $6.00 |",
        "| fallback | $3.00 | $15.00 |",
    ):
        assert row in text

    assert "input_tokens" in text
    assert "output_tokens" in text
    assert "input_price_per_m" in text
    assert "output_price_per_m" in text


def test_cost_model_documents_cap_and_generation_formulas() -> None:
    text = _doc_text()

    for formula in (
        "call_cost_usd = (input_tokens / 1_000_000 * input_price_per_m) + "
        "(output_tokens / 1_000_000 * output_price_per_m)",
        "projected_tokens_per_project = task_p90_cost * avg_tasks_per_project",
        "reserve_tokens = token_limit * reserve_fraction",
        "remaining_after_reserve = remaining_tokens - reserve_tokens",
        "max_simultaneous_projects = floor(remaining_after_reserve / "
        "projected_tokens_per_project)",
        "safe_concurrency = min(provider_max_projects..., configured_worker_bound)",
        "generation_estimate_usd = per_second_usd[model] * duration_sec * 1.5",
    ):
        assert formula in text

    for row in (
        "| musicgen-medium | $0.0050 | audio-second |",
        "| stable-audio-open | $0.0035 | audio-second |",
        "| modal-a10g | $0.0003056 | compute-second |",
    ):
        assert row in text

    assert "CYPHERCLAW_GENERATION_DAILY_CAP_USD" in text
    assert "CYPHERCLAW_GENERATION_MONTHLY_CAP_USD" in text
    assert "$5.00" in text
    assert "$100.00" in text


def test_cost_model_documents_overhead_and_edge_cases() -> None:
    text = _doc_text()

    for required in (
        "selector_reserve_fraction",
        "0.20",
        "No fixed per-call USD charge is added to SDP token calls.",
        "cache_creation_tokens",
        "cache_read_tokens",
        "thinking_tokens",
        "No telemetry: p50/p90 are 0.0 with no_data confidence.",
        "Fewer than 5 matching samples: fall back to global telemetry.",
        "Unknown token model: use fallback pricing.",
        "Cost rejection is strict: predicted_p90_cost > remaining_tokens.",
        "Estimated quota data does not hard-deny admission.",
        "Unknown generation model: use the highest configured generation rate.",
    ):
        assert required in text
