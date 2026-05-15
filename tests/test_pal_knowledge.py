from __future__ import annotations

from pathlib import Path

from promptclaw.config import default_project_config, save_config
from promptclaw.models import PALConfig
from promptclaw.pal_knowledge import discover_pal_source_files


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


def _relative_paths(paths: tuple[Path, ...], root: Path) -> list[str]:
    return [path.relative_to(root).as_posix() for path in paths]
