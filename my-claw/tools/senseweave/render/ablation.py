"""Core rule-ablation engine for the SenseWeave render layer."""
from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Generic, Protocol, TypeVar, overload

ScoreT = TypeVar("ScoreT")
RuleT = TypeVar("RuleT")
OutputT = TypeVar("OutputT")
ScoreT_contra = TypeVar("ScoreT_contra", contravariant=True)
RuleT_contra = TypeVar("RuleT_contra", contravariant=True)
OutputT_co = TypeVar("OutputT_co", covariant=True)


class AblationRenderer(Protocol[ScoreT_contra, RuleT_contra, OutputT_co]):
    """Callable render pipeline used by the ablation engine."""

    def __call__(
        self,
        score: ScoreT_contra,
        *,
        seeds: Mapping[str, int] | None,
        rules: Sequence[RuleT_contra],
    ) -> OutputT_co:
        """Render *score* with the supplied active rules and seed context."""


@dataclass(frozen=True)
class AblationCase:
    """One planned ablation run."""

    disabled_rules: tuple[str, ...]
    remaining_rule_ids: tuple[str, ...]
    removed_rule_ids: tuple[str, ...]


@dataclass(frozen=True)
class AblationResult(Generic[OutputT]):
    """One ablated render compared with the full-stack baseline."""

    disabled_rules: tuple[str, ...]
    remaining_rule_ids: tuple[str, ...]
    removed_rule_ids: tuple[str, ...]
    rendered: OutputT
    changed: bool
    summary: str


@dataclass(frozen=True)
class AblationSuite(Generic[OutputT]):
    """Baseline render plus all requested ablation results."""

    rule_ids: tuple[str, ...]
    baseline: OutputT
    results: tuple[AblationResult[OutputT], ...]


def _rule_identifier(rule: object) -> str:
    if isinstance(rule, str) and rule:
        return rule
    for attr in ("rule_id", "id"):
        value = getattr(rule, attr, None)
        if isinstance(value, str) and value:
            return value
    raise TypeError("render rule must define a non-empty string rule_id or id")


def rule_identifiers(active_rules: Sequence[RuleT]) -> tuple[str, ...]:
    """Return active render rule IDs in execution order."""

    return tuple(_rule_identifier(rule) for rule in active_rules)


def filter_active_rules(
    active_rules: Sequence[RuleT],
    disabled_rules: Iterable[str],
) -> tuple[RuleT, ...]:
    """Return active rules with selected rule IDs removed.

    Rule order is preserved. Unknown disabled IDs are treated as configuration
    errors because silent no-op ablations make listener debugging misleading.
    """

    disabled = frozenset(disabled_rules)
    indexed_rules = tuple((_rule_identifier(rule), rule) for rule in active_rules)
    known_ids = {rule_id for rule_id, _rule in indexed_rules}
    unknown_ids = sorted(disabled.difference(known_ids))
    if unknown_ids:
        joined = ", ".join(unknown_ids)
        raise ValueError(f"unknown disabled rule id(s): {joined}")
    return tuple(rule for rule_id, rule in indexed_rules if rule_id not in disabled)


def _dedupe_rule_ids(rule_ids: Iterable[str]) -> tuple[str, ...]:
    deduped: list[str] = []
    seen: set[str] = set()
    for rule_id in rule_ids:
        if rule_id in seen:
            continue
        seen.add(rule_id)
        deduped.append(rule_id)
    return tuple(deduped)


def _unknown_rule_error(unknown_ids: Sequence[str]) -> ValueError:
    joined = ", ".join(unknown_ids)
    return ValueError(f"unknown disabled rule id(s): {joined}")


def build_ablation_cases(
    active_rules: Sequence[RuleT],
    disabled_rule_sets: Iterable[Iterable[str]] | None = None,
) -> tuple[AblationCase, ...]:
    """Build a stable ablation plan from active rules and disabled ID sets."""

    rule_ids = rule_identifiers(active_rules)
    if len(rule_ids) != len(set(rule_ids)):
        raise ValueError("active rule IDs must be unique")

    known_ids = set(rule_ids)
    requested_sets = (
        ((rule_id,) for rule_id in rule_ids)
        if disabled_rule_sets is None
        else disabled_rule_sets
    )
    cases: list[AblationCase] = []
    seen_cases: set[tuple[str, ...]] = set()
    for requested in requested_sets:
        disabled = _dedupe_rule_ids(requested)
        if disabled in seen_cases:
            continue
        unknown_ids = sorted(set(disabled).difference(known_ids))
        if unknown_ids:
            raise _unknown_rule_error(unknown_ids)
        disabled_set = set(disabled)
        cases.append(
            AblationCase(
                disabled_rules=disabled,
                remaining_rule_ids=tuple(
                    rule_id for rule_id in rule_ids if rule_id not in disabled_set
                ),
                removed_rule_ids=tuple(
                    rule_id for rule_id in rule_ids if rule_id in disabled_set
                ),
            )
        )
        seen_cases.add(disabled)
    return tuple(cases)


def _default_renderer(
    score: ScoreT,
    *,
    seeds: Mapping[str, int] | None,
    rules: Sequence[RuleT],
) -> Any:
    """Render through the existing no-rule score preview seam."""

    del seeds
    if rules:
        raise ValueError("renderer is required when active_rules are provided")

    from ..generative_scores import score_to_frequencies

    return score_to_frequencies(score)  # type: ignore[arg-type]


@overload
def ablate(
    score: ScoreT,
    seeds: Mapping[str, int] | None = None,
    *,
    disabled_rules: Iterable[str] = (),
    active_rules: Sequence[RuleT],
    renderer: AblationRenderer[ScoreT, RuleT, OutputT],
) -> OutputT:
    ...


@overload
def ablate(
    score: ScoreT,
    seeds: Mapping[str, int] | None = None,
    *,
    disabled_rules: Iterable[str] = (),
    active_rules: Sequence[RuleT] = (),
    renderer: None = None,
) -> Any:
    ...


def ablate(
    score: ScoreT,
    seeds: Mapping[str, int] | None = None,
    *,
    disabled_rules: Iterable[str] = (),
    active_rules: Sequence[RuleT] = (),
    renderer: AblationRenderer[ScoreT, RuleT, OutputT] | None = None,
) -> Any:
    """Render *score* with selected active rules disabled.

    The ablation core owns only rule-set filtering and rerender dispatch. The
    concrete renderer decides how rules affect the performed output.
    """

    filtered_rules = filter_active_rules(active_rules, disabled_rules)
    render = renderer if renderer is not None else _default_renderer
    return render(score, seeds=seeds, rules=filtered_rules)


def _format_ablation_summary(case: AblationCase, changed: bool) -> str:
    disabled = ",".join(case.disabled_rules) if case.disabled_rules else "none"
    remaining = (
        ",".join(case.remaining_rule_ids) if case.remaining_rule_ids else "baseline"
    )
    status = "changed" if changed else "unchanged"
    return f"disabled {disabled}; remaining {remaining}; {status}"


def run_ablation_suite(
    score: ScoreT,
    seeds: Mapping[str, int] | None = None,
    *,
    active_rules: Sequence[RuleT],
    renderer: AblationRenderer[ScoreT, RuleT, OutputT],
    disabled_rule_sets: Iterable[Iterable[str]] | None = None,
) -> AblationSuite[OutputT]:
    """Render the full stack and a planned set of ablated alternatives."""

    rule_ids = rule_identifiers(active_rules)
    cases = build_ablation_cases(active_rules, disabled_rule_sets)
    baseline = renderer(score, seeds=seeds, rules=active_rules)
    results: list[AblationResult[OutputT]] = []
    for case in cases:
        rendered = ablate(
            score,
            seeds,
            disabled_rules=case.disabled_rules,
            active_rules=active_rules,
            renderer=renderer,
        )
        changed = rendered != baseline
        results.append(
            AblationResult(
                disabled_rules=case.disabled_rules,
                remaining_rule_ids=case.remaining_rule_ids,
                removed_rule_ids=case.removed_rule_ids,
                rendered=rendered,
                changed=changed,
                summary=_format_ablation_summary(case, changed),
            )
        )
    return AblationSuite(
        rule_ids=rule_ids,
        baseline=baseline,
        results=tuple(results),
    )


def summarize_ablation_suite(suite: AblationSuite[Any]) -> dict[str, object]:
    """Return a JSON-safe summary for operator logs and tests."""

    cases: list[dict[str, object]] = []
    changed_count = 0
    for result in suite.results:
        if result.changed:
            changed_count += 1
        cases.append(
            {
                "disabled_rules": list(result.disabled_rules),
                "remaining_rule_ids": list(result.remaining_rule_ids),
                "removed_rule_ids": list(result.removed_rule_ids),
                "changed": result.changed,
                "summary": result.summary,
            }
        )
    return {
        "rule_ids": list(suite.rule_ids),
        "case_count": len(suite.results),
        "changed_count": changed_count,
        "unchanged_count": len(suite.results) - changed_count,
        "cases": cases,
    }
