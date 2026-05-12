"""Depth-2 tests for promptclaw.memory [frac-0051]."""

from __future__ import annotations

import json
from pathlib import Path

from promptclaw.config import default_project_config
from promptclaw.memory import (
    MemoryEntry,
    MemoryStore,
    format_run_block,
    parse_memory_log,
    summarize_memory_log,
)
from promptclaw.models import RunState
from promptclaw.paths import ProjectPaths


MEMORY_MODULE_PATH = Path("promptclaw/memory.py")


def _make_store(tmp_path: Path) -> MemoryStore:
    config = default_project_config("Memory Claw")
    paths = ProjectPaths(project_root=tmp_path, config=config)
    return MemoryStore(paths)


def _make_state(
    *,
    run_id: str = "run-0051",
    title: str = "Memory Run",
    status: str = "complete",
    current_phase: str = "complete",
    lead_agent: str = "codex",
    verifier_agent: str = "claude",
) -> RunState:
    return RunState(
        run_id=run_id,
        title=title,
        status=status,
        current_phase=current_phase,
        created_at="2026-05-02T00:00:00+00:00",
        updated_at="2026-05-02T00:01:00+00:00",
        task_text="Implement memory helpers",
        lead_agent=lead_agent,
        verifier_agent=verifier_agent,
    )


def test_format_run_block_matches_canonical_layout() -> None:
    state = _make_state()

    block = format_run_block(state, "Final summary body.\n")

    assert block == (
        "\n## Run run-0051\n"
        "- Title: Memory Run\n"
        "- Status: complete\n"
        "- Lead: codex\n"
        "- Verifier: claude\n"
        "- Final phase: complete\n\n"
        "Final summary body.\n"
    )


def test_format_run_block_uses_n_a_for_missing_agents() -> None:
    state = _make_state(lead_agent="", verifier_agent="")

    block = format_run_block(state, "  body \n")

    assert "- Lead: n/a\n" in block
    assert "- Verifier: n/a\n" in block
    assert block.endswith("body\n")


def test_append_run_summary_uses_format_run_block(tmp_path: Path) -> None:
    store = _make_store(tmp_path)
    state = _make_state()

    store.append_run_summary(state, "Run finished cleanly.")

    expected = format_run_block(state, "Run finished cleanly.")
    assert store.paths.memory_file.read_text(encoding="utf-8") == expected


def test_parse_memory_log_round_trips_appended_entries(tmp_path: Path) -> None:
    store = _make_store(tmp_path)
    first = _make_state(run_id="run-A", lead_agent="codex", verifier_agent="claude")
    second = _make_state(
        run_id="run-B",
        title="Second Run",
        status="awaiting_user",
        current_phase="clarification",
        lead_agent="claude",
        verifier_agent="",
    )

    store.append_run_summary(first, "First body line.\nMore detail.")
    store.append_run_summary(second, "Clarification needed.")

    entries = parse_memory_log(store.read())

    assert len(entries) == 2
    assert isinstance(entries[0], MemoryEntry)
    assert entries[0].run_id == "run-A"
    assert entries[0].title == "Memory Run"
    assert entries[0].status == "complete"
    assert entries[0].lead_agent == "codex"
    assert entries[0].verifier_agent == "claude"
    assert entries[0].final_phase == "complete"
    assert entries[0].body == "First body line.\nMore detail."

    assert entries[1].run_id == "run-B"
    assert entries[1].status == "awaiting_user"
    assert entries[1].lead_agent == "claude"
    assert entries[1].verifier_agent == "n/a"
    assert entries[1].final_phase == "clarification"
    assert entries[1].body == "Clarification needed."


def test_parse_memory_log_handles_empty_inputs() -> None:
    assert parse_memory_log("") == ()
    assert parse_memory_log("# Project Memory\n\nNo runs yet.\n") == ()


def test_summarize_memory_log_is_json_safe_and_aggregates(tmp_path: Path) -> None:
    store = _make_store(tmp_path)
    store.append_run_summary(
        _make_state(run_id="run-A", lead_agent="codex", verifier_agent="claude"),
        "A",
    )
    store.append_run_summary(
        _make_state(
            run_id="run-B",
            status="awaiting_user",
            current_phase="clarification",
            lead_agent="claude",
            verifier_agent="",
        ),
        "B",
    )
    store.append_run_summary(
        _make_state(run_id="run-C", lead_agent="codex", verifier_agent="claude"),
        "C",
    )

    summary = summarize_memory_log(store.read())

    json.dumps(summary)
    assert summary["entry_count"] == 3
    assert summary["latest_run_id"] == "run-C"
    assert summary["statuses"] == {"awaiting_user": 1, "complete": 2}
    assert summary["lead_agents"] == {"claude": 1, "codex": 2}


def test_summarize_memory_log_excludes_n_a_lead(tmp_path: Path) -> None:
    store = _make_store(tmp_path)
    store.append_run_summary(
        _make_state(run_id="run-X", lead_agent="", verifier_agent=""),
        "no agents",
    )

    summary = summarize_memory_log(store.read())

    assert summary["entry_count"] == 1
    assert summary["lead_agents"] == {}


def test_memory_store_read_helpers(tmp_path: Path) -> None:
    store = _make_store(tmp_path)

    assert store.entries() == ()
    assert store.latest_entry() is None
    empty_summary = store.summary()
    assert empty_summary["entry_count"] == 0
    assert empty_summary["latest_run_id"] == ""
    assert empty_summary["statuses"] == {}
    assert empty_summary["lead_agents"] == {}

    store.append_run_summary(_make_state(run_id="run-A"), "first")
    store.append_run_summary(_make_state(run_id="run-B"), "second")

    entries = store.entries()
    assert tuple(entry.run_id for entry in entries) == ("run-A", "run-B")
    latest = store.latest_entry()
    assert latest is not None
    assert latest.run_id == "run-B"
    assert latest.body == "second"
    assert store.summary()["entry_count"] == 2


def test_memory_module_reaches_depth_two() -> None:
    from sdp.fractal import classify_depth

    result = classify_depth(MEMORY_MODULE_PATH)

    assert result.depth >= 2, result.reason
