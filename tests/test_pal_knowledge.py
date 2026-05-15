from __future__ import annotations

import argparse
from contextlib import redirect_stdout
from dataclasses import asdict
import io
import json
from pathlib import Path

import pytest

from promptclaw.cli import cmd_pal_kb_build, cmd_pal_kb_query
from promptclaw.config import default_project_config, save_config
from promptclaw.models import PALConfig
from promptclaw.pal_knowledge import (
    PALKnowledgeIndexBuild,
    PALKnowledgeChunk,
    PALKnowledgeQueryResult,
    chunk_pal_source_files,
    discover_pal_source_files,
    query_pal_knowledge_index,
    write_pal_knowledge_index,
)


def test_discover_pal_source_files_returns_configured_sample_files(tmp_path: Path) -> None:
    (tmp_path / "docs" / "deep").mkdir(parents=True)
    (tmp_path / "ops").mkdir()
    (tmp_path / "docs" / "guide.md").write_text("# Guide\n")
    (tmp_path / "docs" / "deep" / "detail.md").write_text("# Detail\n")
    (tmp_path / "docs" / "ignore.tmp").write_text("not configured\n")
    (tmp_path / "ops" / "session-state.md").write_text("# State\n")

    config = default_project_config("PAL Source Discovery")
    config.pal = PALConfig(
        enabled=True,
        knowledge_sources=[
            "docs/**/*.md",
            "ops/session-state.md",
            "missing/**/*.md",
            "docs/guide.md",
            "docs",
        ],
    )
    save_config(tmp_path, config)

    discovered = discover_pal_source_files(tmp_path)

    assert all(path.is_absolute() for path in discovered)
    assert _relative_paths(discovered, tmp_path) == [
        "docs/deep/detail.md",
        "docs/guide.md",
        "ops/session-state.md",
    ]


def test_discover_pal_source_files_uses_default_pal_sources_when_config_is_empty(
    tmp_path: Path,
) -> None:
    (tmp_path / "docs").mkdir()
    (tmp_path / "ops" / "templates").mkdir(parents=True)
    (tmp_path / ".promptclaw" / "pal-smoke").mkdir(parents=True)
    (tmp_path / "prompts").mkdir()
    (tmp_path / "docs" / "PROJECT_GUIDE.md").write_text("# Project\n")
    (tmp_path / "ops" / "templates" / "router-app.py").write_text("app = object()\n")
    (tmp_path / ".promptclaw" / "pal-smoke" / "pal-smoke-20260515T180000Z.json").write_text("{}\n")
    (tmp_path / "prompts" / "not-pal-source.md").write_text("# Not included by default\n")
    save_config(tmp_path, default_project_config("PAL Defaults"))

    discovered = discover_pal_source_files(tmp_path)

    assert _relative_paths(discovered, tmp_path) == [
        ".promptclaw/pal-smoke/pal-smoke-20260515T180000Z.json",
        "docs/PROJECT_GUIDE.md",
        "ops/templates/router-app.py",
    ]
    assert not (tmp_path / ".promptclaw" / "pal-kb").exists()


def test_chunk_pal_source_files_returns_typed_bounded_chunks(tmp_path: Path) -> None:
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "alpha.md").write_text("# Alpha\nfirst line\nsecond line\n")
    (tmp_path / "docs" / "beta.md").write_text("# Beta\nthird line\n")
    _save_pal_config(tmp_path, ["docs/*.md"])

    chunks = chunk_pal_source_files(tmp_path, max_chars=24)

    assert chunks
    assert all(isinstance(chunk, PALKnowledgeChunk) for chunk in chunks)
    assert all(chunk.chunk_id.startswith("pal-kb:") for chunk in chunks)
    assert all(len(chunk.source_sha256) == 64 for chunk in chunks)
    assert all(len(chunk.text) <= 24 for chunk in chunks)
    assert [chunk.source_path for chunk in chunks] == [
        "docs/alpha.md",
        "docs/alpha.md",
        "docs/beta.md",
    ]
    assert [chunk.chunk_index for chunk in chunks] == [0, 1, 0]
    assert chunks[0].start_line == 1
    assert chunks[0].end_line >= chunks[0].start_line
    assert json.dumps([asdict(chunk) for chunk in chunks], sort_keys=True)
    assert not (tmp_path / ".promptclaw" / "pal-kb").exists()


def test_chunk_pal_source_files_keeps_chunk_ids_stable_for_unchanged_files(
    tmp_path: Path,
) -> None:
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "alpha.md").write_text("# Alpha\nfirst line\nsecond line\n")
    (tmp_path / "docs" / "beta.md").write_text("# Beta\nthird line\n")
    _save_pal_config(tmp_path, ["docs/*.md"])

    first = chunk_pal_source_files(tmp_path, max_chars=24)
    second = chunk_pal_source_files(tmp_path, max_chars=24)

    assert [chunk.chunk_id for chunk in second] == [chunk.chunk_id for chunk in first]
    assert [asdict(chunk) for chunk in second] == [asdict(chunk) for chunk in first]


def test_chunk_pal_source_files_keeps_existing_ids_when_new_source_is_added(
    tmp_path: Path,
) -> None:
    (tmp_path / "docs").mkdir()
    alpha = tmp_path / "docs" / "alpha.md"
    alpha.write_text("# Alpha\nfirst line\nsecond line\n")
    _save_pal_config(tmp_path, ["docs/*.md"])

    before = _chunk_ids_by_source(chunk_pal_source_files(tmp_path, max_chars=24))
    (tmp_path / "docs" / "later.md").write_text("# Later\nnew file only\n")
    after = _chunk_ids_by_source(chunk_pal_source_files(tmp_path, max_chars=24))

    assert after["docs/alpha.md"] == before["docs/alpha.md"]
    assert "docs/later.md" in after


def test_chunk_pal_source_files_handles_empty_and_long_line_edges(tmp_path: Path) -> None:
    (tmp_path / "docs").mkdir()
    long_line = "abcdefghijklmnopqrstuvwxyz"
    (tmp_path / "docs" / "blank.md").write_text(" \n\t\n")
    (tmp_path / "docs" / "long.md").write_text(long_line)
    _save_pal_config(tmp_path, ["docs/*.md"])

    chunks = chunk_pal_source_files(tmp_path, max_chars=10)

    assert [chunk.source_path for chunk in chunks] == [
        "docs/long.md",
        "docs/long.md",
        "docs/long.md",
    ]
    assert [chunk.text for chunk in chunks] == ["abcdefghij", "klmnopqrst", "uvwxyz"]
    assert all(len(chunk.text) <= 10 for chunk in chunks)
    assert all(chunk.start_line == 1 for chunk in chunks)
    assert all(chunk.end_line == 1 for chunk in chunks)


def test_chunk_pal_source_files_preserves_isolated_blank_line_chunks(
    tmp_path: Path,
) -> None:
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "with-blank.md").write_text("abcde\n\nfghij\n")
    _save_pal_config(tmp_path, ["docs/*.md"])

    first = chunk_pal_source_files(tmp_path, max_chars=5)
    second = chunk_pal_source_files(tmp_path, max_chars=5)

    assert [chunk.text for chunk in first] == ["abcde", "", "fghij"]
    assert [chunk.start_line for chunk in first] == [1, 2, 3]
    assert [chunk.end_line for chunk in first] == [1, 2, 3]
    assert [chunk.chunk_id for chunk in second] == [chunk.chunk_id for chunk in first]


def test_chunk_pal_source_files_rejects_invalid_max_chars(tmp_path: Path) -> None:
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "alpha.md").write_text("# Alpha\n")
    _save_pal_config(tmp_path, ["docs/*.md"])

    with pytest.raises(ValueError, match="max_chars"):
        chunk_pal_source_files(tmp_path, max_chars=0)


def test_write_pal_knowledge_index_creates_default_jsonl_index(tmp_path: Path) -> None:
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "alpha.md").write_text("# Alpha\nfirst line\nsecond line\n")
    (tmp_path / "docs" / "beta.md").write_text("# Beta\nthird line\n")
    _save_pal_config(tmp_path, ["docs/*.md"])

    result = write_pal_knowledge_index(tmp_path, max_chars=24)

    assert isinstance(result, PALKnowledgeIndexBuild)
    assert result.index_path == tmp_path / ".promptclaw" / "pal-kb" / "index.jsonl"
    assert result.source_count == 2
    assert result.chunk_count == 3
    assert result.max_chars == 24
    assert result.index_path.exists()
    rows = [json.loads(line) for line in result.index_path.read_text().splitlines()]
    chunks = chunk_pal_source_files(tmp_path, max_chars=24)
    assert rows == [asdict(chunk) for chunk in chunks]
    assert [row["source_path"] for row in rows] == [
        "docs/alpha.md",
        "docs/alpha.md",
        "docs/beta.md",
    ]
    assert all(row["chunk_id"].startswith("pal-kb:") for row in rows)


def test_write_pal_knowledge_index_is_stable_and_replaces_stale_content(
    tmp_path: Path,
) -> None:
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "alpha.md").write_text("# Alpha\nfirst line\nsecond line\n")
    _save_pal_config(tmp_path, ["docs/*.md"])

    first = write_pal_knowledge_index(tmp_path, max_chars=24)
    first_bytes = first.index_path.read_bytes()
    first.index_path.write_text("stale content\n", encoding="utf-8")

    second = write_pal_knowledge_index(tmp_path, max_chars=24)

    assert second.index_path == first.index_path
    assert second.index_path.read_bytes() == first_bytes
    assert b"stale content" not in second.index_path.read_bytes()


def test_pal_kb_build_cli_writes_index_and_prints_summary(tmp_path: Path) -> None:
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "alpha.md").write_text("# Alpha\nfirst line\nsecond line\n")
    _save_pal_config(tmp_path, ["docs/*.md"])

    output = io.StringIO()
    args = argparse.Namespace(project_root=tmp_path, max_chars=24, output=None, json=False)
    with redirect_stdout(output):
        rc = cmd_pal_kb_build(args)

    assert rc == 0
    rendered = output.getvalue()
    assert "PAL KB build:" in rendered
    assert "sources=1" in rendered
    assert "chunks=2" in rendered
    assert ".promptclaw/pal-kb/index.jsonl" in rendered
    assert (tmp_path / ".promptclaw" / "pal-kb" / "index.jsonl").exists()


def test_query_pal_knowledge_index_returns_ranked_snippets_with_source_paths(
    tmp_path: Path,
) -> None:
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "router.md").write_text(
        "# Router\nPAL router restart validates health and smoke evidence.\n"
    )
    (tmp_path / "docs" / "deploy.md").write_text(
        "# Deploy\nRouter deployment uses a host-managed start script.\n"
    )
    (tmp_path / "docs" / "shutdown.md").write_text(
        "# Shutdown\nAudit the override flag before changing shutdown state.\n"
    )
    _save_pal_config(tmp_path, ["docs/*.md"])
    write_pal_knowledge_index(tmp_path, max_chars=200)

    results = query_pal_knowledge_index(tmp_path, "router restart", limit=2)

    assert len(results) == 2
    assert all(isinstance(result, PALKnowledgeQueryResult) for result in results)
    assert [result.rank for result in results] == [1, 2]
    assert results[0].source_path == "docs/router.md"
    assert results[0].score > results[1].score
    assert results[0].chunk_id.startswith("pal-kb:")
    assert results[0].start_line == 1
    assert results[0].end_line >= results[0].start_line
    assert "router restart" in results[0].snippet.lower()
    assert [result.source_path for result in results] == [
        "docs/router.md",
        "docs/deploy.md",
    ]
    assert all(len(result.snippet) <= 240 for result in results)
    assert json.dumps([asdict(result) for result in results], sort_keys=True)


def test_query_pal_knowledge_index_is_case_insensitive_and_deterministic(
    tmp_path: Path,
) -> None:
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "tailscale.md").write_text(
        "# Tailscale\nTailscale router checks confirm PAL reachability.\n"
    )
    (tmp_path / "docs" / "router.md").write_text(
        "# Router\nRouter health responses include loaded model state.\n"
    )
    (tmp_path / "docs" / "unrelated.md").write_text(
        "# Garden\nNothing about the operational query appears here.\n"
    )
    _save_pal_config(tmp_path, ["docs/*.md"])
    write_pal_knowledge_index(tmp_path, max_chars=200)

    first = query_pal_knowledge_index(tmp_path, "TAILSCALE ROUTER", limit=5)
    second = query_pal_knowledge_index(tmp_path, "tailscale router", limit=5)

    assert [asdict(result) for result in first] == [asdict(result) for result in second]
    assert [result.source_path for result in first] == [
        "docs/tailscale.md",
        "docs/router.md",
    ]
    assert all("docs/unrelated.md" != result.source_path for result in first)


def test_query_pal_knowledge_index_rejects_invalid_inputs(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="query"):
        query_pal_knowledge_index(tmp_path, " ")

    with pytest.raises(ValueError, match="limit"):
        query_pal_knowledge_index(tmp_path, "router", limit=0)

    with pytest.raises(FileNotFoundError, match="index.jsonl"):
        query_pal_knowledge_index(tmp_path, "router")

    malformed_index = tmp_path / "bad-index.jsonl"
    malformed_index.write_text("{bad json\n", encoding="utf-8")
    with pytest.raises(ValueError, match="line 1"):
        query_pal_knowledge_index(tmp_path, "router", index_path=malformed_index)


def test_pal_kb_query_cli_prints_ranked_snippets(tmp_path: Path) -> None:
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "router.md").write_text(
        "# Router\nPAL router restart validates health and smoke evidence.\n"
    )
    _save_pal_config(tmp_path, ["docs/*.md"])
    write_pal_knowledge_index(tmp_path, max_chars=200)

    output = io.StringIO()
    args = argparse.Namespace(
        project_root=tmp_path,
        query="router restart",
        limit=3,
        index=None,
        json=False,
    )
    with redirect_stdout(output):
        rc = cmd_pal_kb_query(args)

    assert rc == 0
    rendered = output.getvalue()
    assert "PAL KB query: matches=1" in rendered
    assert "1. docs/router.md:1-2" in rendered
    assert "score=" in rendered
    assert "PAL router restart validates health" in rendered


def _relative_paths(paths: tuple[Path, ...], root: Path) -> list[str]:
    return [path.relative_to(root).as_posix() for path in paths]


def _save_pal_config(root: Path, sources: list[str]) -> None:
    config = default_project_config("PAL Knowledge Chunking")
    config.pal = PALConfig(enabled=True, knowledge_sources=sources)
    save_config(root, config)


def _chunk_ids_by_source(chunks: tuple[PALKnowledgeChunk, ...]) -> dict[str, list[str]]:
    by_source: dict[str, list[str]] = {}
    for chunk in chunks:
        by_source.setdefault(chunk.source_path, []).append(chunk.chunk_id)
    return by_source
