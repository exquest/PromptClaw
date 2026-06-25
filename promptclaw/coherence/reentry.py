"""Re-entry digest — the 'Prints' artifact: what the last run left for those who can read.

A newest-first, human- and agent-readable summary of coherence state, written so that
resuming bursty / multi-session work is fast. Derived purely from the event store and the
decision store (and, when present, held tensions). Inspired by the Shadowland working-document
method; see docs/Shadowland2/promptclaw-integration-proposal.md (P3 — generated re-entry digest).
"""

from __future__ import annotations

from typing import Any, Iterable

from .decision_store import Decision
from .models import CoherenceEvent

_PREAMBLE = "*Read this first on re-entry — the print is what the last run left for those who can read.*"


def build_reentry_digest(
    events: list[CoherenceEvent],
    decisions: list[Decision],
    *,
    generated_at: str,
    run_id: str | None = None,
    tensions: list[dict[str, Any]] | None = None,
    max_decisions: int = 8,
) -> str:
    """Render a newest-first markdown re-entry digest from coherence state.

    Pure and deterministic: ``generated_at`` is supplied by the caller rather than read
    from the clock, so the output is fully testable. ``events`` should be a single run's
    events in append order; ``decisions`` is the set of decisions (only ``active`` ones are
    shown); ``tensions`` is a forward-compat hook for the held-tension primitive (P1) and is
    rendered only when non-empty.
    """
    lines: list[str] = ["# Re-entry Digest", "", _PREAMBLE, ""]

    meta = f"_Generated {generated_at}"
    if run_id:
        meta += f" · run `{run_id}`"
    meta += f" · {len(events)} event(s) this run_"
    lines += [meta, ""]

    # --- Where it ended ---
    lines += ["## Where it ended", ""]
    if events:
        last = events[-1]
        ended = f"- **Last activity:** `{last.event_type}`"
        if last.phase:
            ended += f" in phase `{last.phase}`"
        ended += f" (seq {last.sequence_number}, {last.timestamp})"
        lines.append(ended)

        phases = _ordered_unique(e.phase for e in events)
        if phases:
            lines.append(f"- **Phases:** {' → '.join(phases)}")
        agents = _ordered_unique(e.agent for e in events)
        if agents:
            lines.append(f"- **Agents:** {', '.join(agents)}")
        verdict = _last_verdict(events)
        if verdict is not None:
            lines.append(f"- **Last verdict:** {verdict}")
    else:
        lines.append("- No events recorded for this run yet.")
    lines.append("")

    # --- Held tensions (only when present; populated once P1 lands) ---
    if tensions:
        lines += ["## Held tensions (surface — do not silently collapse)", ""]
        for t in tensions:
            statement = t.get("statement", "(unstated)")
            state = t.get("dialectic_state")
            entry = f"- {statement}"
            if state:
                entry += f" — _{state}_"
            lines.append(entry)
        lines.append("")

    # --- What's live: active decisions, newest first ---
    lines += ["## What's live — active decisions (newest first)", ""]
    active = sorted(
        (d for d in decisions if d.status == "active"),
        key=lambda d: d.created_at,
        reverse=True,
    )
    if active:
        shown = active[:max_decisions]
        for d in shown:
            lines.append(f"### {d.title}")
            if d.decision_text:
                lines.append(f"- **Decision:** {d.decision_text}")
            if d.constrains:
                lines.append(f"- **Constrains:** {', '.join(d.constrains)}")
            if d.unlocks:
                lines.append(f"- **Unlocks:** {', '.join(d.unlocks)}")
            if d.file_paths:
                lines.append(f"- **Affects:** {', '.join(d.file_paths)}")
            lines.append("")
        remaining = len(active) - len(shown)
        if remaining > 0:
            lines += [f"_+{remaining} more active decision(s) not shown._", ""]
    else:
        lines += ["No active decisions recorded.", ""]

    # --- Read first ---
    lines += ["## Read first", ""]
    pointers: list[str] = []
    if active:
        top = active[0]
        pointers.append(f"- Most recent decision: **{top.title}** ({top.created_at})")
    if events:
        last = events[-1]
        pointers.append(f"- Last event: `{last.event_type}` @ {last.timestamp}")
    if not pointers:
        pointers.append("- Nothing recorded yet — this is a fresh run.")
    lines += pointers

    return "\n".join(lines).rstrip() + "\n"


def _ordered_unique(values: Iterable[str]) -> list[str]:
    """Distinct truthy values in first-seen order."""
    seen: set[str] = set()
    out: list[str] = []
    for v in values:
        if v and v not in seen:
            seen.add(v)
            out.append(v)
    return out


def _last_verdict(events: list[CoherenceEvent]) -> str | None:
    """The most recent verdict carried in an event payload, if any."""
    for e in reversed(events):
        v = e.payload.get("verdict")
        if v:
            return str(v)
    return None
