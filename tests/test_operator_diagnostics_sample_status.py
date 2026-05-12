"""Unit tests for the sampler status line on `OperatorDiagnostics`.

Pins the four discrete states of `OperatorDiagnostics.sample_source`
produced by `senseweave.operator_diagnostics.collect_operator_diagnostics`:

1. sampling-only — capture active, playback silent.
2. playing-only — playback active, capture idle.
3. both — capture and playback both active.
4. neither — capture and playback both idle, no composer-state fallback.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools"))
sys.path.insert(
    0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools", "senseweave")
)

from senseweave.operator_diagnostics import (
    DiagnosticPaths,
    collect_operator_diagnostics,
)


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def _paths(
    tmp_path: Path,
    *,
    sample_activity: Path | None = None,
    sample_playback: Path | None = None,
    composer_state: Path | None = None,
) -> DiagnosticPaths:
    missing = tmp_path / "missing.json"
    return DiagnosticPaths(
        score_tree=tmp_path / "missing_score_tree.json",
        tracker_runtime=tmp_path / "missing_tracker.json",
        composer_state=composer_state or missing,
        sample_activity=sample_activity or missing,
        sample_playback=sample_playback or missing,
        master_bus=tmp_path / "missing_master_bus.json",
        self_listener=tmp_path / "missing_self_listener.json",
        theramini=tmp_path / "missing_theramini.json",
    )


def test_sample_source_sampling_only(tmp_path: Path) -> None:
    sample_activity_path = tmp_path / "sample_dsp_activity.json"
    sample_playback_path = tmp_path / "sample_playback_state.json"
    _write_json(
        sample_activity_path,
        {
            "requested_sample_source": "theramini_in",
            "sample_source": "room_mic",
            "activity_mode": "grain_cloud",
            "capture_ready": True,
            "trigger_now": True,
        },
    )
    _write_json(sample_playback_path, {"playing": False})

    diagnostics = collect_operator_diagnostics(
        paths=_paths(
            tmp_path,
            sample_activity=sample_activity_path,
            sample_playback=sample_playback_path,
        ),
        now=100.0,
    )

    line = diagnostics.sample_source
    lower = line.lower()
    assert "currently sampling theramini in via room mic" in lower
    assert "playing sample" not in lower
    assert line != "unavailable"


def test_sample_source_playing_only(tmp_path: Path) -> None:
    sample_playback_path = tmp_path / "sample_playback_state.json"
    _write_json(
        sample_playback_path,
        {
            "playing": True,
            "requested_sample_source": "self_bus",
            "sample_source": "self_bus",
            "mode": "freeze_bed",
        },
    )

    diagnostics = collect_operator_diagnostics(
        paths=_paths(tmp_path, sample_playback=sample_playback_path),
        now=100.0,
    )

    line = diagnostics.sample_source
    lower = line.lower()
    assert "playing sample freeze bed from source self bus" in lower
    assert "currently sampling" not in lower
    assert "holding" not in lower


def test_sample_source_both_active(tmp_path: Path) -> None:
    sample_activity_path = tmp_path / "sample_dsp_activity.json"
    sample_playback_path = tmp_path / "sample_playback_state.json"
    _write_json(
        sample_activity_path,
        {
            "requested_sample_source": "theramini_in",
            "sample_source": "room_mic",
            "activity_mode": "grain_cloud",
            "capture_ready": True,
            "trigger_now": True,
        },
    )
    _write_json(
        sample_playback_path,
        {
            "playing": True,
            "requested_sample_source": "self_bus",
            "sample_source": "self_bus",
            "mode": "freeze_bed",
        },
    )

    diagnostics = collect_operator_diagnostics(
        paths=_paths(
            tmp_path,
            sample_activity=sample_activity_path,
            sample_playback=sample_playback_path,
        ),
        now=100.0,
    )

    line = diagnostics.sample_source
    lower = line.lower()
    assert "currently sampling theramini in via room mic" in lower
    assert "playing sample freeze bed from source self bus" in lower
    assert " · " in line


def test_sample_source_neither_active(tmp_path: Path) -> None:
    sample_activity_path = tmp_path / "sample_dsp_activity.json"
    sample_playback_path = tmp_path / "sample_playback_state.json"
    _write_json(sample_activity_path, {})
    _write_json(sample_playback_path, {"playing": False})

    diagnostics = collect_operator_diagnostics(
        paths=_paths(
            tmp_path,
            sample_activity=sample_activity_path,
            sample_playback=sample_playback_path,
        ),
        now=100.0,
    )

    assert diagnostics.sample_source == "unavailable"
