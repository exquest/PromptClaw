from __future__ import annotations

import hashlib
from dataclasses import dataclass
from glob import glob
from pathlib import Path

from .config import load_config
from .models import PromptClawConfig

DEFAULT_PAL_KNOWLEDGE_SOURCES: tuple[str, ...] = (
    "docs/**/*.md",
    "ops/**/*.md",
    "ops/templates/*.conf",
    "ops/templates/*.md",
    "ops/templates/*.py",
    "ops/templates/*.sh",
    "ops/templates/*.yml",
    "ops/templates/router-Dockerfile",
    ".promptclaw/pal-smoke/*.json",
    ".promptclaw/runs/**/summary/*.md",
    ".promptclaw/runs/**/outputs/*.json",
)


@dataclass(frozen=True)
class PALKnowledgeChunk:
    chunk_id: str
    source_path: str
    source_sha256: str
    chunk_index: int
    start_line: int
    end_line: int
    text: str


def discover_pal_source_files(
    project_root: Path,
    config: PromptClawConfig | None = None,
) -> tuple[Path, ...]:
    """Return configured PAL knowledge source files in deterministic order."""
    root = project_root.resolve()
    active_config = config or load_config(root)
    configured_sources = tuple(active_config.pal.knowledge_sources)
    patterns = configured_sources or DEFAULT_PAL_KNOWLEDGE_SOURCES
    discovered: dict[str, Path] = {}

    for pattern in patterns:
        for path in _expand_source_pattern(root, pattern):
            if not path.is_file():
                continue
            resolved = path.resolve()
            discovered[resolved.as_posix()] = resolved

    return tuple(discovered[key] for key in sorted(discovered))


def chunk_pal_source_files(
    project_root: Path,
    config: PromptClawConfig | None = None,
    *,
    max_chars: int = 2000,
) -> tuple[PALKnowledgeChunk, ...]:
    """Return deterministic PAL knowledge chunks for configured source files."""
    if max_chars <= 0:
        raise ValueError("max_chars must be greater than 0")

    root = project_root.resolve()
    chunks: list[PALKnowledgeChunk] = []
    for path in discover_pal_source_files(root, config=config):
        text = _normalize_text(path.read_text(encoding="utf-8"))
        if not text.strip():
            continue
        source_path = _source_reference(root, path.resolve())
        source_sha256 = hashlib.sha256(text.encode("utf-8")).hexdigest()
        chunks.extend(
            _chunk_text(
                source_path=source_path,
                source_sha256=source_sha256,
                text=text,
                max_chars=max_chars,
            )
        )
    return tuple(chunks)


def _expand_source_pattern(project_root: Path, pattern: str) -> tuple[Path, ...]:
    stripped = pattern.strip()
    if not stripped:
        return ()
    pattern_path = Path(stripped).expanduser()
    search_pattern = str(pattern_path if pattern_path.is_absolute() else project_root / stripped)
    return tuple(Path(match) for match in glob(search_pattern, recursive=True))


def _normalize_text(text: str) -> str:
    return "\n".join(text.splitlines())


def _source_reference(project_root: Path, source_path: Path) -> str:
    try:
        return source_path.relative_to(project_root).as_posix()
    except ValueError:
        return source_path.as_posix()


def _chunk_text(
    *,
    source_path: str,
    source_sha256: str,
    text: str,
    max_chars: int,
) -> tuple[PALKnowledgeChunk, ...]:
    lines = text.split("\n")
    chunks: list[PALKnowledgeChunk] = []
    current_lines: list[str] = []
    current_start_line = 1
    current_length = 0

    def flush_current(end_line: int) -> None:
        nonlocal current_lines, current_start_line, current_length
        if not current_lines:
            return
        chunk_text = "\n".join(current_lines)
        if not chunk_text:
            current_lines = []
            current_length = 0
            return
        chunks.append(
            _make_chunk(
                source_path=source_path,
                source_sha256=source_sha256,
                chunk_index=len(chunks),
                start_line=current_start_line,
                end_line=end_line,
                text=chunk_text,
            )
        )
        current_lines = []
        current_length = 0

    for line_number, line in enumerate(lines, start=1):
        if len(line) > max_chars:
            flush_current(line_number - 1)
            for offset in range(0, len(line), max_chars):
                chunks.append(
                    _make_chunk(
                        source_path=source_path,
                        source_sha256=source_sha256,
                        chunk_index=len(chunks),
                        start_line=line_number,
                        end_line=line_number,
                        text=line[offset : offset + max_chars],
                    )
                )
            continue

        added_length = len(line) if not current_lines else len(line) + 1
        if current_lines and current_length + added_length > max_chars:
            flush_current(line_number - 1)

        if not current_lines:
            current_start_line = line_number
            current_length = len(line)
            current_lines = [line]
        else:
            current_lines.append(line)
            current_length += len(line) + 1

    flush_current(len(lines))
    return tuple(chunks)


def _make_chunk(
    *,
    source_path: str,
    source_sha256: str,
    chunk_index: int,
    start_line: int,
    end_line: int,
    text: str,
) -> PALKnowledgeChunk:
    digest = hashlib.sha256(
        "\0".join(
            [
                source_path,
                source_sha256,
                str(chunk_index),
                str(start_line),
                str(end_line),
                text,
            ]
        ).encode("utf-8")
    ).hexdigest()
    return PALKnowledgeChunk(
        chunk_id=f"pal-kb:{digest[:24]}",
        source_path=source_path,
        source_sha256=source_sha256,
        chunk_index=chunk_index,
        start_line=start_line,
        end_line=end_line,
        text=text,
    )
