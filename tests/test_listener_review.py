"""Tests for the listener-review workflow artifacts [T-040@20260416T181925Z]."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools"))

from senseweave.render.listener_review import (  # noqa: E402
    ABLATION_CLI_NAME,
    LISTENER_REVIEW_DOC_PATH,
    ListenerReviewEntry,
    REVIEW_LOG_PATH,
    build_listener_review_report,
    parse_review_log,
    summarize_listener_review_report,
    validate_listener_review_artifacts,
)

REQUIRED_DOC_SECTIONS = [
    "cadence",
    "ablat",
    "review note",
]

REQUIRED_LOG_FIELDS = [
    "piece",
    "date",
    "felt_wrong",
    "suspected_rule",
    "ablation_result",
    "action",
]


def test_listener_review_doc_exists_and_has_required_sections() -> None:
    assert LISTENER_REVIEW_DOC_PATH.is_file(), (
        f"listener-review doc not found at {LISTENER_REVIEW_DOC_PATH}"
    )
    content = LISTENER_REVIEW_DOC_PATH.read_text().lower()
    for keyword in REQUIRED_DOC_SECTIONS:
        assert keyword.lower() in content, (
            f"listener-review doc missing section about '{keyword}'"
        )


def test_review_log_template_has_required_fields() -> None:
    assert REVIEW_LOG_PATH.is_file(), (
        f"review log not found at {REVIEW_LOG_PATH}"
    )
    content = REVIEW_LOG_PATH.read_text().lower()
    for field in REQUIRED_LOG_FIELDS:
        assert field.lower() in content, (
            f"review log template missing field '{field}'"
        )


def test_doc_links_to_ablation_cli() -> None:
    assert LISTENER_REVIEW_DOC_PATH.is_file()
    content = LISTENER_REVIEW_DOC_PATH.read_text()
    assert ABLATION_CLI_NAME in content, (
        f"listener-review doc does not reference ablation CLI '{ABLATION_CLI_NAME}'"
    )


def test_validate_listener_review_artifacts() -> None:
    assert validate_listener_review_artifacts() is True


def test_ablation_cli_prog_matches_documented_name() -> None:
    from senseweave.render.debugger import build_parser

    parser = build_parser()
    assert parser.prog == ABLATION_CLI_NAME, (
        f"debugger CLI prog '{parser.prog}' does not match "
        f"documented name '{ABLATION_CLI_NAME}'"
    )


class ListenerReviewEndToEndTests:
    __test__ = True

    def _write_workflow(self, tmp_path: Path) -> tuple[Path, Path]:
        doc_path = tmp_path / "listener-review.md"
        log_path = tmp_path / "review-log.md"
        doc_path.write_text(
            "\n".join(
                [
                    "# Listener Review Workflow",
                    "Review cadence is weekly.",
                    f"Use `{ABLATION_CLI_NAME}` to ablate suspect rules.",
                    "Attach each review note to the structured log.",
                ]
            )
        )
        log_path.write_text(
            "\n".join(
                [
                    "# Weekly Listener Review Log",
                    "",
                    "| piece | date | felt_wrong | suspected_rule | ablation_result | action |",
                    "|-------|------|------------|----------------|-----------------|--------|",
                    "| dusk.wav | 2026-04-17 | dynamics flat | R6 | R6 single_impact=4.20 | tune |",
                    "| dawn.wav | 2026-04-18 | rhythm rushed | R2 | R2 single_impact=3.10 | escalate |",
                ]
            )
        )
        return doc_path, log_path

    def test_parse_review_log_returns_typed_entries(self, tmp_path: Path) -> None:
        _, log_path = self._write_workflow(tmp_path)

        entries = parse_review_log(log_path)

        assert entries == (
            ListenerReviewEntry(
                piece="dusk.wav",
                date="2026-04-17",
                felt_wrong="dynamics flat",
                suspected_rule="R6",
                ablation_result="R6 single_impact=4.20",
                action="tune",
            ),
            ListenerReviewEntry(
                piece="dawn.wav",
                date="2026-04-18",
                felt_wrong="rhythm rushed",
                suspected_rule="R2",
                ablation_result="R2 single_impact=3.10",
                action="escalate",
            ),
        )
        assert entries[0].to_dict() == {
            "piece": "dusk.wav",
            "date": "2026-04-17",
            "felt_wrong": "dynamics flat",
            "suspected_rule": "R6",
            "ablation_result": "R6 single_impact=4.20",
            "action": "tune",
        }

    def test_report_summarizes_artifacts_entries_and_actions(
        self,
        tmp_path: Path,
    ) -> None:
        doc_path, log_path = self._write_workflow(tmp_path)

        report = build_listener_review_report(doc_path=doc_path, log_path=log_path)
        summary = summarize_listener_review_report(report)

        assert report.doc_exists is True
        assert report.log_exists is True
        assert report.doc_references_ablation_cli is True
        assert report.missing_fields == ()
        assert report.entry_count == 2
        assert report.action_counts == {"escalate": 1, "tune": 1}
        assert report.invalid_actions == ()
        assert summary["entry_count"] == 2
        assert summary["action_counts"] == {"escalate": 1, "tune": 1}
        assert summary["entries"][1]["piece"] == "dawn.wav"
        json.dumps(summary, sort_keys=True)

    def test_report_surfaces_missing_fields_and_invalid_actions(
        self,
        tmp_path: Path,
    ) -> None:
        doc_path, log_path = self._write_workflow(tmp_path)
        log_path.write_text(
            "\n".join(
                [
                    "# Weekly Listener Review Log",
                    "",
                    "| piece | date | felt_wrong | suspected_rule | ablation_result | action |",
                    "|-------|------|------------|----------------|-----------------|--------|",
                    "| noon.wav | 2026-04-19 | timbre harsh | R7 | N/A | punt |",
                    "",
                    "| piece | date | felt_wrong | suspected_rule | ablation_result |",
                    "|-------|------|------------|----------------|-----------------|",
                ]
            )
        )

        report = build_listener_review_report(doc_path=doc_path, log_path=log_path)
        summary = summarize_listener_review_report(report)

        assert report.entry_count == 1
        assert report.missing_fields == ("action",)
        assert report.invalid_actions == ("punt",)
        assert summary["missing_fields"] == ["action"]
        assert summary["invalid_actions"] == ["punt"]
