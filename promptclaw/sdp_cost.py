"""SDP steady-state cost extractor (T-032@b).

Reads SDP telemetry rows out of `.sdp/state.db`, applies the pricing table
documented in `sdp/telemetry/cost-model.md`, and rolls per-task token usage
up into one row per active UTC day.
"""

from __future__ import annotations

import argparse
import csv
import os
import sqlite3
import sys
from dataclasses import dataclass, field
from pathlib import Path

# Pricing rows mirror the table in sdp/telemetry/cost-model.md. Order matters:
# the first matching substring wins. The trailing ("fallback", ...) row is the
# sentinel used when no specific pattern matches.
TOKEN_PRICING: tuple[tuple[str, float, float], ...] = (
    ("claude-opus-4", 15.00, 75.00),
    ("claude-sonnet-4", 3.00, 15.00),
    ("claude-haiku", 0.80, 4.00),
    ("gpt-4o", 2.50, 10.00),
    ("o3", 10.00, 40.00),
    ("codex-mini", 1.50, 6.00),
    ("fallback", 3.00, 15.00),
)

DEFAULT_DAILY_CAP_USD = 5.00
COST_MODEL_DOC = Path("sdp/telemetry/cost-model.md")


def match_pricing(profile_id: str) -> tuple[str, float, float]:
    """Return ``(tier, input_per_m, output_per_m)`` for a model profile id.

    Match is case-insensitive substring against ``TOKEN_PRICING`` patterns
    in declared order. Falls back to the ``fallback`` row when nothing matches.
    """
    needle = (profile_id or "").lower()
    for pattern, in_p, out_p in TOKEN_PRICING:
        if pattern == "fallback":
            continue
        if pattern in needle:
            return pattern, in_p, out_p
    fallback = TOKEN_PRICING[-1]
    return fallback[0], fallback[1], fallback[2]


def call_cost_usd(input_tokens: int, output_tokens: int, profile_id: str) -> float:
    """Apply the cost-model.md per-call formula for a single telemetry row."""
    _tier, in_p, out_p = match_pricing(profile_id)
    return (input_tokens / 1_000_000.0) * in_p + (output_tokens / 1_000_000.0) * out_p


@dataclass(slots=True)
class DailyCostRow:
    date: str
    runs: int
    input_tokens: int
    output_tokens: int
    cache_creation_tokens: int
    cache_read_tokens: int
    total_cost_usd: float
    models: list[str] = field(default_factory=list)


@dataclass(slots=True)
class DailyCapCheck:
    date: str
    total_cost_usd: float
    cap_usd: float
    over_by_usd: float

    @property
    def breached(self) -> bool:
        return self.over_by_usd > 0.0

    @property
    def status(self) -> str:
        return "BREACH" if self.breached else "OK"


@dataclass(slots=True)
class CostCapSummary:
    cap_usd: float
    min_days: int
    checks: list[DailyCapCheck]
    cost_model_doc: Path = COST_MODEL_DOC

    @property
    def days_checked(self) -> int:
        return len(self.checks)

    @property
    def breaches(self) -> list[DailyCapCheck]:
        return [check for check in self.checks if check.breached]

    @property
    def breach_count(self) -> int:
        return len(self.breaches)

    @property
    def missing_days(self) -> int:
        return max(0, self.min_days - self.days_checked)

    @property
    def result(self) -> str:
        if self.missing_days or self.breach_count:
            return "FAIL"
        return "PASS"


def extract_steady_state_cost(db_path: Path, days: int = 7) -> list[DailyCostRow]:
    """Return one ``DailyCostRow`` per active UTC day in the telemetry table.

    Selects the ``days`` most recent distinct ``date(created_at)`` values that
    have at least one telemetry row, then aggregates token totals and applies
    cost-model.md pricing per row using the row's ``lead_profile_id``.
    """
    conn = sqlite3.connect(db_path)
    try:
        conn.row_factory = sqlite3.Row
        active_dates = [
            row[0]
            for row in conn.execute(
                "SELECT DISTINCT date(created_at) AS d "
                "FROM telemetry "
                "ORDER BY d DESC "
                "LIMIT ?",
                (days,),
            )
        ]
        if not active_dates:
            return []
        keep = sorted(active_dates)
        placeholders = ",".join("?" for _ in keep)
        cursor = conn.execute(
            f"SELECT date(created_at) AS d, lead_profile_id, "
            f"input_tokens, output_tokens, "
            f"cache_creation_tokens, cache_read_tokens "
            f"FROM telemetry "
            f"WHERE date(created_at) IN ({placeholders}) "
            f"ORDER BY d ASC, telemetry_id ASC",
            keep,
        )
        per_day: dict[str, DailyCostRow] = {
            d: DailyCostRow(
                date=d,
                runs=0,
                input_tokens=0,
                output_tokens=0,
                cache_creation_tokens=0,
                cache_read_tokens=0,
                total_cost_usd=0.0,
            )
            for d in keep
        }
        per_day_models: dict[str, set[str]] = {d: set() for d in keep}
        for row in cursor:
            day = row["d"]
            bucket = per_day[day]
            bucket.runs += 1
            bucket.input_tokens += int(row["input_tokens"] or 0)
            bucket.output_tokens += int(row["output_tokens"] or 0)
            bucket.cache_creation_tokens += int(row["cache_creation_tokens"] or 0)
            bucket.cache_read_tokens += int(row["cache_read_tokens"] or 0)
            tier, _, _ = match_pricing(row["lead_profile_id"] or "")
            bucket.total_cost_usd += call_cost_usd(
                int(row["input_tokens"] or 0),
                int(row["output_tokens"] or 0),
                row["lead_profile_id"] or "",
            )
            per_day_models[day].add(tier)
        for day, bucket in per_day.items():
            bucket.models = sorted(per_day_models[day])
        return [per_day[d] for d in keep]
    finally:
        conn.close()


CSV_HEADER: tuple[str, ...] = (
    "date",
    "runs",
    "input_tokens",
    "output_tokens",
    "cache_creation_tokens",
    "cache_read_tokens",
    "total_cost_usd",
    "models",
)


def write_csv(rows: list[DailyCostRow], out_path: Path) -> None:
    """Write daily cost rows to ``out_path`` with the locked header schema."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh, lineterminator="\n")
        writer.writerow(CSV_HEADER)
        for row in rows:
            writer.writerow(
                [
                    row.date,
                    row.runs,
                    row.input_tokens,
                    row.output_tokens,
                    row.cache_creation_tokens,
                    row.cache_read_tokens,
                    f"{row.total_cost_usd:.4f}",
                    "|".join(row.models),
                ]
            )


def read_csv(csv_path: Path) -> list[DailyCostRow]:
    """Read rows previously written by :func:`write_csv`."""
    with csv_path.open(encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        fieldnames = set(reader.fieldnames or [])
        missing = set(CSV_HEADER) - fieldnames
        if missing:
            raise ValueError(
                f"{csv_path} is missing required columns: {', '.join(sorted(missing))}"
            )
        rows: list[DailyCostRow] = []
        for record in reader:
            models = [m for m in (record["models"] or "").split("|") if m]
            rows.append(
                DailyCostRow(
                    date=record["date"],
                    runs=int(record["runs"]),
                    input_tokens=int(record["input_tokens"]),
                    output_tokens=int(record["output_tokens"]),
                    cache_creation_tokens=int(record["cache_creation_tokens"]),
                    cache_read_tokens=int(record["cache_read_tokens"]),
                    total_cost_usd=float(record["total_cost_usd"]),
                    models=models,
                )
            )
    return rows


def check_daily_caps(
    rows: list[DailyCostRow],
    *,
    daily_cap_usd: float,
) -> list[DailyCapCheck]:
    """Return one cap check per row; costs equal to the cap pass."""
    return [
        DailyCapCheck(
            date=row.date,
            total_cost_usd=row.total_cost_usd,
            cap_usd=float(daily_cap_usd),
            over_by_usd=max(0.0, row.total_cost_usd - float(daily_cap_usd)),
        )
        for row in rows
    ]


def summarize_daily_cap(
    rows: list[DailyCostRow],
    *,
    daily_cap_usd: float = DEFAULT_DAILY_CAP_USD,
    min_days: int = 7,
    cost_model_doc: Path = COST_MODEL_DOC,
) -> CostCapSummary:
    """Build a PASS/FAIL cap summary for daily cost rows."""
    return CostCapSummary(
        cap_usd=float(daily_cap_usd),
        min_days=int(min_days),
        checks=check_daily_caps(rows, daily_cap_usd=daily_cap_usd),
        cost_model_doc=cost_model_doc,
    )


def total_cost_usd(rows: list[DailyCostRow]) -> float:
    """Return the summed ``total_cost_usd`` across ``rows``."""
    total = 0.0
    for row in rows:
        total += row.total_cost_usd
    return total


def cost_by_model(rows: list[DailyCostRow]) -> dict[str, float]:
    """Partition each row's cost evenly across its declared model tiers.

    Rows with an empty ``models`` list bucket their full cost under
    ``"fallback"`` — the same sentinel ``match_pricing`` returns when no
    pricing pattern matches. The returned dict is sorted by tier name.
    """
    bucket: dict[str, float] = {}
    for row in rows:
        tiers = list(row.models) if row.models else ["fallback"]
        share = row.total_cost_usd / len(tiers)
        for tier in tiers:
            bucket[tier] = bucket.get(tier, 0.0) + share
    return dict(sorted(bucket.items()))


def aggregate_rows(rows: list[DailyCostRow]) -> DailyCostRow:
    """Sum runs, tokens, and cost across rows into a single ``DailyCostRow``.

    The aggregate's ``date`` is the earliest input date (``""`` for an
    empty input). The ``models`` field is the sorted union of all per-row
    model tiers.
    """
    runs = 0
    input_tokens = 0
    output_tokens = 0
    cache_creation = 0
    cache_read = 0
    total = 0.0
    tiers: set[str] = set()
    earliest = ""
    for row in rows:
        runs += row.runs
        input_tokens += row.input_tokens
        output_tokens += row.output_tokens
        cache_creation += row.cache_creation_tokens
        cache_read += row.cache_read_tokens
        total += row.total_cost_usd
        tiers.update(row.models)
        if not earliest or row.date < earliest:
            earliest = row.date
    return DailyCostRow(
        date=earliest,
        runs=runs,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cache_creation_tokens=cache_creation,
        cache_read_tokens=cache_read,
        total_cost_usd=total,
        models=sorted(tiers),
    )


@dataclass(slots=True)
class CostRunSummary:
    """End-to-end roll-up of one ``summarize_cost_run`` invocation."""

    rows: list[DailyCostRow]
    total_cost_usd: float
    cost_by_model: dict[str, float]
    csv_path: Path
    cap: CostCapSummary | None = None


def summarize_cost_run(
    *,
    db_path: Path,
    out_path: Path,
    days: int = 7,
    summary_out: Path | None = None,
    daily_cap_usd: float = DEFAULT_DAILY_CAP_USD,
    min_days: int = 7,
    cost_model_doc: Path = COST_MODEL_DOC,
) -> CostRunSummary:
    """Run extract → CSV write → optional cap summary in one call."""
    rows = extract_steady_state_cost(db_path, days=days)
    write_csv(rows, out_path)
    total = total_cost_usd(rows)
    by_model = cost_by_model(rows)
    cap: CostCapSummary | None = None
    if summary_out is not None:
        cap = write_cap_summary(
            rows,
            summary_out,
            daily_cap_usd=daily_cap_usd,
            min_days=min_days,
            cost_model_doc=cost_model_doc,
        )
    return CostRunSummary(
        rows=rows,
        total_cost_usd=total,
        cost_by_model=by_model,
        csv_path=out_path,
        cap=cap,
    )


def _cost_model_link(cost_model_doc: Path, summary_path: Path | None) -> str:
    label = cost_model_doc.as_posix()
    target = label
    if summary_path is not None:
        target_path = cost_model_doc
        start_path = summary_path.parent
        if summary_path.is_absolute() != cost_model_doc.is_absolute():
            target_path = cost_model_doc.resolve()
            start_path = summary_path.parent.resolve()
        target = os.path.relpath(target_path, start=start_path)
    return f"[{label}]({target})"


def render_cap_summary(
    summary: CostCapSummary,
    *,
    summary_path: Path | None = None,
) -> str:
    """Render a short Markdown PASS/FAIL summary for cap checks."""
    lines = [
        "# Steady-State Cost Cap Summary",
        "",
        f"**Result:** {summary.result}",
        f"**Cost model:** {_cost_model_link(summary.cost_model_doc, summary_path)}",
        f"**Daily cap:** ${summary.cap_usd:.2f}",
        f"**Days checked:** {summary.days_checked} / {summary.min_days}",
        f"**Breaches:** {summary.breach_count}",
    ]
    if summary.missing_days:
        lines.append(f"Minimum days missing: {summary.missing_days}")
    lines.extend(
        [
            "",
            "| Date | Cost | Cap | Status |",
            "| --- | ---: | ---: | --- |",
        ]
    )
    for check in summary.checks:
        status = check.status
        if check.breached:
            status = f"BREACH (+${check.over_by_usd:.4f})"
        lines.append(
            f"| {check.date} | ${check.total_cost_usd:.4f} | "
            f"${check.cap_usd:.2f} | {status} |"
        )
    return "\n".join(lines) + "\n"


def write_cap_summary(
    rows: list[DailyCostRow],
    out_path: Path,
    *,
    daily_cap_usd: float = DEFAULT_DAILY_CAP_USD,
    min_days: int = 7,
    cost_model_doc: Path = COST_MODEL_DOC,
) -> CostCapSummary:
    """Write the Markdown cap summary and return the summary object."""
    summary = summarize_daily_cap(
        rows,
        daily_cap_usd=daily_cap_usd,
        min_days=min_days,
        cost_model_doc=cost_model_doc,
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        render_cap_summary(summary, summary_path=out_path),
        encoding="utf-8",
    )
    return summary


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m promptclaw.sdp_cost",
        description="Extract steady-state SDP cost data per day to CSV.",
    )
    parser.add_argument("--db", type=Path, default=Path(".sdp/state.db"))
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("sdp/telemetry/steady-state-cost.csv"),
    )
    parser.add_argument("--daily-cap-usd", type=float, default=DEFAULT_DAILY_CAP_USD)
    parser.add_argument("--min-days", type=int, default=7)
    parser.add_argument("--summary-out", type=Path, default=None)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    rows = extract_steady_state_cost(args.db, days=args.days)
    write_csv(rows, args.out)
    print(str(args.out))
    if args.summary_out is not None:
        summary = write_cap_summary(
            rows,
            args.summary_out,
            daily_cap_usd=args.daily_cap_usd,
            min_days=args.min_days,
        )
        print(str(args.summary_out))
        return 0 if summary.result == "PASS" else 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
