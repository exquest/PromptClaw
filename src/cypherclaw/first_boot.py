"""First-boot federation announcement wiring.

Implements FEDREAD-004: on the very first startup of a federated clone,
emit an announcement containing identity, lineage skeleton, release, mode,
capability summary, and publication status.
"""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Literal

log = logging.getLogger("cypherclaw.first_boot")

Mode = Literal["standalone", "federated"]

_DEFAULT_IDENTITY_PATH = Path("/home/user/cypherclaw/.promptclaw/identity.json")
_DEFAULT_ANNOUNCED_PATH = Path("/home/user/cypherclaw/.promptclaw/.first_boot_announced")


@dataclass
class InstanceIdentity:
    """Canonical home identity record."""

    instance_id: str
    instance_name: str
    mode: Mode
    created_at: str
    release: str
    parent_id: str | None = None
    clone_timestamp: str | None = None
    capabilities: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "InstanceIdentity":
        return cls(
            instance_id=payload["instance_id"],
            instance_name=payload["instance_name"],
            mode=payload["mode"],
            created_at=payload["created_at"],
            release=payload["release"],
            parent_id=payload.get("parent_id"),
            clone_timestamp=payload.get("clone_timestamp"),
            capabilities=payload.get("capabilities", []),
        )


def _build_announcement(identity: InstanceIdentity) -> dict[str, Any]:
    """Build the public first-boot announcement payload."""
    return {
        "type": "first_boot_announcement",
        "instance_id": identity.instance_id,
        "instance_name": identity.instance_name,
        "mode": identity.mode,
        "release": identity.release,
        "lineage": {
            "parent_id": identity.parent_id,
            "clone_timestamp": identity.clone_timestamp,
        },
        "capabilities": identity.capabilities,
        "publication_status": "local",
        "announced_at": datetime.now(timezone.utc).isoformat(),
    }


class FirstBootAnnouncer:
    """Manage one-time first-boot announcements for federated clones."""

    def __init__(
        self,
        *,
        identity_path: Path = _DEFAULT_IDENTITY_PATH,
        announced_path: Path = _DEFAULT_ANNOUNCED_PATH,
        announce_fn: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        self.identity_path = identity_path
        self.announced_path = announced_path
        self.announce_fn = announce_fn

    def load_identity(self) -> InstanceIdentity | None:
        """Load the persisted identity record, if present and valid."""
        if not self.identity_path.exists():
            return None

        try:
            payload = json.loads(self.identity_path.read_text())
        except json.JSONDecodeError as exc:
            log.warning("Failed to read identity file: %s", exc)
            return None

        try:
            return InstanceIdentity.from_dict(payload)
        except (KeyError, TypeError) as exc:
            log.warning("Failed to read identity file: %s", exc)
            return None

    def already_announced(self) -> bool:
        """Return whether the first-boot marker already exists."""
        return self.announced_path.exists()

    def maybe_announce(self) -> dict[str, Any] | None:
        """Announce a federated clone once, then persist the marker."""
        identity = self.load_identity()
        if identity is None or identity.mode != "federated" or self.already_announced():
            return None

        payload = _build_announcement(identity)
        if self.announce_fn is not None:
            self.announce_fn(payload)

        self.announced_path.parent.mkdir(parents=True, exist_ok=True)
        self.announced_path.write_text(json.dumps({"announced_at": payload["announced_at"]}))
        return payload


def mint_identity(
    *,
    mode: Mode = "standalone",
    instance_name: str = "",
    release: str = "",
    parent_id: str | None = None,
    identity_path: Path = _DEFAULT_IDENTITY_PATH,
) -> InstanceIdentity:
    """Create and persist a new instance identity."""
    identity = InstanceIdentity(
        instance_id=str(uuid.uuid4()),
        instance_name=instance_name or f"home-{uuid.uuid4().hex[:8]}",
        mode=mode,
        created_at=datetime.now(timezone.utc).isoformat(),
        release=release,
        parent_id=parent_id,
        clone_timestamp=datetime.now(timezone.utc).isoformat() if parent_id else None,
    )
    identity_path.parent.mkdir(parents=True, exist_ok=True)
    identity_path.write_text(json.dumps(identity.to_dict(), indent=2))
    return identity
