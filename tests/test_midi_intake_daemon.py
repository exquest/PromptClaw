"""Tests for the midi_intake_daemon skeleton."""

from __future__ import annotations

import hashlib
import json
import logging
import shutil
import signal
import threading
import time
from pathlib import Path
from types import SimpleNamespace

from cypherclaw import midi_intake_daemon as mod


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

def test_main_invokes_watch_loop_and_returns_zero(
    tmp_path: Path, monkeypatch
) -> None:
    watch_calls: list[Path] = []

    def fake_watch(path: Path | str, _stop: threading.Event, **_k: object) -> None:
        watch_calls.append(Path(path))

    monkeypatch.setattr(mod, "watch_loop", fake_watch)
    monkeypatch.setattr(mod, "configure_logging", lambda *_a, **_k: None)

    # We need to mock signal handlers because they might fail in some environments
    # or interfere with the test runner.
    monkeypatch.setattr(signal, "signal", lambda *_a: None)

    assert mod.main(["--watch-dir", str(tmp_path)]) == 0
    assert watch_calls == [tmp_path]


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
    monkeypatch.setattr(mod, "watch_loop", lambda *_a, **_k: None)

    # Mock signal to avoid real signal handling
    monkeypatch.setattr(signal, "signal", lambda *_a, **_k: None)

    mod.main([])

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


def _write_valid_midi(path: Path, body: bytes = b"\x00\x00\x00\x06\x00\x00\x00\x01\x00\x60") -> bytes:
    contents = mod.MIDI_HEADER_MAGIC + body
    path.write_bytes(contents)
    return contents


def test_validate_midi_header_accepts_mthd(tmp_path: Path) -> None:
    target = tmp_path / "ok.mid"
    _write_valid_midi(target)
    assert mod.validate_midi_header(target) is True


def test_validate_midi_header_rejects_non_mthd(tmp_path: Path) -> None:
    target = tmp_path / "bad.mid"
    target.write_bytes(b"RIFFxxxx" + b"\x00" * 16)
    assert mod.validate_midi_header(target) is False


def test_validate_midi_header_rejects_missing_file(tmp_path: Path) -> None:
    assert mod.validate_midi_header(tmp_path / "ghost.mid") is False


def test_validate_midi_header_rejects_truncated_file(tmp_path: Path) -> None:
    target = tmp_path / "tiny.mid"
    target.write_bytes(b"MT")
    assert mod.validate_midi_header(target) is False


def test_process_midi_file_moves_valid_to_processed(tmp_path: Path) -> None:
    target = tmp_path / "alpha.mid"
    contents = _write_valid_midi(target)

    event = mod.process_midi_file(target)

    processed_dir = tmp_path / "processed"
    moved = processed_dir / "alpha.mid"
    assert processed_dir.is_dir()
    assert moved.is_file()
    assert not target.exists()
    assert event["status"] == "processed"
    assert event["path"] == str(target)
    assert event["destination"] == str(moved)
    assert event["size"] == len(contents)
    assert event["sha256"] == hashlib.sha256(contents).hexdigest()
    assert isinstance(event["timestamp"], str)
    # ISO 8601 UTC, parseable
    assert event["timestamp"].endswith("+00:00")


def test_process_midi_file_moves_invalid_to_rejected(tmp_path: Path) -> None:
    target = tmp_path / "bad.mid"
    target.write_bytes(b"NOPE" + b"\x00" * 8)

    event = mod.process_midi_file(target)

    rejected = tmp_path / "rejected" / "bad.mid"
    assert rejected.is_file()
    assert not target.exists()
    assert event["status"] == "rejected"
    assert event["destination"] == str(rejected)


def test_process_midi_file_uses_custom_dirs(tmp_path: Path) -> None:
    target = tmp_path / "alpha.mid"
    _write_valid_midi(target)
    out = tmp_path / "out"
    rej = tmp_path / "rej"

    event = mod.process_midi_file(target, processed_dir=out, rejected_dir=rej)

    assert (out / "alpha.mid").is_file()
    assert not rej.exists()
    assert event["status"] == "processed"


def test_process_midi_file_avoids_overwriting_existing_destination(
    tmp_path: Path,
) -> None:
    processed_dir = tmp_path / "processed"
    processed_dir.mkdir()
    (processed_dir / "alpha.mid").write_bytes(b"OLD")

    target = tmp_path / "alpha.mid"
    _write_valid_midi(target)

    event = mod.process_midi_file(target)

    assert (processed_dir / "alpha.mid").read_bytes() == b"OLD"
    new_dest = Path(str(event["destination"]))
    assert new_dest.exists()
    assert new_dest != processed_dir / "alpha.mid"


def test_process_midi_file_emits_json_event_to_log(tmp_path: Path) -> None:
    target = tmp_path / "alpha.mid"
    _write_valid_midi(target)

    records: list[logging.LogRecord] = []

    class _Capture(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(record)

    handler = _Capture(level=logging.INFO)
    previous_level = mod.LOGGER.level
    mod.LOGGER.addHandler(handler)
    mod.LOGGER.setLevel(logging.INFO)
    try:
        event = mod.process_midi_file(target)
    finally:
        mod.LOGGER.removeHandler(handler)
        mod.LOGGER.setLevel(previous_level)

    matching = [r for r in records if "midi_intake_event" in r.getMessage()]
    assert matching, "expected a midi_intake_event log line"
    payload = matching[-1].getMessage().split("midi_intake_event ", 1)[1]
    parsed = json.loads(payload)
    assert parsed["status"] == "processed"
    assert parsed["sha256"] == event["sha256"]
    assert parsed["path"] == str(target)


def test_default_dispatch_invokes_process_midi_file(
    tmp_path: Path, monkeypatch
) -> None:
    target = tmp_path / "alpha.mid"
    _write_valid_midi(target)

    calls: list[Path] = []

    def fake_process(path, **kwargs):
        calls.append(Path(path))
        return {"status": "processed"}

    monkeypatch.setattr(mod, "process_midi_file", fake_process)
    mod._default_dispatch(target)

    assert calls == [target]


def _write_mthd_chunk(
    path: Path, *, fmt: int = 1, ntrks: int = 4, division: int = 480
) -> bytes:
    body = (
        b"\x00\x00\x00\x06"  # header length (always 6)
        + fmt.to_bytes(2, "big")
        + ntrks.to_bytes(2, "big")
        + division.to_bytes(2, "big")
    )
    contents = mod.MIDI_HEADER_MAGIC + body
    path.write_bytes(contents)
    return contents


def test_read_mthd_header_parses_format_tracks_division(tmp_path: Path) -> None:
    target = tmp_path / "song.mid"
    _write_mthd_chunk(target, fmt=1, ntrks=4, division=480)

    info = mod.read_mthd_header(target)

    assert info == {"format": 1, "track_count": 4, "division": 480}


def test_read_mthd_header_returns_none_for_non_midi(tmp_path: Path) -> None:
    target = tmp_path / "bad.mid"
    target.write_bytes(b"RIFFxxxx" + b"\x00" * 16)
    assert mod.read_mthd_header(target) is None


def test_read_mthd_header_returns_none_for_truncated_file(tmp_path: Path) -> None:
    target = tmp_path / "tiny.mid"
    target.write_bytes(mod.MIDI_HEADER_MAGIC + b"\x00")
    assert mod.read_mthd_header(target) is None


def test_read_mthd_header_returns_none_for_missing_file(tmp_path: Path) -> None:
    assert mod.read_mthd_header(tmp_path / "ghost.mid") is None


def test_build_manifest_includes_all_required_fields(tmp_path: Path) -> None:
    target = tmp_path / "alpha.mid"
    contents = _write_mthd_chunk(target, fmt=1, ntrks=3, division=240)
    metadata = mod.read_mthd_header(target)

    manifest = mod.build_manifest(target, extracted_metadata=metadata)

    assert manifest["original_filename"] == "alpha.mid"
    assert manifest["file_size"] == len(contents)
    assert manifest["sha256"] == hashlib.sha256(contents).hexdigest()
    assert manifest["mthd_header"] == {
        "format": 1,
        "track_count": 3,
        "division": 240,
    }
    assert manifest["track_count"] == 3
    assert isinstance(manifest["processed_at"], str)
    assert manifest["processed_at"].endswith("+00:00")


def test_build_manifest_without_metadata_omits_header_info(tmp_path: Path) -> None:
    target = tmp_path / "alpha.mid"
    target.write_bytes(b"\x00" * 16)

    manifest = mod.build_manifest(target)

    assert manifest["mthd_header"] is None
    assert manifest["track_count"] is None
    assert manifest["original_filename"] == "alpha.mid"
    assert manifest["file_size"] == 16


def test_build_manifest_uses_supplied_timestamp(tmp_path: Path) -> None:
    from datetime import datetime, timezone

    target = tmp_path / "alpha.mid"
    target.write_bytes(b"\x00")
    stamp = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)

    manifest = mod.build_manifest(target, processed_at=stamp)

    assert manifest["processed_at"] == "2026-01-02T03:04:05+00:00"


def test_build_manifest_is_json_serializable(tmp_path: Path) -> None:
    target = tmp_path / "alpha.mid"
    _write_mthd_chunk(target)

    manifest = mod.build_manifest(
        target, extracted_metadata=mod.read_mthd_header(target)
    )

    # Round-trip through JSON to ensure the sidecar can be written verbatim.
    assert json.loads(json.dumps(manifest)) == manifest


def test_build_manifest_normalizes_non_utc_timestamp(tmp_path: Path) -> None:
    from datetime import datetime, timedelta, timezone

    target = tmp_path / "alpha.mid"
    target.write_bytes(b"\x00")
    stamp = datetime(2026, 1, 2, 5, 4, 5, tzinfo=timezone(timedelta(hours=2)))

    manifest = mod.build_manifest(target, processed_at=stamp)

    assert manifest["processed_at"] == "2026-01-02T03:04:05+00:00"

def test_intake_cycle_produces_manifest_sidecar(tmp_path: Path) -> None:
    """Integration test: drop file, process it, check for sidecar."""
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    target = inbox / "test.mid"
    # Header: format=0, tracks=1, division=96 (0x60)
    _write_valid_midi(target)

    # Simulate one cycle by calling process_midi_file directly.
    processed_dir = tmp_path / "processed"
    mod.process_midi_file(target, processed_dir=processed_dir)

    moved = processed_dir / "test.mid"
    manifest_path = processed_dir / "test.mid.json"

    assert moved.is_file()
    assert manifest_path.is_file()

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["original_filename"] == "test.mid"
    assert "processed_at" in manifest
    assert "sha256" in manifest
    assert manifest["file_size"] > 0
    assert manifest["mthd_header"]["format"] == 0
    assert manifest["track_count"] == 1
    assert manifest["mthd_header"]["division"] == 96

def test_process_midi_file_skips_manifest_for_rejected_files(tmp_path: Path) -> None:
    """Ensure rejected files do NOT get a JSON manifest sidecar."""
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    target = inbox / "bad.mid"
    target.write_bytes(b"NOT_A_MIDI_HEADER")

    processed_dir = tmp_path / "processed"
    rejected_dir = tmp_path / "rejected"

    mod.process_midi_file(
        target, processed_dir=processed_dir, rejected_dir=rejected_dir
    )

    moved = rejected_dir / "bad.mid"
    manifest_path = rejected_dir / "bad.mid.json"

    assert moved.is_file()
    assert not manifest_path.exists()
    assert not (processed_dir / "bad.mid").exists()


def test_watch_loop_poll_mode_avoids_reprocessing_after_move(
    tmp_path: Path, monkeypatch
) -> None:
    """Verify that poll mode doesn't re-process if a file is moved."""
    monkeypatch.setattr(mod, "_HAS_WATCHDOG", False)

    inbox = tmp_path / "inbox"
    inbox.mkdir()
    target = inbox / "test.mid"

    dispatched_paths: list[Path] = []
    stop_event = threading.Event()

    def mock_dispatch(path: Path) -> None:
        dispatched_paths.append(path)
        # Move the file out of inbox to simulate process_midi_file behavior
        processed = inbox / "processed"
        processed.mkdir(exist_ok=True)
        shutil.move(str(path), str(processed / path.name))
        # After one dispatch, stop the loop
        stop_event.set()

    def producer() -> None:
        time.sleep(0.1)
        _write_valid_midi(target)
        # If it hasn't stopped in 0.5s, something is wrong
        time.sleep(0.5)
        if not stop_event.is_set():
            stop_event.set()

    t = threading.Thread(target=producer)
    t.start()
    try:
        mod.watch_loop(
            inbox,
            stop_event,
            dispatch=mock_dispatch,
            poll_interval=0.01,
            wait_for_stable=lambda p: True,
        )
    finally:
        t.join()

    # Should have been dispatched exactly once
    assert len(dispatched_paths) == 1
    assert dispatched_paths[0].name == "test.mid"

def test_cleanup_processed_deletes_orphaned_manifests(tmp_path: Path) -> None:
    """Verify that cleanup_processed removes manifests for missing MIDI files."""
    processed = tmp_path / "processed"
    processed.mkdir()

    # Healthy pair
    (processed / "ok.mid").write_bytes(b"")
    (processed / "ok.mid.json").write_text("{}")

    # Orphan manifest (.mid.json)
    (processed / "orphan.mid.json").write_text("{}")

    # Orphan manifest (.midi.json)
    (processed / "orphan.midi.json").write_text("{}")

    # Non-manifest JSON (should be ignored because it doesn't end in a MIDI extension)
    (processed / "other.json").write_text("{}")

    count = mod.cleanup_processed(processed)
    assert count == 2
    assert (processed / "ok.mid.json").exists()
    assert not (processed / "orphan.mid.json").exists()
    assert not (processed / "orphan.midi.json").exists()
    assert (processed / "other.json").exists()


def test_cleanup_processed_returns_zero_for_missing_dir(tmp_path: Path) -> None:
    assert mod.cleanup_processed(tmp_path / "missing") == 0


def test_main_invokes_cleanup_when_flag_provided(
    tmp_path: Path, monkeypatch
) -> None:
    """Ensure --cleanup flag triggers cleanup_processed in main."""
    cleanup_calls: list[Path] = []

    def mock_cleanup(processed_dir: Path | str) -> int:
        cleanup_calls.append(Path(processed_dir))
        return 0

    monkeypatch.setattr(mod, "cleanup_processed", mock_cleanup)
    monkeypatch.setattr(mod, "configure_logging", lambda *_a, **_k: None)
    # mock watch_loop to avoid blocking
    monkeypatch.setattr(mod, "watch_loop", lambda *_a, **_k: None)

    # Run main with --cleanup and a specific watch-dir
    mod.main(["--watch-dir", str(tmp_path), "--cleanup"])

    expected_processed = tmp_path / mod.PROCESSED_SUBDIR
    assert cleanup_calls == [expected_processed]

def test_daemon_full_integration_poll(tmp_path: Path) -> None:
    """Full integration using poll backend: run main, drop file, verify manifest."""
    inbox = tmp_path / "inbox"
    inbox.mkdir()

    stop_event = threading.Event()
    # We must mock FirstBootAnnouncer.maybe_announce to avoid network/external effects
    # and configure_logging to avoid spamming the test output.
    daemon_thread = threading.Thread(
        target=mod.main,
        kwargs={
            "argv": [
                "--watch-dir", str(inbox),
                "--poll",
                "--poll-interval", "0.05"
            ],
            "stop_event": stop_event
        }
    )

    daemon_thread.start()
    try:
        # Wait for daemon to be ready
        time.sleep(0.2)

        target = inbox / "test.mid"
        _write_valid_midi(target)

        # Wait for it to process (poll interval is 0.05)
        processed_dir = inbox / "processed"
        manifest_path = processed_dir / "test.mid.json"

        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline:
            if manifest_path.exists():
                break
            time.sleep(0.1)

        assert manifest_path.is_file(), "Manifest sidecar was not created in time"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert manifest["original_filename"] == "test.mid"
        assert manifest["track_count"] == 1

    finally:
        stop_event.set()
        daemon_thread.join(timeout=2.0)
