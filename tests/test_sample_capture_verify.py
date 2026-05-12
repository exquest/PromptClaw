"""Tests for sample_capture_verify smoke-test entry point."""
from __future__ import annotations

import json
import os
import sqlite3
import sys

import pytest


sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools"))

from sample_capture_verify import (
    EXPECTED_ACOUSTIC_TAGS,
    assert_descriptor_complete,
    capture_known_room_sound,
    main,
    read_descriptor_row,
    synthesize_known_room_sound,
)


def test_synthesize_known_room_sound_is_deterministic() -> None:
    a = synthesize_known_room_sound()
    b = synthesize_known_room_sound()
    assert a.shape == b.shape
    assert (a == b).all()


def test_capture_known_room_sound_writes_full_descriptor(tmp_path) -> None:
    capture = capture_known_room_sound(
        capture_root=tmp_path, captured_at=1777160000.0
    )

    assert capture.path.exists()
    descriptor = read_descriptor_row(capture)
    assert_descriptor_complete(descriptor)

    assert descriptor["source"] == "room"
    assert descriptor["arc_phase"] == "rest"
    assert descriptor["mood_label"] == "content"
    assert descriptor["presence"] == "solo"
    assert descriptor["someone_here"] == 1
    assert tuple(json.loads(str(descriptor["acoustic_tags_json"]))) == EXPECTED_ACOUSTIC_TAGS

    payload = json.loads(str(descriptor["tags_json"]))
    assert payload["mode"] == "solo"
    assert payload["extra_tags"] == {"smoke_test": "known_220hz_sine"}


def test_main_prints_descriptor_ok_on_success(tmp_path, capsys) -> None:
    rc = main(["--capture-root", str(tmp_path)])
    assert rc == 0
    captured_out = capsys.readouterr().out
    assert "DESCRIPTOR_OK" in captured_out

    index_path = tmp_path / "index.sqlite"
    with sqlite3.connect(str(index_path)) as con:
        row = con.execute(
            "SELECT acoustic_tags_json FROM samples ORDER BY captured_at_unix DESC LIMIT 1"
        ).fetchone()
    assert row is not None
    assert tuple(json.loads(row[0])) == EXPECTED_ACOUSTIC_TAGS


def test_assert_descriptor_complete_rejects_missing_acoustic_tags() -> None:
    descriptor = {
        "source": "room",
        "arc_phase": "rest",
        "acoustic_tags_json": json.dumps([]),
        "tags_json": json.dumps({"mood_label": "content"}),
    }
    with pytest.raises(AssertionError):
        assert_descriptor_complete(descriptor)
