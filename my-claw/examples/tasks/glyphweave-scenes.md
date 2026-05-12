Create the GlyphWeave scene library for the CypherClaw Telegram daemon.

File to create: /Users/anthony/Programming/PromptClaw/my-claw/tools/glyphweave/scenes.py

This file provides a `CypherClawArt` class that builds all visual output for the CypherClaw Telegram bot using the Canvas DSL from /Users/anthony/Programming/PromptClaw/my-claw/tools/glyphweave/dsl.py.

The Canvas DSL provides:
- `Canvas(width, height)` — fixed-size character grid
- `canvas.place_text(x, y, text)` — place text at position
- `canvas.place_emoji(x, y, emoji)` — place emoji (2-cell wide aware)
- `canvas.place(x, y, char)` — place single char
- `canvas.fill_row(y, char)` — fill entire row
- `canvas.to_string()` — render to plain text
- Palettes: PALETTE_WATER, PALETTE_SPACE, PALETTE_CUTE, PALETTE_DRAGON, PALETTE_NIGHT, PALETTE_UI

Requirements for CypherClawArt class:

1. `startup_banner() -> str` — Cat face ASCII art + "CypherClaw v2 🦀" + system status lines. Use the crab emoji. Example output:
```
 /\_/\
( o.o )  CypherClaw v2 🦀
 > ^ <   ═══════════════

⚡ Systems online
🧠 Memory loaded
🤖 Agents standing by
📡 Listening...
```

2. `shutdown_banner() -> str` — Cat with closed eyes + "going offline" message.

3. `help_menu(commands: dict[str, str]) -> str` — Box-drawn help menu with commands listed. Use ╔═╗║╚═╝ box chars. Include shortcut section.

4. `status_display(memory: int, tasks: int, schedules: int, artifacts: int) -> str` — Cat face + metrics table with ━ rules and │ separators.

5. `greeting() -> str` — Random selection from 5+ themed greetings. Mix cat faces, crab emoji, sparkles. Each should be 3-5 lines max.

6. `plan_preview(steps: list[dict]) -> str` — Bordered step list. Each step shows an icon based on type: 🤖 agent, ⚙️ shell, 🔀 parallel, 📋 background, 💬 reply, 🕐 schedule, ⚠️ confirm. Use ┌─┐ and └─┘ borders.

7. `step_progress(current: int, total: int, label: str) -> str` — Progress indicator with filled/empty dots: ● for done, ○ for pending. Include cat face and step label.

8. `task_complete(agent: str, label: str) -> str` — Completion display with agent color icon (🟣 claude, 🟢 codex, 🔵 gemini) and checkmark.

9. `task_failed(agent: str, error: str) -> str` — Error display with ❌ and error text.

10. `parallel_progress(agents: list[str], done: int) -> str` — Shows agents running with filled/empty dots.

11. `confirmation_prompt(text: str) -> str` — Warning-styled confirmation with ⚠️ border.

12. `select_theme(task_desc: str) -> str` — Map task keywords to themes:
    - "health/check/ping/deploy/sync" → "water"
    - "search/research/find/read" → "space"
    - "test/build/compile" → "dragon"
    - default → "cute"

13. `processing_indicator() -> str` — Simple "thinking" indicator with cat face.

All methods must produce output under 4000 characters (Telegram limit).
Use `import random` for greeting variety.
Keep emoji sparse (max 5 per scene).
Canvas width should generally be 24-28 chars for Telegram readability.
