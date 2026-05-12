"""Depth-2 tests for promptclaw.templates [frac-0048]."""

from __future__ import annotations

import json
from pathlib import Path

from promptclaw.templates import (
    ScaffoldTemplateEntry,
    ScaffoldTemplateReport,
    project_scaffold,
    required_startup_prompt_paths,
    scaffold_template_entries,
    scaffold_template_report,
    summarize_scaffold_templates,
    template_category,
)


TEMPLATES_MODULE_PATH = Path("promptclaw/templates.py")


def test_template_category_classifies_known_paths() -> None:
    assert template_category("promptclaw.json") == "config"
    assert template_category("docs/PROJECT_GUIDE.md") == "docs"
    assert template_category("prompts/control/routing.md") == "control_prompt"
    assert template_category("prompts/agents/codex.md") == "agent_prompt"
    assert template_category("prompts/00-project-vision.md") == "startup_prompt"
    assert template_category(".promptclaw/memory/project-memory.md") == "memory"
    assert template_category("examples/tasks/sample-task.md") == "example"
    assert template_category("scratch/notes.txt") == "other"


def test_scaffold_template_entries_preserve_project_scaffold_contract() -> None:
    scaffold = project_scaffold("Template Claw")

    entries = scaffold_template_entries("Template Claw")

    assert all(isinstance(entry, ScaffoldTemplateEntry) for entry in entries)
    assert [entry.path for entry in entries] == list(scaffold.keys())
    assert {entry.path: entry.content for entry in entries} == scaffold
    assert all(entry.size_bytes == len(entry.content.encode("utf-8")) for entry in entries)
    assert all(entry.size_bytes > 0 for entry in entries)
    assert entries[0].path == "promptclaw.json"
    assert json.loads(entries[0].content)["project"]["name"] == "Template Claw"


def test_scaffold_template_report_summarizes_generated_templates() -> None:
    report = scaffold_template_report("Report Claw")

    assert isinstance(report, ScaffoldTemplateReport)
    assert report.project_name == "Report Claw"
    assert report.file_count == 14
    assert report.total_size_bytes == sum(entry.size_bytes for entry in report.entries)
    assert report.categories == {
        "agent_prompt": 3,
        "config": 1,
        "control_prompt": 3,
        "docs": 1,
        "example": 2,
        "memory": 1,
        "startup_prompt": 3,
    }
    assert report.required_prompt_paths == required_startup_prompt_paths()
    assert report.missing_required_prompt_paths == ()


def test_summarize_scaffold_templates_is_json_safe() -> None:
    summary = summarize_scaffold_templates("Summary Claw")

    json.dumps(summary)
    assert summary["project_name"] == "Summary Claw"
    assert summary["file_count"] == 14
    assert summary["categories"]["startup_prompt"] == 3
    assert summary["required_prompt_paths"] == list(required_startup_prompt_paths())
    assert summary["missing_required_prompt_paths"] == []
    assert summary["entries"][0] == {
        "path": "promptclaw.json",
        "category": "config",
        "size_bytes": len(project_scaffold("Summary Claw")["promptclaw.json"].encode("utf-8")),
    }


def test_templates_module_reaches_depth_two() -> None:
    from sdp.fractal import classify_depth

    result = classify_depth(TEMPLATES_MODULE_PATH)

    assert result.depth >= 2, result.reason
