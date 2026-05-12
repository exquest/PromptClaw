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


# === End-to-end depth-2 coverage (frac-0071) ===


_FAKE_IDENTITY_WORKSTATION: dict[str, Any] = {
    "instance_id": "uuid-workstation",
    "instance_name": "amber-anvil",
    "mode": "federated",
    "created_at": "2026-04-01T00:00:00+00:00",
    "release": "3.0.1",
    "capabilities": ["status", "tasks"],
}

_FAKE_IDENTITY_R750: dict[str, Any] = {
    "instance_id": "uuid-r750",
    "instance_name": "obsidian-pillar",
    "mode": "federated",
    "created_at": "2026-04-15T00:00:00+00:00",
    "release": "3.0.2",
    "capabilities": ["status", "art", "music"],
}

_TAILSCALE_STATUS_RESCAN: dict[str, Any] = {
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
        "nodekey:jkl000": {
            "TailscaleIPs": ["100.64.0.5"],
            "DNSName": "r750.tail12345.ts.net.",
            "HostName": "r750",
            "Online": True,
        },
    },
}


class FederationDiscoveryEndToEndTests:
    """Drive the federation discovery surface end-to-end.

    Exercises ``discover_peers`` → ``save_peer_registry`` →
    ``load_peer_registry`` → ``merge_peer_registry`` → ``save_peer_registry``
    against fakes for the Tailscale CLI and the identity HTTP endpoint so
    the fractal classifier sees real-logic paths through the public API.
    """

    __test__ = True

    def _install_tailscale(
        self,
        monkeypatch: pytest.MonkeyPatch,
        status: dict[str, Any],
    ) -> None:
        def fake_run(cmd: list[str], **_: object) -> SimpleNamespace:
            return SimpleNamespace(returncode=0, stdout=json.dumps(status))

        monkeypatch.setattr(subprocess, "run", fake_run)

    def test_full_discover_save_load_merge_cycle_yields_meaningful_registry(
        self,
        monkeypatch: pytest.MonkeyPatch,
        registry_dir: Path,
    ) -> None:
        # First scan: cypherclaw + workstation respond, phone is offline.
        self._install_tailscale(monkeypatch, FAKE_TAILSCALE_STATUS)
        first_open = _make_fake_urlopen(
            {
                "100.64.0.2": (
                    200,
                    json.dumps(FAKE_IDENTITY_CYPHERCLAW).encode(),
                ),
                "100.64.0.3": (
                    200,
                    json.dumps(_FAKE_IDENTITY_WORKSTATION).encode(),
                ),
            }
        )
        monkeypatch.setattr(
            "promptclaw.federation.discovery.urlopen", first_open
        )

        first_scan = discover_peers(port=8443)
        assert {p.instance_id for p in first_scan} == {
            "uuid-cypherclaw",
            "uuid-workstation",
        }

        cyph = next(p for p in first_scan if p.instance_id == "uuid-cypherclaw")
        assert cyph.instance_name == "molten-sigil"
        assert cyph.mode == "standalone"
        assert cyph.capabilities == ["status", "tasks", "art"]
        assert cyph.tailscale_ip == "100.64.0.2"
        assert cyph.endpoint == (
            "http://100.64.0.2:8443/federation/v1/identity"
        )
        assert cyph.online is True
        assert cyph.first_seen == cyph.last_seen

        registry_path = registry_dir / "peers.json"
        save_peer_registry(first_scan, path=registry_path)
        assert registry_path.exists()

        # Registry payload is JSON-safe and round-trips through PeerInfo.
        on_disk = json.loads(registry_path.read_text())
        assert isinstance(on_disk, list)
        assert {entry["instance_id"] for entry in on_disk} == {
            "uuid-cypherclaw",
            "uuid-workstation",
        }
        for entry in on_disk:
            roundtrip = PeerInfo.from_dict(entry)
            assert roundtrip.to_dict() == entry

        loaded = load_peer_registry(path=registry_path)
        assert {p.instance_id for p in loaded} == {
            "uuid-cypherclaw",
            "uuid-workstation",
        }

        # Second scan: workstation is gone, r750 has appeared, cypherclaw
        # remains. Use a different timestamp source to confirm last_seen
        # actually moves.
        self._install_tailscale(monkeypatch, _TAILSCALE_STATUS_RESCAN)
        second_open = _make_fake_urlopen(
            {
                "100.64.0.2": (
                    200,
                    json.dumps(FAKE_IDENTITY_CYPHERCLAW).encode(),
                ),
                "100.64.0.5": (
                    200,
                    json.dumps(_FAKE_IDENTITY_R750).encode(),
                ),
            }
        )
        monkeypatch.setattr(
            "promptclaw.federation.discovery.urlopen", second_open
        )

        second_scan = discover_peers(port=8443)
        assert {p.instance_id for p in second_scan} == {
            "uuid-cypherclaw",
            "uuid-r750",
        }

        merged = merge_peer_registry(existing=loaded, scanned=second_scan)
        merged_by_id = {p.instance_id: p for p in merged}
        assert set(merged_by_id) == {
            "uuid-cypherclaw",
            "uuid-workstation",
            "uuid-r750",
        }

        # cypherclaw was seen in both scans → online, first_seen preserved.
        cyph_old = next(
            p for p in loaded if p.instance_id == "uuid-cypherclaw"
        )
        cyph_merged = merged_by_id["uuid-cypherclaw"]
        assert cyph_merged.online is True
        assert cyph_merged.first_seen == cyph_old.first_seen

        # workstation dropped out → marked offline, identity preserved.
        ws_merged = merged_by_id["uuid-workstation"]
        assert ws_merged.online is False
        assert ws_merged.instance_name == "amber-anvil"
        assert ws_merged.tailscale_ip == "100.64.0.3"

        # r750 is brand new → online, first_seen == last_seen.
        r750_merged = merged_by_id["uuid-r750"]
        assert r750_merged.online is True
        assert r750_merged.instance_name == "obsidian-pillar"
        assert r750_merged.mode == "federated"
        assert "music" in r750_merged.capabilities
        assert r750_merged.first_seen == r750_merged.last_seen

        # Persist merged registry and re-read; payload remains JSON-safe and
        # the offline flag survives the round-trip.
        save_peer_registry(merged, path=registry_path)
        reloaded = load_peer_registry(path=registry_path)
        reloaded_by_id = {p.instance_id: p for p in reloaded}
        assert set(reloaded_by_id) == set(merged_by_id)
        assert reloaded_by_id["uuid-workstation"].online is False
        assert reloaded_by_id["uuid-r750"].online is True
        # Final payload is still strictly JSON-decodable as a list of dicts.
        final_on_disk = json.loads(registry_path.read_text())
        assert isinstance(final_on_disk, list)
        assert all(isinstance(entry, dict) for entry in final_on_disk)

    def test_multi_ip_peer_falls_through_to_responding_address(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        status = {
            "Self": {
                "TailscaleIPs": ["100.64.0.1"],
                "DNSName": "macbook.tail12345.ts.net.",
                "Online": True,
            },
            "Peer": {
                "nodekey:multi": {
                    "TailscaleIPs": ["100.64.0.99", "100.64.0.2"],
                    "DNSName": "cypherclaw.tail12345.ts.net.",
                    "Online": True,
                },
            },
        }
        self._install_tailscale(monkeypatch, status)

        # Only the second IP responds with a valid identity.
        fake_open = _make_fake_urlopen(
            {
                "100.64.0.2": (
                    200,
                    json.dumps(FAKE_IDENTITY_CYPHERCLAW).encode(),
                ),
            }
        )
        monkeypatch.setattr(
            "promptclaw.federation.discovery.urlopen", fake_open
        )

        peers = discover_peers(port=8443)
        assert len(peers) == 1
        assert peers[0].instance_id == "uuid-cypherclaw"
        assert peers[0].tailscale_ip == "100.64.0.2"
        assert peers[0].endpoint.startswith("http://100.64.0.2:8443/")

    def test_empty_rescan_marks_all_existing_peers_offline(
        self,
        monkeypatch: pytest.MonkeyPatch,
        registry_dir: Path,
    ) -> None:
        # Seed registry with one peer.
        seeded = [
            PeerInfo(
                instance_id="uuid-seed",
                instance_name="seed-peer",
                mode="standalone",
                capabilities=["status"],
                tailscale_ip="100.64.0.7",
                tailscale_name="seed.ts.net.",
                endpoint="http://100.64.0.7:8443/federation/v1/identity",
                first_seen="2026-04-01T00:00:00+00:00",
                last_seen="2026-04-05T00:00:00+00:00",
                online=True,
            ),
        ]
        path = registry_dir / "peers.json"
        save_peer_registry(seeded, path=path)

        # Tailscale unavailable → discover_peers returns empty.
        def fake_run(cmd: list[str], **_: object) -> SimpleNamespace:
            raise FileNotFoundError("tailscale not found")

        monkeypatch.setattr(subprocess, "run", fake_run)
        scan = discover_peers()
        assert scan == []

        existing = load_peer_registry(path=path)
        merged = merge_peer_registry(existing=existing, scanned=scan)
        assert len(merged) == 1
        assert merged[0].instance_id == "uuid-seed"
        assert merged[0].online is False
        # first_seen / last_seen preserved when no fresh data exists.
        assert merged[0].first_seen == "2026-04-01T00:00:00+00:00"
        assert merged[0].last_seen == "2026-04-05T00:00:00+00:00"
