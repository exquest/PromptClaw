"""Verification tests for T-058a hardening (identity bootstrapping at startup)."""

from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools"))

from audio_streamer import run as run_streamer  # noqa: E402
from session_archiver import run as run_archiver  # noqa: E402


def test_audio_streamer_run_bootstraps_identity() -> None:
    """Verify that audio_streamer.run() bootstraps identity early."""
    with patch("audio_streamer._bootstrap_identity") as mock_bootstrap:
        with patch("audio_streamer.parse_args") as mock_parse:
            mock_args = MagicMock()
            mock_args.identity_mode = "standalone"
            mock_args.identity_release = "1.2.3"
            mock_args.identity_parent_id = "parent-456"
            mock_args.verify_dir = "/tmp/verify"  # Exit early after bootstrap
            mock_args.segment_seconds = 6
            mock_args.duration_tolerance = 0.5
            mock_args.bitrate_kbps = 96
            mock_args.bitrate_tolerance_ratio = 0.1
            mock_parse.return_value = mock_args

            with patch("audio_streamer.validate_segment_directory") as mock_validate:
                mock_validate.return_value = []
                
                with patch("audio_streamer._print_json"):
                    run_streamer(["--verify-dir", "/tmp/verify"])

                    mock_bootstrap.assert_called_once_with(
                        mode="standalone",
                        release="1.2.3",
                        parent_id="parent-456",
                    )


def test_session_archiver_run_bootstraps_identity() -> None:
    """Verify that session_archiver.run() bootstraps identity early."""
    with patch("session_archiver._bootstrap_identity") as mock_bootstrap:
        with patch("session_archiver.parse_args") as mock_parse:
            mock_args = MagicMock()
            mock_args.identity_mode = "federated"
            mock_args.identity_release = "2.0.0"
            mock_args.identity_parent_id = None
            mock_args.dry_run = True  # Exit early after bootstrap
            mock_args.checkpoint_source = None
            mock_args.checkpoint_slug = None
            mock_parse.return_value = mock_args

            with patch("session_archiver._config_from_args"):
                with patch("session_archiver._dry_run") as mock_dry:
                    mock_dry.return_value = 0
                    
                    run_archiver(["--dry-run"])

                    mock_bootstrap.assert_called_once_with(
                        mode="federated",
                        release="2.0.0",
                        parent_id=None,
                    )
