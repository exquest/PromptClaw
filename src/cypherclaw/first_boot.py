"""First-boot federation announcement wiring.

Implements FEDREAD-004: on the very first startup of a federated clone,
emit an announcement containing identity, lineage skeleton, release, mode,
capability summary, and publication status.
"""

from __future__ import annotations

import json
import logging
import random
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Literal

log = logging.getLogger("cypherclaw.first_boot")

Mode = Literal["standalone", "federated"]

_DEFAULT_IDENTITY_PATH = Path.home() / ".promptclaw" / "identity.json"
_DEFAULT_ANNOUNCED_PATH = Path.home() / ".promptclaw" / ".first_boot_announced"

# ── Artistic name generator ────────────────────────────────────

_ADJECTIVES: tuple[str, ...] = (
    "amber", "arcane", "astral", "blazing", "cobalt",
    "crimson", "crystal", "dappled", "drifting", "dusted",
    "echoing", "ember", "fading", "ferric", "flickering",
    "gilded", "glinting", "hollow", "hushed", "ivory",
    "jade", "latticed", "liminal", "lucid", "midnight",
    "molten", "mossy", "nebula", "obsidian", "onyx",
    "opal", "pearlescent", "phantom", "prismatic", "quilted",
    "radiant", "rippled", "rusted", "sapphire", "shimmering",
    "silken", "smoldering", "spectral", "tidal", "twilight",
    "umbral", "veiled", "verdant", "woven", "zephyr",
)

_NOUNS: tuple[str, ...] = (
    "anvil", "archive", "basilisk", "beacon", "cairn",
    "canopy", "chimera", "citadel", "conduit", "crucible",
    "drake", "ember", "falcon", "forge", "furnace",
    "garnet", "glyph", "grotto", "harbor", "hearth",
    "heron", "junction", "kiln", "labyrinth", "lantern",
    "lattice", "loom", "monolith", "nexus", "obelisk",
    "oracle", "parchment", "pinnacle", "prism", "quarry",
    "raven", "relay", "ridge", "sanctum", "sentinel",
    "shard", "sigil", "spire", "terrace", "thorn",
    "totem", "turret", "vault", "vortex", "wellspring",
)


def generate_artistic_name(*, rng: random.Random | None = None) -> str:
    """Generate an artistic instance name from word lists.

    Returns a name like ``"molten-sigil"`` or ``"twilight-beacon"``.
    """
    r = rng or random.Random()  # noqa: S311
    adj = r.choice(_ADJECTIVES)
    noun = r.choice(_NOUNS)
    return f"{adj}-{noun}"


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
        instance_name=instance_name or generate_artistic_name(),
        mode=mode,
        created_at=datetime.now(timezone.utc).isoformat(),
        release=release,
        parent_id=parent_id,
        clone_timestamp=datetime.now(timezone.utc).isoformat() if parent_id else None,
    )
    identity_path.parent.mkdir(parents=True, exist_ok=True)
    identity_path.write_text(json.dumps(identity.to_dict(), indent=2))
    return identity


def bootstrap_identity(
    *,
    mode: Mode = "standalone",
    release: str = "",
    parent_id: str | None = None,
    identity_path: Path = _DEFAULT_IDENTITY_PATH,
) -> InstanceIdentity:
    """Load an existing identity or mint a new one on first boot.

    If *identity_path* already contains a valid identity record it is
    returned as-is.  Otherwise a fresh identity is minted, persisted,
    and returned.
    """
    if identity_path.exists():
        try:
            payload = json.loads(identity_path.read_text())
            identity = InstanceIdentity.from_dict(payload)
            log.info("Loaded existing identity %s (%s)", identity.instance_id, identity.instance_name)
            return identity
        except (json.JSONDecodeError, KeyError, TypeError) as exc:
            log.warning("Corrupt identity file, minting fresh: %s", exc)

    identity = mint_identity(
        mode=mode,
        release=release,
        parent_id=parent_id,
        identity_path=identity_path,
    )
    log.info("Minted new identity %s (%s)", identity.instance_id, identity.instance_name)
    return identity
