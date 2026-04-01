"""Tests for the project scanner runtime helpers."""

from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "my-claw" / "tools"))

import project_scanner


def test_discover_projects_respects_max_depth(tmp_path) -> None:
    shallow = tmp_path / "shallow-app"
    shallow.mkdir()
    (shallow / "pyproject.toml").write_text("[project]\nname='shallow'\n")

    deep = tmp_path / "too" / "deep" / "repo"
    deep.mkdir(parents=True)
    (deep / "package.json").write_text('{"name": "deep"}')

    discovered = project_scanner.discover_projects([str(tmp_path)], max_depth=1)

    assert str(shallow) in discovered
    assert str(deep) not in discovered


def test_analyze_project_collects_framework_deployment_and_git_info(tmp_path, monkeypatch) -> None:
    project = tmp_path / "sample-app"
    project.mkdir()
    (project / ".git").mkdir()
    (project / "package.json").write_text(
        json.dumps(
            {
                "name": "sample-app",
                "dependencies": {
                    "react": "^18.0.0",
                    "next": "^15.0.0",
                    "tailwindcss": "^4.0.0",
                },
                "scripts": {"test": "vitest"},
                "private": False,
                "files": ["dist"],
            }
        )
    )
    (project / "Dockerfile").write_text("FROM python:3.12-slim\n")
    workflows = project / ".github" / "workflows"
    workflows.mkdir(parents=True)
    (workflows / "deploy.yml").write_text("name: deploy\nsteps:\n  - run: vercel deploy\n")
    (project / "tests").mkdir()
    (project / "src").mkdir()
    (project / "src" / "app.tsx").write_text("export default function App() { return null }\n")

    git_responses = {
        ("config", "--get", "remote.origin.url"): "git@github.com:artist/sample-app.git",
        ("log", "-1", "--format=%aI"): "2026-03-25T00:00:00+00:00",
        ("rev-list", "--count", "HEAD"): "42",
    }

    monkeypatch.setattr(
        project_scanner,
        "run_git",
        lambda args, cwd, timeout=15: git_responses.get(tuple(args)),
    )
    monkeypatch.setattr(project_scanner, "dir_size_mb", lambda path: 12.5)

    info = project_scanner.analyze_project(
        str(project),
        now=dt.datetime(2026, 4, 1, tzinfo=dt.timezone.utc),
    )

    assert info["has_git"] is True
    assert info["git_remote"] == "git@github.com:artist/sample-app.git"
    assert info["last_commit_age_days"] == 7
    assert info["total_commits"] == 42
    assert info["primary_language"] == "TypeScript"
    assert {"React", "Next.js", "Tailwind CSS"}.issubset(info["frameworks"])
    assert info["has_tests"] is True
    assert info["has_ci"] is True
    assert info["has_docker"] is True
    assert info["deployment_status"] == "deployed"
    assert info["migration_ready"] == "yes"


def test_correlate_github_matches_remote_and_name(monkeypatch) -> None:
    projects = [
        {
            "name": "sample-app",
            "path": "/tmp/sample-app",
            "has_git": True,
            "git_remote": "git@github.com:artist/sample-app.git",
        },
        {
            "name": "local-only",
            "path": "/tmp/local-only",
            "has_git": False,
            "git_remote": None,
        },
    ]
    github_json = [
        {
            "name": "sample-app",
            "full_name": "artist/sample-app",
            "clone_url": "https://github.com/artist/sample-app.git",
            "html_url": "https://github.com/artist/sample-app",
        },
        {
            "name": "remote-only",
            "full_name": "artist/remote-only",
            "clone_url": "https://github.com/artist/remote-only.git",
            "html_url": "https://github.com/artist/remote-only",
        },
    ]

    monkeypatch.setattr(project_scanner, "_check_sync_status", lambda path: "ahead by 2")

    correlation_path = Path("/tmp/project-scanner-gh.json")
    correlation_path.write_text(json.dumps(github_json))
    try:
        result = project_scanner.correlate_github(projects, str(correlation_path))
    finally:
        correlation_path.unlink(missing_ok=True)

    assert result["github_file_loaded"] is True
    assert result["matched"][0]["github_repo"] == "artist/sample-app"
    assert result["matched"][0]["sync_status"] == "ahead by 2"
    assert result["local_only"][0]["name"] == "local-only"
    assert result["github_only"][0]["name"] == "remote-only"


def test_generate_reports_write_summary_sections(tmp_path) -> None:
    projects = [
        {
            "name": "sample-app",
            "path": "/tmp/sample-app",
            "disk_size_mb": 12.5,
            "has_git": True,
            "git_remote": "git@github.com:artist/sample-app.git",
            "last_commit_date": "2026-03-25T00:00:00+00:00",
            "last_commit_age_days": 7,
            "total_commits": 42,
            "primary_language": "TypeScript",
            "languages": ["TypeScript"],
            "frameworks": ["React"],
            "has_tests": True,
            "has_ci": True,
            "has_docker": True,
            "mac_specific": False,
            "mac_specific_reasons": [],
            "dependencies_file": "package.json",
            "is_monorepo": False,
            "nested_projects": [],
            "deployment_status": "deployed",
            "deployment_targets": ["Vercel"],
            "deployment_notes": ["Has automated deployment pipeline or hosting config"],
            "activity": "active",
            "migration_ready": "yes",
            "migration_notes": ["No mac-specific dependencies detected"],
        }
    ]
    correlation = {
        "github_file_loaded": True,
        "total_github_repos": 1,
        "matched": [
            {
                "name": "sample-app",
                "path": "/tmp/sample-app",
                "github_repo": "artist/sample-app",
                "match_method": "remote_url",
                "sync_status": "in_sync",
            }
        ],
        "local_only": [],
        "github_only": [],
    }

    json_path = tmp_path / "report" / "scan.json"
    md_path = tmp_path / "report" / "scan.md"

    project_scanner.generate_json_report(projects, correlation, str(json_path))
    project_scanner.generate_markdown_report(projects, correlation, str(md_path))

    report = json.loads(json_path.read_text())
    markdown = md_path.read_text()

    assert report["total_projects"] == 1
    assert report["projects"][0]["name"] == "sample-app"
    assert "# Project Scanner Report" in markdown
    assert "## Executive Summary" in markdown
    assert "## GitHub Correlation" in markdown
    assert "sample-app" in markdown
