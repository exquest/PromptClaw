"""Tests for shared capture-alias persistence."""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools"))

from capture_alias import persist_capture_alias


def test_persist_capture_alias_copies_existing_clip(tmp_path: Path) -> None:
    source = tmp_path / "source.wav"
    alias = tmp_path / "alias.wav"
    source.write_bytes(b"1234567890")

    persisted = persist_capture_alias(source, alias)

    assert persisted is True
    assert alias.read_bytes() == b"1234567890"


def test_persist_capture_alias_ignores_missing_source(tmp_path: Path) -> None:
    persisted = persist_capture_alias(tmp_path / "missing.wav", tmp_path / "alias.wav")

    assert persisted is False
