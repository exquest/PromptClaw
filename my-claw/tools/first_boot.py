"""First-boot federation announcement wiring.

Implements FEDREAD-004: on the very first startup of a *federated* clone,
emit an announcement containing identity, lineage skeleton, release, mode,
capability summary, and publication status.

Rules:
- Federated clones announce on first boot.
- Standalone instances never announce automatically.
- A repeat boot of a federated clone does NOT re-announce.
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

# Default paths — overridable for testing via constructor args.
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
    """Canonical home identity record (IDLINE-001)."""

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
    def from_dict(cls, d: dict[str, Any]) -> InstanceIdentity:
        return cls(
            instance_id=d["instance_id"],
            instance_name=d["instance_name"],
            mode=d["mode"],
            created_at=d["created_at"],
            release=d["release"],
            parent_id=d.get("parent_id"),
            clone_timestamp=d.get("clone_timestamp"),
            capabilities=d.get("capabilities", []),
        )


def _build_announcement(identity: InstanceIdentity) -> dict[str, Any]:
    """Build the first-boot announcement payload (FEDREAD-004).

    Includes identity, lineage skeleton, release, mode, capability summary,
    and publication status.  Excludes raw private memory and secrets.
    """
    lineage: dict[str, Any] = {
        "parent_id": identity.parent_id,
        "clone_timestamp": identity.clone_timestamp,
    }
    return {
        "type": "first_boot_announcement",
        "instance_id": identity.instance_id,
        "instance_name": identity.instance_name,
        "mode": identity.mode,
        "release": identity.release,
        "lineage": lineage,
        "capabilities": identity.capabilities,
        "publication_status": "local",
        "announced_at": datetime.now(timezone.utc).isoformat(),
    }


class FirstBootAnnouncer:
    """Manages first-boot federation announcement logic.

    Parameters
    ----------
    identity_path:
        Path to the identity JSON file.
    announced_path:
        Marker file whose existence means "already announced".
    announce_fn:
        Callable invoked with the announcement payload dict when
        announcing.  In production this posts to the federation bus;
        in tests it can be a mock.
    """

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

    # ── Public API ──────────────────────────────────────────────

    def load_identity(self) -> InstanceIdentity | None:
        """Load the instance identity from disk, or *None* if missing."""
        if not self.identity_path.exists():
            return None
        try:
            data = json.loads(self.identity_path.read_text())
            return InstanceIdentity.from_dict(data)
        except (json.JSONDecodeError, KeyError, TypeError) as exc:
            log.warning("Failed to read identity file: %s", exc)
            return None

    def already_announced(self) -> bool:
        """Return *True* if the first-boot marker file exists."""
        return self.announced_path.exists()

    def maybe_announce(self) -> dict[str, Any] | None:
        """Run the first-boot announcement check.

        Returns the announcement payload if an announcement was made,
        or *None* if no announcement was needed.
        """
        identity = self.load_identity()
        if identity is None:
            log.debug("No identity file — skipping first-boot announcement")
            return None

        if identity.mode != "federated":
            log.debug("Instance mode is '%s' — no announcement", identity.mode)
            return None

        if self.already_announced():
            log.debug("First-boot already announced — skipping")
            return None

        payload = _build_announcement(identity)

        if self.announce_fn is not None:
            self.announce_fn(payload)

        # Mark as announced so subsequent boots skip this.
        self.announced_path.parent.mkdir(parents=True, exist_ok=True)
        self.announced_path.write_text(
            json.dumps({"announced_at": payload["announced_at"]}),
        )
        log.info("First-boot announcement sent for %s", identity.instance_id)
        return payload


def mint_identity(
    *,
    mode: Mode = "standalone",
    instance_name: str = "",
    release: str = "",
    parent_id: str | None = None,
    identity_path: Path = _DEFAULT_IDENTITY_PATH,
) -> InstanceIdentity:
    """Create and persist a new instance identity (IDLINE-002)."""
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
