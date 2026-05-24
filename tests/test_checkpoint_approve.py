"""Tests for the T-056d checkpoint approval + queue resume tool."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "my-claw" / "tools"))

import checkpoint_approve  # noqa: E402
import checkpoint_notify  # noqa: E402


def _write_pause_flag(tmp_path: Path, *, slug: str = "feature-1-reverb-spaces") -> Path:
    flag = tmp_path / ".sdp" / "CHECKPOINT_PAUSE"
    details = checkpoint_notify.CheckpointDetails(
        slug=slug,
        archive_url="https://cypherclaw.holdenu.com/x.opus",
        metadata_url="https://cypherclaw.holdenu.com/metadata.json",
        sha256="a" * 64,
        size_bytes=4096,
        timestamp="20260523T120000Z",
    )
    checkpoint_notify.write_pause_flag(
        flag, details, reason="checkpoint review", actor="lead"
    )
    return flag


def test_read_pause_flag_round_trip(tmp_path: Path) -> None:
    flag = _write_pause_flag(tmp_path)
    payload = checkpoint_approve.read_pause_flag(flag)
    assert payload["active"] is True
    assert payload["checkpoint"]["slug"] == "feature-1-reverb-spaces"


def test_read_pause_flag_missing_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        checkpoint_approve.read_pause_flag(tmp_path / "absent.json")


def test_read_pause_flag_invalid_json_raises(tmp_path: Path) -> None:
    bad = tmp_path / "flag.json"
    bad.write_text("not-json", encoding="utf-8")
    with pytest.raises(ValueError, match="not valid JSON"):
        checkpoint_approve.read_pause_flag(bad)


@pytest.mark.parametrize("decision", checkpoint_approve.DECISIONS)
def test_approve_checkpoint_clears_flag_and_records_decision(
    tmp_path: Path, decision: str
) -> None:
    flag = _write_pause_flag(tmp_path)
    decisions = tmp_path / ".sdp" / "CHECKPOINT_DECISIONS.jsonl"

    record = checkpoint_approve.approve_checkpoint(
        decision=decision,
        flag_path=flag,
        decisions_path=decisions,
        actor="anthony",
        note=None,
    )

    assert not flag.exists(), "queue must resume by removing the pause flag"
    assert decisions.exists()
    line = decisions.read_text(encoding="utf-8").strip().splitlines()[-1]
    on_disk = json.loads(line)
    assert on_disk["decision"] == decision
    assert on_disk["actor"] == "anthony"
    assert on_disk["checkpoint"]["slug"] == "feature-1-reverb-spaces"
    assert record.decision == decision


def test_approve_checkpoint_rejects_unknown_decision(tmp_path: Path) -> None:
    flag = _write_pause_flag(tmp_path)
    decisions = tmp_path / ".sdp" / "CHECKPOINT_DECISIONS.jsonl"
    with pytest.raises(ValueError, match="decision must be one of"):
        checkpoint_approve.approve_checkpoint(
            decision="MAYBE",
            flag_path=flag,
            decisions_path=decisions,
            actor="anthony",
            note=None,
        )
    assert flag.exists(), "flag must remain when decision is rejected"
    assert not decisions.exists()


def test_approve_checkpoint_appends_subsequent_decisions(tmp_path: Path) -> None:
    flag = _write_pause_flag(tmp_path)
    decisions = tmp_path / ".sdp" / "CHECKPOINT_DECISIONS.jsonl"
    checkpoint_approve.approve_checkpoint(
        decision="APPROVE",
        flag_path=flag,
        decisions_path=decisions,
        actor="anthony",
        note=None,
    )
    # second checkpoint cycle
    flag = _write_pause_flag(tmp_path, slug="feature-2-room-tone")
    checkpoint_approve.approve_checkpoint(
        decision="REWORK",
        flag_path=flag,
        decisions_path=decisions,
        actor="anthony",
        note="lower the wet gain",
    )
    lines = decisions.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    first, second = (json.loads(line) for line in lines)
    assert first["decision"] == "APPROVE"
    assert first["checkpoint"]["slug"] == "feature-1-reverb-spaces"
    assert second["decision"] == "REWORK"
    assert second["checkpoint"]["slug"] == "feature-2-room-tone"
    assert second["note"] == "lower the wet gain"


def test_compose_ack_message_caps_length_and_keeps_decision_and_tail() -> None:
    record = checkpoint_approve.ApprovalRecord(
        decision="APPROVE",
        actor="anthony",
        decided_at="2026-05-23T12:00:00Z",
        note=None,
        checkpoint={"slug": "feature-1-reverb-spaces"},
    )
    msg = checkpoint_approve.compose_ack_message(record)
    assert "APPROVE" in msg
    assert "feature-1-reverb-spaces" in msg
    assert msg.endswith("Queue resumed.")
    assert len(msg) <= checkpoint_notify.TELEGRAM_MAX_CHARS


def test_compose_ack_message_truncates_long_note() -> None:
    record = checkpoint_approve.ApprovalRecord(
        decision="REWORK",
        actor="anthony",
        decided_at="2026-05-23T12:00:00Z",
        note="x" * 500,
        checkpoint={"slug": "feature-1-reverb-spaces"},
    )
    msg = checkpoint_approve.compose_ack_message(record)
    assert len(msg) <= checkpoint_notify.TELEGRAM_MAX_CHARS
    assert msg.endswith("Queue resumed.")
    assert "..." in msg


def test_run_full_path_sends_telegram_and_clears_flag(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    flag = _write_pause_flag(tmp_path)
    decisions = tmp_path / ".sdp" / "CHECKPOINT_DECISIONS.jsonl"
    sent: list[dict[str, object]] = []

    def fake_send(text: str, parse_mode: str | None = None) -> dict[str, object]:
        sent.append({"text": text, "parse_mode": parse_mode})
        return {"ok": True, "result": {"message_id": 7}}

    monkeypatch.setattr(checkpoint_approve.telegram, "send_message", fake_send)
    rc = checkpoint_approve.run(
        [
            "APPROVE",
            "--flag-path",
            str(flag),
            "--decisions-path",
            str(decisions),
            "--actor",
            "anthony",
        ]
    )
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["ok"] is True
    assert out["decision"] == "APPROVE"
    assert out["telegram"]["sent"] is True
    assert out["telegram"]["response"]["result"]["message_id"] == 7
    assert not flag.exists()
    assert sent and sent[0]["parse_mode"] == "Markdown"


def test_run_no_telegram_still_clears_flag(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    flag = _write_pause_flag(tmp_path)
    decisions = tmp_path / ".sdp" / "CHECKPOINT_DECISIONS.jsonl"

    def fail_send(*_args: object, **_kwargs: object) -> dict[str, object]:
        raise AssertionError("Telegram must not be called with --no-telegram")

    monkeypatch.setattr(checkpoint_approve.telegram, "send_message", fail_send)
    rc = checkpoint_approve.run(
        [
            "REJECT",
            "--flag-path",
            str(flag),
            "--decisions-path",
            str(decisions),
            "--no-telegram",
            "--note",
            "scope drift",
        ]
    )
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["decision"] == "REJECT"
    assert out["note"] == "scope drift"
    assert out["telegram"]["sent"] is False
    assert not flag.exists()
    record = json.loads(decisions.read_text(encoding="utf-8").strip())
    assert record["note"] == "scope drift"


def test_run_missing_flag_returns_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def fail_send(*_args: object, **_kwargs: object) -> dict[str, object]:
        raise AssertionError("Telegram must not be called when flag is missing")

    monkeypatch.setattr(checkpoint_approve.telegram, "send_message", fail_send)
    rc = checkpoint_approve.run(
        [
            "APPROVE",
            "--flag-path",
            str(tmp_path / "missing.json"),
            "--decisions-path",
            str(tmp_path / ".sdp" / "CHECKPOINT_DECISIONS.jsonl"),
            "--no-telegram",
        ]
    )
    assert rc == 2
    err = json.loads(capsys.readouterr().err)
    assert err["ok"] is False
    assert "no pause flag" in err["error"]


def test_run_telegram_failure_returns_one_but_flag_still_cleared(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    flag = _write_pause_flag(tmp_path)
    decisions = tmp_path / ".sdp" / "CHECKPOINT_DECISIONS.jsonl"

    def boom(*_args: object, **_kwargs: object) -> dict[str, object]:
        raise RuntimeError("network down")

    monkeypatch.setattr(checkpoint_approve.telegram, "send_message", boom)
    rc = checkpoint_approve.run(
        [
            "APPROVE",
            "--flag-path",
            str(flag),
            "--decisions-path",
            str(decisions),
        ]
    )
    assert rc == 1
    out = json.loads(capsys.readouterr().out)
    assert out["ok"] is True
    assert out["telegram"]["sent"] is False
    assert "network down" in out["telegram"]["error"]
    assert not flag.exists(), "queue must still resume even if Telegram ack fails"


def test_end_to_end_pause_then_resume(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Drive checkpoint_notify -> checkpoint_approve as the runner would."""
    flag = tmp_path / ".sdp" / "CHECKPOINT_PAUSE"
    decisions = tmp_path / ".sdp" / "CHECKPOINT_DECISIONS.jsonl"

    def fake_send(text: str, parse_mode: str | None = None) -> dict[str, object]:
        return {"ok": True}

    monkeypatch.setattr(checkpoint_notify.telegram, "send_message", fake_send)
    monkeypatch.setattr(checkpoint_approve.telegram, "send_message", fake_send)

    notify_rc = checkpoint_notify.run(
        [
            "--slug",
            "feature-1-reverb-spaces",
            "--archive-url",
            "https://cypherclaw.holdenu.com/x.opus",
            "--flag-path",
            str(flag),
        ]
    )
    assert notify_rc == 0
    assert flag.exists(), "queue must be paused after notify"
    capsys.readouterr()  # drain notify output

    approve_rc = checkpoint_approve.run(
        [
            "APPROVE",
            "--flag-path",
            str(flag),
            "--decisions-path",
            str(decisions),
        ]
    )
    assert approve_rc == 0
    assert not flag.exists(), "queue must resume after approval"
    out = json.loads(capsys.readouterr().out)
    assert out["decision"] == "APPROVE"
    assert out["checkpoint"]["slug"] == "feature-1-reverb-spaces"
