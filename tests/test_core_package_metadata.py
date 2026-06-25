"""Packaging metadata checks for the slim PromptClaw core."""

from __future__ import annotations

import re
import tomllib
from pathlib import Path


PYPROJECT = Path("pyproject.toml")


def _pyproject() -> dict[str, object]:
    return tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))


def _dependency_names(dependencies: list[str]) -> set[str]:
    return {re.split(r"[\[<>=!~; ]", dependency, maxsplit=1)[0].lower() for dependency in dependencies}


def test_core_dependencies_do_not_install_cypherclaw_music_libraries() -> None:
    project = _pyproject()["project"]
    dependencies = _dependency_names(project.get("dependencies", []))

    assert "librosa" not in dependencies
    assert "partitura" not in dependencies


def test_cypherclaw_extra_restores_music_and_runtime_dependencies() -> None:
    project = _pyproject()["project"]
    optional = project["optional-dependencies"]

    cypherclaw_dependencies = _dependency_names(optional["cypherclaw"])
    narrative_dependencies = _dependency_names(optional["narrative-api"])

    assert {"librosa", "partitura"} <= cypherclaw_dependencies
    assert narrative_dependencies <= cypherclaw_dependencies


def test_cypherclaw_scripts_are_covered_by_the_cypherclaw_extra() -> None:
    project = _pyproject()["project"]
    scripts = project["scripts"]
    cypherclaw_dependencies = _dependency_names(project["optional-dependencies"]["cypherclaw"])

    assert scripts["narrative-api"].startswith("cypherclaw.")
    assert scripts["cypherclaw-midi-intake"].startswith("cypherclaw.")
    assert scripts["cypherclaw-live-midi-emitter"].startswith("cypherclaw.")
    assert {"fastapi", "librosa", "partitura"} <= cypherclaw_dependencies


def test_package_discovery_includes_promptclaw_core() -> None:
    package_find = _pyproject()["tool"]["setuptools"]["packages"]["find"]

    assert "promptclaw*" in package_find["include"]
