from __future__ import annotations

from pathlib import Path
from shutil import get_terminal_size
from typing import Iterable


def terminal_width(default: int = 78) -> int:
    try:
        return max(60, min(get_terminal_size((default, 24)).columns, 100))
    except OSError:
        return default


def _fit(text: str, width: int) -> str:
    if len(text) <= width:
        return text
    return text[: max(0, width - 1)] + "…"


def _box(lines: list[str], title: str = "", width: int | None = None) -> str:
    width = width or terminal_width()
    inner_width = max(24, min(width - 4, 92))
    title_text = f" {title} " if title else ""
    top = "╔" + title_text + "═" * max(0, inner_width - len(title_text)) + "╗"
    body = [f"║ {_fit(line, inner_width - 1).ljust(inner_width - 1)}║" for line in lines]
    bottom = "╚" + "═" * inner_width + "╝"
    return "\n".join([top, *body, bottom])


def banner(project_name: str = "PromptClaw", subtitle: str = "Startup Wizard") -> str:
    width = terminal_width()
    mascot = [
        r" /\_/\\",
        r"( o.o )",
        r" > ^ <",
    ]
    panel = _box(
        [
            f"{project_name} — {subtitle} 🦀✨🎉",
            "one question at a time • smart follow-ups • playful setup",
        ],
        title=" PromptClaw ",
        width=max(width - 8, 60),
    ).splitlines()

    combined: list[str] = []
    for idx in range(max(len(mascot), len(panel))):
        left = mascot[idx] if idx < len(mascot) else " " * len(mascot[0])
        right = panel[idx] if idx < len(panel) else ""
        combined.append(f"{left}  {right}")
    return "\n".join(combined)


def question_card(index: int, prompt: str, hint: str = "") -> str:
    lines = [f"Question {index} 🪄", prompt.strip()]
    if hint.strip():
        lines.append(f"Hint: {hint.strip()}")
    lines.append("Type your answer and press Enter.")
    return _box(lines, title=" Startup ")


def follow_up_card(prompt: str, hint: str = "") -> str:
    lines = ["Follow-up sparkle ✨", prompt.strip()]
    if hint.strip():
        lines.append(f"Hint: {hint.strip()}")
    lines.append("A short answer is fine.")
    return _box(lines, title=" Follow-up ")


def status_line(message: str, emoji: str = "✨") -> str:
    return f"{emoji} {message}"


def files_written_card(files: Iterable[Path], project_root: Path) -> str:
    relative_paths = [str(path.relative_to(project_root)) for path in files]
    lines = ["Fresh files and updates 🍬", *[f"- {path}" for path in relative_paths]]
    return _box(lines, title=" Files ")


def summary_card(lines: list[str], title: str = " Summary ") -> str:
    return _box(lines, title=title)
