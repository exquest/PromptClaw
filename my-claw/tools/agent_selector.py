"""Agent selector — rotates agents using fitness-based selection with alternation penalties."""

import json
import os
import random
import time
from pathlib import Path

try:
    from cypherclaw.pet_classes import CLASS_DEFINITIONS, get_dominant_class as _get_dominant_class
except ImportError:
    CLASS_DEFINITIONS = {}

    def _get_dominant_class(agent: str) -> tuple[str, int] | None:
        return None

PROVIDERS = {
    "claude": "anthropic",
    "codex": "openai",
    "gemini": "google",
    "ollama": "local",
    "qwen3.5:9b": "local",
    "qwen3.5:4b": "local",
    "qwen3.5:27b": "local",
    "gemma3:4b": "local",
    "llama3.2:3b": "local",
}

DEFAULT_AGENTS = ("claude", "codex", "gemini")

# Category detection keywords
CATEGORY_KEYWORDS = {
    "architecture": ["architect", "design", "plan", "spec", "structure", "system"],
    "coding": ["code", "implement", "build", "fix", "refactor", "write", "create", "add"],
    "review": ["review", "verify", "check", "audit", "examine"],
    "research": ["research", "search", "find", "investigate", "compare", "evaluate"],
    "testing": ["test", "pytest", "coverage", "spec", "validate"],
    "devops": ["deploy", "staging", "production", "server", "docker", "nginx"],
    "netops": ["netops", "network", "router", "switch", "firewall", "fortigate", "vlan", "bgp", "vpn"],
    "writing": ["write", "draft", "document", "compose", "report"],
    "routing": ["route", "decide", "classify", "determine"],
    "narrative_prose": [
        "narrative_prose",
        "story beat",
        "narrative beat",
        "glyphweave narrative",
        "prose calibration",
    ],
}

# Default fitness seeds per agent per category
DEFAULT_FITNESS = {
    "claude": {"architecture": 0.85, "review": 0.90, "coding": 0.70, "research": 0.75, "routing": 0.80, "writing": 0.80, "testing": 0.65, "devops": 0.60, "narrative_prose": 0.86},
    "codex": {"architecture": 0.55, "review": 0.60, "coding": 0.90, "research": 0.50, "routing": 0.50, "writing": 0.45, "testing": 0.85, "devops": 0.70, "narrative_prose": 0.72},
    "gemini": {"architecture": 0.60, "review": 0.55, "coding": 0.55, "research": 0.90, "routing": 0.60, "writing": 0.85, "testing": 0.50, "devops": 0.50, "narrative_prose": 0.84},
    "ollama": {
        "architecture": 0.65,
        "coding": 0.70,
        "review": 0.60,
        "research": 0.65,
        "routing": 0.70,
        "writing": 0.70,
        "testing": 0.65,
        "devops": 0.60,
        "netops": 0.80,
    },
    "qwen3.5:9b": {"narrative_prose": 0.78},
    "qwen3.5:4b": {"narrative_prose": 0.60},
    "qwen3.5:27b": {"narrative_prose": 0.88},
    "gemma3:4b": {"narrative_prose": 0.58},
    "llama3.2:3b": {"narrative_prose": 0.52},
}

# Dual-socket Ollama model-per-role routing.
# Maps task categories to specific models on NUMA-pinned ports.
# Socket 0 → port 11434, Socket 1 → port 11435.
# Override at runtime via OLLAMA_ROUTE_JSON env var (JSON string).
OLLAMA_ROUTE_DEFAULTS: dict[str, dict[str, object]] = {
    "coding":       {"model": "qwen3-coder:30b", "port": 11434},
    "review":       {"model": "qwen3.5:122b",    "port": 11435},
    "netops":       {"model": "qwen3:30b-a3b",   "port": 11435},
    "orchestrator": {"model": "qwen3:30b-a3b",   "port": 11434},
    "default":      {"model": "qwen3:30b-a3b",   "port": 11434},
}


def _load_ollama_routes() -> dict[str, dict[str, object]]:
    """Build the active route table from defaults + env override."""
    routes = {k: dict(v) for k, v in OLLAMA_ROUTE_DEFAULTS.items()}
    env_raw = os.environ.get("OLLAMA_ROUTE_JSON", "").strip()
    if env_raw:
        try:
            overrides = json.loads(env_raw)
            if isinstance(overrides, dict):
                for role, cfg in overrides.items():
                    if isinstance(cfg, dict) and "model" in cfg and "port" in cfg:
                        routes[role] = {"model": str(cfg["model"]), "port": int(cfg["port"])}
        except (json.JSONDecodeError, ValueError, TypeError):
            pass  # malformed env var — stick with defaults
    return routes


def get_ollama_route(category: str) -> dict[str, object]:
    """Return ``{"model": ..., "port": ...}`` for a task category.

    Falls back to the ``"default"`` route for unmapped categories.
    """
    routes = _load_ollama_routes()
    return dict(routes.get(category, routes["default"]))


ALTERNATION_PENALTY = 0.3
CROSS_PROVIDER_BONUS = 0.25
EXPLORATION_RATE = 0.10  # 10% random exploration
CLASS_BONUS_PER_LEVEL = 0.005
MAX_CLASS_BONUS = 0.10
HEADROOM_BONUS_MULTIPLIER = 0.10


def _class_categories(class_name: object) -> tuple[str, ...]:
    if class_name is None:
        return ()

    normalized_name = str(class_name).strip()
    if not normalized_name:
        return ()

    definition = CLASS_DEFINITIONS.get(normalized_name)
    if definition is None:
        definition = next(
            (
                candidate_definition
                for candidate_name, candidate_definition in CLASS_DEFINITIONS.items()
                if candidate_name.casefold() == normalized_name.casefold()
            ),
            None,
        )

    categories = definition.get("categories", ()) if definition else ()
    return tuple(str(category).casefold() for category in categories)


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
        if lower in CATEGORY_KEYWORDS:
            return lower
        for category, keywords in CATEGORY_KEYWORDS.items():
            if any(kw in lower for kw in keywords):
                return category
        return "coding"  # default

    def get_fitness(self, agent: str, category: str) -> float:
        """Get fitness score for agent+category from Observatory or defaults."""
        # Try Observatory first
        if self.observatory:
            try:
                skills_list = self.observatory.get_agent_skills(agent)
                skills = {s['category']: s['score'] for s in skills_list}
                if skills and category in skills:
                    return skills[category]
            except Exception:
                pass
        # Fall back to defaults
        return DEFAULT_FITNESS.get(agent, {}).get(category, 0.5)

    def get_dominant_class(self, agent: str) -> tuple[str, int] | None:
        """Get an agent's dominant pet class, if pet-class data is available."""
        try:
            return _get_dominant_class(agent)
        except Exception:
            return None

    def get_class_bonus(self, agent: str, category: str) -> float:
        """Return the capped selector bonus for a matching dominant class."""
        dominant = self.get_dominant_class(agent)
        if not dominant:
            return 0.0

        class_name, level = dominant
        if str(category).strip().casefold() not in _class_categories(class_name):
            return 0.0

        return min(MAX_CLASS_BONUS, max(level, 0) * CLASS_BONUS_PER_LEVEL)

    def _record_class_bonus_influence(
        self,
        task_desc: str,
        category: str,
        baseline_agent: str,
        chosen_agent: str,
        base_scores: dict[str, float],
        bonuses: dict[str, float],
        final_scores: dict[str, float],
    ) -> None:
        if not self.observatory:
            return

        dominant = self.get_dominant_class(chosen_agent)
        class_name, class_level = dominant if dominant else (None, None)
        try:
            self.observatory.record(
                "agent_selector_class_bonus",
                {
                    "task_desc": task_desc,
                    "category": category,
                    "baseline_agent": baseline_agent,
                    "baseline_score": base_scores[baseline_agent],
                    "chosen_agent": chosen_agent,
                    "chosen_base_score": base_scores[chosen_agent],
                    "chosen_bonus": bonuses[chosen_agent],
                    "chosen_score": final_scores[chosen_agent],
                    "class_name": class_name,
                    "class_level": class_level,
                    "flipped_winner": chosen_agent != baseline_agent,
                },
            )
        except Exception:
            pass

    def _record_exploration_roll(
        self,
        task_desc: str,
        category: str,
        chosen_agent: str,
    ) -> None:
        if not self.observatory:
            return
        try:
            self.observatory.record(
                "agent_selector_exploration",
                {
                    "task_desc": task_desc,
                    "category": category,
                    "chosen_agent": chosen_agent,
                    "class_bonus_disabled": True,
                },
            )
        except Exception:
            pass

    def _eligible_agents(
        self,
        available_agents: list[str] | tuple[str, ...] | None = None,
        disabled_agents: set[str] | None = None,
    ) -> list[str]:
        agents = list(available_agents) if available_agents is not None else list(DEFAULT_AGENTS)
        disabled = set(disabled_agents or ())
        filtered = [agent for agent in agents if agent not in disabled]
        if not filtered:
            return []
        if not self.quota_monitor:
            return filtered
        try:
            quota_filtered = self.quota_monitor.get_available_agents(filtered)
        except Exception:
            return filtered
        available = [agent for agent in quota_filtered if agent in filtered]
        if available:
            return available
        return [] if not quota_filtered else filtered

    def _headroom_bonus(self, agent: str) -> float:
        if not self.quota_monitor:
            return 0.0
        try:
            return float(self.quota_monitor.get_agent_headroom(agent)) * HEADROOM_BONUS_MULTIPLIER
        except Exception:
            return 0.0

    def select(
        self,
        task_desc: str,
        available_agents: list[str] | tuple[str, ...] | None = None,
        disabled_agents: set[str] | None = None,
    ) -> str:
        """Select the best agent for this task."""
        agents = self._eligible_agents(available_agents, disabled_agents)
        if not agents:
            raise ValueError("no agents available for selection")
        category = self.detect_category(task_desc)

        # Compute baseline scores before any pet-class bonus is applied.
        base_scores = {}
        for agent in agents:
            fitness = self.get_fitness(agent, category)
            score = fitness

            # Alternation penalty — discourage using same provider twice
            if self._last_lead_provider and PROVIDERS.get(agent) == self._last_lead_provider:
                score -= ALTERNATION_PENALTY

            # Cross-provider bonus
            if self._last_lead_provider and PROVIDERS.get(agent) != self._last_lead_provider:
                score += CROSS_PROVIDER_BONUS

            score += self._headroom_bonus(agent)
            base_scores[agent] = score

        # Exploration — 10% chance of random pick (class bonus disabled)
        if random.random() < EXPLORATION_RATE:
            chosen = random.choice(agents)
            self._record_exploration_roll(task_desc, category, chosen)
        else:
            bonuses = {agent: self.get_class_bonus(agent, category) for agent in agents}
            scores = {
                agent: base_scores[agent] + bonuses[agent]
                for agent in agents
            }
            baseline_agent = max(base_scores, key=base_scores.get)
            chosen = max(scores, key=scores.get)
            if any(b > 0.0 for b in bonuses.values()):
                self._record_class_bonus_influence(
                    task_desc=task_desc,
                    category=category,
                    baseline_agent=baseline_agent,
                    chosen_agent=chosen,
                    base_scores=base_scores,
                    bonuses=bonuses,
                    final_scores=scores,
                )

        # Update state
        self._last_lead = chosen
        self._last_lead_provider = PROVIDERS.get(chosen)
        self._task_count += 1
        self._save_state()

        return chosen

    def select_pair(self, task_desc: str) -> tuple[str, str]:
        """Select lead + verify agents (different providers preferred)."""
        lead = self.select(task_desc)
        agents = self._eligible_agents()
        others = [agent for agent in agents if agent != lead]
        if not others:
            return lead, lead
        verify_scores = {a: self.get_fitness(a, "review") for a in others}
        verify = max(verify_scores, key=verify_scores.get)
        return lead, verify

    def record_outcome(self, agent: str, task_desc: str, success: bool):
        """Record task outcome to improve future selections."""
        if self.observatory:
            category = self.detect_category(task_desc)
            try:
                self.observatory.record_task_result(
                    agent=agent,
                    task_id=f"{agent}_{int(time.time())}",
                    success=success,
                    duration_ms=0,
                    tokens=0,
                    gate_pass=False,
                    category=category,
                    model=agent,
                )
            except Exception:
                pass

    def status_summary(self) -> str:
        """Return a Telegram-friendly status of agent fitness."""
        lines = ["\U0001f3af Agent Fitness\n"]
        for agent in DEFAULT_AGENTS:
            icon = {"claude": "\U0001f7e3", "codex": "\U0001f7e2", "gemini": "\U0001f535"}[agent]
            top_categories = []
            for cat in ("coding", "architecture", "review", "research", "writing"):
                score = self.get_fitness(agent, cat)
                top_categories.append(f"{cat}:{score:.0%}")
            cats_str = " | ".join(top_categories)
            last_marker = " \u25c0" if agent == self._last_lead else ""
            lines.append(f"{icon} {agent}{last_marker}\n  {cats_str}")
        if self.quota_monitor:
            lines.append("\nQuota:")
            try:
                provider_status = self.quota_monitor.get_provider_status()
            except Exception:
                provider_status = {}
            for provider in sorted(provider_status):
                info = provider_status[provider]
                status = str(info.get("status", "unknown"))
                headroom = float(info.get("headroom", 0.0))
                lines.append(f"  {provider}: {status} ({headroom:.0%})")
        lines.append(f"\nRotation: {self._task_count} tasks, last lead: {self._last_lead or 'none'}")
        return "\n".join(lines)
