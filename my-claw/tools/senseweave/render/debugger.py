"""Rule localization debugger for SenseWeave render output."""
from __future__ import annotations

import argparse
import importlib
import json
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from itertools import combinations
from pathlib import Path
from typing import TypeVar

from .ablation import AblationRenderer, ablate
from .diff import ScoreDelta, diff_scores

ScoreT = TypeVar("ScoreT")
RuleT = TypeVar("RuleT")
OutputT = TypeVar("OutputT")

DiffFunction = Callable[[OutputT, OutputT], ScoreDelta]


@dataclass(frozen=True)
class ProblemRegion:
    """Subset of a rendered score that should drive localization ranking."""

    phrase_indices: tuple[int, ...] = ()
    note_indices: tuple[tuple[int, int], ...] = ()
    include_global: bool = True

    @classmethod
    def from_selection(
        cls,
        *,
        phrase_indices: Iterable[int] = (),
        note_indices: Iterable[tuple[int, int]] = (),
        include_global: bool = True,
    ) -> "ProblemRegion":
        phrases = tuple(sorted(set(phrase_indices)))
        notes = tuple(sorted(set(note_indices)))
        return cls(phrases, notes, include_global)

    @property
    def unbounded(self) -> bool:
        return not self.phrase_indices and not self.note_indices

    def includes_phrase(self, phrase_index: int) -> bool:
        if self.unbounded:
            return True
        return phrase_index in self.phrase_indices or any(
            phrase_index == phrase for phrase, _note in self.note_indices
        )

    def includes_note(self, phrase_index: int, note_index: int) -> bool:
        if self.unbounded:
            return True
        return (
            phrase_index in self.phrase_indices
            or (phrase_index, note_index) in self.note_indices
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "phrase_indices": list(self.phrase_indices),
            "note_indices": [
                {"phrase_index": phrase, "note_index": note}
                for phrase, note in self.note_indices
            ],
            "include_global": self.include_global,
            "scope": "all" if self.unbounded else "selected",
        }


@dataclass(frozen=True)
class AblationRun:
    """One ablation render and its diff against the all-rules baseline."""

    disabled_rules: tuple[str, ...]
    rendered: object
    delta: ScoreDelta
    impact_score: float
    summary: str

    def to_dict(self) -> dict[str, object]:
        return {
            "disabled_rules": list(self.disabled_rules),
            "impact_score": self.impact_score,
            "summary": self.summary,
        }


@dataclass(frozen=True)
class RuleImpact:
    """Aggregated localization score for one rule across ablation runs."""

    rule_id: str
    expressive_impact: float
    single_impact: float
    combination_impact: float
    supporting_cases: tuple[tuple[str, ...], ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "rule_id": self.rule_id,
            "expressive_impact": self.expressive_impact,
            "single_impact": self.single_impact,
            "combination_impact": self.combination_impact,
            "supporting_cases": [list(case) for case in self.supporting_cases],
        }


@dataclass(frozen=True)
class LocalizationReport:
    """A complete rule-localization report."""

    problem_region: ProblemRegion
    ablation_runs: tuple[AblationRun, ...]
    ranked_rules: tuple[RuleImpact, ...]

    @property
    def top_rule(self) -> RuleImpact | None:
        return self.ranked_rules[0] if self.ranked_rules else None

    def to_dict(self) -> dict[str, object]:
        return {
            "problem_region": self.problem_region.to_dict(),
            "ranked_rules": [impact.to_dict() for impact in self.ranked_rules],
            "ablation_runs": [run.to_dict() for run in self.ablation_runs],
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)

    def to_text(self) -> str:
        lines = ["SenseWeave render localization report"]
        region = "all rendered score changes"
        if not self.problem_region.unbounded:
            region = json.dumps(self.problem_region.to_dict(), sort_keys=True)
        lines.append(f"Problem region: {region}")
        lines.append("")
        lines.append("Ranked rules:")
        if not self.ranked_rules:
            lines.append("- no rules supplied")
        for index, impact in enumerate(self.ranked_rules, start=1):
            lines.append(
                f"{index}. {impact.rule_id}: "
                f"{impact.expressive_impact:.2f} impact "
                f"(single {impact.single_impact:.2f}, "
                f"combination {impact.combination_impact:.2f})"
            )
        lines.append("")
        lines.append("Ablation runs:")
        for run in self.ablation_runs:
            label = ", ".join(run.disabled_rules)
            lines.append(f"- disable {label}: {run.impact_score:.2f}; {run.summary}")
        return "\n".join(lines)


@dataclass(frozen=True)
class RuleHandle:
    """Minimal rule object used by the CLI when only IDs are supplied."""

    rule_id: str


@dataclass
class _RuleAccumulator:
    total: float = 0.0
    single: float = 0.0
    combination: float = 0.0
    cases: list[tuple[str, ...]] = field(default_factory=list)


def _rule_identifier(rule: object) -> str:
    if isinstance(rule, str) and rule:
        return rule
    for attr in ("rule_id", "id"):
        value = getattr(rule, attr, None)
        if isinstance(value, str) and value:
            return value
    raise TypeError("render rule must define a non-empty string rule_id or id")


def _impact_score(delta: ScoreDelta, region: ProblemRegion) -> float:
    score = 0.0
    for note in delta.note_changes:
        if region.includes_note(note.phrase_index, note.note_index):
            score += 1.0
    for phrase in delta.phrase_changes:
        if region.includes_phrase(phrase.phrase_index):
            score += 2.0
    for phrase_index in delta.added_phrases:
        if region.includes_phrase(phrase_index):
            score += 3.0
    for phrase_index in delta.removed_phrases:
        if region.includes_phrase(phrase_index):
            score += 3.0
    if region.include_global:
        if delta.key_changed:
            score += 3.0
        if delta.tempo_delta:
            score += abs(delta.tempo_delta) / 10.0
    return round(score, 4)


def _ablation_rule_sets(
    rule_ids: Sequence[str],
    max_combination_size: int,
) -> tuple[tuple[str, ...], ...]:
    if max_combination_size < 1:
        raise ValueError("max_combination_size must be at least 1")
    capped_size = min(max_combination_size, len(rule_ids))
    return tuple(
        combo
        for size in range(1, capped_size + 1)
        for combo in combinations(rule_ids, size)
    )


def _rank_rules(rule_ids: Sequence[str], runs: Sequence[AblationRun]) -> tuple[RuleImpact, ...]:
    accumulators = {rule_id: _RuleAccumulator() for rule_id in rule_ids}
    for run in runs:
        if not run.disabled_rules:
            continue
        share = run.impact_score / len(run.disabled_rules)
        for rule_id in run.disabled_rules:
            accumulator = accumulators[rule_id]
            accumulator.total += share
            accumulator.cases.append(run.disabled_rules)
            if len(run.disabled_rules) == 1:
                accumulator.single = max(accumulator.single, run.impact_score)
            else:
                accumulator.combination = max(accumulator.combination, run.impact_score)

    impacts = (
        RuleImpact(
            rule_id=rule_id,
            expressive_impact=round(accumulator.total, 4),
            single_impact=round(accumulator.single, 4),
            combination_impact=round(accumulator.combination, 4),
            supporting_cases=tuple(accumulator.cases),
        )
        for rule_id, accumulator in accumulators.items()
    )
    return tuple(
        sorted(
            impacts,
            key=lambda impact: (
                -impact.expressive_impact,
                -impact.single_impact,
                impact.rule_id,
            ),
        )
    )


def localize_rule_impacts(
    score: ScoreT,
    seeds: Mapping[str, int] | None,
    *,
    active_rules: Sequence[RuleT],
    renderer: AblationRenderer[ScoreT, RuleT, OutputT],
    diff: DiffFunction[OutputT] = diff_scores,
    problem_region: ProblemRegion | None = None,
    max_combination_size: int = 2,
) -> LocalizationReport:
    """Run single and combinatorial ablations and rank rule impact."""

    rule_ids = tuple(_rule_identifier(rule) for rule in active_rules)
    if len(rule_ids) != len(set(rule_ids)):
        raise ValueError("active rule IDs must be unique")

    region = problem_region or ProblemRegion()
    baseline = renderer(score, seeds=seeds, rules=active_rules)
    runs: list[AblationRun] = []
    for disabled_rules in _ablation_rule_sets(rule_ids, max_combination_size):
        rendered = ablate(
            score,
            seeds,
            disabled_rules=disabled_rules,
            active_rules=active_rules,
            renderer=renderer,
        )
        delta = diff(baseline, rendered)
        runs.append(
            AblationRun(
                disabled_rules=disabled_rules,
                rendered=rendered,
                delta=delta,
                impact_score=_impact_score(delta, region),
                summary=delta.summary(),
            )
        )

    return LocalizationReport(
        problem_region=region,
        ablation_runs=tuple(runs),
        ranked_rules=_rank_rules(rule_ids, runs),
    )


def run_debugger(
    score: ScoreT,
    seeds: Mapping[str, int] | None,
    *,
    active_rules: Sequence[RuleT],
    renderer: AblationRenderer[ScoreT, RuleT, OutputT],
    diff: DiffFunction[OutputT] = diff_scores,
    problem_region: ProblemRegion | None = None,
    max_combination_size: int = 2,
) -> LocalizationReport:
    """Compatibility wrapper for the debugger API entry point."""

    return localize_rule_impacts(
        score,
        seeds,
        active_rules=active_rules,
        renderer=renderer,
        diff=diff,
        problem_region=problem_region,
        max_combination_size=max_combination_size,
    )


def _load_callable(dotted_path: str) -> Callable[..., object]:
    module_name, sep, attr_path = dotted_path.partition(":")
    if not sep:
        module_name, _, attr_path = dotted_path.rpartition(".")
    if not module_name or not attr_path:
        raise ValueError("callable path must be in module:function form")
    target: object = importlib.import_module(module_name)
    for attr in attr_path.split("."):
        target = getattr(target, attr)
    if not callable(target):
        raise TypeError(f"{dotted_path!r} is not callable")
    return target


def _load_score(path: Path) -> object:
    from ..generative_scores import Note, Phrase, Score

    raw = json.loads(path.read_text())
    data = raw.get("score", raw) if isinstance(raw, dict) else raw
    if not isinstance(data, dict):
        raise ValueError("score JSON must contain an object")

    phrases = []
    for phrase in data.get("phrases", []):
        notes = [
            Note(
                scale_degree=int(note["scale_degree"]),
                duration_beats=float(note["duration_beats"]),
                accent=bool(note["accent"]),
            )
            for note in phrase.get("notes", [])
        ]
        phrases.append(
            Phrase(
                notes=notes,
                voice=str(phrase["voice"]),
                dynamic=str(phrase["dynamic"]),
                role=str(phrase["role"]),
                metadata={str(key): str(value) for key, value in phrase.get("metadata", {}).items()},
            )
        )
    return Score(
        phrases=phrases,
        key=str(data["key"]),
        tempo_bpm=float(data["tempo_bpm"]),
        mood=str(data.get("mood", "")),
        created_at=float(data.get("created_at", 0.0)),
        metadata={str(key): str(value) for key, value in data.get("metadata", {}).items()},
    )


def _parse_seed(value: str) -> tuple[str, int]:
    name, sep, raw = value.partition("=")
    if not sep or not name:
        raise argparse.ArgumentTypeError("seed must use name=int syntax")
    try:
        return name, int(raw)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("seed value must be an integer") from exc


def _parse_note(value: str) -> tuple[int, int]:
    phrase, sep, note = value.partition(":")
    if not sep:
        raise argparse.ArgumentTypeError("note must use phrase_index:note_index syntax")
    try:
        return int(phrase), int(note)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("note indices must be integers") from exc


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="senseweave-render-debugger",
        description="Localize expressive impact by ablating render rules.",
    )
    parser.add_argument("--score", type=Path, required=True, help="Path to score JSON.")
    parser.add_argument(
        "--renderer",
        required=True,
        help="Import path for renderer callable, e.g. package.module:function.",
    )
    parser.add_argument(
        "--rules",
        required=True,
        help="Comma-separated rule IDs to ablate.",
    )
    parser.add_argument("--seed", action="append", type=_parse_seed, default=[])
    parser.add_argument("--phrase", action="append", type=int, default=[])
    parser.add_argument("--note", action="append", type=_parse_note, default=[])
    parser.add_argument("--exclude-global", action="store_true")
    parser.add_argument("--max-combination-size", type=int, default=2)
    parser.add_argument("--format", choices=("json", "text"), default="json")
    parser.add_argument("--output", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    rule_ids = tuple(rule.strip() for rule in args.rules.split(",") if rule.strip())
    if not rule_ids:
        raise SystemExit("at least one rule ID is required")

    report = localize_rule_impacts(
        _load_score(args.score),
        dict(args.seed),
        active_rules=tuple(RuleHandle(rule_id) for rule_id in rule_ids),
        renderer=_load_callable(args.renderer),  # type: ignore[arg-type]
        problem_region=ProblemRegion.from_selection(
            phrase_indices=args.phrase,
            note_indices=args.note,
            include_global=not args.exclude_global,
        ),
        max_combination_size=args.max_combination_size,
    )

    output = report.to_json() if args.format == "json" else report.to_text()
    if args.output:
        args.output.write_text(output + "\n")
    else:
        print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
