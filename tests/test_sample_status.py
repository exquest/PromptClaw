"""Tests for sample-status text shown on the face."""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools", "senseweave"))

from senseweave.sample_status import (
    face_display_sample_status_text,
    sample_status_text,
)


def test_sample_status_text_prefers_requested_and_actual_source() -> None:
    text = sample_status_text(
        {
            "requested_sample_source": "theramini_in",
            "sample_source": "self_bus",
            "activity_mode": "grain_cloud",
            "capture_ready": True,
            "trigger_now": True,
        }
    )

    assert "theramini" in text.lower()
    assert "self" in text.lower()
    assert "grain cloud" in text.lower()


def test_sample_status_text_reports_inactive_capture() -> None:
    text = sample_status_text(
        {
            "requested_sample_source": "room_mic",
            "sample_source": "room_mic",
            "activity_mode": "freeze_bed",
            "capture_ready": False,
            "trigger_now": False,
        }
    )

    assert "not ready" in text.lower()


def test_sample_status_text_prefers_live_playback_state_when_active() -> None:
    text = sample_status_text(
        {
            "requested_sample_source": "room_mic",
            "sample_source": "room_mic",
            "activity_mode": "freeze_bed",
            "capture_ready": True,
            "trigger_now": False,
        },
        {
            "playing": True,
            "sample_source": "room_mic",
            "requested_sample_source": "room_mic",
            "mode": "freeze_bed",
        },
    )

    assert "playing" in text.lower()
    assert "freeze bed" in text.lower()


def test_sample_status_text_combines_current_sampling_and_playback_state() -> None:
    text = sample_status_text(
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
        combine_activity_and_playback=True,
    )

    lower = text.lower()
    assert "currently sampling theramini in via room mic" in lower
    assert "playing sample freeze bed from source self bus" in lower


def test_sample_status_text_surfaces_monitor_failure_over_playback_claim() -> None:
    text = sample_status_text(
        {
            "requested_sample_source": "room_mic",
            "sample_source": "room_mic",
            "activity_mode": "freeze_bed",
            "capture_ready": True,
            "trigger_now": False,
        },
        {
            "playing": True,
            "sample_source": "room_mic",
            "requested_sample_source": "room_mic",
            "mode": "freeze_bed",
        },
        {
            "error": "no_capture",
            "is_playing": False,
        },
    )

    assert "monitor offline" in text.lower()


class SampleStatusEndToEndTests:
    """End-to-end coverage for the senseweave sample-status helpers."""

    __test__ = True

    def test_sample_status_helpers_render_lifecycle_and_round_trip_json_diagnostic(
        self,
    ) -> None:
        capture_only_activity = {
            "requested_sample_source": "theramini_in",
            "sample_source": "room_mic",
            "activity_mode": "grain_cloud",
            "capture_ready": True,
            "trigger_now": True,
        }
        playback_state = {
            "playing": True,
            "sample_source": "self_bus",
            "requested_sample_source": "self_bus",
            "mode": "freeze_bed",
        }
        monitor_failure = {"error": "no_capture", "is_playing": False}

        legacy_playback_text = sample_status_text(
            capture_only_activity, playback_state
        )
        assert "playing" in legacy_playback_text.lower()
        assert "self bus" in legacy_playback_text.lower()
        assert "freeze bed" in legacy_playback_text.lower()

        legacy_capture_text = sample_status_text(capture_only_activity)
        legacy_capture_lower = legacy_capture_text.lower()
        assert "sampling theramini in via room mic" in legacy_capture_lower
        assert "grain cloud" in legacy_capture_lower
        assert "playing" not in legacy_capture_lower

        combined_text = sample_status_text(
            capture_only_activity,
            playback_state,
            combine_activity_and_playback=True,
        )
        combined_lower = combined_text.lower()
        assert "currently sampling theramini in via room mic" in combined_lower
        assert "playing sample freeze bed from source self bus" in combined_lower
        assert " · " in combined_text

        monitor_failure_text = sample_status_text(
            capture_only_activity,
            playback_state,
            monitor_failure,
            combine_activity_and_playback=True,
        )
        monitor_failure_lower = monitor_failure_text.lower()
        assert monitor_failure_lower.startswith("monitor offline")
        assert "currently sampling theramini in via room mic" in monitor_failure_lower
        assert "playing sample freeze bed from source self bus" in monitor_failure_lower

        face_display_text = face_display_sample_status_text(
            capture_only_activity, playback_state, None
        )
        assert face_display_text == combined_text

        face_display_failure_text = face_display_sample_status_text(
            capture_only_activity, playback_state, monitor_failure
        )
        assert face_display_failure_text == monitor_failure_text

        diagnostic = {
            "legacy_playback": legacy_playback_text,
            "legacy_capture": legacy_capture_text,
            "combined": combined_text,
            "combined_with_monitor_failure": monitor_failure_text,
            "face_display": face_display_text,
            "face_display_with_monitor_failure": face_display_failure_text,
            "fragments": {
                "currently_sampling": "currently sampling theramini in via room mic",
                "playing_sample": "playing sample freeze bed from source self bus",
                "monitor_offline_prefix": "monitor offline",
            },
        }
        round_tripped = json.loads(json.dumps(diagnostic, sort_keys=True))

        assert round_tripped == diagnostic
        assert (
            round_tripped["fragments"]["currently_sampling"]
            in round_tripped["combined"].lower()
        )
        assert (
            round_tripped["fragments"]["playing_sample"]
            in round_tripped["combined"].lower()
        )
        assert round_tripped["combined_with_monitor_failure"].lower().startswith(
            round_tripped["fragments"]["monitor_offline_prefix"]
        )
        assert round_tripped["face_display"] == round_tripped["combined"]
