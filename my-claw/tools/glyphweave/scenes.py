"""GlyphWeave scene library for the CypherClaw Telegram daemon.

Provides the CypherClawArt class that builds all visual output
for the CypherClaw Telegram bot.  Output is plain text sent to
Telegram and must stay under 4 000 characters.

Style Guide: docs/STYLE_GUIDE.md
- ASCII art ONLY inside ``` code blocks
- No box-drawing characters outside code blocks
- Emoji bullets for menus, never boxes
- Agent icons: 🟣 claude, 🟢 codex, 🔵 gemini, 🦀 cypherclaw
"""

from __future__ import annotations

import random
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tamagotchi import Pet


# ── agent color icons ────────────────────────────────────────
_AGENT_ICONS: dict[str, str] = {
    "claude":     "🟣",
    "codex":      "🟢",
    "gemini":     "🔵",
    "cypherclaw": "🦀",
}

# ── plan-step type icons ─────────────────────────────────────
_STEP_ICONS: dict[str, str] = {
    "agent":      "🤖",
    "shell":      "⚙️",
    "parallel":   "🔀",
    "background": "📋",
    "reply":      "💬",
    "schedule":   "🕐",
    "confirm":    "⚠️",
}

_PET_ORDER = ("claude", "codex", "gemini", "cypherclaw")

_PET_STATE_EMOJI: dict[str, str] = {
    "idle":           "💤",
    "thinking":       "🧠",
    "success":        "✨",
    "error":          "💢",
    "sleeping":       "🌙",
    "communicating":  "🔀",
    "hungry":         "🍖",
}

_DEFAULT_CRAB = (
    " /\\_/\\\n"
    "( o.o )\n"
    " > ^ <"
)


def _bar(value: int, width: int = 10, max_value: int = 100) -> str:
    """Simple block bar: ▓ filled, ░ empty."""
    clamped = max(0, min(max_value, int(value)))
    filled = round((clamped / max_value) * width) if max_value else 0
    return ("▓" * filled) + ("░" * (width - filled))


def _mood_face(mood: int) -> str:
    if mood >= 70:
        return "😊"
    if mood >= 30:
        return "😐"
    return "😢"


def _xp_progress(xp: int, stage: int) -> tuple[int, int | None]:
    from tamagotchi import STAGE_THRESHOLDS
    current_floor = STAGE_THRESHOLDS.get(stage, 0)
    next_floor = STAGE_THRESHOLDS.get(stage + 1)
    return xp - current_floor, None if next_floor is None else next_floor - current_floor


class CypherClawArt:
    """All visual scenes for CypherClaw Telegram output.

    Every public method returns a str ready for bot.send_message().
    All ASCII art is wrapped in ``` code blocks.
    No box-drawing characters appear outside code blocks.
    """

    # ── 1. startup_banner ────────────────────────────────────
    def startup_banner(self, pets: dict[str, "Pet"] | None = None) -> str:
        pet_lineup = ""
        if pets:
            from tamagotchi import STAGE_NAMES
            lines = []
            for agent in _PET_ORDER:
                if agent in pets:
                    pet = pets[agent]
                    icon = _AGENT_ICONS.get(agent, "⚪")
                    state = pet.effective_state()
                    emoji = _PET_STATE_EMOJI.get(state, "❔")
                    lines.append(f"  {icon} {agent} {STAGE_NAMES[pet.stage]} {emoji}")
            if lines:
                pet_lineup = "\n🐾 Pets:\n" + "\n".join(lines) + "\n"

            claw_pet = pets.get("cypherclaw")
            if claw_pet:
                portrait = claw_pet.get_portrait()
                return (
                    f"```\n{portrait}\n```\n"
                    "🦀 Systems online | 🧠 Memory loaded\n"
                    "🤖 Agents ready | 📡 Listening...\n"
                    f"{pet_lineup}"
                )

        return (
            "```\n"
            " /\\_/\\\n"
            "( o.o )  CypherClaw v2\n"
            " > ^ <\n"
            "```\n"
            "🦀 Systems online | 🧠 Memory loaded\n"
            "🤖 Agents ready | 📡 Listening..."
        )

    # ── 2. shutdown_banner ───────────────────────────────────
    def shutdown_banner(self) -> str:
        return (
            "```\n"
            " /\\_/\\\n"
            "( -.- )  going offline\n"
            " > ^ <\n"
            "```\n"
            "💤 Saving state...\n"
            "🔒 Connections closed\n"
            "👋 See you soon!"
        )

    # ── 3. help_menu ─────────────────────────────────────────
    def help_menu(self, commands: dict[str, str]) -> str:
        """Emoji-bullet help menu. No box-drawing characters."""
        # Map commands to emoji categories
        cmd_icons: dict[str, str] = {
            "/status":    "📋",
            "/tasks":     "📋",
            "/schedules": "🕐",
            "/workspace": "📁",
            "/art":       "🎨",
            "/pets":      "🐾",
            "/feed":      "🍖",
            "/play":      "✨",
            "/stats":     "📊",
            "/retro":     "📋",
            "/brief":     "📊",
            "/research":  "🔬",
            "/help":      "🦀",
        }

        lines = ["🦀 CypherClaw Commands\n"]
        for cmd, desc in commands.items():
            icon = cmd_icons.get(cmd, "▸")
            lines.append(f"{icon} {cmd}  →  {desc}")

        lines.append("")
        lines.append("⚡ Shortcuts:")
        lines.append("ping, status, $ <cmd>")
        lines.append("@claude, @codex, @gemini")

        return "\n".join(lines)

    # ── 4. status_display ────────────────────────────────────
    def status_display(
        self,
        memory: int,
        tasks: int,
        schedules: int,
        artifacts: int,
        pets: dict[str, "Pet"] | None = None,
    ) -> str:
        # Pet portrait or default crab
        if pets and "cypherclaw" in pets:
            portrait = pets["cypherclaw"].get_portrait()
        else:
            portrait = f"{_DEFAULT_CRAB}"

        header = f"```\n{portrait}\n```\n"
        vitals = f"🧠 {memory} msgs | 📋 {tasks} tasks | 🕐 {schedules} sched | 📁 {artifacts} files"

        pet_section = ""
        if pets:
            pet_lines = []
            for agent in _PET_ORDER:
                if agent in pets:
                    pet_lines.append(pets[agent].status_line())
            if pet_lines:
                pet_section = "\n\n🐾 Pets:\n" + "\n".join(pet_lines)

        return f"{header}{vitals}{pet_section}"

    # ── 5. greeting ──────────────────────────────────────────
    def greeting(self, pet_portrait: str | None = None) -> str:
        taglines = [
            "🦀 Hey! What are we building?",
            "✨ Ready to pounce on tasks",
            "🦀 Claws sharpened, let's go!",
            "✨ Systems purring nicely",
            "🦀 All agents standing by",
        ]
        tag = random.choice(taglines)

        if pet_portrait:
            return f"```\n{pet_portrait}\n```\n{tag}"

        faces = [
            "( ^.^ )",
            "( o.o )",
            "( =^.^= )",
            "( ^.^ )",
            "( o.o )",
        ]
        face = random.choice(faces)
        return (
            "```\n"
            " /\\_/\\\n"
            f"{face}\n"
            " > ^ <\n"
            "```\n"
            f"{tag}"
        )

    # ── 6. plan_preview ──────────────────────────────────────
    def plan_preview(self, steps: list[dict]) -> str:
        """Numbered list with step-type icons. No box-drawing."""
        lines = ["📜 Plan Preview\n"]
        for i, step in enumerate(steps, 1):
            step_type = step.get("type", "agent")
            label = step.get("label", step.get("name", "step"))
            icon = _STEP_ICONS.get(step_type, "🤖")
            lines.append(f"{i}. {icon} {label}")
        return "\n".join(lines)

    # ── 7. step_progress ─────────────────────────────────────
    def step_progress(self, current: int, total: int, label: str) -> str:
        bar_width = min(total, 10)
        filled_count = round(current / total * bar_width) if total > 0 else 0
        bar = "\u2593" * filled_count + "\u2591" * (bar_width - filled_count)
        pct = round(current / total * 100) if total > 0 else 0
        return (
            f"\U0001f6e0\ufe0f Step {current}/{total} [{bar}] {pct}%\n"
            f"\u25b6 {label}"
        )

    # ── 8. task_complete ─────────────────────────────────────
    def task_complete(self, agent: str, label: str, pet_portrait: str | None = None) -> str:
        icon = _AGENT_ICONS.get(agent.lower(), "⚪")
        portrait_block = f"```\n{pet_portrait}\n```\n" if pet_portrait else ""
        return (
            f"{portrait_block}"
            f"✅ {icon} {agent} → {label}"
        )

    # ── 9. task_failed ───────────────────────────────────────
    def task_failed(self, agent: str, error: str, pet_portrait: str | None = None) -> str:
        icon = _AGENT_ICONS.get(agent.lower(), "⚪")
        portrait_block = f"```\n{pet_portrait}\n```\n" if pet_portrait else ""
        return (
            f"{portrait_block}"
            f"❌ {icon} {agent} failed: {error}"
        )

    # ── 10. parallel_progress ────────────────────────────────
    def parallel_progress(self, agents: list[str], done: int) -> str:
        icons = [_AGENT_ICONS.get(a.lower(), "⚪") for a in agents]
        header = "🔀 Parallel: " + " + ".join(
            f"{icons[i]} {agents[i]}" for i in range(len(agents))
        )
        lines = [header, ""]
        for i, agent in enumerate(agents):
            status = "✅" if i < done else "→"
            lines.append(f"{status} {agent}: working...")
        lines.append(f"\n{done}/{len(agents)} complete")
        return "\n".join(lines)

    # ── 11. confirmation_prompt ──────────────────────────────
    def confirmation_prompt(self, text: str) -> str:
        return (
            "⚠️ Confirmation needed:\n"
            f"\n{text}\n"
            "\nReply ✅ yes or ❌ no"
        )

    # ── 12. select_theme ─────────────────────────────────────
    def select_theme(self, task_desc: str) -> str:
        desc = task_desc.lower()
        water_keys = {"health", "check", "ping", "deploy", "sync"}
        space_keys = {"search", "research", "find", "read"}
        dragon_keys = {"test", "build", "compile"}

        for kw in water_keys:
            if kw in desc:
                return "water"
        for kw in space_keys:
            if kw in desc:
                return "space"
        for kw in dragon_keys:
            if kw in desc:
                return "dragon"
        return "cute"

    # ── 13. processing_indicator ─────────────────────────────
    def processing_indicator(self, pet_portrait: str | None = None) -> str:
        if pet_portrait:
            return (
                f"```\n{pet_portrait}\n```\n"
                "🧠 analyzing your request..."
            )
        return (
            "```\n"
            " /\\_/\\\n"
            "( o.o )  thinking...\n"
            " > ^ <\n"
            "```\n"
            "🧠 analyzing your request..."
        )

    # ── 14. pet_xp_summary ───────────────────────────────────
    @staticmethod
    def pet_xp_summary(pets: dict[str, "Pet"]) -> str:
        """Compact pet XP section for /brief and /retro."""
        from tamagotchi import STAGE_NAMES

        lines = ["🐾 Pet Status"]
        for agent in _PET_ORDER:
            if agent not in pets:
                continue
            pet = pets[agent]
            icon = _AGENT_ICONS.get(agent, "⚪")
            state = pet.effective_state()
            emoji = _PET_STATE_EMOJI.get(state, "❔")
            mood_face = _mood_face(pet.mood)
            lines.append(
                f"  {icon} {agent} · {STAGE_NAMES[pet.stage]} · "
                f"XP {pet.xp} · {mood_face}{pet.mood} {emoji}"
            )
        return "\n".join(lines)

    # ── 15. pet_status_display ───────────────────────────────
    @staticmethod
    def pet_status_display(pets: dict[str, "Pet"]) -> str:
        """Render all pets vertically -- Telegram-safe, no side-by-side."""
        from glyphweave.pet_sprites import get_portrait

        stage_names = {0: "Egg", 1: "Baby", 2: "Teen", 3: "Adult", 4: "Elite", 5: "Master"}
        thresholds = {1: 50, 2: 200, 3: 500, 4: 1000, 5: 9999}
        state_emoji = {
            "idle": "💤", "thinking": "🧠", "success": "✨", "error": "💢",
            "sleeping": "🌙", "communicating": "🔀", "hungry": "🍖",
        }

        lines = ["🐾 PET STATUS 🐾\n"]

        for agent in ("claude", "codex", "gemini", "cypherclaw"):
            pet = pets.get(agent)
            if pet is None:
                continue

            icon = _AGENT_ICONS.get(agent, "⚪")
            stage = stage_names.get(pet.stage, "?")
            state = state_emoji.get(pet.effective_state(), "❔")

            # XP bar and target
            if pet.stage < 5:
                xp_target = thresholds.get(pet.stage, 999)
                pct = min(10, int(10 * pet.xp / xp_target)) if xp_target > 0 else 10
                xp_label = f"{pet.xp}/{xp_target}"
            else:
                pct = 10
                xp_label = f"{pet.xp}/MAX"

            bar = "▓" * pct + "░" * (10 - pct)

            # Pet portrait in code block
            portrait = get_portrait(agent, pet.stage)

            lines.append(f"{icon} {agent.upper()} — {stage} {state}")
            lines.append(f"```\n{portrait}\n```")
            lines.append(f"XP [{bar}] {xp_label}")
            lines.append(
                f"😊 {pet.mood}  🍖 {pet.hunger}  ⚡ {pet.energy}"
                f"  ✓{pet.tasks_completed} ✗{pet.tasks_failed}"
            )
            lines.append("")

        return "\n".join(lines)

    # ── 16. pet_interaction_scene ────────────────────────────
    @staticmethod
    def pet_interaction_scene(agents: list[str], pets: dict[str, "Pet"]) -> str:
        """Render a collaboration scene for two or more pets -- vertical layout."""
        from tamagotchi import STAGE_NAMES

        active_agents = [agent for agent in agents if agent in pets]
        if not active_agents:
            return "No pet interaction available."
        if len(active_agents) == 1:
            pet = pets[active_agents[0]]
            icon = _AGENT_ICONS.get(active_agents[0], "⚪")
            return f"{icon} {active_agents[0]}\n```\n{pet.get_portrait()}\n```"

        lines = ["🔀 Agent Sync\n"]
        for agent in active_agents:
            pet = pets[agent]
            icon = _AGENT_ICONS.get(agent, "⚪")
            lines.append(f"{icon} {agent} · {STAGE_NAMES[pet.stage]}")
            lines.append(f"```\n{pet.get_portrait()}\n```")

        return "\n".join(lines)
