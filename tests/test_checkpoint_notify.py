"""Tests for the T-056c checkpoint notification + queue pause tool."""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "my-claw" / "tools"))

import checkpoint_notify  # noqa: E402


def _details(**overrides: object) -> checkpoint_notify.CheckpointDetails:
    base: dict[str, object] = {
        "slug": "feature-1-reverb-spaces",
        "archive_url": (
            "https://cypherclaw.holdenu.com/cypherclaw/archive/checkpoints/"
            "feature-1-reverb-spaces-20260523T120000Z/feature-1-reverb-spaces-"
            "20260523T120000Z.opus"
        ),
        "metadata_url": (
            "https://cypherclaw.holdenu.com/cypherclaw/archive/checkpoints/"
            "feature-1-reverb-spaces-20260523T120000Z/metadata.json"
        ),
        "sha256": "a" * 64,
        "size_bytes": 12345,
        "timestamp": "20260523T120000Z",
    }
    base.update(overrides)
    return checkpoint_notify.CheckpointDetails(**base)


def test_compose_message_includes_url_and_caps_length() -> None:
    msg = checkpoint_notify.compose_message(_details())
    assert "feature-1-reverb-spaces" in msg
    assert "https://cypherclaw.holdenu.com/" in msg
    assert "Queue paused" in msg
    assert len(msg) <= checkpoint_notify.TELEGRAM_MAX_CHARS


def test_compose_message_truncates_when_too_long_but_keeps_url_and_tail() -> None:
    long_slug = "feature-1-" + ("x" * 400)
    url = "https://cypherclaw.holdenu.com/x.opus"
    msg = checkpoint_notify.compose_message(_details(slug=long_slug, archive_url=url))
    assert len(msg) <= checkpoint_notify.TELEGRAM_MAX_CHARS
    assert url in msg
    assert msg.endswith("Queue paused — reply to resume.")
    assert "..." in msg


def test_write_pause_flag_persists_expected_fields(tmp_path: Path) -> None:
    flag = tmp_path / ".sdp" / "CHECKPOINT_PAUSE"
    now = datetime(2026, 5, 23, 12, 0, 0, tzinfo=UTC)
    payload = checkpoint_notify.write_pause_flag(
        flag, _details(), reason="checkpoint review", actor="lead", now=now
    )
    assert flag.exists()
    on_disk = json.loads(flag.read_text())
    assert on_disk == payload
    assert on_disk["active"] is True
    assert on_disk["reason"] == "checkpoint review"
    assert on_disk["actor"] == "lead"
    assert on_disk["requested_at"] == "2026-05-23T12:00:00Z"
    assert on_disk["checkpoint"]["slug"] == "feature-1-reverb-spaces"
    assert on_disk["checkpoint"]["archive_url"].startswith("https://cypherclaw.holdenu.com/")
    assert on_disk["checkpoint"]["sha256"] == "a" * 64
    assert on_disk["checkpoint"]["size_bytes"] == 12345
    assert "release_hint" in on_disk


def test_send_checkpoint_notification_uses_markdown_and_message_text() -> None:
    sent: list[dict[str, object]] = []

    def fake_send(text: str, parse_mode: str | None = None) -> dict[str, object]:
        sent.append({"text": text, "parse_mode": parse_mode})
        return {"ok": True}

    result = checkpoint_notify.send_checkpoint_notification(
        _details(), send_message=fake_send
    )
    assert sent and sent[0]["parse_mode"] == "Markdown"
    assert result["text"] == sent[0]["text"]
    assert result["response"] == {"ok": True}


def test_details_from_upload_json_reads_session_archiver_shape() -> None:
    payload = {
        "ok": True,
        "checkpoint": {
            "slug": "feature-1-reverb-spaces",
            "timestamp": "20260523T120000Z",
            "source_path": "/tmp/x.opus",
            "audio_key": "cypherclaw/archive/checkpoints/feature-1-reverb-spaces-20260523T120000Z/x.opus",
            "metadata_key": "cypherclaw/archive/checkpoints/feature-1-reverb-spaces-20260523T120000Z/metadata.json",
            "audio_url": "https://cypherclaw.holdenu.com/cypherclaw/archive/checkpoints/x.opus",
            "metadata_url": "https://cypherclaw.holdenu.com/cypherclaw/archive/checkpoints/metadata.json",
            "sha256": "b" * 64,
            "size_bytes": 4096,
            "content_type": "audio/ogg; codecs=opus",
        },
    }
    details = checkpoint_notify.details_from_upload_json(payload)
    assert details.slug == "feature-1-reverb-spaces"
    assert details.archive_url == "https://cypherclaw.holdenu.com/cypherclaw/archive/checkpoints/x.opus"
    assert details.metadata_url == "https://cypherclaw.holdenu.com/cypherclaw/archive/checkpoints/metadata.json"
    assert details.sha256 == "b" * 64
    assert details.size_bytes == 4096
    assert details.timestamp == "20260523T120000Z"


def test_details_from_upload_json_rejects_missing_slug() -> None:
    with pytest.raises(ValueError, match="slug"):
        checkpoint_notify.details_from_upload_json(
            {"checkpoint": {"audio_url": "https://x/y"}}
        )


def test_details_from_upload_json_rejects_missing_archive_url() -> None:
    with pytest.raises(ValueError, match="audio_url"):
        checkpoint_notify.details_from_upload_json(
            {"checkpoint": {"slug": "feature-1-reverb-spaces"}}
        )


def test_details_from_upload_json_rejects_non_object_payload() -> None:
    with pytest.raises(ValueError, match="checkpoint"):
        checkpoint_notify.details_from_upload_json({"ok": True})


def test_run_dry_run_writes_no_flag_and_no_telegram(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def fail_send(*_args: object, **_kwargs: object) -> dict[str, object]:
        raise AssertionError("Telegram must not be called in --dry-run")

    monkeypatch.setattr(checkpoint_notify.telegram, "send_message", fail_send)
    flag = tmp_path / ".sdp" / "CHECKPOINT_PAUSE"
    rc = checkpoint_notify.run(
        [
            "--slug",
            "feature-1-reverb-spaces",
            "--archive-url",
            "https://cypherclaw.holdenu.com/x.opus",
            "--flag-path",
            str(flag),
            "--dry-run",
        ]
    )
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["ok"] is True
    assert out["dry_run"] is True
    assert out["telegram"]["sent"] is False
    assert out["pause"]["written"] is False
    assert not flag.exists()


def test_run_full_path_sends_telegram_and_writes_flag(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    sent: list[dict[str, object]] = []

    def fake_send(text: str, parse_mode: str | None = None) -> dict[str, object]:
        sent.append({"text": text, "parse_mode": parse_mode})
        return {"ok": True, "result": {"message_id": 42}}

    monkeypatch.setattr(checkpoint_notify.telegram, "send_message", fake_send)
    flag = tmp_path / ".sdp" / "CHECKPOINT_PAUSE"
    rc = checkpoint_notify.run(
        [
            "--slug",
            "feature-1-reverb-spaces",
            "--archive-url",
            "https://cypherclaw.holdenu.com/x.opus",
            "--flag-path",
            str(flag),
            "--actor",
            "lead-claude",
        ]
    )
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["ok"] is True
    assert out["telegram"]["sent"] is True
    assert out["telegram"]["response"]["result"]["message_id"] == 42
    assert out["pause"]["written"] is True

    flag_payload = json.loads(flag.read_text())
    assert flag_payload["active"] is True
    assert flag_payload["actor"] == "lead-claude"
    assert flag_payload["checkpoint"]["slug"] == "feature-1-reverb-spaces"
    assert sent and sent[0]["parse_mode"] == "Markdown"


def test_run_no_pause_skips_flag(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        checkpoint_notify.telegram, "send_message", lambda *a, **k: {"ok": True}
    )
    flag = tmp_path / ".sdp" / "CHECKPOINT_PAUSE"
    rc = checkpoint_notify.run(
        [
            "--slug",
            "feature-1-reverb-spaces",
            "--archive-url",
            "https://cypherclaw.holdenu.com/x.opus",
            "--flag-path",
            str(flag),
            "--no-pause",
        ]
    )
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["telegram"]["sent"] is True
    assert out["pause"]["written"] is False
    assert not flag.exists()


def test_run_no_telegram_still_writes_flag(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def fail_send(*_args: object, **_kwargs: object) -> dict[str, object]:
        raise AssertionError("Telegram must not be called with --no-telegram")

    monkeypatch.setattr(checkpoint_notify.telegram, "send_message", fail_send)
    flag = tmp_path / ".sdp" / "CHECKPOINT_PAUSE"
    rc = checkpoint_notify.run(
        [
            "--slug",
            "feature-1-reverb-spaces",
            "--archive-url",
            "https://cypherclaw.holdenu.com/x.opus",
            "--flag-path",
            str(flag),
            "--no-telegram",
        ]
    )
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["telegram"]["sent"] is False
    assert out["pause"]["written"] is True
    assert flag.exists()


def test_run_from_upload_json_drives_details(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    upload_json = tmp_path / "upload.json"
    upload_json.write_text(
        json.dumps(
            {
                "ok": True,
                "checkpoint": {
                    "slug": "feature-1-reverb-spaces",
                    "timestamp": "20260523T120000Z",
                    "audio_url": "https://cypherclaw.holdenu.com/x.opus",
                    "metadata_url": "https://cypherclaw.holdenu.com/metadata.json",
                    "sha256": "c" * 64,
                    "size_bytes": 9001,
                }
            }
        )
    )
    sent: list[str] = []

    def fake_send(text: str, parse_mode: str | None = None) -> dict[str, object]:
        sent.append(text)
        return {"ok": True}

    monkeypatch.setattr(checkpoint_notify.telegram, "send_message", fake_send)
    flag = tmp_path / ".sdp" / "CHECKPOINT_PAUSE"
    rc = checkpoint_notify.run(
        [
            "--from-upload-json",
            str(upload_json),
            "--flag-path",
            str(flag),
        ]
    )
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["checkpoint"]["sha256"] == "c" * 64
    assert out["checkpoint"]["size_bytes"] == 9001
    assert sent and "https://cypherclaw.holdenu.com/x.opus" in sent[0]
    flag_payload = json.loads(flag.read_text())
    assert flag_payload["checkpoint"]["timestamp"] == "20260523T120000Z"


def test_run_requires_slug_and_url_without_upload_json(
    capsys: pytest.CaptureFixture[str],
) -> None:
    rc = checkpoint_notify.run([])
    assert rc == 2
    err = json.loads(capsys.readouterr().err)
    assert err["ok"] is False
    assert "slug" in err["error"] or "archive-url" in err["error"]
