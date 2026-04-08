"""Regression tests for agent selector provider and fitness defaults."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "my-claw" / "tools"))

import agent_selector


OLLAMA_CATEGORIES = {
    "architecture",
    "coding",
    "review",
    "research",
    "routing",
    "writing",
    "testing",
    "devops",
    "netops",
}


def test_ollama_provider_and_fitness_defaults() -> None:
    assert agent_selector.PROVIDERS["ollama"] == "local"

    fitness = agent_selector.DEFAULT_FITNESS["ollama"]

    assert set(fitness) == OLLAMA_CATEGORIES
    assert fitness["netops"] == pytest.approx(0.80)
    assert fitness["netops"] == max(fitness.values())
