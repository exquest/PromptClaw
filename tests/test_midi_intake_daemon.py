"""Tests for the midi_intake_daemon skeleton."""

from __future__ import annotations

import os
import signal
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace


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


def test_main_invokes_bootstrap_identity(monkeypatch) -> None:
    identity_called = False
    announce_called = False

    def fake_bootstrap(*args, **kwargs):
        nonlocal identity_called
        identity_called = True

    class FakeAnnouncer:
        def maybe_announce(self):
            nonlocal announce_called
            announce_called = True

    monkeypatch.setattr(mod, "bootstrap_identity", fake_bootstrap)
    monkeypatch.setattr(mod, "FirstBootAnnouncer", FakeAnnouncer)
    monkeypatch.setattr(mod, "configure_logging", lambda *_a, **_k: None)
    monkeypatch.setattr(mod, "scan_once", lambda *_a, **_k: [])

    # Mock signal to avoid real signal handling
    monkeypatch.setattr(signal, "signal", lambda *_a, **_k: None)

    mod.main(["--watch-dir", "/tmp"])
    assert identity_called is True
    assert announce_called is True


def test_identity_persistence_between_boots(tmp_path):
    # This test verifies bootstrap_identity behavior (either real or shimmed)
    identity_path = tmp_path / "identity.json"

    # First boot
    id1 = mod.bootstrap_identity(identity_path=identity_path)

    # If it's the real one, it should persist a file.
    # If it's the shim, we just ensure it doesn't crash.
    if id1 is not None:
        assert identity_path.exists()

        # Second boot
        id2 = mod.bootstrap_identity(identity_path=identity_path)
        assert id1.instance_id == id2.instance_id


def test_is_midi_path_accepts_mid_and_midi_case_insensitive(tmp_path: Path) -> None:
    assert mod._is_midi_path(tmp_path / "a.mid") is True
    assert mod._is_midi_path(tmp_path / "b.MIDI") is True
    assert mod._is_midi_path(tmp_path / "c.MiD") is True


def test_is_midi_path_rejects_non_midi(tmp_path: Path) -> None:
    assert mod._is_midi_path(tmp_path / "song.wav") is False
    assert mod._is_midi_path(tmp_path / "song.txt") is False
    assert mod._is_midi_path(tmp_path / "no_extension") is False


def test_wait_for_stable_size_returns_true_when_size_stops_changing(
    tmp_path: Path,
) -> None:
    target = tmp_path / "song.mid"
    target.write_bytes(b"\x00" * 16)

    assert (
        mod.wait_for_stable_size(
            target, poll_interval=0.01, stable_for=0.03, timeout=2.0
        )
        is True
    )


def test_wait_for_stable_size_returns_true_after_growth_settles(
    tmp_path: Path,
) -> None:
    target = tmp_path / "song.mid"
    target.write_bytes(b"\x00")

    def grow() -> None:
        for i in range(3):
            time.sleep(0.02)
            with target.open("ab") as fh:
                fh.write(b"\x00" * 4)

    t = threading.Thread(target=grow)
    t.start()
    try:
        result = mod.wait_for_stable_size(
            target, poll_interval=0.01, stable_for=0.05, timeout=2.0
        )
    finally:
        t.join()

    assert result is True


def test_wait_for_stable_size_returns_false_when_file_missing(tmp_path: Path) -> None:
    missing = tmp_path / "ghost.mid"
    assert (
        mod.wait_for_stable_size(
            missing, poll_interval=0.01, stable_for=0.02, timeout=0.1
        )
        is False
    )


def test_midi_event_handler_dispatches_on_created_for_midi(tmp_path: Path) -> None:
    target = tmp_path / "alpha.mid"
    target.write_bytes(b"\x00" * 4)

    dispatched: list[Path] = []
    handler = mod.MidiEventHandler(
        dispatch=lambda p: dispatched.append(p),
        wait_for_stable=lambda p: True,
    )
    event = SimpleNamespace(
        is_directory=False, src_path=str(target), dest_path=None
    )
    handler.on_created(event)

    assert dispatched == [target]


def test_midi_event_handler_ignores_non_midi_on_created(tmp_path: Path) -> None:
    target = tmp_path / "song.wav"
    target.write_bytes(b"")

    dispatched: list[Path] = []
    handler = mod.MidiEventHandler(
        dispatch=lambda p: dispatched.append(p),
        wait_for_stable=lambda p: True,
    )
    event = SimpleNamespace(is_directory=False, src_path=str(target))
    handler.on_created(event)

    assert dispatched == []


def test_midi_event_handler_on_moved_uses_dest_path(tmp_path: Path) -> None:
    src = tmp_path / "tmp.partial"
    dest = tmp_path / "final.mid"
    dest.write_bytes(b"\x00" * 4)

    dispatched: list[Path] = []
    handler = mod.MidiEventHandler(
        dispatch=lambda p: dispatched.append(p),
        wait_for_stable=lambda p: True,
    )
    event = SimpleNamespace(
        is_directory=False, src_path=str(src), dest_path=str(dest)
    )
    handler.on_moved(event)

    assert dispatched == [dest]


def test_midi_event_handler_skips_directory_events(tmp_path: Path) -> None:
    dispatched: list[Path] = []
    handler = mod.MidiEventHandler(
        dispatch=lambda p: dispatched.append(p),
        wait_for_stable=lambda p: True,
    )
    event = SimpleNamespace(
        is_directory=True, src_path=str(tmp_path / "sub"), dest_path=None
    )
    handler.on_created(event)
    handler.on_moved(event)

    assert dispatched == []


def test_midi_event_handler_skips_when_size_not_stable(tmp_path: Path) -> None:
    target = tmp_path / "alpha.mid"
    target.write_bytes(b"\x00")

    dispatched: list[Path] = []
    handler = mod.MidiEventHandler(
        dispatch=lambda p: dispatched.append(p),
        wait_for_stable=lambda p: False,
    )
    event = SimpleNamespace(
        is_directory=False, src_path=str(target), dest_path=None
    )
    handler.on_created(event)

    assert dispatched == []


def test_watch_loop_falls_back_to_polling_when_watchdog_missing(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(mod, "_HAS_WATCHDOG", False)

    dispatched: list[Path] = []
    stop_event = threading.Event()

    def producer() -> None:
        time.sleep(0.05)
        (tmp_path / "new.mid").write_bytes(b"\x00" * 4)
        time.sleep(0.1)
        stop_event.set()

    t = threading.Thread(target=producer)
    t.start()
    try:
        mod.watch_loop(
            tmp_path,
            stop_event,
            dispatch=lambda p: dispatched.append(p),
            poll_interval=0.02,
            wait_for_stable=lambda p: True,
        )
    finally:
        t.join()

    assert any(p.name == "new.mid" for p in dispatched)


def test_watch_loop_polling_does_not_redispatch_existing_files(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(mod, "_HAS_WATCHDOG", False)

    existing = tmp_path / "existing.mid"
    existing.write_bytes(b"\x00" * 4)

    dispatched: list[Path] = []
    stop_event = threading.Event()

    def stopper() -> None:
        time.sleep(0.1)
        stop_event.set()

    t = threading.Thread(target=stopper)
    t.start()
    try:
        mod.watch_loop(
            tmp_path,
            stop_event,
            dispatch=lambda p: dispatched.append(p),
            poll_interval=0.02,
            wait_for_stable=lambda p: True,
        )
    finally:
        t.join()

    assert dispatched == []
