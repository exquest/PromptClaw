"""Shared test bootstrap."""

from __future__ import annotations

import os
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
import tempfile

os.environ["PROMPTCLAW_PETS_FILE"] = os.path.join(tempfile.gettempdir(), "promptclaw_pets.json")
os.environ["NUMBA_CACHE_DIR"] = os.path.join(tempfile.gettempdir(), "numba_cache")

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = REPO_ROOT / "src"
LIVE_PYTEST_OPTIONS: tuple[tuple[str, str], ...] = (
    ("--run-live-modal", "run live Modal tests"),
    ("--run-live-replicate", "run live Replicate tests"),
)
PYTEST_MARKER_DEFINITIONS: tuple[tuple[str, str], ...] = (
    ("live_modal", "mark test as requiring a live Modal environment"),
    ("live_replicate", "mark test as requiring a live Replicate environment"),
    ("cypherclaw_e2e", "mark test as requiring the live CypherClaw audio host"),
)

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


@dataclass(frozen=True)
class CollectionGateDecision:
    """Resolved pytest collection gate for one marker."""

    marker: str
    option: str | None
    enabled: bool
    skip_reason: str
    matched_count: int
    skipped_count: int


def collection_gate_decisions(
    config: pytest.Config,
    items: Sequence[pytest.Item],
    environ: Mapping[str, str] | None = None,
) -> tuple[CollectionGateDecision, ...]:
    """Return skip decisions for live/host-specific collection markers."""

    environment = os.environ if environ is None else environ
    gate_inputs: tuple[tuple[str, str | None, bool, str], ...] = (
        (
            "live_modal",
            "--run-live-modal",
            bool(config.getoption("--run-live-modal")),
            "need --run-live-modal option to run",
        ),
        (
            "live_replicate",
            "--run-live-replicate",
            bool(config.getoption("--run-live-replicate")),
            "need --run-live-replicate option to run",
        ),
        (
            "cypherclaw_e2e",
            None,
            "CI" not in environment,
            "cypherclaw e2e skipped on CI",
        ),
    )

    decisions: list[CollectionGateDecision] = []
    for marker, option, enabled, skip_reason in gate_inputs:
        matched_count = 0
        for item in items:
            if marker in item.keywords:
                matched_count += 1
        skipped_count = 0 if enabled else matched_count
        decisions.append(
            CollectionGateDecision(
                marker=marker,
                option=option,
                enabled=enabled,
                skip_reason=skip_reason,
                matched_count=matched_count,
                skipped_count=skipped_count,
            )
        )
    return tuple(decisions)


def apply_collection_gate_decisions(
    config: pytest.Config,
    items: Sequence[pytest.Item],
    environ: Mapping[str, str] | None = None,
) -> tuple[CollectionGateDecision, ...]:
    """Apply skip markers and return the collection-gate decisions."""

    decisions = collection_gate_decisions(config, items, environ=environ)
    for decision in decisions:
        if decision.enabled or decision.skipped_count == 0:
            continue
        skip_marker = pytest.mark.skip(reason=decision.skip_reason)
        for item in items:
            if decision.marker in item.keywords:
                item.add_marker(skip_marker)
    return decisions


def summarize_collection_gate_decisions(
    decisions: Sequence[CollectionGateDecision],
) -> dict[str, object]:
    """Render collection-gate decisions as JSON-safe operator output."""

    marker_rows: list[dict[str, object]] = []
    enabled_count = 0
    matched_item_count = 0
    skipped_item_count = 0
    for decision in decisions:
        if decision.enabled:
            enabled_count += 1
        matched_item_count += decision.matched_count
        skipped_item_count += decision.skipped_count
        marker_rows.append(
            {
                "marker": decision.marker,
                "option": decision.option,
                "enabled": decision.enabled,
                "skip_reason": decision.skip_reason,
                "matched_count": decision.matched_count,
                "skipped_count": decision.skipped_count,
            }
        )

    return {
        "marker_count": len(decisions),
        "enabled_count": enabled_count,
        "matched_item_count": matched_item_count,
        "skipped_item_count": skipped_item_count,
        "markers": marker_rows,
    }


def pytest_addoption(parser: pytest.Parser) -> None:
    for option, help_text in LIVE_PYTEST_OPTIONS:
        parser.addoption(option, action="store_true", default=False, help=help_text)


def pytest_configure(config: pytest.Config) -> None:
    for marker, description in PYTEST_MARKER_DEFINITIONS:
        config.addinivalue_line("markers", f"{marker}: {description}")


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    decisions = apply_collection_gate_decisions(config, items)
    if not decisions:
        return
