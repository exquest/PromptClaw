"""Listener-review workflow artifact validation."""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_MY_CLAW = Path(__file__).resolve().parent.parent.parent.parent

LISTENER_REVIEW_DOC_PATH: Path = _MY_CLAW / "docs" / "listener-review.md"
REVIEW_LOG_PATH: Path = _MY_CLAW / "sdp" / "review-log.md"
ABLATION_CLI_NAME: str = "senseweave-render-debugger"
REQUIRED_REVIEW_LOG_FIELDS: tuple[str, ...] = (
    "piece",
    "date",
    "felt_wrong",
    "suspected_rule",
    "ablation_result",
    "action",
)
VALID_REVIEW_ACTIONS: tuple[str, ...] = ("keep", "disable", "tune", "escalate")


@dataclass(frozen=True)
class ListenerReviewEntry:
    """One parsed listener-review log row."""

    piece: str
    date: str
    felt_wrong: str
    suspected_rule: str
    ablation_result: str
    action: str

    def to_dict(self) -> dict[str, str]:
        return {
            "piece": self.piece,
            "date": self.date,
            "felt_wrong": self.felt_wrong,
            "suspected_rule": self.suspected_rule,
            "ablation_result": self.ablation_result,
            "action": self.action,
        }


@dataclass(frozen=True)
class ListenerReviewReport:
    """Artifact status and parsed listener-review log output."""

    doc_path: Path
    log_path: Path
    doc_exists: bool
    log_exists: bool
    doc_references_ablation_cli: bool
    missing_fields: tuple[str, ...]
    entries: tuple[ListenerReviewEntry, ...]
    invalid_actions: tuple[str, ...]

    @property
    def entry_count(self) -> int:
        return len(self.entries)

    @property
    def action_counts(self) -> dict[str, int]:
        counts = Counter(entry.action for entry in self.entries)
        return {action: counts[action] for action in sorted(counts)}

    def to_dict(self) -> dict[str, Any]:
        return {
            "doc_path": str(self.doc_path),
            "log_path": str(self.log_path),
            "doc_exists": self.doc_exists,
            "log_exists": self.log_exists,
            "doc_references_ablation_cli": self.doc_references_ablation_cli,
            "missing_fields": list(self.missing_fields),
            "entry_count": self.entry_count,
            "action_counts": self.action_counts,
            "invalid_actions": list(self.invalid_actions),
            "entries": [entry.to_dict() for entry in self.entries],
        }


def _markdown_cells(line: str) -> tuple[str, ...]:
    stripped = line.strip()
    if not stripped.startswith("|") or not stripped.endswith("|"):
        return ()
    return tuple(cell.strip() for cell in stripped.strip("|").split("|"))


def _is_separator_row(cells: tuple[str, ...]) -> bool:
    return bool(cells) and all(set(cell) <= {"-", ":", " "} for cell in cells)


def _normalized_header(cells: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(cell.strip().lower().replace(" ", "_") for cell in cells)


def _row_to_entry(header: tuple[str, ...], cells: tuple[str, ...]) -> ListenerReviewEntry:
    values = {
        name: cells[index].strip() if index < len(cells) else ""
        for index, name in enumerate(header)
    }
    return ListenerReviewEntry(
        piece=values["piece"],
        date=values["date"],
        felt_wrong=values["felt_wrong"],
        suspected_rule=values["suspected_rule"],
        ablation_result=values["ablation_result"],
        action=values["action"],
    )


def _missing_fields_for_log(path: Path) -> tuple[str, ...]:
    if not path.is_file():
        return REQUIRED_REVIEW_LOG_FIELDS

    missing: set[str] = set()
    saw_header = False
    for line in path.read_text().splitlines():
        cells = _markdown_cells(line)
        header = _normalized_header(cells)
        if "piece" in header and "date" in header:
            saw_header = True
            missing.update(field for field in REQUIRED_REVIEW_LOG_FIELDS if field not in header)

    if not saw_header:
        return REQUIRED_REVIEW_LOG_FIELDS
    return tuple(field for field in REQUIRED_REVIEW_LOG_FIELDS if field in missing)


def parse_review_log(path: Path = REVIEW_LOG_PATH) -> tuple[ListenerReviewEntry, ...]:
    """Parse listener-review markdown table rows into typed entries."""
    if not path.is_file():
        return ()

    entries: list[ListenerReviewEntry] = []
    current_header: tuple[str, ...] = ()
    for line in path.read_text().splitlines():
        cells = _markdown_cells(line)
        if not cells:
            continue
        header = _normalized_header(cells)
        if "piece" in header and "date" in header:
            current_header = header
            continue
        if _is_separator_row(cells) or not current_header:
            continue
        if all(field in current_header for field in REQUIRED_REVIEW_LOG_FIELDS):
            entries.append(_row_to_entry(current_header, cells))

    return tuple(entries)


def build_listener_review_report(
    *,
    doc_path: Path = LISTENER_REVIEW_DOC_PATH,
    log_path: Path = REVIEW_LOG_PATH,
) -> ListenerReviewReport:
    """Build a JSON-safe listener-review workflow report."""
    doc_exists = doc_path.is_file()
    log_exists = log_path.is_file()
    doc_content = doc_path.read_text() if doc_exists else ""
    entries = parse_review_log(log_path)
    invalid_actions = tuple(
        sorted({
            entry.action
            for entry in entries
            if entry.action not in VALID_REVIEW_ACTIONS
        })
    )
    return ListenerReviewReport(
        doc_path=doc_path,
        log_path=log_path,
        doc_exists=doc_exists,
        log_exists=log_exists,
        doc_references_ablation_cli=ABLATION_CLI_NAME in doc_content,
        missing_fields=_missing_fields_for_log(log_path),
        entries=entries,
        invalid_actions=invalid_actions,
    )


def summarize_listener_review_report(
    report: ListenerReviewReport,
) -> dict[str, Any]:
    """Return a JSON-safe summary for dashboards and tests."""
    return report.to_dict()


def validate_listener_review_artifacts() -> bool:
    """Return True when both workflow files exist and the doc references the CLI."""
    report = build_listener_review_report()
    return (
        report.doc_exists
        and report.log_exists
        and report.doc_references_ablation_cli
    )
