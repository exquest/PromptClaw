"""Smoke-test entry point: drive 3 composer pieces and confirm a self-quote motif/tag match.

Operators run this on cypherclaw (or any host with the daemon module) after
a known room sound has been captured by ``sample_capture_verify``. It
simulates the composer's post-piece ``self_quote`` hook three times against
a fake JACK self-bus pre-loaded with the same known room tone, then
confirms that at least one resulting ``samples/self/`` descriptor row
shares motif/tag overlap (acoustic_tags + arc_phase) with the original
captured room descriptor.

The verifier is hardware-free: it uses the same fake-JACK pattern as
``tests/test_sample_capture_daemon.py`` so it can run anywhere the
``sample_capture_daemon`` module imports.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import cast

import numpy as np

from sample_capture_daemon import (
    SAMPLE_CAPTURE_ROOT,
    JackClientProtocol,
    SampleCaptureDaemon,
    self_quote,
)
from sample_capture_verify import (
    EXPECTED_ACOUSTIC_TAGS,
    KNOWN_ROOM_SOUND_CONTEXT,
    KNOWN_ROOM_SOUND_SAMPLE_RATE,
    capture_known_room_sound,
    synthesize_known_room_sound,
)


SELF_BUS_RATE = KNOWN_ROOM_SOUND_SAMPLE_RATE
SELF_BUS_BUFFER_SECONDS = 12
PIECES_TO_RUN = 3
STATUS_SELF_QUOTE_MATCH_OK = "self_quote_match_ok"
STATUS_NO_SELF_QUOTES = "no_self_quotes"
STATUS_NO_MOTIF_TAG_MATCH = "no_motif_tag_match"


class _FakeInputPort:
    def __init__(self, name: str) -> None:
        self.name = name
        self._frames: np.ndarray = np.zeros(0, dtype=np.float32)

    def get_array(self) -> np.ndarray:
        return self._frames

    def set_frames(self, frames: np.ndarray) -> None:
        self._frames = np.asarray(frames, dtype=np.float32)


class _FakeInputPorts:
    def __init__(self) -> None:
        self._ports: dict[str, _FakeInputPort] = {}

    def register(self, name: str) -> _FakeInputPort:
        port = _FakeInputPort(name)
        self._ports[name] = port
        return port


class _FakeJackClient:
    def __init__(self, name: str) -> None:
        self.name = name
        self.inports = _FakeInputPorts()
        self._process_callback: Callable[[int], object] | None = None

    def set_process_callback(self, callback: Callable[[int], object]) -> None:
        self._process_callback = callback

    def set_xrun_callback(self, callback: Callable[[float], object]) -> None:
        pass

    def activate(self) -> None:
        pass

    def connect(self, source: str, destination: _FakeInputPort) -> None:
        pass

    def close(self) -> None:
        pass

    def push_self_frames(self, frames: np.ndarray) -> None:
        for name in ("in_contact", "in_room"):
            self.inports._ports[name].set_frames(np.zeros(len(frames), dtype=np.float32))
        self.inports._ports["in_self"].set_frames(np.asarray(frames, dtype=np.float32))
        assert self._process_callback is not None
        self._process_callback(len(frames))


def _build_self_daemon() -> tuple[SampleCaptureDaemon, _FakeJackClient]:
    client = _FakeJackClient("cypherclaw-capture")
    daemon = SampleCaptureDaemon(
        sample_rate=SELF_BUS_RATE,
        buffer_duration_seconds=SELF_BUS_BUFFER_SECONDS,
        client_factory=lambda _name: cast(JackClientProtocol, client),
    )
    daemon.start()
    return daemon, client


def _piece_score_summary(song_id: int) -> dict[str, object]:
    """Return a passing score summary echoing the captured descriptor's mood/arc."""
    organism = cast(dict, KNOWN_ROOM_SOUND_CONTEXT["organism"])
    mood = cast(dict, organism["mood"])
    return {
        "arc_payoff": 0.85,
        "click_count": 0,
        "mode": "solo",
        "arc_phase": organism["arc_phase"],
        "mood": mood["label"],
        "song_id": f"piece-{song_id}",
    }


@dataclass(frozen=True)
class QuoteMatch:
    sample_id: str
    arc_phase: str
    acoustic_tags: tuple[str, ...]
    overlap: tuple[str, ...]
    song_id: str


@dataclass(frozen=True)
class QuoteVerificationReport:
    descriptor_sample_id: str
    descriptor_arc_phase: str
    descriptor_acoustic_tags: tuple[str, ...]
    pieces_requested: int
    self_quotes_captured: int
    song_ids: tuple[str, ...]
    match: QuoteMatch | None
    match_overlap: tuple[str, ...]
    match_score: float
    status: str


def _read_self_quote_rows(index_path: Path) -> list[dict[str, object]]:
    with sqlite3.connect(str(index_path)) as con:
        con.row_factory = sqlite3.Row
        rows = con.execute(
            "SELECT sample_id, arc_phase, acoustic_tags_json, tags_json "
            "FROM samples WHERE source = 'self' ORDER BY captured_at_unix"
        ).fetchall()
    return [dict(row) for row in rows]


def _normalize_acoustic_tags(tags: tuple[str, ...]) -> tuple[str, ...]:
    normalized: list[str] = []
    seen: set[str] = set()
    for tag in tags:
        cleaned = str(tag).strip()
        if not cleaned or cleaned in seen:
            continue
        normalized.append(cleaned)
        seen.add(cleaned)
    return tuple(normalized)


def _tag_overlap(
    candidate_tags: tuple[str, ...],
    descriptor_tags: tuple[str, ...],
) -> tuple[str, ...]:
    descriptor_set = set(_normalize_acoustic_tags(descriptor_tags))
    overlap: list[str] = []
    for tag in _normalize_acoustic_tags(candidate_tags):
        if tag in descriptor_set:
            overlap.append(tag)
    return tuple(overlap)


def _overlap_score(
    overlap: tuple[str, ...],
    descriptor_tags: tuple[str, ...],
) -> float:
    normalized_descriptor = _normalize_acoustic_tags(descriptor_tags)
    if not normalized_descriptor:
        return 0.0
    return round(len(overlap) / len(normalized_descriptor), 3)


def _quote_match_from_row(
    row: dict[str, object],
    *,
    descriptor_arc_phase: str,
    descriptor_acoustic_tags: tuple[str, ...],
) -> QuoteMatch | None:
    acoustic_tags = tuple(json.loads(str(row["acoustic_tags_json"])))
    overlap = _tag_overlap(acoustic_tags, descriptor_acoustic_tags)
    if not overlap:
        return None
    if row["arc_phase"] != descriptor_arc_phase:
        return None
    payload = json.loads(str(row["tags_json"]))
    extras = payload.get("extra_tags", {})
    song_id = str(extras.get("self_quote_source_song_id", ""))
    return QuoteMatch(
        sample_id=str(row["sample_id"]),
        arc_phase=str(row["arc_phase"]),
        acoustic_tags=_normalize_acoustic_tags(acoustic_tags),
        overlap=overlap,
        song_id=song_id,
    )


def find_motif_tag_match(
    index_path: Path,
    *,
    descriptor_arc_phase: str,
    descriptor_acoustic_tags: tuple[str, ...],
) -> QuoteMatch | None:
    """Return the first self-quote row whose motif/tag overlaps the descriptor."""
    for row in _read_self_quote_rows(index_path):
        match = _quote_match_from_row(
            row,
            descriptor_arc_phase=descriptor_arc_phase,
            descriptor_acoustic_tags=descriptor_acoustic_tags,
        )
        if match is not None:
            return match
    return None


def trigger_composer_pieces(
    *,
    capture_root: Path | str = SAMPLE_CAPTURE_ROOT,
    pieces: int = PIECES_TO_RUN,
    captured_at: float | None = None,
) -> tuple[int, list[str]]:
    """Drive ``pieces`` post-song self-quote attempts against a fake self bus.

    Each piece pre-loads the daemon's self buffer with the same known room
    tone (so the resulting self-quote inherits matching acoustic features)
    and submits a passing score summary echoing the descriptor's arc/mood.
    Returns (captured_count, song_ids) for downstream verification.
    """
    daemon, client = _build_self_daemon()
    song_ids: list[str] = []
    captured = 0
    base_at = captured_at if captured_at is not None else 1_777_160_000.0
    try:
        tone = synthesize_known_room_sound()
        for index in range(pieces):
            client.push_self_frames(tone)
            summary = _piece_score_summary(song_id=index + 1)
            quote = self_quote(
                summary,
                daemon=daemon,
                capture_root=capture_root,
                captured_at=base_at + float(index),
            )
            if quote is not None:
                captured += 1
                song_ids.append(str(summary["song_id"]))
    finally:
        daemon.stop()
    return captured, song_ids


def _report_status(captured: int, match: QuoteMatch | None) -> str:
    if captured == 0:
        return STATUS_NO_SELF_QUOTES
    if match is None:
        return STATUS_NO_MOTIF_TAG_MATCH
    return STATUS_SELF_QUOTE_MATCH_OK


def _build_report_from_parts(
    *,
    descriptor_sample_id: str,
    descriptor_arc_phase: str,
    descriptor_acoustic_tags: tuple[str, ...],
    pieces_requested: int,
    self_quotes_captured: int,
    song_ids: list[str],
    match: QuoteMatch | None,
) -> QuoteVerificationReport:
    match_overlap: tuple[str, ...] = ()
    if match is not None:
        match_overlap = match.overlap
    normalized_descriptor_tags = _normalize_acoustic_tags(descriptor_acoustic_tags)
    return QuoteVerificationReport(
        descriptor_sample_id=descriptor_sample_id,
        descriptor_arc_phase=descriptor_arc_phase,
        descriptor_acoustic_tags=normalized_descriptor_tags,
        pieces_requested=pieces_requested,
        self_quotes_captured=self_quotes_captured,
        song_ids=tuple(song_ids),
        match=match,
        match_overlap=match_overlap,
        match_score=_overlap_score(match_overlap, normalized_descriptor_tags),
        status=_report_status(self_quotes_captured, match),
    )


def build_quote_verification_report(
    *,
    capture_root: Path | str = SAMPLE_CAPTURE_ROOT,
    pieces: int = PIECES_TO_RUN,
    captured_at: float | None = None,
) -> QuoteVerificationReport:
    """Run known-room capture, composer self-quotes, and motif matching."""
    descriptor = capture_known_room_sound(
        capture_root=capture_root,
        captured_at=captured_at,
    )
    quote_captured_at = captured_at + 10.0 if captured_at is not None else None
    captured, song_ids = trigger_composer_pieces(
        capture_root=capture_root,
        pieces=pieces,
        captured_at=quote_captured_at,
    )
    descriptor_tags = (
        tuple(descriptor.tags.acoustic_tags)
        if descriptor.tags.acoustic_tags
        else EXPECTED_ACOUSTIC_TAGS
    )
    match = find_motif_tag_match(
        descriptor.index_path,
        descriptor_arc_phase=descriptor.tags.arc_phase,
        descriptor_acoustic_tags=descriptor_tags,
    )
    return _build_report_from_parts(
        descriptor_sample_id=descriptor.sample_id,
        descriptor_arc_phase=descriptor.tags.arc_phase,
        descriptor_acoustic_tags=descriptor_tags,
        pieces_requested=pieces,
        self_quotes_captured=captured,
        song_ids=song_ids,
        match=match,
    )


def summarize_quote_verification_report(
    report: QuoteVerificationReport,
) -> dict[str, object]:
    """Return a JSON-safe operator summary for a quote verification report."""
    match_summary: dict[str, object] | None = None
    if report.match is not None:
        match_summary = {
            "sample_id": report.match.sample_id,
            "arc_phase": report.match.arc_phase,
            "acoustic_tags": list(report.match.acoustic_tags),
            "overlap": list(report.match_overlap),
            "song_id": report.match.song_id,
        }
    return {
        "status": report.status,
        "descriptor": {
            "sample_id": report.descriptor_sample_id,
            "arc_phase": report.descriptor_arc_phase,
            "acoustic_tags": list(report.descriptor_acoustic_tags),
        },
        "capture": {
            "pieces_requested": report.pieces_requested,
            "self_quotes_captured": report.self_quotes_captured,
            "song_ids": list(report.song_ids),
        },
        "match": match_summary,
        "match_score": report.match_score,
    }


def render_quote_verification_lines(report: QuoteVerificationReport) -> list[str]:
    """Render the success report using the existing CLI key/value contract."""
    if report.match is None:
        return []
    return [
        f"descriptor_sample_id={report.descriptor_sample_id}",
        f"descriptor_arc_phase={report.descriptor_arc_phase}",
        f"descriptor_acoustic_tags={list(report.descriptor_acoustic_tags)}",
        f"pieces_run={report.pieces_requested}",
        f"self_quotes_captured={report.self_quotes_captured}",
        f"match_sample_id={report.match.sample_id}",
        f"match_arc_phase={report.match.arc_phase}",
        f"match_acoustic_tags={list(report.match.acoustic_tags)}",
        f"motif_tag_overlap={list(report.match_overlap)}",
        f"match_song_id={report.match.song_id}",
        "SELF_QUOTE_MATCH_OK",
    ]


def quote_verification_exit_code(report: QuoteVerificationReport) -> int:
    """Map report status to the legacy CLI exit code."""
    if report.status == STATUS_NO_SELF_QUOTES:
        return 1
    if report.status == STATUS_NO_MOTIF_TAG_MATCH:
        return 2
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--capture-root",
        default=str(SAMPLE_CAPTURE_ROOT),
        help="sample store root (default: %(default)s)",
    )
    parser.add_argument(
        "--pieces",
        type=int,
        default=PIECES_TO_RUN,
        help="number of composer pieces to simulate (default: %(default)s)",
    )
    args = parser.parse_args(argv)

    report = build_quote_verification_report(
        capture_root=args.capture_root,
        pieces=args.pieces,
    )
    rc = quote_verification_exit_code(report)
    if rc == 1:
        print(f"NO_SELF_QUOTES (pieces={args.pieces})", file=sys.stderr)
        return rc
    if rc == 2:
        print(
            f"NO_MOTIF_TAG_MATCH (pieces={args.pieces}, "
            f"captured={report.self_quotes_captured}, "
            f"song_ids={list(report.song_ids)})",
            file=sys.stderr,
        )
        return rc

    for line in render_quote_verification_lines(report):
        print(line)
    return rc


if __name__ == "__main__":
    sys.exit(main())
