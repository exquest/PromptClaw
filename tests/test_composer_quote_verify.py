"""Tests for composer_quote_verify smoke-test entry point."""
from __future__ import annotations

import json
import os
import sqlite3
import sys


sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools"))

from composer_quote_verify import (  # noqa: E402
    PIECES_TO_RUN,
    QuoteMatch,
    find_motif_tag_match,
    main,
    trigger_composer_pieces,
)
from sample_capture_verify import (  # noqa: E402
    EXPECTED_ACOUSTIC_TAGS,
    capture_known_room_sound,
)


def _self_quote_count(index_path) -> int:
    with sqlite3.connect(str(index_path)) as con:
        return int(con.execute(
            "SELECT COUNT(*) FROM samples WHERE source = 'self'"
        ).fetchone()[0])


def test_trigger_composer_pieces_writes_three_self_quotes(tmp_path) -> None:
    captured, song_ids = trigger_composer_pieces(
        capture_root=tmp_path,
        pieces=PIECES_TO_RUN,
        captured_at=1_777_160_000.0,
    )

    assert captured == PIECES_TO_RUN
    assert song_ids == [f"piece-{i}" for i in range(1, PIECES_TO_RUN + 1)]
    assert _self_quote_count(tmp_path / "index.sqlite") == PIECES_TO_RUN


def test_find_motif_tag_match_returns_overlap_with_descriptor(tmp_path) -> None:
    descriptor = capture_known_room_sound(
        capture_root=tmp_path, captured_at=1_777_160_000.0
    )
    trigger_composer_pieces(
        capture_root=tmp_path,
        pieces=PIECES_TO_RUN,
        captured_at=1_777_160_000.0 + 10.0,
    )

    match = find_motif_tag_match(
        descriptor.index_path,
        descriptor_arc_phase=descriptor.tags.arc_phase,
        descriptor_acoustic_tags=tuple(descriptor.tags.acoustic_tags),
    )

    assert isinstance(match, QuoteMatch)
    assert match.arc_phase == descriptor.tags.arc_phase
    assert set(match.overlap) <= set(descriptor.tags.acoustic_tags)
    assert len(match.overlap) >= 1
    assert match.song_id.startswith("piece-")


def test_find_motif_tag_match_returns_none_when_arc_phase_diverges(tmp_path) -> None:
    descriptor = capture_known_room_sound(
        capture_root=tmp_path, captured_at=1_777_160_000.0
    )
    trigger_composer_pieces(
        capture_root=tmp_path,
        pieces=PIECES_TO_RUN,
        captured_at=1_777_160_000.0 + 10.0,
    )

    match = find_motif_tag_match(
        descriptor.index_path,
        descriptor_arc_phase="climax",
        descriptor_acoustic_tags=tuple(descriptor.tags.acoustic_tags),
    )

    assert match is None


def test_main_prints_self_quote_match_ok_and_returns_zero(tmp_path, capsys) -> None:
    rc = main(["--capture-root", str(tmp_path)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "SELF_QUOTE_MATCH_OK" in out
    assert "motif_tag_overlap=" in out
    assert f"pieces_run={PIECES_TO_RUN}" in out

    payload = {
        line.split("=", 1)[0]: line.split("=", 1)[1]
        for line in out.splitlines()
        if "=" in line
    }
    overlap = json.loads(payload["motif_tag_overlap"].replace("'", '"'))
    assert set(overlap) <= set(EXPECTED_ACOUSTIC_TAGS)


def test_main_returns_nonzero_when_no_match(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(
        "composer_quote_verify.find_motif_tag_match",
        lambda *args, **kwargs: None,
    )
    rc = main(["--capture-root", str(tmp_path)])
    assert rc == 2
