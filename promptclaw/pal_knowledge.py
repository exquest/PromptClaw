from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from dataclasses import asdict, dataclass
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


@dataclass(frozen=True)
class PALKnowledgeIndexBuild:
    index_path: Path
    source_count: int
    chunk_count: int
    max_chars: int


@dataclass(frozen=True)
class PALKnowledgeQueryResult:
    rank: int
    score: float
    chunk_id: str
    source_path: str
    start_line: int
    end_line: int
    snippet: str


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


def write_pal_knowledge_index(
    project_root: Path,
    config: PromptClawConfig | None = None,
    *,
    max_chars: int = 2000,
    output_path: Path | None = None,
) -> PALKnowledgeIndexBuild:
    """Write the deterministic PAL knowledge chunk stream as JSON Lines."""
    if max_chars <= 0:
        raise ValueError("max_chars must be greater than 0")

    root = project_root.resolve()
    active_config = config or load_config(root)
    source_paths = discover_pal_source_files(root, config=active_config)
    chunks = chunk_pal_source_files(root, config=active_config, max_chars=max_chars)
    index_path = output_path if output_path is not None else _default_index_path(root, active_config)
    _write_jsonl_index(index_path, chunks)
    return PALKnowledgeIndexBuild(
        index_path=index_path,
        source_count=len(source_paths),
        chunk_count=len(chunks),
        max_chars=max_chars,
    )


def query_pal_knowledge_index(
    project_root: Path,
    query: str,
    *,
    index_path: Path | None = None,
    limit: int = 5,
) -> tuple[PALKnowledgeQueryResult, ...]:
    """Return ranked local PAL knowledge snippets from a JSONL index."""
    normalized_query = " ".join(query.split())
    if not normalized_query:
        raise ValueError("query must not be empty")
    if limit <= 0:
        raise ValueError("limit must be greater than 0")

    root = project_root.resolve()
    if index_path is None:
        resolved_index_path = _default_query_index_path(root)
    else:
        resolved_index_path = index_path
    chunks = _read_jsonl_index(resolved_index_path)
    query_terms = _unique_terms(_tokenize(normalized_query))
    query_phrase = normalized_query.lower()
    scored: list[tuple[float, PALKnowledgeChunk]] = []

    for chunk in chunks:
        score = _score_chunk(chunk.text, query_terms=query_terms, query_phrase=query_phrase)
        if score <= 0:
            continue
        scored.append((score, chunk))

    scored.sort(
        key=lambda item: (
            -item[0],
            item[1].source_path,
            item[1].start_line,
            item[1].end_line,
            item[1].chunk_id,
        )
    )
    results: list[PALKnowledgeQueryResult] = []
    for rank, (score, chunk) in enumerate(scored[:limit], start=1):
        results.append(
            PALKnowledgeQueryResult(
                rank=rank,
                score=round(score, 3),
                chunk_id=chunk.chunk_id,
                source_path=chunk.source_path,
                start_line=chunk.start_line,
                end_line=chunk.end_line,
                snippet=_make_snippet(
                    chunk.text,
                    query_terms=query_terms,
                    query_phrase=query_phrase,
                ),
            )
        )
    return tuple(results)


def _expand_source_pattern(project_root: Path, pattern: str) -> tuple[Path, ...]:
    stripped = pattern.strip()
    if not stripped:
        return ()
    pattern_path = Path(stripped).expanduser()
    search_pattern = str(pattern_path if pattern_path.is_absolute() else project_root / stripped)
    return tuple(Path(match) for match in glob(search_pattern, recursive=True))


def _normalize_text(text: str) -> str:
    return "\n".join(text.splitlines())


def _default_index_path(project_root: Path, config: PromptClawConfig) -> Path:
    return project_root / config.artifacts.root / "pal-kb" / "index.jsonl"


def _default_query_index_path(project_root: Path) -> Path:
    try:
        return _default_index_path(project_root, load_config(project_root))
    except FileNotFoundError:
        return project_root / ".promptclaw" / "pal-kb" / "index.jsonl"


def _write_jsonl_index(path: Path, chunks: tuple[PALKnowledgeChunk, ...]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f".{path.name}.tmp")
    try:
        lines = [json.dumps(asdict(chunk), sort_keys=True, ensure_ascii=False) for chunk in chunks]
        content = "\n".join(lines)
        if content:
            content += "\n"
        temp_path.write_text(content, encoding="utf-8")
        temp_path.replace(path)
    finally:
        if temp_path.exists():
            temp_path.unlink()


def _read_jsonl_index(path: Path) -> tuple[PALKnowledgeChunk, ...]:
    if not path.exists():
        raise FileNotFoundError(f"PAL KB index not found: {path}")

    chunks: list[PALKnowledgeChunk] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Malformed PAL KB index JSONL at {path}: line {line_number}") from exc
        try:
            chunks.append(
                PALKnowledgeChunk(
                    chunk_id=str(payload["chunk_id"]),
                    source_path=str(payload["source_path"]),
                    source_sha256=str(payload["source_sha256"]),
                    chunk_index=int(payload["chunk_index"]),
                    start_line=int(payload["start_line"]),
                    end_line=int(payload["end_line"]),
                    text=str(payload["text"]),
                )
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"Malformed PAL KB index row at {path}: line {line_number}") from exc
    return tuple(chunks)


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


_TOKEN_RE = re.compile(r"[A-Za-z0-9_]+")


def _tokenize(text: str) -> tuple[str, ...]:
    return tuple(match.group(0).lower() for match in _TOKEN_RE.finditer(text))


def _unique_terms(terms: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(terms))


def _score_chunk(
    text: str,
    *,
    query_terms: tuple[str, ...],
    query_phrase: str,
) -> float:
    text_terms = Counter(_tokenize(text))
    if not text_terms:
        return 0.0

    overlap = sum(1 for term in query_terms if term in text_terms)
    if overlap == 0:
        return 0.0

    frequency = sum(min(text_terms[term], 3) for term in query_terms)
    score = float(overlap * 10 + frequency)
    if query_phrase and query_phrase in " ".join(text.split()).lower():
        score += 5.0
    return score


def _make_snippet(
    text: str,
    *,
    query_terms: tuple[str, ...],
    query_phrase: str,
    max_chars: int = 240,
) -> str:
    collapsed = " ".join(text.split())
    if len(collapsed) <= max_chars:
        return collapsed

    lower = collapsed.lower()
    match_index = lower.find(query_phrase) if query_phrase else -1
    if match_index < 0:
        term_positions = [lower.find(term) for term in query_terms if lower.find(term) >= 0]
        match_index = min(term_positions) if term_positions else 0

    start = max(0, match_index - max_chars // 3)
    end = min(len(collapsed), start + max_chars)
    start = max(0, end - max_chars)
    snippet = collapsed[start:end]
    if start > 0:
        snippet = "..." + snippet[3:]
    if end < len(collapsed):
        snippet = snippet[:-3] + "..."
    return snippet
