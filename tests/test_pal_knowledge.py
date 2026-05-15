from __future__ import annotations

from dataclasses import asdict
import json
from pathlib import Path

import pytest

from promptclaw.config import default_project_config, save_config
from promptclaw.models import PALConfig
from promptclaw.pal_knowledge import (
    PALKnowledgeChunk,
    chunk_pal_source_files,
    discover_pal_source_files,
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


def test_chunk_pal_source_files_rejects_invalid_max_chars(tmp_path: Path) -> None:
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "alpha.md").write_text("# Alpha\n")
    _save_pal_config(tmp_path, ["docs/*.md"])

    with pytest.raises(ValueError, match="max_chars"):
        chunk_pal_source_files(tmp_path, max_chars=0)


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
