"""Depth-2 tests for shared pytest collection gates [frac-0054]."""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path
from typing import Any

import conftest

CONFTST_MODULE_PATH = Path(__file__).resolve().parent / "conftest.py"


class FakeParser:
    def __init__(self) -> None:
        self.options: list[tuple[tuple[str, ...], dict[str, object]]] = []

    def addoption(self, *names: str, **kwargs: object) -> None:
        self.options.append((names, kwargs))


class FakeConfig:
    def __init__(self, options: dict[str, bool] | None = None) -> None:
        self.options = options or {}
        self.ini_lines: list[tuple[str, str]] = []

    def getoption(self, name: str) -> bool:
        return self.options.get(name, False)

    def addinivalue_line(self, key: str, value: str) -> None:
        self.ini_lines.append((key, value))


class FakeItem:
    def __init__(self, *keywords: str) -> None:
        self.keywords = {keyword: True for keyword in keywords}
        self.markers: list[Any] = []

    def add_marker(self, marker: Any) -> None:
        self.markers.append(marker)


def _skip_reasons(item: FakeItem) -> list[str]:
    return [marker.mark.kwargs["reason"] for marker in item.markers]


def test_conftest_exposes_collection_gate_surface() -> None:
    for name in (
        "CollectionGateDecision",
        "collection_gate_decisions",
        "apply_collection_gate_decisions",
        "summarize_collection_gate_decisions",
    ):
        assert hasattr(conftest, name)

    decision = conftest.CollectionGateDecision(
        marker="live_modal",
        option="--run-live-modal",
        enabled=False,
        skip_reason="need --run-live-modal option to run",
        matched_count=2,
        skipped_count=2,
    )

    assert dataclasses.is_dataclass(decision)
    assert getattr(decision, "__dataclass_params__").frozen
    assert decision.marker == "live_modal"
    assert decision.skipped_count == 2


def test_pytest_addoption_registers_live_flags() -> None:
    parser = FakeParser()

    conftest.pytest_addoption(parser)  # type: ignore[arg-type]

    registered = {names[0]: kwargs for names, kwargs in parser.options}
    assert registered["--run-live-modal"] == {
        "action": "store_true",
        "default": False,
        "help": "run live Modal tests",
    }
    assert registered["--run-live-replicate"] == {
        "action": "store_true",
        "default": False,
        "help": "run live Replicate tests",
    }
    assert registered["--run-live-pal"] == {
        "action": "store_true",
        "default": False,
        "help": "run live PAL router tests",
    }


def test_pytest_configure_registers_expected_markers() -> None:
    config = FakeConfig()

    conftest.pytest_configure(config)  # type: ignore[arg-type]

    assert config.ini_lines == [
        ("markers", "live_modal: mark test as requiring a live Modal environment"),
        (
            "markers",
            "live_replicate: mark test as requiring a live Replicate environment",
        ),
        (
            "markers",
            "cypherclaw_e2e: mark test as requiring the live CypherClaw audio host",
        ),
        ("markers", "live_pal: mark test as requiring a live PAL router"),
    ]


def test_default_gate_application_skips_live_markers_only() -> None:
    config = FakeConfig()
    live_modal = FakeItem("live_modal")
    live_replicate = FakeItem("live_replicate")
    cypherclaw_e2e = FakeItem("cypherclaw_e2e")
    live_pal = FakeItem("live_pal")
    ordinary = FakeItem()

    decisions = conftest.apply_collection_gate_decisions(
        config,
        [live_modal, live_replicate, cypherclaw_e2e, live_pal, ordinary],  # type: ignore[list-item]
        environ={},
    )

    by_marker = {decision.marker: decision for decision in decisions}
    assert by_marker["live_modal"].matched_count == 1
    assert by_marker["live_modal"].skipped_count == 1
    assert by_marker["live_replicate"].matched_count == 1
    assert by_marker["live_replicate"].skipped_count == 1
    assert by_marker["cypherclaw_e2e"].matched_count == 1
    assert by_marker["cypherclaw_e2e"].skipped_count == 0
    assert by_marker["live_pal"].matched_count == 1
    assert by_marker["live_pal"].skipped_count == 1

    assert _skip_reasons(live_modal) == ["need --run-live-modal option to run"]
    assert _skip_reasons(live_replicate) == [
        "need --run-live-replicate option to run"
    ]
    assert _skip_reasons(cypherclaw_e2e) == []
    assert _skip_reasons(live_pal) == ["need --run-live-pal option to run"]
    assert _skip_reasons(ordinary) == []


def test_enabled_live_flags_and_ci_gate_apply_expected_skips() -> None:
    config = FakeConfig(
        {
            "--run-live-modal": True,
            "--run-live-replicate": True,
            "--run-live-pal": True,
        }
    )
    live_modal = FakeItem("live_modal")
    live_replicate = FakeItem("live_replicate")
    cypherclaw_e2e = FakeItem("cypherclaw_e2e")
    live_pal = FakeItem("live_pal")

    decisions = conftest.apply_collection_gate_decisions(
        config,
        [live_modal, live_replicate, cypherclaw_e2e, live_pal],  # type: ignore[list-item]
        environ={"CI": "true"},
    )

    by_marker = {decision.marker: decision for decision in decisions}
    assert by_marker["live_modal"].enabled is True
    assert by_marker["live_modal"].skipped_count == 0
    assert by_marker["live_replicate"].enabled is True
    assert by_marker["live_replicate"].skipped_count == 0
    assert by_marker["cypherclaw_e2e"].enabled is False
    assert by_marker["cypherclaw_e2e"].skipped_count == 1
    assert by_marker["live_pal"].enabled is True
    assert by_marker["live_pal"].skipped_count == 0

    assert _skip_reasons(live_modal) == []
    assert _skip_reasons(live_replicate) == []
    assert _skip_reasons(cypherclaw_e2e) == ["cypherclaw e2e skipped on CI"]
    assert _skip_reasons(live_pal) == []


def test_collection_gate_summary_is_json_safe() -> None:
    config = FakeConfig()
    decisions = conftest.apply_collection_gate_decisions(
        config,
        [FakeItem("live_modal"), FakeItem("live_replicate"), FakeItem()],  # type: ignore[list-item]
        environ={},
    )

    summary = conftest.summarize_collection_gate_decisions(decisions)

    assert summary["marker_count"] == 4
    assert summary["enabled_count"] == 1
    assert summary["matched_item_count"] == 2
    assert summary["skipped_item_count"] == 2
    rows = summary["markers"]
    assert isinstance(rows, list)
    assert rows[0] == {
        "marker": "live_modal",
        "option": "--run-live-modal",
        "enabled": False,
        "skip_reason": "need --run-live-modal option to run",
        "matched_count": 1,
        "skipped_count": 1,
    }
    json.dumps(summary)


def test_conftest_reaches_depth_two() -> None:
    from sdp.fractal import classify_depth

    result = classify_depth(CONFTST_MODULE_PATH)
    assert result.depth >= 2, result.reason
