"""Feature flags for staged SenseWeave rollout and rollback."""
from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass


CURRICULUM_EXERCISE_ENV = "CYPHERCLAW_ENABLE_CURRICULUM_EXERCISE"
PREVIEW_RENDER_ENV = "CYPHERCLAW_ENABLE_PREVIEW_RENDER"
SELF_CRITIQUE_ENV = "CYPHERCLAW_ENABLE_SELF_CRITIQUE"
LONG_FORM_SUITE_ENV = "CYPHERCLAW_ENABLE_LONG_FORM_SUITE"

_TRUE_VALUES = {"1", "true", "yes", "on", "enabled"}
_FALSE_VALUES = {"0", "false", "no", "off", "disabled"}


@dataclass(frozen=True)
class SenseWeaveFeatureFlags:
    """Runtime gates for independently rolling out SenseWeave behavior."""

    curriculum_exercise: bool = True
    preview_render: bool = True
    self_critique: bool = True
    long_form_suite: bool = True

    @property
    def effective_self_critique(self) -> bool:
        """Self-critique requires preview metrics to make a revision decision."""
        return self.preview_render and self.self_critique

    def to_status_dict(self) -> dict[str, str]:
        """Return compact operator-facing flag states."""
        return {
            "curriculum": _state(self.curriculum_exercise),
            "preview": _state(self.preview_render),
            "critique": _state(self.self_critique),
            "suite": _state(self.long_form_suite),
            "effective_critique": _state(self.effective_self_critique),
        }


@dataclass(frozen=True)
class RolloutFlagState:
    """Resolved state for one environment-backed rollout flag."""

    name: str
    env_var: str
    enabled: bool
    raw_value: str | None
    default_enabled: bool = True
    source: str = "default"


@dataclass(frozen=True)
class RolloutControlReport:
    """Operator-readable report for one rollout-control environment snapshot."""

    flags: SenseWeaveFeatureFlags
    flag_states: tuple[RolloutFlagState, ...]
    enabled_count: int
    disabled_count: int
    effective_self_critique: bool


def _state(enabled: bool) -> str:
    return "on" if enabled else "off"


def _env_bool(raw: str | None, *, default: bool) -> bool:
    if raw is None:
        return default
    value = raw.strip().lower()
    if value in _TRUE_VALUES:
        return True
    if value in _FALSE_VALUES:
        return False
    return default


def load_feature_flags(env: Mapping[str, str] | None = None) -> SenseWeaveFeatureFlags:
    """Load SenseWeave rollout flags from an environment-like mapping."""
    source = os.environ if env is None else env
    return SenseWeaveFeatureFlags(
        curriculum_exercise=_env_bool(source.get(CURRICULUM_EXERCISE_ENV), default=True),
        preview_render=_env_bool(source.get(PREVIEW_RENDER_ENV), default=True),
        self_critique=_env_bool(source.get(SELF_CRITIQUE_ENV), default=True),
        long_form_suite=_env_bool(source.get(LONG_FORM_SUITE_ENV), default=True),
    )


def flag_state(
    name: str,
    env_var: str,
    raw_value: str | None,
    *,
    default_enabled: bool = True,
) -> RolloutFlagState:
    """Resolve one rollout flag and preserve diagnostic source information."""
    enabled = _env_bool(raw_value, default=default_enabled)
    if raw_value is None:
        source = "default"
    else:
        normalized = raw_value.strip().lower()
        source = "env" if normalized in _TRUE_VALUES or normalized in _FALSE_VALUES else "defaulted"
    return RolloutFlagState(
        name=name,
        env_var=env_var,
        enabled=enabled,
        raw_value=raw_value,
        default_enabled=default_enabled,
        source=source,
    )


def rollout_control_report(
    env: Mapping[str, str] | None = None,
) -> RolloutControlReport:
    """Resolve rollout flags and return a stable operator report."""
    source = os.environ if env is None else env
    definitions = (
        ("curriculum", CURRICULUM_EXERCISE_ENV),
        ("preview", PREVIEW_RENDER_ENV),
        ("critique", SELF_CRITIQUE_ENV),
        ("suite", LONG_FORM_SUITE_ENV),
    )
    states: list[RolloutFlagState] = []
    for name, env_var in definitions:
        states.append(flag_state(name, env_var, source.get(env_var)))

    flags = SenseWeaveFeatureFlags(
        curriculum_exercise=states[0].enabled,
        preview_render=states[1].enabled,
        self_critique=states[2].enabled,
        long_form_suite=states[3].enabled,
    )
    enabled_count = sum(1 for state in states if state.enabled)
    disabled_count = len(states) - enabled_count
    return RolloutControlReport(
        flags=flags,
        flag_states=tuple(states),
        enabled_count=enabled_count,
        disabled_count=disabled_count,
        effective_self_critique=flags.effective_self_critique,
    )


def summarize_rollout_controls(report: RolloutControlReport) -> dict[str, object]:
    """Return a JSON-safe summary for status surfaces and logs."""
    state_rows: list[dict[str, object]] = []
    for state in report.flag_states:
        state_rows.append(
            {
                "name": state.name,
                "env_var": state.env_var,
                "enabled": state.enabled,
                "raw_value": state.raw_value,
                "default_enabled": state.default_enabled,
                "source": state.source,
            }
        )
    return {
        "flags": report.flags.to_status_dict(),
        "enabled_count": report.enabled_count,
        "disabled_count": report.disabled_count,
        "effective_self_critique": report.effective_self_critique,
        "states": state_rows,
    }
