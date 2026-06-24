"""SHARED SHADOW — the wall, written down (P4).

A compact, inspectable record of the current agreement, carried on the lead->verify handoff.
Two disciplines from the Shadowland field guide:
  - absence is always visible: every field renders a line, so a gap is a conscious claim
    ("(none stated)") rather than a silent omission;
  - Material unknowns must not be empty when something is in fact unknown — the engine fills
    it from open tensions, and ``validate_shared_shadow`` flags the empty-but-open case.
See docs/Shadowland2/promptclaw-integration-proposal.md (P4).
"""

from __future__ import annotations

from dataclasses import dataclass, field

_NONE = "_(none stated)_"
_NONE_UNKNOWNS = "_(none stated — confirm nothing material is unknown)_"


@dataclass
class SharedShadow:
    """The best shared cast of the shape so far — not proof either side understood the other."""

    purpose: str = ""
    audience: str = ""
    deliverable: str = ""
    constraints: list[str] = field(default_factory=list)
    agreed_definitions: list[str] = field(default_factory=list)
    decisions: list[str] = field(default_factory=list)
    material_unknowns: list[str] = field(default_factory=list)
    current_phase: str = ""
    next_move: str = ""
    success_criteria: list[str] = field(default_factory=list)


def render_shared_shadow(shadow: SharedShadow) -> str:
    """Render the record as markdown, making every absent field visible."""
    lines = ["# Shared Shadow", ""]
    lines.append(f"**Purpose:** {shadow.purpose or _NONE}")
    lines.append(f"**Audience:** {shadow.audience or _NONE}")
    lines.append(f"**Deliverable:** {shadow.deliverable or _NONE}")
    lines += _section("Constraints", shadow.constraints)
    lines += _section("Agreed definitions", shadow.agreed_definitions)
    lines += _section("Decisions", shadow.decisions)
    lines += _section("Material unknowns", shadow.material_unknowns, empty=_NONE_UNKNOWNS)
    lines.append("")
    lines.append(f"**Current phase:** {shadow.current_phase or _NONE}")
    lines.append(f"**Next move:** {shadow.next_move or _NONE}")
    lines += _section("Success criteria", shadow.success_criteria)
    return "\n".join(lines) + "\n"


def validate_shared_shadow(shadow: SharedShadow, *, open_item_count: int = 0) -> list[str]:
    """Return integrity issues with the record (empty = clean).

    ``open_item_count`` is the number of known-unresolved items (e.g. open tensions); if there
    are any but Material unknowns is empty, the record is hiding its own gaps.
    """
    issues: list[str] = []
    if not shadow.purpose:
        issues.append("Purpose is empty — the record must state what is being built.")
    if open_item_count > 0 and not shadow.material_unknowns:
        issues.append(
            f"Material unknowns is empty but {open_item_count} unresolved item(s) exist — "
            "record the gaps; do not let the record hide what is unknown."
        )
    return issues


def _section(title: str, items: list[str], empty: str = _NONE) -> list[str]:
    out = ["", f"**{title}:**"]
    if items:
        out += [f"- {item}" for item in items]
    else:
        out.append(empty)
    return out
