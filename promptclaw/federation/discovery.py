"""Federation peer discovery via Tailscale.

Scans the local tailnet for other PromptClaw instances by probing each
Tailscale peer for the ``/federation/v1/identity`` endpoint, then stores
discovered peers in a local registry at ``~/.promptclaw/federation/peers.json``.
"""

from __future__ import annotations

import json
import logging
import subprocess
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

log = logging.getLogger("promptclaw.federation.discovery")

_DEFAULT_REGISTRY_PATH = (
    Path.home() / ".promptclaw" / "federation" / "peers.json"
)
_DEFAULT_PORT = 8443
_PROBE_TIMEOUT_S = 3.0
_IDENTITY_PATH = "/federation/v1/identity"


@dataclass
class PeerInfo:
    """A discovered PromptClaw peer on the tailnet."""

    instance_id: str
    instance_name: str
    mode: str
    capabilities: list[str]
    tailscale_ip: str
    tailscale_name: str
    endpoint: str
    first_seen: str
    last_seen: str
    online: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> PeerInfo:
        return cls(
            instance_id=d["instance_id"],
            instance_name=d["instance_name"],
            mode=d["mode"],
            capabilities=d.get("capabilities", []),
            tailscale_ip=d["tailscale_ip"],
            tailscale_name=d["tailscale_name"],
            endpoint=d["endpoint"],
            first_seen=d["first_seen"],
            last_seen=d["last_seen"],
            online=d.get("online", False),
        )


# ── Tailscale status ──────────────────────────────────────────────


def _get_tailscale_status() -> dict[str, Any] | None:
    """Run ``tailscale status --json`` and return parsed output.

    Returns *None* when Tailscale is unavailable or returns an error.
    """
    try:
        result = subprocess.run(
            ["tailscale", "status", "--json"],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        log.warning("Tailscale unavailable: %s", exc)
        return None

    if result.returncode != 0:
        log.warning("Tailscale returned non-zero exit code %d", result.returncode)
        return None

    try:
        return json.loads(result.stdout)  # type: ignore[no-any-return]
    except json.JSONDecodeError as exc:
        log.warning("Failed to parse tailscale status JSON: %s", exc)
        return None


def _self_ips(status: dict[str, Any]) -> set[str]:
    """Extract the local machine's Tailscale IPs from status."""
    self_node = status.get("Self", {})
    return set(self_node.get("TailscaleIPs", []))


def _iter_peers(
    status: dict[str, Any],
) -> list[tuple[str, str, list[str]]]:
    """Yield (node_key, dns_name, ips) for each online peer."""
    peers: list[tuple[str, str, list[str]]] = []
    peer_map = status.get("Peer", {})
    for _key, info in peer_map.items():
        if not info.get("Online", False):
            continue
        dns_name = info.get("DNSName", "")
        ips = info.get("TailscaleIPs", [])
        if ips:
            peers.append((_key, dns_name, ips))
    return peers


# ── Identity probing ──────────────────────────────────────────────


def _probe_identity(ip: str, port: int) -> dict[str, Any] | None:
    """Probe a peer for its PromptClaw identity endpoint.

    Returns the parsed identity dict on success, *None* on any failure.
    """
    url = f"http://{ip}:{port}{_IDENTITY_PATH}"
    req = Request(url)
    try:
        with urlopen(req, timeout=_PROBE_TIMEOUT_S) as resp:
            body = resp.read()
    except (HTTPError, URLError, OSError, TimeoutError) as exc:
        log.debug("Probe %s failed: %s", url, exc)
        return None

    try:
        data = json.loads(body)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        log.debug("Malformed identity response from %s: %s", url, exc)
        return None

    # Validate required fields
    required = ("instance_id", "instance_name", "mode", "created_at")
    if not all(k in data for k in required):
        log.debug("Incomplete identity from %s: missing keys", url)
        return None

    return data  # type: ignore[no-any-return]


# ── Discovery ─────────────────────────────────────────────────────


def discover_peers(*, port: int = _DEFAULT_PORT) -> list[PeerInfo]:
    """Scan the Tailscale network for PromptClaw instances.

    Returns a list of :class:`PeerInfo` for each peer that responds with
    a valid identity payload.  Returns an empty list when Tailscale is
    unavailable.
    """
    status = _get_tailscale_status()
    if status is None:
        return []

    self_ips = _self_ips(status)
    now = datetime.now(timezone.utc).isoformat()
    found: list[PeerInfo] = []

    for _key, dns_name, ips in _iter_peers(status):
        # Skip self
        if self_ips & set(ips):
            continue

        identity: dict[str, Any] | None = None
        probed_ip = ""
        for ip in ips:
            identity = _probe_identity(ip, port)
            if identity is not None:
                probed_ip = ip
                break

        if identity is None:
            continue

        endpoint = f"http://{probed_ip}:{port}{_IDENTITY_PATH}"
        found.append(
            PeerInfo(
                instance_id=identity["instance_id"],
                instance_name=identity["instance_name"],
                mode=identity["mode"],
                capabilities=identity.get("capabilities", []),
                tailscale_ip=probed_ip,
                tailscale_name=dns_name,
                endpoint=endpoint,
                first_seen=now,
                last_seen=now,
                online=True,
            )
        )

    return found


# ── Registry persistence ──────────────────────────────────────────


def save_peer_registry(
    peers: list[PeerInfo],
    *,
    path: Path = _DEFAULT_REGISTRY_PATH,
) -> None:
    """Persist peers to the JSON registry file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps([p.to_dict() for p in peers], indent=2))


def load_peer_registry(
    *,
    path: Path = _DEFAULT_REGISTRY_PATH,
) -> list[PeerInfo]:
    """Load the peer registry from disk.

    Returns an empty list if the file does not exist or is invalid.
    """
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text())
        return [PeerInfo.from_dict(d) for d in data]
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        log.warning("Failed to load peer registry: %s", exc)
        return []


def merge_peer_registry(
    *,
    existing: list[PeerInfo],
    scanned: list[PeerInfo],
) -> list[PeerInfo]:
    """Merge a fresh scan into an existing registry.

    - Peers present in both are updated with new ``last_seen`` and data.
    - Peers in *existing* but not in *scanned* are marked offline.
    - Peers only in *scanned* are added as new.
    """
    scanned_by_id = {p.instance_id: p for p in scanned}
    merged: list[PeerInfo] = []

    for old in existing:
        if old.instance_id in scanned_by_id:
            # Update with fresh scan data, keep first_seen
            fresh = scanned_by_id.pop(old.instance_id)
            merged.append(
                PeerInfo(
                    instance_id=fresh.instance_id,
                    instance_name=fresh.instance_name,
                    mode=fresh.mode,
                    capabilities=fresh.capabilities,
                    tailscale_ip=fresh.tailscale_ip,
                    tailscale_name=fresh.tailscale_name,
                    endpoint=fresh.endpoint,
                    first_seen=old.first_seen,
                    last_seen=fresh.last_seen,
                    online=True,
                )
            )
        else:
            # Mark as offline
            merged.append(
                PeerInfo(
                    instance_id=old.instance_id,
                    instance_name=old.instance_name,
                    mode=old.mode,
                    capabilities=old.capabilities,
                    tailscale_ip=old.tailscale_ip,
                    tailscale_name=old.tailscale_name,
                    endpoint=old.endpoint,
                    first_seen=old.first_seen,
                    last_seen=old.last_seen,
                    online=False,
                )
            )

    # Add new peers from scan
    for fresh in scanned_by_id.values():
        merged.append(fresh)

    return merged
