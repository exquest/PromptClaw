"""Tests for sampler_fx_mode_verify smoke-test entry point."""
from __future__ import annotations

import os
import sys


sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools"))

from sampler_fx_mode_verify import (  # noqa: E402
    MODE_SEQUENCE,
    assert_mode_snapshots_match_presets,
    capture_mode_snapshots,
    main,
)
from senseweave.sampler_dispatch import FX_PRESETS_BY_MODE  # noqa: E402


def test_capture_mode_snapshots_triggers_each_mode_in_order() -> None:
    snapshots = capture_mode_snapshots()

    assert list(snapshots) == list(MODE_SEQUENCE)
    for mode in MODE_SEQUENCE:
        assert snapshots[mode] == FX_PRESETS_BY_MODE[mode]


def test_assert_mode_snapshots_match_presets_rejects_drift() -> None:
    snapshots = capture_mode_snapshots()
    snapshots["storm"] = dict(snapshots["storm"])
    snapshots["storm"]["freeze_amount"] = 0.0

    import pytest

    with pytest.raises(AssertionError, match="storm"):
        assert_mode_snapshots_match_presets(snapshots)


def test_main_prints_success_marker(tmp_path, capsys) -> None:
    del tmp_path  # smoke entry point is hardware-free; keep signature consistent.

    rc = main([])

    assert rc == 0
    out = capsys.readouterr().out
    assert "FX_MODE_PRESETS_OK" in out
    for mode in MODE_SEQUENCE:
        assert f"{mode}=" in out
