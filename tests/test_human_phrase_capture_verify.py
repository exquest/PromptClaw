"""Tests for human_phrase_capture_verify smoke-test entry point."""
from __future__ import annotations

import json
import os
import sys


sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools"))

from human_phrase_capture_verify import main  # type: ignore[import-not-found]


def test_main_prints_human_phrase_capture_ok_and_returns_zero(tmp_path, capsys) -> None:
    rc = main(["--capture-root", str(tmp_path)])
    assert rc == 0

    out = capsys.readouterr().out
    assert "HUMAN_PHRASE_CAPTURE_OK" in out
    assert "keyboard_path=" in out
    assert "theramini_path=" in out

    payload = {
        line.split("=", 1)[0]: line.split("=", 1)[1]
        for line in out.splitlines()
        if "=" in line
    }
    keyboard_meta = json.loads(payload["keyboard_metadata"])
    theramini_meta = json.loads(payload["theramini_metadata"])
    assert keyboard_meta["instrument"] == "midi_keyboard"
    assert theramini_meta["instrument"] == "theramini"
