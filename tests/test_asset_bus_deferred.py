"""Tests for deferred-capability request handling (T-011).

A ``voiceover`` request must yield a ``deferred`` manifest with explanatory
``notes``; no renderer must be invoked; and the same ``request_id`` must
remain usable for a later fulfillment when a renderer is wired.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from promptclaw.asset_bus import (
    FakeBoxRunner,
    atomic_write_text,
    build_deferred_manifest,
    is_deferred,
    result_manifest_path,
)


REQUEST_ID = "8f3c1d8a-1111-4222-9333-aaaaaaaaaaaa"


def _voiceover_request() -> dict[str, Any]:
    return {
        "request_id": REQUEST_ID,
        "schema": "deniable-asset-bus/v0.1",
        "asset_type": "voiceover",
        "title": "handler-line",
        "format": "wav",
        "spec": {
            "script": "You were never here.",
            "character": "handler",
            "language": "en",
        },
    }


def test_voiceover_request_yields_deferred_manifest() -> None:
    manifest = build_deferred_manifest(_voiceover_request())

    assert manifest["status"] == "deferred"
    assert manifest["request_id"] == REQUEST_ID
    assert manifest["schema"] == "deniable-asset-bus/v0.1"
    assert manifest["producer"] == "cypherclaw"
    assert manifest["assets"] == []
    assert manifest["error"] is None


def test_deferred_manifest_has_explanatory_notes() -> None:
    manifest = build_deferred_manifest(_voiceover_request())

    notes = manifest["notes"]
    assert isinstance(notes, str)
    assert notes
    assert "voiceover" in notes.lower()
    assert "deferred" in notes.lower()


def test_voiceover_request_does_not_invoke_renderer() -> None:
    """The acceptance criterion: fake renderer records zero calls."""
    runner = FakeBoxRunner()

    manifest = build_deferred_manifest(_voiceover_request())

    assert manifest["status"] == "deferred"
    assert runner.calls == []


def test_is_deferred_matches_capability_matrix() -> None:
    assert is_deferred("voiceover") is True
    assert is_deferred("image") is False
    assert is_deferred("music") is False
    assert is_deferred("sfx") is False
    assert is_deferred("hologram") is False


def test_deferred_manifest_serializes_to_json() -> None:
    manifest = build_deferred_manifest(_voiceover_request())
    encoded = json.dumps(manifest, sort_keys=True)
    decoded = json.loads(encoded)
    assert decoded["status"] == "deferred"
    assert decoded["request_id"] == REQUEST_ID


def test_deferred_manifest_for_unknown_asset_type_still_well_formed() -> None:
    request = {
        "request_id": REQUEST_ID,
        "asset_type": "hologram",
        "spec": {},
    }

    manifest = build_deferred_manifest(request)

    assert manifest["status"] == "deferred"
    assert manifest["assets"] == []
    assert isinstance(manifest["notes"], str) and manifest["notes"]


def test_same_request_id_can_be_fulfilled_later(tmp_path: Path) -> None:
    """A deferred manifest does not lock the request_id.

    A later producer pass (e.g. once the TTS path is wired) can write the
    fulfilled manifest at the same path via the atomic-write primitive.
    """
    request = _voiceover_request()
    deferred = build_deferred_manifest(request)
    target = result_manifest_path(tmp_path, REQUEST_ID)

    atomic_write_text(target, json.dumps(deferred, sort_keys=True))
    assert json.loads(target.read_text(encoding="utf-8"))["status"] == "deferred"

    fulfilled = {
        "request_id": REQUEST_ID,
        "schema": "deniable-asset-bus/v0.1",
        "status": "done",
        "producer": "cypherclaw",
        "assets": [
            {
                "path": f"deliverables/{REQUEST_ID}/handler-line.wav",
                "type": "voiceover",
                "bytes": 12345,
                "sha256": "0" * 64,
                "meta": {},
            }
        ],
        "notes": "",
        "error": None,
    }
    atomic_write_text(target, json.dumps(fulfilled, sort_keys=True))
    after = json.loads(target.read_text(encoding="utf-8"))
    assert after["status"] == "done"
    assert after["request_id"] == REQUEST_ID
