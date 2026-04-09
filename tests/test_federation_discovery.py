"""Tests for federation peer discovery via Tailscale."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from promptclaw.federation.discovery import (
    PeerInfo,
    discover_peers,
    load_peer_registry,
    merge_peer_registry,
    save_peer_registry,
)

# ── Fixtures ──────────────────────────────────────────────────────

FAKE_TAILSCALE_STATUS: dict[str, Any] = {
    "Self": {
        "TailscaleIPs": ["100.64.0.1"],
        "DNSName": "macbook.tail12345.ts.net.",
        "HostName": "macbook",
        "Online": True,
    },
    "Peer": {
        "nodekey:abc123": {
            "TailscaleIPs": ["100.64.0.2"],
            "DNSName": "cypherclaw.tail12345.ts.net.",
            "HostName": "cypherclaw",
            "Online": True,
        },
        "nodekey:def456": {
            "TailscaleIPs": ["100.64.0.3"],
            "DNSName": "workstation.tail12345.ts.net.",
            "HostName": "workstation",
            "Online": True,
        },
        "nodekey:ghi789": {
            "TailscaleIPs": ["100.64.0.4"],
            "DNSName": "phone.tail12345.ts.net.",
            "HostName": "phone",
            "Online": False,
        },
    },
}

FAKE_IDENTITY_CYPHERCLAW: dict[str, Any] = {
    "instance_id": "uuid-cypherclaw",
    "instance_name": "molten-sigil",
    "mode": "standalone",
    "created_at": "2026-03-29T00:00:00+00:00",
    "release": "3.0.0",
    "capabilities": ["status", "tasks", "art"],
}


class _FakeResponse:
    """Minimal fake HTTP response supporting the context manager protocol."""

    def __init__(self, status: int, body: bytes) -> None:
        self.status = status
        self._body = body

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> _FakeResponse:
        return self

    def __exit__(self, *args: object) -> None:
        pass


def _make_fake_urlopen(
    responses: dict[str, tuple[int, bytes]],
) -> Any:
    """Return a fake urlopen that returns canned responses keyed by URL substring."""

    def fake_urlopen(req: Any, *, timeout: float = 5.0) -> _FakeResponse:
        url = req if isinstance(req, str) else req.full_url
        for pattern, (status, body) in responses.items():
            if pattern in url:
                if status != 200:
                    from urllib.error import HTTPError

                    raise HTTPError(url, status, "error", {}, None)  # type: ignore[arg-type]
                return _FakeResponse(status, body)
        from urllib.error import URLError

        raise URLError("Connection refused")

    return fake_urlopen


@pytest.fixture()
def registry_dir(tmp_path: Path) -> Path:
    d = tmp_path / ".promptclaw" / "federation"
    d.mkdir(parents=True)
    return d


# ── Tests ─────────────────────────────────────────────────────────


def test_discover_peers_finds_promptclaw_instances(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Peers running PromptClaw are discovered and returned as PeerInfo."""

    def fake_run(cmd: list[str], **_: object) -> SimpleNamespace:
        return SimpleNamespace(
            returncode=0,
            stdout=json.dumps(FAKE_TAILSCALE_STATUS),
        )

    monkeypatch.setattr(subprocess, "run", fake_run)

    fake_open = _make_fake_urlopen(
        {
            "100.64.0.2": (200, json.dumps(FAKE_IDENTITY_CYPHERCLAW).encode()),
            # workstation returns 404, phone is offline — both excluded
        }
    )
    monkeypatch.setattr("promptclaw.federation.discovery.urlopen", fake_open)

    peers = discover_peers(port=8443)

    assert len(peers) == 1
    assert peers[0].instance_id == "uuid-cypherclaw"
    assert peers[0].instance_name == "molten-sigil"
    assert peers[0].tailscale_ip == "100.64.0.2"
    assert peers[0].tailscale_name == "cypherclaw.tail12345.ts.net."
    assert peers[0].online is True


def test_discover_peers_tailscale_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When tailscale is not installed, return empty list."""

    def fake_run(cmd: list[str], **_: object) -> SimpleNamespace:
        raise FileNotFoundError("tailscale not found")

    monkeypatch.setattr(subprocess, "run", fake_run)

    peers = discover_peers()
    assert peers == []


def test_discover_peers_skips_non_promptclaw_peers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Peers that don't expose the identity endpoint are excluded."""

    def fake_run(cmd: list[str], **_: object) -> SimpleNamespace:
        return SimpleNamespace(
            returncode=0,
            stdout=json.dumps(FAKE_TAILSCALE_STATUS),
        )

    monkeypatch.setattr(subprocess, "run", fake_run)

    # All probes fail — no PromptClaw instances
    fake_open = _make_fake_urlopen({})
    monkeypatch.setattr("promptclaw.federation.discovery.urlopen", fake_open)

    peers = discover_peers(port=8443)
    assert peers == []


def test_save_peer_registry_creates_file(registry_dir: Path) -> None:
    """save_peer_registry writes peers.json."""
    peers = [
        PeerInfo(
            instance_id="uuid-1",
            instance_name="amber-anvil",
            mode="standalone",
            capabilities=["status"],
            tailscale_ip="100.64.0.2",
            tailscale_name="peer1.ts.net.",
            endpoint="http://100.64.0.2:8443/federation/v1/identity",
            first_seen="2026-04-08T00:00:00+00:00",
            last_seen="2026-04-08T00:00:00+00:00",
            online=True,
        ),
    ]
    out = registry_dir / "peers.json"
    save_peer_registry(peers, path=out)

    assert out.exists()
    data = json.loads(out.read_text())
    assert len(data) == 1
    assert data[0]["instance_id"] == "uuid-1"


def test_load_peer_registry_reads_saved_data(registry_dir: Path) -> None:
    """load_peer_registry round-trips with save."""
    peers = [
        PeerInfo(
            instance_id="uuid-1",
            instance_name="amber-anvil",
            mode="standalone",
            capabilities=["status"],
            tailscale_ip="100.64.0.2",
            tailscale_name="peer1.ts.net.",
            endpoint="http://100.64.0.2:8443/federation/v1/identity",
            first_seen="2026-04-08T00:00:00+00:00",
            last_seen="2026-04-08T00:00:00+00:00",
            online=True,
        ),
    ]
    out = registry_dir / "peers.json"
    save_peer_registry(peers, path=out)
    loaded = load_peer_registry(path=out)

    assert len(loaded) == 1
    assert loaded[0].instance_id == "uuid-1"
    assert loaded[0].instance_name == "amber-anvil"
    assert loaded[0].online is True


def test_merge_peer_registry_updates_existing_and_marks_offline(
    registry_dir: Path,
) -> None:
    """Re-scanning merges: updates last_seen, marks missing peers offline, adds new."""
    old_peers = [
        PeerInfo(
            instance_id="uuid-old",
            instance_name="old-peer",
            mode="standalone",
            capabilities=[],
            tailscale_ip="100.64.0.10",
            tailscale_name="old.ts.net.",
            endpoint="http://100.64.0.10:8443/federation/v1/identity",
            first_seen="2026-04-01T00:00:00+00:00",
            last_seen="2026-04-01T00:00:00+00:00",
            online=True,
        ),
    ]
    new_scan = [
        PeerInfo(
            instance_id="uuid-new",
            instance_name="new-peer",
            mode="federated",
            capabilities=["status"],
            tailscale_ip="100.64.0.20",
            tailscale_name="new.ts.net.",
            endpoint="http://100.64.0.20:8443/federation/v1/identity",
            first_seen="2026-04-08T12:00:00+00:00",
            last_seen="2026-04-08T12:00:00+00:00",
            online=True,
        ),
    ]

    merged = merge_peer_registry(existing=old_peers, scanned=new_scan)

    assert len(merged) == 2

    old = next(p for p in merged if p.instance_id == "uuid-old")
    assert old.online is False  # was not in new scan

    new = next(p for p in merged if p.instance_id == "uuid-new")
    assert new.online is True
    assert new.instance_name == "new-peer"


def test_discover_peers_excludes_self(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The local machine's own Tailscale IP is not probed."""

    probed_ips: list[str] = []

    def fake_run(cmd: list[str], **_: object) -> SimpleNamespace:
        return SimpleNamespace(
            returncode=0,
            stdout=json.dumps(FAKE_TAILSCALE_STATUS),
        )

    monkeypatch.setattr(subprocess, "run", fake_run)

    def tracking_urlopen(req: Any, *, timeout: float = 5.0) -> SimpleNamespace:
        url = req if isinstance(req, str) else req.full_url
        probed_ips.append(url)
        from urllib.error import URLError

        raise URLError("refused")

    monkeypatch.setattr("promptclaw.federation.discovery.urlopen", tracking_urlopen)

    discover_peers(port=8443)

    # Self IP is 100.64.0.1 — must not appear in probed URLs
    for url in probed_ips:
        assert "100.64.0.1" not in url, f"Self IP was probed: {url}"


def test_discover_peers_handles_malformed_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Malformed JSON identity responses are skipped gracefully."""

    def fake_run(cmd: list[str], **_: object) -> SimpleNamespace:
        return SimpleNamespace(
            returncode=0,
            stdout=json.dumps(FAKE_TAILSCALE_STATUS),
        )

    monkeypatch.setattr(subprocess, "run", fake_run)

    # cypherclaw returns invalid JSON, workstation returns incomplete identity
    fake_open = _make_fake_urlopen(
        {
            "100.64.0.2": (200, b"not json at all"),
            "100.64.0.3": (200, json.dumps({"incomplete": True}).encode()),
        }
    )
    monkeypatch.setattr("promptclaw.federation.discovery.urlopen", fake_open)

    peers = discover_peers(port=8443)
    assert peers == []
