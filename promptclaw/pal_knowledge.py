from __future__ import annotations

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


def _expand_source_pattern(project_root: Path, pattern: str) -> tuple[Path, ...]:
    stripped = pattern.strip()
    if not stripped:
        return ()
    pattern_path = Path(stripped).expanduser()
    search_pattern = str(pattern_path if pattern_path.is_absolute() else project_root / stripped)
    return tuple(Path(match) for match in glob(search_pattern, recursive=True))
