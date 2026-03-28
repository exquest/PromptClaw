"""Constitutional rule enforcement for the coherence engine."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:
    yaml = None  # type: ignore[assignment]

from .models import EnforcementMode, Violation, ViolationSeverity


@dataclass
class Rule:
    """A single constitutional rule."""

    rule_id: str
    severity: ViolationSeverity
    description: str
    pattern: str | None = None
    keywords: list[str] = field(default_factory=list)
    applies_to_phases: list[str] = field(default_factory=list)
    applies_to_agents: list[str] = field(default_factory=list)
    message: str = ""


def _parse_severity(value: str) -> ViolationSeverity:
    """Parse a severity string into the enum."""
    return ViolationSeverity(value.lower())


def _rule_from_dict(data: dict[str, Any]) -> Rule:
    """Build a Rule from a raw dict (JSON or YAML)."""
    severity_raw = data.get("severity", "soft")
    severity = _parse_severity(severity_raw)

    applies_to = data.get("applies_to", [])
    applies_to_agents = data.get("applies_to_agents", [])

    return Rule(
        rule_id=data.get("id", data.get("rule_id", "")),
        severity=severity,
        description=data.get("description", ""),
        pattern=data.get("pattern"),
        keywords=data.get("keywords", []),
        applies_to_phases=applies_to if isinstance(applies_to, list) else [applies_to],
        applies_to_agents=applies_to_agents if isinstance(applies_to_agents, list) else [applies_to_agents],
        message=data.get("message", ""),
    )


class Constitution:
    """Loads and evaluates constitutional rules against text."""

    def __init__(self, path: Path | None = None) -> None:
        self.rules: list[Rule] = []
        if path and path.exists():
            self.rules = self._load(path)

    def _load(self, path: Path) -> list[Rule]:
        """Load rules from a YAML or JSON constitution file."""
        suffix = path.suffix.lower()
        raw: dict[str, Any] | None = None

        if suffix in (".yaml", ".yml"):
            if yaml is not None:
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        raw = yaml.safe_load(f)
                except Exception:
                    raw = None

            # Fallback: try JSON if yaml unavailable or failed
            if raw is None:
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        raw = json.load(f)
                except Exception:
                    return []
        elif suffix == ".json":
            try:
                with open(path, "r", encoding="utf-8") as f:
                    raw = json.load(f)
            except Exception:
                return []
        else:
            # Unknown extension — try JSON
            try:
                with open(path, "r", encoding="utf-8") as f:
                    raw = json.load(f)
            except Exception:
                return []

        if not raw or "rules" not in raw:
            return []

        rules: list[Rule] = []
        for entry in raw["rules"]:
            try:
                rules.append(_rule_from_dict(entry))
            except (KeyError, ValueError):
                continue
        return rules

    def evaluate(self, text: str, phase: str = "", agent: str = "") -> list[Violation]:
        """Check text against all applicable rules.

        Returns a list of Violations for every rule that matches.
        """
        violations: list[Violation] = []
        text_lower = text.lower()

        for rule in self._applicable_rules(phase, agent):
            matched = False

            # Check regex pattern
            if rule.pattern:
                if re.search(rule.pattern, text, re.IGNORECASE):
                    matched = True

            # Check keywords (case-insensitive substring)
            if rule.keywords:
                for kw in rule.keywords:
                    if kw.lower() in text_lower:
                        matched = True
                        break

            if matched:
                violations.append(Violation(
                    rule_id=rule.rule_id,
                    severity=rule.severity,
                    message=rule.message or rule.description,
                ))

        return violations

    def _applicable_rules(self, phase: str, agent: str) -> list[Rule]:
        """Filter rules by phase and agent."""
        result: list[Rule] = []
        for rule in self.rules:
            # Phase filter: empty list means applies to all phases
            if rule.applies_to_phases and phase and phase not in rule.applies_to_phases:
                continue
            # Agent filter: empty list means applies to all agents
            if rule.applies_to_agents and agent and agent not in rule.applies_to_agents:
                continue
            result.append(rule)
        return result

    def rules_for_phase(self, phase: str) -> list[Rule]:
        """Return rules that apply to a specific phase."""
        return [
            r for r in self.rules
            if not r.applies_to_phases or phase in r.applies_to_phases
        ]

    def hard_rules(self) -> list[Rule]:
        """Return all rules with HARD severity."""
        return [r for r in self.rules if r.severity == ViolationSeverity.HARD]

    def soft_rules(self) -> list[Rule]:
        """Return all rules with SOFT severity."""
        return [r for r in self.rules if r.severity == ViolationSeverity.SOFT]

    def should_block(self, violations: list[Violation], mode: EnforcementMode) -> bool:
        """Determine whether the given violations should block execution.

        - MONITOR: never block
        - SOFT: block if any HARD violation
        - FULL: block if any violation
        """
        if not violations:
            return False

        if mode == EnforcementMode.MONITOR:
            return False

        if mode == EnforcementMode.SOFT:
            return any(v.severity == ViolationSeverity.HARD for v in violations)

        if mode == EnforcementMode.FULL:
            return True

        return False
