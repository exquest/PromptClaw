"""Coherence engine data models."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class EnforcementMode(Enum):
    MONITOR = "monitor"
    SOFT = "soft"
    FULL = "full"


class ViolationSeverity(Enum):
    HARD = "hard"
    SOFT = "soft"


@dataclass
class CoherenceEvent:
    """A single immutable event in the append-only log."""

    event_id: str
    run_id: str
    timestamp: str
    event_type: str
    phase: str = ""
    agent: str = ""
    role: str = ""
    payload: dict[str, Any] = field(default_factory=dict)
    sequence_number: int = 0


@dataclass
class Violation:
    """A constitutional rule violation."""

    rule_id: str
    severity: ViolationSeverity
    message: str
    blocked: bool = False
    context: dict[str, Any] = field(default_factory=dict)


@dataclass
class CoherenceVerdict:
    """Result of a coherence hook evaluation."""

    approved: bool = True
    violations: list[Violation] = field(default_factory=list)
    injected_context: str = ""
    trust_delta: float = 0.0
    mode: EnforcementMode = EnforcementMode.MONITOR


@dataclass
class CoherenceConfig:
    """Configuration for the coherence engine."""

    enabled: bool = True
    database_url: str = ""
    redis_url: str = ""
    constitution_path: str = "constitution.yaml"
    enforcement_mode: str = "monitor"
    auto_graduate: bool = True
    graduation_confidence_threshold: float = 0.85
    graduation_false_positive_threshold: float = 0.05

    @property
    def mode(self) -> EnforcementMode:
        try:
            return EnforcementMode(self.enforcement_mode)
        except ValueError:
            return EnforcementMode.MONITOR
