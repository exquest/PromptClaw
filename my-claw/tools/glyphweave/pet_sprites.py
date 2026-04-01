"""ASCII and emoji pet sprites for CypherClaw's Tamagotchi system."""

from __future__ import annotations

from typing import Final

AGENTS: Final[tuple[str, ...]] = ("claude", "codex", "gemini", "cypherclaw")
STATES: Final[tuple[str, ...]] = (
    "idle",
    "thinking",
    "success",
    "error",
    "sleeping",
    "communicating",
    "hungry",
)

_PORTRAITS: Final[dict[str, dict[int, tuple[str, ...]]]] = {
    "claude": {
        0: (
            "   .--.   ",
            "  / 🟣 \\  ",
            "  \\____/  ",
        ),
        1: (
            "╭────────╮",
            "│ (◉ᴥ◉) │",
            "╰────────╯",
        ),
        2: (
            "  ~╔══════╗~",
            " ╔═╝(◉ᴥ◉)╚═╗",
            " ║   ║║   ║",
            " ║   ╚╝   ║",
            " ~╚══════╝~",
        ),
        3: (
            "    🎓",
            "  ╭──────╮",
            "╭─│(◉ᴥ◉)│─╮",
            "│ │ ╱📖╲ │ │",
            "│ │ ╲__╱ │ │",
            "╰─│  ╱╲  │─╯",
            "  ╰──────╯",
        ),
        4: (
            " ✨   🎓   ✨",
            "  ╭────────╮",
            "╭─│ (⊚ᴥ⊚) │─╮",
            "│ │  ╭──╮  │ │",
            "│ │  📖📜  │ │",
            "│ │  ╰──╯  │ │",
            "│ ✦   ╱╲   ✦ │",
            "╰───╮    ╭───╯",
            "   ☆      ☆",
        ),
        5: (
            " ✨   🎓   ✨",
            "   ☆ ╭────╮ ☆",
            " ╭───│(⊚ᴥ⊚)│───╮",
            " │   │╭📜╮│   │",
            " │   │📖📖│   │",
            " │   │╰📜╯│   │",
            " ╰─╮ │ ╱╲ │ ╭─╯",
            "   ╰─┴────┴─╯",
            "    ☆    ☆",
        ),
    },
    "codex": {
        0: (
            "   .--.   ",
            "  / 🟢 \\  ",
            "  \\____/  ",
        ),
        1: (
            "┌───────┐",
            "│ [□_□] │",
            "└───────┘",
        ),
        2: (
            "   ╤",
            "┌─[□_□]─┐",
            "│ ╟─⚙─╢ │",
            "└─┬───┬─┘",
            "  ╵   ╵",
        ),
        3: (
            "   ╤",
            " ╔[□_□]╗",
            "┌╣ ▓░▓ ╠┐",
            "│┤┌─┼─┐├│",
            "││ │ │ ││",
            "└┬┘   └┬┘",
            " /_\\ /_\\",
        ),
        4: (
            " ⚡  ╤  ⚡",
            "╔══[■_■]══╗",
            "║ █▀▓▓▀█ ║",
            "╠┤ ▒██▒ ├╣",
            "║ █▄▓▓▄█ ║",
            "╠┤ ╭──╮ ├╣",
            "╚╤═╧══╧═╤╝",
            " ⚡/_/\\_\\⚡",
        ),
        5: (
            " ⚡  ╤╤╤  ⚡",
            "╔═══[■_■]═══╗",
            "║ █▀▓▒▒▓▀█ ║",
            "╠╦┤ ╔═╬═╗ ├╦╣",
            "║║ │ ║║ ║ │║║",
            "╠╩┤ ╚═╬═╝ ├╩╣",
            "║  ╱╲╱╲╱╲  ║",
            "╚═⚡╧═══╧⚡═╝",
            "  0 1 0 1 0",
        ),
    },
    "gemini": {
        0: (
            "   .--.   ",
            "  / 🔵 \\  ",
            "  \\____/  ",
        ),
        1: (
            "╭──────╮",
            "│ ◑  ◐ │",
            "╰──────╯",
        ),
        2: (
            "  🟢◑◐🔵",
            " ╭╮╭∿╮╭╮",
            " │││ │││",
            " ╰╯╰─╯╰╯",
            "   /  \\",
        ),
        3: (
            "  ◑╮  ╭◐",
            " ╭││  ││╮",
            " ││𖦹──𖦹││",
            " │╰╮  ╭╯│",
            " ╰─╯  ╰─╯",
        ),
        4: (
            "🌈 ≋◑══◐≈ 🌈",
            " ╭∾╲╱╲╱∿╮",
            "≈│ 𖦹  𖦹 │≋",
            " ∿╰╮╭──╮╯∾",
            " ≈ │╰──╯│ ≋",
            "🌈 ╰─∾∿─╯ 🌈",
        ),
        5: (
            "🌈  ╭─∞─╮  🌈",
            "  ◑╲│  │╱◐",
            " ╭│ 𖦹╲╱𖦹 │╮",
            "≈│╲  ╳╳  ╱│≈",
            " ∿╰╮╱──╲╭╯∾",
            " ≈ │∿╲╱∾│ ≋",
            "🌈 ╰─∾∿∾─╯ 🌈",
        ),
    },
    "cypherclaw": {
        0: (
            "   .--.   ",
            "  / 👑 \\  ",
            "  \\____/  ",
        ),
        1: (
            "╭──────────╮",
            "│ /ᐠ. ˕.ᐟ\\ │",
            "╰──────────╯",
        ),
        2: (
            "  ╭────────╮",
            "╾╼│/ᐠ◉ ˕.ᐟ\\│╾╼",
            "  │  ╲╱╲╱  │",
            "  ╰────────╯",
        ),
        3: (
            "   ▌▐",
            " ╭/ᐠ◉ ˕ ◉ᐟ\\╮",
            "⫽│  ╲___╱  │⫽",
            " │ ╱╱   ╲╲ │",
            " ╰▌▐───▌▐╯",
        ),
        4: (
            "   ✨👑✨",
            "⚡█▓/ᐠ◉ ˕ ◉ᐟ\\▓█⚡",
            "▒│  ╲___╱  │▒",
            "░│ ╱ ⫽ ⫽ ╲ │░",
            "▒│╱  ⚡⚡  ╲│▒",
            "⚡╰█▓▒░░▒▓█╯⚡",
            "   ✨   ✨",
        ),
        5: (
            "    ✨👑✨",
            "⚡╭█/ᐠ◉ ˕ ◉ᐟ\\█╮⚡",
            "▒│   ╲___╱   │▒",
            "░│ ╱╱ ⫽ ⫽ ╲╲ │░",
            "▒│╱  ⚡🔥⚡  ╲│▒",
            "⚡╰█╮  ╱╲  ╭█╯⚡",
            "  ╰▓█▒▒▒█▓╯",
            "   ✨   ✨",
        ),
    },
}


def _replace_many(lines: tuple[str, ...], mapping: dict[str, str]) -> tuple[str, ...]:
    updated: list[str] = []
    for line in lines:
        new_line = line
        for old, new in mapping.items():
            new_line = new_line.replace(old, new)
        updated.append(new_line)
    return tuple(updated)


def _expressions(agent: str, lines: tuple[str, ...]) -> tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]]:
    if agent == "claude":
        half = _replace_many(lines, {"◉": "◕", "⊚": "⊛"})
        closed = _replace_many(lines, {"◉": "-", "⊚": "-", "◕": "-", "⊛": "-"})
        return lines, half, closed
    if agent == "codex":
        half = _replace_many(lines, {"□": "▣", "■": "▣"})
        closed = _replace_many(lines, {"□": "-", "■": "-", "▣": "-"})
        return lines, half, closed
    if agent == "gemini":
        half = _replace_many(lines, {"◑": "◔", "◐": "◕"})
        closed = _replace_many(lines, {"◑": "-", "◐": "-", "◔": "-", "◕": "-", "𖦹": "◌"})
        return lines, half, closed
    half = _replace_many(lines, {"◉": "◌", ".": "·"})
    closed = _replace_many(lines, {"◉": "-", ".": "-", "◌": "-"})
    return lines, half, closed


def _compose_frame(
    lines: tuple[str, ...],
    *,
    top: tuple[str, ...] = (),
    bottom: tuple[str, ...] = (),
    shift: int = 0,
) -> str:
    content = [*top, *lines, *bottom]
    width = max(len(line) for line in content) if content else 0
    centered = [line.center(width) for line in content]
    if shift > 0:
        centered = ([""] * shift) + centered
    return "\n".join(centered).rstrip()


def _idle_frames(agent: str, lines: tuple[str, ...]) -> list[str]:
    open_lines, half_lines, closed_lines = _expressions(agent, lines)
    return [
        _compose_frame(open_lines),
        _compose_frame(half_lines, shift=1),
        _compose_frame(closed_lines),
        _compose_frame(open_lines, shift=1),
    ]


def _thinking_frames(agent: str, lines: tuple[str, ...]) -> list[str]:
    open_lines, half_lines, _ = _expressions(agent, lines)
    return [
        _compose_frame(open_lines, top=("  ·",)),
        _compose_frame(half_lines, top=(" ·.°",)),
        _compose_frame(open_lines, top=("·.°•", "  💧")),
        _compose_frame(half_lines, top=("·.°•", " ·.°•")),
    ]


def _success_frames(agent: str, lines: tuple[str, ...]) -> list[str]:
    open_lines, _, _ = _expressions(agent, lines)
    return [
        _compose_frame(open_lines, bottom=("  ✨",), shift=1),
        _compose_frame(open_lines, top=(" ✨   ✨",)),
        _compose_frame(open_lines, top=("✨ ✨ ✨",)),
        _compose_frame(open_lines, top=("✨ 🎉 ✨",)),
    ]


def _error_frames(agent: str, lines: tuple[str, ...]) -> list[str]:
    _, half_lines, closed_lines = _expressions(agent, lines)
    marker = "💢" if agent == "codex" else "😿"
    return [
        _compose_frame(half_lines, bottom=("  ...",), shift=1),
        _compose_frame(closed_lines, top=(f"  {marker}",)),
        _compose_frame(closed_lines, top=(f" {marker} ", "  ...")),
        _compose_frame(half_lines, top=("  ...",)),
    ]


def _sleeping_frames(agent: str, lines: tuple[str, ...]) -> list[str]:
    _, _, closed_lines = _expressions(agent, lines)
    return [
        _compose_frame(closed_lines, top=("🌙  z",)),
        _compose_frame(closed_lines, top=("🌙 zZ",)),
        _compose_frame(closed_lines, top=("🌙 zZZ",)),
        _compose_frame(closed_lines, top=("🌙 zZz",)),
    ]


def _communicating_frames(agent: str, lines: tuple[str, ...]) -> list[str]:
    open_lines, half_lines, _ = _expressions(agent, lines)
    return [
        _compose_frame(open_lines, top=("「·  」",)),
        _compose_frame(half_lines, top=("「·· 」",)),
        _compose_frame(open_lines, top=("「···」",)),
        _compose_frame(half_lines, top=("「·· 」",)),
    ]


def _hungry_frames(agent: str, lines: tuple[str, ...]) -> list[str]:
    open_lines, half_lines, _ = _expressions(agent, lines)
    snack = "🍖" if agent != "codex" else "🔋"
    return [
        _compose_frame(open_lines, top=(f"  {snack} ?",)),
        _compose_frame(half_lines, top=(f" {snack} ...",)),
        _compose_frame(open_lines, bottom=("  rumble",), shift=1),
        _compose_frame(half_lines, top=(f" {snack} !",)),
    ]


def _build_sprites() -> dict[str, dict[int, dict[str, list[str]]]]:
    sprites: dict[str, dict[int, dict[str, list[str]]]] = {}
    for agent, stages in _PORTRAITS.items():
        sprites[agent] = {}
        for stage, lines in stages.items():
            sprites[agent][stage] = {
                "idle": _idle_frames(agent, lines),
                "thinking": _thinking_frames(agent, lines),
                "success": _success_frames(agent, lines),
                "error": _error_frames(agent, lines),
                "sleeping": _sleeping_frames(agent, lines),
                "communicating": _communicating_frames(agent, lines),
                "hungry": _hungry_frames(agent, lines),
            }
    return sprites


def _validate_widths() -> None:
    for agent, stages in SPRITES.items():
        for stage, states in stages.items():
            for state, frames in states.items():
                if not frames:
                    raise ValueError(f"missing frames for {agent} stage {stage} state {state}")
                for frame in frames:
                    line_width = max((len(line) for line in frame.splitlines()), default=0)
                    if line_width > 30:
                        raise ValueError(
                            f"{agent} stage {stage} {state} frame exceeds 30 chars: {line_width}"
                        )


SPRITES: Final[dict[str, dict[int, dict[str, list[str]]]]] = _build_sprites()
_validate_widths()


def get_frames(agent: str, stage: int, state: str) -> list[str]:
    """Return animation frames for a pet state."""
    agent_key = agent.lower()
    if agent_key not in SPRITES:
        agent_key = "cypherclaw"
    stage_key = stage if stage in SPRITES[agent_key] else 0
    state_key = state if state in SPRITES[agent_key][stage_key] else "idle"
    return SPRITES[agent_key][stage_key][state_key]


def get_portrait(agent: str, stage: int) -> str:
    """Return a single static portrait frame for status displays."""
    agent_key = agent.lower()
    if agent_key not in _PORTRAITS:
        agent_key = "cypherclaw"
    stage_key = stage if stage in _PORTRAITS[agent_key] else 0
    return "\n".join(_PORTRAITS[agent_key][stage_key])


def get_evolution_frames(agent: str, from_stage: int, to_stage: int) -> list[str]:
    """Return transition frames showing evolution from one stage to the next."""
    agent_key = agent.lower()
    if agent_key not in _PORTRAITS:
        agent_key = "cypherclaw"
    old_stage = from_stage if from_stage in _PORTRAITS[agent_key] else min(_PORTRAITS[agent_key])
    new_stage = to_stage if to_stage in _PORTRAITS[agent_key] else max(_PORTRAITS[agent_key])
    old_lines = _PORTRAITS[agent_key][old_stage]
    new_lines = _PORTRAITS[agent_key][new_stage]
    flash_lines = (
        "    ✨✨✨    ",
        "  ✨⚡✨⚡✨  ",
        "    ✨✨✨    ",
    )
    wobble_lines = tuple(
        ((" " if index % 2 == 0 else "") + line)
        for index, line in enumerate(old_lines)
    )
    return [
        _compose_frame(wobble_lines, top=("  ⚡ evolving ⚡",)),
        _compose_frame(old_lines, top=(" ✨ sparkle burst ✨",), bottom=("   ✨ ✨ ✨",)),
        _compose_frame(flash_lines, top=("    EVOLVE!    ",), bottom=("  ✨⚡✨⚡✨  ",)),
        _compose_frame(new_lines, top=("  🎉 ascended 🎉",), bottom=("   ✨  ✨  ✨",)),
    ]
