"""Agent selector — rotates agents using fitness-based selection with alternation penalties."""

import random
import json
from pathlib import Path


PROVIDERS = {
    "claude": "anthropic",
    "codex": "openai",
    "gemini": "google",
}

# Category detection keywords
CATEGORY_KEYWORDS = {
    "architecture": ["architect", "design", "plan", "spec", "structure", "system"],
    "coding": ["code", "implement", "build", "fix", "refactor", "write", "create", "add"],
    "review": ["review", "verify", "check", "audit", "examine"],
    "research": ["research", "search", "find", "investigate", "compare", "evaluate"],
    "testing": ["test", "pytest", "coverage", "spec", "validate"],
    "devops": ["deploy", "staging", "production", "server", "docker", "nginx"],
    "writing": ["write", "draft", "document", "compose", "report"],
    "routing": ["route", "decide", "classify", "determine"],
}

# Default fitness seeds per agent per category
DEFAULT_FITNESS = {
    "claude": {"architecture": 0.85, "review": 0.90, "coding": 0.70, "research": 0.75, "routing": 0.80, "writing": 0.80, "testing": 0.65, "devops": 0.60},
    "codex": {"architecture": 0.55, "review": 0.60, "coding": 0.90, "research": 0.50, "routing": 0.50, "writing": 0.45, "testing": 0.85, "devops": 0.70},
    "gemini": {"architecture": 0.60, "review": 0.55, "coding": 0.55, "research": 0.90, "routing": 0.60, "writing": 0.85, "testing": 0.50, "devops": 0.50},
}

ALTERNATION_PENALTY = 0.3
CROSS_PROVIDER_BONUS = 0.1
EXPLORATION_RATE = 0.10  # 10% random exploration
HEADROOM_BONUS_MAX = 0.15


class AgentSelector:
    """Selects the best agent for a task based on fitness scores + rotation."""

    def __init__(self, observatory=None, quota_monitor=None, state_file: str | Path = ""):
        self.observatory = observatory
        self.quota_monitor = quota_monitor
        self._state_file = Path(state_file) if state_file else None
        self._last_lead = None
        self._last_lead_provider = None
        self._task_count = 0
        self._load_state()

    def _load_state(self):
        if self._state_file and self._state_file.exists():
            try:
                data = json.loads(self._state_file.read_text())
                self._last_lead = data.get("last_lead")
                self._last_lead_provider = data.get("last_lead_provider")
                self._task_count = data.get("task_count", 0)
            except Exception:
                pass

    def _save_state(self):
        if self._state_file:
            try:
                self._state_file.parent.mkdir(parents=True, exist_ok=True)
                self._state_file.write_text(json.dumps({
                    "last_lead": self._last_lead,
                    "last_lead_provider": self._last_lead_provider,
                    "task_count": self._task_count,
                }))
            except Exception:
                pass

    def detect_category(self, task_desc: str) -> str:
        lower = task_desc.lower()
        for category, keywords in CATEGORY_KEYWORDS.items():
            if any(kw in lower for kw in keywords):
                return category
        return "coding"  # default

    def get_fitness(self, agent: str, category: str) -> float:
        """Get fitness score for agent+category from Observatory or defaults."""
        # Try Observatory first
        if self.observatory:
            try:
                skills = self.observatory.get_agent_skills(agent)
                if isinstance(skills, dict) and category in skills:
                    return float(skills[category])
                if isinstance(skills, list):
                    for row in skills:
                        if isinstance(row, dict) and row.get("category") == category:
                            return float(row.get("score", 0.5))
            except Exception:
                pass
        # Fall back to defaults
        return DEFAULT_FITNESS.get(agent, {}).get(category, 0.5)

    def _resolve_agents(
        self,
        available_agents: list[str] | tuple[str, ...] | None,
        disabled_agents: set[str] | None = None,
    ) -> list[str]:
        agents = list(available_agents or ["claude", "codex", "gemini"])
        disabled = set(disabled_agents or ())
        filtered = [agent for agent in agents if agent not in disabled]
        if not filtered:
            filtered = agents
        if self.quota_monitor:
            try:
                filtered = self.quota_monitor.get_available_agents(filtered)
            except Exception:
                pass
        return filtered or agents

    def _headroom_bonus(self, agent: str) -> float:
        if not self.quota_monitor:
            return 0.0
        try:
            headroom = float(self.quota_monitor.get_agent_headroom(agent))
        except Exception:
            return 0.0
        return max(0.0, min(1.0, headroom)) * HEADROOM_BONUS_MAX

    def select(
        self,
        task_desc: str,
        available_agents: list[str] | tuple[str, ...] | None = None,
        disabled_agents: set[str] | None = None,
    ) -> str:
        """Select the best agent for this task."""
        agents = self._resolve_agents(available_agents, disabled_agents)
        category = self.detect_category(task_desc)

        # Compute scores
        scores = {}
        for agent in agents:
            fitness = self.get_fitness(agent, category)
            score = fitness + self._headroom_bonus(agent)

            # Alternation penalty — discourage using same provider twice
            if self._last_lead_provider and PROVIDERS.get(agent) == self._last_lead_provider:
                score -= ALTERNATION_PENALTY

            # Cross-provider bonus
            if self._last_lead_provider and PROVIDERS.get(agent) != self._last_lead_provider:
                score += CROSS_PROVIDER_BONUS

            scores[agent] = score

        # Exploration — 10% chance of random pick
        if random.random() < EXPLORATION_RATE:
            chosen = random.choice(agents)
        else:
            chosen = max(scores, key=scores.get)

        # Update state
        self._last_lead = chosen
        self._last_lead_provider = PROVIDERS.get(chosen)
        self._task_count += 1
        self._save_state()

        return chosen

    def select_pair(
        self,
        task_desc: str,
        available_agents: list[str] | tuple[str, ...] | None = None,
        disabled_agents: set[str] | None = None,
    ) -> tuple[str, str]:
        """Select lead + verify agents (different providers preferred)."""
        agents = self._resolve_agents(available_agents, disabled_agents)
        if len(agents) == 1:
            return agents[0], agents[0]

        lead = self.select(task_desc, available_agents=agents)
        # Pick a different agent for verify
        others = [a for a in agents if a != lead]
        if not others:
            return lead, lead
        verify_scores = {a: self.get_fitness(a, "review") + self._headroom_bonus(a) for a in others}
        verify = max(verify_scores, key=verify_scores.get)
        return lead, verify

    def record_outcome(self, agent: str, task_desc: str, success: bool):
        """Record task outcome to improve future selections."""
        if self.observatory:
            category = self.detect_category(task_desc)
            try:
                self.observatory.update_agent_skill(agent, category, success)
            except Exception:
                pass

    def status_summary(self) -> str:
        """Return a Telegram-friendly status of agent fitness."""
        lines = ["\U0001f3af Agent Fitness\n"]
        quota_status = self.quota_monitor.get_provider_status() if self.quota_monitor else {}
        for agent in ("claude", "codex", "gemini"):
            provider = PROVIDERS[agent]
            icon = {"claude": "\U0001f7e3", "codex": "\U0001f7e2", "gemini": "\U0001f535"}[agent]
            top_categories = []
            for cat in ("coding", "architecture", "review", "research", "writing"):
                score = self.get_fitness(agent, cat)
                top_categories.append(f"{cat}:{score:.0%}")
            cats_str = " | ".join(top_categories)
            quota_info = quota_status.get(provider, {})
            quota_str = ""
            if quota_info:
                quota_str = f" | quota:{quota_info.get('status', 'unknown')} {float(quota_info.get('headroom', 0.0)):.0%}"
            last_marker = " \u25c0" if agent == self._last_lead else ""
            lines.append(f"{icon} {agent}{last_marker}\n  {cats_str}{quota_str}")
        lines.append(f"\nRotation: {self._task_count} tasks, last lead: {self._last_lead or 'none'}")
        return "\n".join(lines)
