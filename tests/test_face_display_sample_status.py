"""Tests for the face-display combined sampler status helper.

Covers T-021@20260425T183959Zb: wiring the combined sampler plan+playback
status line into the face display renderer so it mirrors operator
diagnostics.
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools", "senseweave"))

from senseweave.sample_status import face_display_sample_status_text


def test_face_display_sample_status_combines_plan_and_playback() -> None:
    text = face_display_sample_status_text(
        {
            "requested_sample_source": "theramini_in",
            "sample_source": "room_mic",
            "activity_mode": "grain_cloud",
            "capture_ready": True,
            "trigger_now": True,
        },
        {
            "playing": True,
            "sample_source": "self_bus",
            "requested_sample_source": "self_bus",
            "mode": "freeze_bed",
        },
    )

    lower = text.lower()
    assert "currently sampling theramini in via room mic" in lower
    assert "playing sample freeze bed from source self bus" in lower


def test_face_display_sample_status_returns_plan_only_when_playback_inactive() -> None:
    text = face_display_sample_status_text(
        {
            "requested_sample_source": "theramini_in",
            "sample_source": "room_mic",
            "activity_mode": "grain_cloud",
            "capture_ready": True,
            "trigger_now": True,
        },
        {"playing": False},
    )

    lower = text.lower()
    assert "currently sampling theramini in via room mic" in lower
    assert "playing sample" not in lower


def test_face_display_sample_status_degrades_cleanly() -> None:
    assert face_display_sample_status_text(None, None, None) == ""
    assert face_display_sample_status_text({}, {}, {}) == ""

    monitor_only = face_display_sample_status_text(
        None,
        None,
        {"error": "no_capture"},
    )
    assert monitor_only.lower().startswith("monitor offline")


def test_face_display_renderer_uses_combined_helper() -> None:
    """The renderer must call the new combined helper, not the legacy form."""
    source = Path(__file__).resolve().parents[1] / "my-claw" / "tools" / "face_display.py"
    text = source.read_text()

    assert "face_display_sample_status_text" in text, (
        "face_display.py must import/use the new combined helper"
    )

    call_pattern = re.compile(
        r"face_display_sample_status_text\s*\(\s*"
        r"_sample_state\s*,\s*"
        r"_sample_playback_state\s*,\s*"
        r"_self_listen_state\s*\)"
    )
    assert call_pattern.search(text), (
        "face_display.py must invoke face_display_sample_status_text with "
        "the activity, playback, and self-listen states"
    )
