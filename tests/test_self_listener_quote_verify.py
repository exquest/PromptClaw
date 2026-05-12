"""Tests for self_listener_quote_verify smoke-test entry point."""
from __future__ import annotations

import os
import sys
import wave


sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools"))

from composer_quote_verify import PIECES_TO_RUN  # noqa: E402
from self_listener_quote_verify import (  # noqa: E402
    EXPECTED_PEAK_FLOOR,
    _decode_24bit_mono_to_16bit_wav,
    list_self_quote_paths,
    main,
    observe_peak,
)


def _bootstrap_quotes(tmp_path):
    from composer_quote_verify import trigger_composer_pieces

    captured, _ = trigger_composer_pieces(
        capture_root=tmp_path,
        pieces=PIECES_TO_RUN,
        captured_at=1_777_160_000.0,
    )
    assert captured == PIECES_TO_RUN
    return tmp_path / "index.sqlite"


def test_decode_24bit_mono_to_16bit_wav_preserves_peak(tmp_path) -> None:
    index_path = _bootstrap_quotes(tmp_path)
    sample_id, src_path = list_self_quote_paths(index_path)[0]
    assert sample_id

    dst = tmp_path / "transcoded.wav"
    _decode_24bit_mono_to_16bit_wav(src_path, dst)

    with wave.open(str(dst), "rb") as handle:
        assert handle.getnchannels() == 1
        assert handle.getsampwidth() == 2
        assert handle.getnframes() > 0


def test_list_self_quote_paths_returns_rows_in_capture_order(tmp_path) -> None:
    index_path = _bootstrap_quotes(tmp_path)
    paths = list_self_quote_paths(index_path)

    assert len(paths) == PIECES_TO_RUN
    seen_ids: set[str] = set()
    for sample_id, path in paths:
        assert sample_id and sample_id not in seen_ids
        seen_ids.add(sample_id)
        assert path.exists()
        assert path.parent.name == "self"


def test_observe_peak_clears_floor_for_known_room_tone(tmp_path) -> None:
    index_path = _bootstrap_quotes(tmp_path)
    _, quote_path = list_self_quote_paths(index_path)[0]

    peak = observe_peak(quote_path, scratch_root=tmp_path / "scratch")

    assert peak >= EXPECTED_PEAK_FLOOR
    assert peak <= 1.0


def test_main_prints_self_listener_peak_ok_and_returns_zero(tmp_path, capsys) -> None:
    rc = main(["--capture-root", str(tmp_path)])
    assert rc == 0

    out = capsys.readouterr().out
    assert "SELF_LISTENER_PEAK_OK" in out
    assert f"pieces_run={PIECES_TO_RUN}" in out
    assert f"self_quotes_captured={PIECES_TO_RUN}" in out
    assert f"matches={PIECES_TO_RUN}/{PIECES_TO_RUN}" in out


def test_main_returns_nonzero_when_no_peak_observed(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(
        "self_listener_quote_verify.observe_peak",
        lambda *args, **kwargs: 0.0,
    )
    rc = main(["--capture-root", str(tmp_path)])
    assert rc == 3


def test_main_returns_nonzero_when_no_self_quotes(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(
        "self_listener_quote_verify.trigger_composer_pieces",
        lambda **kwargs: (0, []),
    )
    rc = main(["--capture-root", str(tmp_path)])
    assert rc == 1
