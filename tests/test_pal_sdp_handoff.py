from __future__ import annotations

from pathlib import Path

SDP_HANDOFF = Path(__file__).resolve().parents[1] / "pal-2026" / "docs" / "SDP_HANDOFF.md"


def test_sdp_handoff_lists_analyze_and_run_loop_commands() -> None:
    text = SDP_HANDOFF.read_text()
    assert "sdp-cli analyze --prd" in text
    assert "--validate-only" in text
    assert "--load --merge append" in text
    assert "sdp-cli run-loop" in text
