#!/usr/bin/env python3
"""Reviewer — daily briefs, weekly retros, and monthly reviews for PromptClaw.

Reads from the Observatory event store and generates Telegram-friendly
summaries at daily, weekly, and monthly cadences. Pure query + formatting;
never writes to Observatory.

Uses only Python stdlib.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone


class Reviewer:
    """Generates periodic review reports from Observatory data."""

    def __init__(self, observatory):
        self.obs = observatory

    # ==================================================================
    # Public report generators
    # ==================================================================

    def daily_brief(self, date: str | None = None) -> str:
        """Generate a Telegram-friendly daily summary.

        Args:
            date: ISO date string (YYYY-MM-DD). Defaults to today (UTC).

        Returns:
            Formatted daily brief string.
        """
        if date is None:
            date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        dt = datetime.strptime(date, "%Y-%m-%d")
        header_date = dt.strftime("%B %d, %Y")  # e.g. "March 26, 2026"

        # --- Gather data ---
        agent_stats = self.obs.get_agent_stats(days=1)
        healing_events = self.obs.get_healing_log(days=1)
        task_results = self.obs.get_task_results(
            since=datetime.now(timezone.utc) - timedelta(days=1)
        )
        skills = self.obs.get_agent_skills()

        # --- Compute aggregates ---
        total_completed = 0
        total_failed = 0
        total_tokens = 0
        total_duration = 0
        task_count = 0
        stuck_count = 0  # tasks that took excessively long (>10 min)

        agent_summaries = {}
        for agent, stats in agent_stats.items():
            t = stats.get("total", 0) or 0
            s = stats.get("successes", 0) or 0
            f = t - s
            tok = stats.get("total_tokens", 0) or 0
            avg_dur = stats.get("avg_duration", 0) or 0
            gp = stats.get("gate_passes", 0) or 0

            total_completed += s
            total_failed += f
            total_tokens += tok
            total_duration += avg_dur * t
            task_count += t

            success_rate = (s / t * 100) if t > 0 else 0
            agent_summaries[agent] = {
                "total": t,
                "successes": s,
                "failures": f,
                "tokens": tok,
                "avg_duration_ms": avg_dur,
                "success_rate": success_rate,
                "gate_passes": gp,
            }

        # Detect stuck tasks (duration > 10 min)
        for tr in task_results:
            if tr.get("duration_ms", 0) > 600_000:
                stuck_count += 1

        # Find top agent
        top_agent = None
        top_rate = -1.0
        for agent, s in agent_summaries.items():
            if s["success_rate"] > top_rate:
                top_rate = s["success_rate"]
                top_agent = agent

        # Healing breakdown
        healing_count = len(healing_events)
        healing_types = Counter(h["failure_type"] for h in healing_events)
        healing_breakdown = ", ".join(
            f"{count} {ftype.replace('_', ' ')}" + ("s" if count > 1 else "")
            for ftype, count in healing_types.most_common(3)
        )
        if not healing_breakdown:
            healing_breakdown = "none"

        # Gate failure analysis
        gate_failures = []
        for agent, s in agent_summaries.items():
            gf = s["total"] - s["gate_passes"]
            if gf > 0:
                gate_failures.append((agent, gf))

        # --- Build output ---
        lines = []
        lines.append(f"\U0001f4ca Daily Brief \u2014 {header_date}")
        lines.append("")

        # Task summary
        parts = [f"{total_completed} completed"]
        if total_failed > 0:
            parts.append(f"{total_failed} failed")
        if stuck_count > 0:
            parts.append(f"{stuck_count} stuck")
        lines.append(f"Tasks: {', '.join(parts)}")

        # Top agent
        if top_agent and agent_summaries:
            s = agent_summaries[top_agent]
            avg_str = self._duration_human(s["avg_duration_ms"])
            lines.append(
                f"Top agent: {top_agent} ({s['success_rate']:.0f}% success, avg {avg_str})"
            )

        # Healing
        lines.append(f"Healing: {healing_count} auto-fix{'es' if healing_count != 1 else ''} ({healing_breakdown})")

        # Token cost
        cost_str = self._cost_estimate(total_tokens)
        token_k = total_tokens / 1000
        lines.append(f"Tokens: ~{token_k:.0f}k ({cost_str} est.)")

        # Attention section
        attention_items = []
        for agent, gf_count in gate_failures:
            attention_items.append(f"- {gf_count} task{'s' if gf_count > 1 else ''} failed gate checks ({agent})")
        if stuck_count > 0:
            attention_items.append(f"- {stuck_count} task{'s' if stuck_count > 1 else ''} stuck (>10min)")

        if attention_items:
            lines.append("")
            lines.append("\u26a0\ufe0f Attention:")
            lines.extend(attention_items)

        # Insight section
        insights = self._generate_daily_insights(agent_summaries, skills, healing_events)
        if insights:
            lines.append("")
            lines.append("\U0001f4a1 Insight:")
            for insight in insights[:3]:
                lines.append(f"- {insight}")

        return "\n".join(lines)

    def weekly_retro(self) -> str:
        """Generate a weekly retrospective report.

        Returns:
            Formatted weekly retro string.
        """
        today = datetime.now(timezone.utc).date()
        week_start = today - timedelta(days=today.weekday())
        header_date = week_start.strftime("%B %d")  # e.g. "March 24"

        # --- Current week data ---
        this_week = self.obs.get_weekly_rollups(weeks_back=0)
        last_week = self.obs.get_weekly_rollups(weeks_back=1)

        # Aggregate current week
        cw = self._aggregate_rollups(this_week)
        lw = self._aggregate_rollups(last_week)

        # Agent stats for the week
        agent_stats = self.obs.get_agent_stats(days=7)
        healing_events = self.obs.get_healing_log(days=7)
        skills = self.obs.get_agent_skills()

        # --- Performance section ---
        lines = []
        lines.append(f"\U0001f4cb Weekly Retro \u2014 Week of {header_date}")
        lines.append("")
        lines.append("Performance:")

        completed = int(cw["tasks_completed"])
        prev_completed = int(lw["tasks_completed"])
        diff_str = self._diff_string(completed, prev_completed)
        lines.append(f"- {completed} tasks completed ({diff_str})")

        avg_time = cw["avg_duration_ms"]
        prev_avg = lw["avg_duration_ms"]
        avg_str = self._duration_human(avg_time)
        avg_diff = self._diff_string_duration(avg_time, prev_avg)
        lines.append(f"- Avg time: {avg_str} ({avg_diff})")

        gate_rate = (cw["gate_passes"] / cw["gate_total"] * 100) if cw["gate_total"] > 0 else 0
        prev_gate = (lw["gate_passes"] / lw["gate_total"] * 100) if lw["gate_total"] > 0 else 0
        gate_arrow = self._trend_arrow(gate_rate, prev_gate)
        gate_diff_abs = abs(gate_rate - prev_gate)
        lines.append(f"- Gate pass: {gate_rate:.0f}% ({gate_arrow}{gate_diff_abs:.0f}%)")

        healed_count = sum(1 for h in healing_events if h.get("success"))
        lines.append(f"- Self-healed: {healed_count} failures")

        # --- Agent Evolution section ---
        lines.append("")
        lines.append("Agent Evolution:")
        skills_by_agent = defaultdict(list)
        for s in skills:
            skills_by_agent[s["agent"]].append(s)

        for agent, agent_skills in sorted(skills_by_agent.items()):
            for sk in agent_skills[:2]:  # top 2 skills per agent
                score = sk["score"]
                lines.append(
                    f"- {agent}: {sk['category']} {score:.2f}"
                )

        # --- Routing Changes section ---
        lines.append("")
        lines.append("Routing Changes:")
        if agent_stats:
            total_tasks = sum(s.get("total", 0) or 0 for s in agent_stats.values())
            for agent, stats in sorted(agent_stats.items()):
                t = stats.get("total", 0) or 0
                pct = (t / total_tasks * 100) if total_tasks > 0 else 0
                if pct > 20:
                    lines.append(f"- {agent}: {pct:.0f}% of tasks this week")
        else:
            lines.append("- No routing data this week")

        # --- Top Healing Events ---
        lines.append("")
        lines.append("Top Healing Events:")
        healing_types = Counter(h["failure_type"] for h in healing_events)
        if healing_types:
            for ftype, count in healing_types.most_common(5):
                lines.append(f"- {count}x {ftype.replace('_', ' ')}")
        else:
            lines.append("- No healing events this week")

        # --- Goals ---
        lines.append("")
        lines.append("Goals for Next Week:")
        goals = self._generate_weekly_goals(cw, agent_stats, skills, healing_events)
        for goal in goals[:4]:
            lines.append(f"- {goal}")

        return "\n".join(lines)

    def monthly_review(self) -> str:
        """Generate a longer-form monthly analysis.

        Returns:
            Formatted monthly review string.
        """
        today = datetime.now(timezone.utc).date()
        month_name = today.strftime("%B %Y")  # e.g. "March 2026"

        # --- Gather 30-day data ---
        agent_stats = self.obs.get_agent_stats(days=30)
        healing_events = self.obs.get_healing_log(days=30)
        skills = self.obs.get_agent_skills()
        agg = self.obs.aggregate(metric="tasks", period="monthly")

        total = agg.get("total", 0) or 0
        successes = agg.get("successes", 0) or 0
        failures = agg.get("failures", 0) or 0
        total_tokens = agg.get("total_tokens", 0) or 0
        avg_duration = agg.get("avg_duration", 0) or 0
        gate_passes = agg.get("gate_passes", 0) or 0
        success_rate = (successes / total * 100) if total > 0 else 0
        gate_rate = (gate_passes / total * 100) if total > 0 else 0

        lines = []
        lines.append(f"\U0001f4d6 Monthly Review \u2014 {month_name}")
        lines.append("")

        # --- Overview ---
        lines.append("Overview:")
        lines.append(f"- Total tasks: {total} ({successes} succeeded, {failures} failed)")
        lines.append(f"- Success rate: {success_rate:.1f}%")
        lines.append(f"- Gate pass rate: {gate_rate:.1f}%")
        lines.append(f"- Avg completion time: {self._duration_human(avg_duration)}")
        lines.append(f"- Total tokens: {total_tokens:,}")
        lines.append(f"- Estimated cost: {self._cost_estimate(total_tokens)}")

        # --- Agent Performance ---
        lines.append("")
        lines.append("Agent Performance:")
        for agent, stats in sorted(agent_stats.items()):
            t = stats.get("total", 0) or 0
            s = stats.get("successes", 0) or 0
            rate = (s / t * 100) if t > 0 else 0
            avg_d = stats.get("avg_duration", 0) or 0
            tok = stats.get("total_tokens", 0) or 0
            lines.append(
                f"- {agent}: {t} tasks, {rate:.0f}% success, "
                f"avg {self._duration_human(avg_d)}, {self._cost_estimate(tok)}"
            )

        # --- Skill Progression ---
        lines.append("")
        lines.append("Agent Skills (current):")
        skills_by_agent = defaultdict(list)
        for s in skills:
            skills_by_agent[s["agent"]].append(s)
        for agent, agent_skills in sorted(skills_by_agent.items()):
            skill_strs = [f"{sk['category']}={sk['score']:.2f}" for sk in agent_skills[:4]]
            lines.append(f"- {agent}: {', '.join(skill_strs)}")

        # --- Failure Analysis ---
        lines.append("")
        lines.append("Most Common Failure Types:")
        healing_types = Counter(h["failure_type"] for h in healing_events)
        if healing_types:
            for ftype, count in healing_types.most_common(5):
                lines.append(f"- {ftype.replace('_', ' ')}: {count} occurrences")
        else:
            lines.append("- No failures recorded")

        # --- Self-improvement actions ---
        lines.append("")
        lines.append("Self-Improvement Actions:")
        total_heals = len(healing_events)
        successful_heals = sum(1 for h in healing_events if h.get("success"))
        if total_heals > 0:
            lines.append(f"- {total_heals} healing events ({successful_heals} successful)")
            heal_rate = (successful_heals / total_heals * 100)
            lines.append(f"- Healing success rate: {heal_rate:.0f}%")
        else:
            lines.append("- No self-healing events this month")

        # --- Recommendations ---
        lines.append("")
        lines.append("Recommendations for Next Month:")
        recommendations = self._generate_monthly_recommendations(
            agent_stats, skills, healing_events, agg
        )
        for rec in recommendations[:5]:
            lines.append(f"- {rec}")

        return "\n".join(lines)

    def generate_insight(self, stats: dict) -> str:
        """Generate a 1-2 sentence actionable insight from aggregate stats.

        Args:
            stats: Dict with keys like 'agent_stats', 'gate_rate', 'healing_count',
                   'prev_gate_rate', 'prev_healing_count', 'error_counts'.

        Returns:
            Actionable insight string.
        """
        insights = []

        # Check for underperforming agents in specific categories
        agent_stats = stats.get("agent_stats", {})
        for agent, data in agent_stats.items():
            categories = data.get("categories", {})
            for cat, cat_stats in categories.items():
                rate = cat_stats.get("success_rate", 100)
                if rate < 60:
                    insights.append(
                        f"Recommend routing {cat} tasks away from {agent} "
                        f"(success rate {rate:.0f}%)"
                    )

        # Gate pass rate trending down
        gate_rate = stats.get("gate_rate", 100)
        prev_gate_rate = stats.get("prev_gate_rate", gate_rate)
        if gate_rate < prev_gate_rate - 5:
            insights.append(
                "Gate pass rate declining \u2014 review recent prompt patterns"
            )

        # Healing events increasing
        healing_count = stats.get("healing_count", 0)
        prev_healing_count = stats.get("prev_healing_count", 0)
        if healing_count > prev_healing_count * 1.5 and healing_count > 3:
            insights.append(
                "More failures being auto-healed \u2014 investigate root cause"
            )

        # Recurring errors
        error_counts = stats.get("error_counts", {})
        for error, count in error_counts.items():
            if count >= 3:
                insights.append(
                    f"Recurring error: {error} ({count}x) \u2014 consider permanent fix"
                )

        if not insights:
            return "All systems performing within normal parameters."

        return " ".join(insights[:2])

    # ==================================================================
    # Private helpers
    # ==================================================================

    def _generate_daily_insights(self, agent_summaries: dict, skills: list,
                                  healing_events: list) -> list:
        """Generate insight lines for the daily brief."""
        insights = []

        # Find agents excelling or underperforming
        for agent, s in agent_summaries.items():
            if s["success_rate"] >= 95 and s["total"] >= 3:
                insights.append(
                    f"{agent} excelling ({s['success_rate']:.0f}% success rate)"
                )
            elif s["success_rate"] < 60 and s["total"] >= 3:
                insights.append(
                    f"{agent} underperforming ({s['success_rate']:.0f}% success) "
                    f"\u2014 recommend routing tasks to alternatives"
                )

        # Skill-based insights
        skills_by_agent = defaultdict(list)
        for sk in skills:
            skills_by_agent[sk["agent"]].append(sk)
        for agent, agent_skills in skills_by_agent.items():
            for sk in agent_skills:
                if sk["score"] < 0.4 and sk["sample_count"] >= 3:
                    insights.append(
                        f"{agent} struggling with {sk['category']} "
                        f"(score {sk['score']:.2f}) \u2014 route elsewhere"
                    )

        # Healing insights
        if len(healing_events) > 5:
            insights.append(
                f"High healing activity ({len(healing_events)} events) "
                f"\u2014 check for systemic issues"
            )

        return insights

    def _generate_weekly_goals(self, current_week: dict, agent_stats: dict,
                                skills: list, healing_events: list) -> list:
        """Generate goal suggestions for next week."""
        goals = []

        gate_rate = 0
        if current_week["gate_total"] > 0:
            gate_rate = current_week["gate_passes"] / current_week["gate_total"] * 100

        if gate_rate < 85:
            target = min(gate_rate + 10, 95)
            goals.append(f"Improve gate pass rate to {target:.0f}% (currently {gate_rate:.0f}%)")

        # Find weakest agent-skill combos
        skills_by_agent = defaultdict(list)
        for s in skills:
            skills_by_agent[s["agent"]].append(s)
        for agent, agent_skills in skills_by_agent.items():
            for sk in agent_skills:
                if sk["score"] < 0.5 and sk["sample_count"] >= 3:
                    goals.append(
                        f"Improve {agent} {sk['category']} score (currently {sk['score']:.2f})"
                    )

        # Healing-based goals
        healing_types = Counter(h["failure_type"] for h in healing_events)
        for ftype, count in healing_types.most_common(2):
            if count >= 3:
                goals.append(f"Reduce {ftype.replace('_', ' ')} failures (had {count} this week)")

        if not goals:
            goals.append("Maintain current performance levels")

        return goals

    def _generate_monthly_recommendations(self, agent_stats: dict, skills: list,
                                           healing_events: list, agg: dict) -> list:
        """Generate recommendations for next month."""
        recs = []

        total = agg.get("total", 0) or 0
        successes = agg.get("successes", 0) or 0
        success_rate = (successes / total * 100) if total > 0 else 0

        if success_rate < 80:
            recs.append(
                f"Overall success rate ({success_rate:.0f}%) needs improvement \u2014 "
                f"review agent routing and prompt quality"
            )

        # Cost optimization
        total_tokens = agg.get("total_tokens", 0) or 0
        if total_tokens > 500_000:
            recs.append(
                f"Token usage is high ({total_tokens:,}) \u2014 "
                f"consider caching or prompt optimization"
            )

        # Agent-specific recommendations
        for agent, stats in agent_stats.items():
            t = stats.get("total", 0) or 0
            s = stats.get("successes", 0) or 0
            rate = (s / t * 100) if t > 0 else 0
            if rate < 60 and t >= 5:
                recs.append(
                    f"Re-evaluate {agent} usage (only {rate:.0f}% success on {t} tasks)"
                )

        # Healing recommendations
        healing_types = Counter(h["failure_type"] for h in healing_events)
        for ftype, count in healing_types.most_common(2):
            if count >= 5:
                recs.append(
                    f"Address recurring {ftype.replace('_', ' ')} failures ({count} this month)"
                )

        if not recs:
            recs.append("System performing well \u2014 continue current strategy")

        return recs

    def _aggregate_rollups(self, rollups: list) -> dict[str, int | float]:
        """Aggregate a list of daily rollup rows into totals."""
        result: dict[str, int | float] = {
            "tasks_completed": 0,
            "tasks_failed": 0,
            "total_tokens": 0,
            "total_duration_ms": 0,
            "gate_passes": 0,
            "gate_total": 0,
            "avg_duration_ms": 0,
        }
        for r in rollups:
            result["tasks_completed"] += r.get("tasks_completed", 0) or 0
            result["tasks_failed"] += r.get("tasks_failed", 0) or 0
            result["total_tokens"] += r.get("total_tokens", 0) or 0
            result["total_duration_ms"] += r.get("total_duration_ms", 0) or 0
            result["gate_passes"] += r.get("gate_passes", 0) or 0
            result["gate_total"] += r.get("gate_total", 0) or 0

        total_tasks = result["tasks_completed"] + result["tasks_failed"]
        if total_tasks > 0:
            result["avg_duration_ms"] = float(result["total_duration_ms"]) / total_tasks
        return result

    # ==================================================================
    # Format helpers
    # ==================================================================

    @staticmethod
    def _trend_arrow(current: float, previous: float) -> str:
        """Return a trend arrow comparing current to previous value.

        Returns: up-arrow, down-arrow, or right-arrow for flat.
        """
        delta = current - previous
        if abs(delta) < 0.5:  # within 0.5 units = flat
            return "\u2192"
        return "\u2191" if delta > 0 else "\u2193"

    @staticmethod
    def _duration_human(ms: float) -> str:
        """Convert milliseconds to a human-readable duration string.

        Examples: "3.2min", "45s", "1.5hr"
        """
        if ms is None or ms == 0:
            return "0s"
        seconds = ms / 1000
        if seconds < 60:
            return f"{seconds:.0f}s"
        minutes = seconds / 60
        if minutes < 60:
            return f"{minutes:.1f}min"
        hours = minutes / 60
        return f"{hours:.1f}hr"

    @staticmethod
    def _cost_estimate(tokens: int) -> str:
        """Estimate cost from token count.

        Rough estimate: $0.005 per 1k tokens (blended input/output average).
        """
        if tokens is None or tokens == 0:
            return "$0.00"
        cost = tokens / 1000 * 0.005
        return f"${cost:.2f}"

    def _diff_string(self, current: int, previous: int) -> str:
        """Format a comparison string like 'up 16 from last week'."""
        arrow = self._trend_arrow(current, previous)
        diff = abs(current - previous)
        if diff == 0:
            return "same as last week"
        return f"{arrow}{diff} from last week"

    def _diff_string_duration(self, current_ms: float, previous_ms: float) -> str:
        """Format a duration comparison string."""
        arrow = self._trend_arrow(previous_ms, current_ms)  # inverted: lower is better
        diff = abs(current_ms - previous_ms)
        diff_str = self._duration_human(diff)
        if abs(current_ms - previous_ms) < 500:
            return "flat"
        direction = "faster" if current_ms < previous_ms else "slower"
        return f"{arrow}{diff_str} {direction}"
