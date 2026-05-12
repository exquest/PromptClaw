"""Single shared role-filter contract for R1–R8 humanization rules."""
from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum
from typing import Final


class Role(StrEnum):
    OSTINATO = "ostinato"
    MELODY = "melody"
    PAD = "pad"
    PERC = "perc"
    ACCENT = "accent"
    SILENCE = "silence"

    @property
    def grid_locked(self) -> bool | None:
        if self is Role.SILENCE:
            return None
        return self in {Role.OSTINATO, Role.PERC}


_ROLE_ALIASES: Final[dict[str, Role]] = {
    "counter": Role.MELODY,
    "counter_melody": Role.MELODY,
    "drum": Role.PERC,
    "drums": Role.PERC,
    "figuration": Role.MELODY,
    "lead": Role.MELODY,
    "machine": Role.PERC,
    "percussion": Role.PERC,
    "rhythm": Role.PERC,
    "sample": Role.PERC,
}

MELODIC_ACCENT_ROLES: Final[frozenset[str]] = frozenset(
    {
        "accent",
        "counter",
        "counter_melody",
        "figuration",
        "lead",
        "melody",
        "pad",
    }
)

GRID_LOCKED_ROLES: Final[frozenset[str]] = frozenset(
    {
        "drum",
        "drums",
        "machine",
        "ostinato",
        "perc",
        "percussion",
        "rhythm",
        "sample",
        "silence",
    }
)

_TRUTHY: Final[frozenset[str]] = frozenset(
    {"1", "true", "yes", "y", "on", "grid", "locked", "machine"}
)
_GRID_LOCKED_KEYS: Final[tuple[str, ...]] = (
    "grid_locked",
    "locked_to_grid",
    "machine_locked",
    "machine_identity",
    "timing_policy",
)


def _is_truthy(value: object) -> bool:
    return str(value).strip().lower() in _TRUTHY


def metadata_is_grid_locked(metadata: Mapping[str, object] | None) -> bool:
    if not metadata:
        return False
    return any(_is_truthy(metadata.get(key, "")) for key in _GRID_LOCKED_KEYS)


def resolve_role(role: str | Role) -> Role | None:
    if isinstance(role, Role):
        return role
    normalized = str(role).strip().lower()
    try:
        return Role(normalized)
    except ValueError:
        return _ROLE_ALIASES.get(normalized)


def role_is_eligible(
    role: str | Role, metadata: Mapping[str, object] | None = None
) -> bool:
    resolved = resolve_role(role)
    if resolved is None or resolved is Role.SILENCE:
        return False
    if resolved.grid_locked:
        return False
    return not metadata_is_grid_locked(metadata)
