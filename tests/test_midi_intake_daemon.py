"""Tests for the midi_intake_daemon skeleton."""

from __future__ import annotations

import os
import signal
import sys
import threading
from pathlib import Path


sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools"))

import midi_intake_daemon as mod


def test_scan_once_returns_empty_when_directory_missing(tmp_path: Path) -> None:
    assert mod.scan_once(tmp_path / "no-such-dir") == []


def test_scan_once_returns_empty_when_directory_has_no_midi(tmp_path: Path) -> None:
    (tmp_path / "not_midi.txt").write_text("hi")
    (tmp_path / "song.wav").write_bytes(b"")
    assert mod.scan_once(tmp_path) == []


def test_scan_once_lists_mid_and_midi_files(tmp_path: Path) -> None:
    alpha = tmp_path / "alpha.mid"
    beta = tmp_path / "beta.MIDI"
    gamma = tmp_path / "gamma.midi"
    ignored = tmp_path / "song.wav"
    for p in (alpha, beta, gamma, ignored):
        p.write_bytes(b"")

    found = mod.scan_once(tmp_path)

    assert found == sorted([alpha, beta, gamma])


def test_scan_once_skips_subdirectories(tmp_path: Path) -> None:
    nested = tmp_path / "nested"
    nested.mkdir()
    (nested / "ignored.mid").write_bytes(b"")
    top = tmp_path / "top.mid"
    top.write_bytes(b"")

    assert mod.scan_once(tmp_path) == [top]


def test_parse_args_default_watch_dir() -> None:
    args = mod.parse_args([])
    assert args.watch_dir == mod.DEFAULT_WATCH_DIR


def test_parse_args_accepts_watch_dir_override(tmp_path: Path) -> None:
    args = mod.parse_args(["--watch-dir", str(tmp_path)])
    assert args.watch_dir == tmp_path


def test_install_signal_handlers_sets_stop_event() -> None:
    stop_event = threading.Event()
    previous_term = signal.getsignal(signal.SIGTERM)
    previous_int = signal.getsignal(signal.SIGINT)
    try:
        mod.install_signal_handlers(stop_event)

        term_handler = signal.getsignal(signal.SIGTERM)
        int_handler = signal.getsignal(signal.SIGINT)
        assert callable(term_handler)
        assert callable(int_handler)

        term_handler(signal.SIGTERM, None)
        assert stop_event.is_set()

        stop_event.clear()
        int_handler(signal.SIGINT, None)
        assert stop_event.is_set()
    finally:
        signal.signal(signal.SIGTERM, previous_term)
        signal.signal(signal.SIGINT, previous_int)


def test_main_invokes_scan_once_and_returns_zero(
    tmp_path: Path, monkeypatch
) -> None:
    calls: list[Path] = []

    def fake_scan(path: Path | str) -> list[Path]:
        calls.append(Path(path))
        return []

    monkeypatch.setattr(mod, "scan_once", fake_scan)
    monkeypatch.setattr(mod, "configure_logging", lambda *_a, **_k: None)

    previous_term = signal.getsignal(signal.SIGTERM)
    previous_int = signal.getsignal(signal.SIGINT)
    try:
        rc = mod.main(["--watch-dir", str(tmp_path)])
    finally:
        signal.signal(signal.SIGTERM, previous_term)
        signal.signal(signal.SIGINT, previous_int)

    assert rc == 0
    assert calls == [tmp_path]
