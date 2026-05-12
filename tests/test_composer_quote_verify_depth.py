"""Depth-2 report tests for composer_quote_verify."""
from __future__ import annotations

import json
import os
import sys


sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools"))

from composer_quote_verify import (  # noqa: E402
    PIECES_TO_RUN,
    QuoteMatch,
    QuoteVerificationReport,
    build_quote_verification_report,
    quote_verification_exit_code,
    render_quote_verification_lines,
    summarize_quote_verification_report,
)
from sample_capture_verify import EXPECTED_ACOUSTIC_TAGS  # noqa: E402


def _successful_report(tmp_path) -> QuoteVerificationReport:
    return build_quote_verification_report(
        capture_root=tmp_path,
        pieces=PIECES_TO_RUN,
        captured_at=1_777_160_000.0,
    )


def test_build_quote_verification_report_runs_end_to_end(tmp_path) -> None:
    report = _successful_report(tmp_path)

    assert isinstance(report, QuoteVerificationReport)
    assert report.status == "self_quote_match_ok"
    assert report.descriptor_arc_phase == "rest"
    assert report.descriptor_acoustic_tags == EXPECTED_ACOUSTIC_TAGS
    assert report.pieces_requested == PIECES_TO_RUN
    assert report.self_quotes_captured == PIECES_TO_RUN
    assert report.song_ids == tuple(f"piece-{i}" for i in range(1, PIECES_TO_RUN + 1))
    assert isinstance(report.match, QuoteMatch)
    assert report.match.song_id in report.song_ids
    assert report.match_overlap == report.match.overlap
    assert report.match_score > 0.0
    assert set(report.match_overlap) <= set(EXPECTED_ACOUSTIC_TAGS)


def test_summarize_quote_verification_report_is_json_safe(tmp_path) -> None:
    report = _successful_report(tmp_path)

    summary = summarize_quote_verification_report(report)

    assert json.loads(json.dumps(summary)) == summary
    assert summary["status"] == "self_quote_match_ok"
    assert summary["descriptor"] == {
        "sample_id": report.descriptor_sample_id,
        "arc_phase": "rest",
        "acoustic_tags": list(EXPECTED_ACOUSTIC_TAGS),
    }
    assert summary["capture"] == {
        "pieces_requested": PIECES_TO_RUN,
        "self_quotes_captured": PIECES_TO_RUN,
        "song_ids": list(report.song_ids),
    }
    assert summary["match"]["song_id"] in list(report.song_ids)
    assert summary["match"]["overlap"] == list(report.match_overlap)
    assert summary["match_score"] == report.match_score


def test_rendered_report_lines_preserve_cli_success_shape(tmp_path) -> None:
    report = _successful_report(tmp_path)

    lines = render_quote_verification_lines(report)
    payload = {
        line.split("=", 1)[0]: line.split("=", 1)[1]
        for line in lines
        if "=" in line
    }

    assert quote_verification_exit_code(report) == 0
    assert "SELF_QUOTE_MATCH_OK" in lines
    assert payload["descriptor_sample_id"] == report.descriptor_sample_id
    assert payload["descriptor_arc_phase"] == "rest"
    assert payload["pieces_run"] == str(PIECES_TO_RUN)
    assert payload["self_quotes_captured"] == str(PIECES_TO_RUN)
    assert payload["match_song_id"] in report.song_ids
    assert json.loads(payload["motif_tag_overlap"].replace("'", '"')) == list(
        report.match_overlap
    )


def test_report_exit_codes_cover_failure_statuses() -> None:
    no_captures = QuoteVerificationReport(
        descriptor_sample_id="room-1",
        descriptor_arc_phase="rest",
        descriptor_acoustic_tags=EXPECTED_ACOUSTIC_TAGS,
        pieces_requested=PIECES_TO_RUN,
        self_quotes_captured=0,
        song_ids=(),
        match=None,
        match_overlap=(),
        match_score=0.0,
        status="no_self_quotes",
    )
    no_match = QuoteVerificationReport(
        descriptor_sample_id="room-1",
        descriptor_arc_phase="rest",
        descriptor_acoustic_tags=EXPECTED_ACOUSTIC_TAGS,
        pieces_requested=PIECES_TO_RUN,
        self_quotes_captured=2,
        song_ids=("piece-1", "piece-2"),
        match=None,
        match_overlap=(),
        match_score=0.0,
        status="no_motif_tag_match",
    )

    assert quote_verification_exit_code(no_captures) == 1
    assert quote_verification_exit_code(no_match) == 2
    assert summarize_quote_verification_report(no_captures)["status"] == "no_self_quotes"
    assert (
        summarize_quote_verification_report(no_match)["status"]
        == "no_motif_tag_match"
    )


def test_composer_quote_verify_module_reaches_depth_two() -> None:
    from sdp.fractal import classify_depth

    result = classify_depth("my-claw/tools/composer_quote_verify.py")

    assert result.depth >= 2, result
