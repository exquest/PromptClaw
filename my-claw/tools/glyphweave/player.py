"""AEAF Telegram animation player for CypherClaw.

Provides frame-based animations that edit a Telegram message on a timer.
"""

from __future__ import annotations

import threading
from typing import Callable

# ---------------------------------------------------------------------------
# Contextual animation imports (new system)
# ---------------------------------------------------------------------------

try:
    from glyphweave.pet_animations import (
        build_contextual_frames,
        build_thinking_frames,
    )
    _HAS_PET_ANIMATIONS = True
except ImportError:
    _HAS_PET_ANIMATIONS = False

# ---------------------------------------------------------------------------
# Agent icon lookup
# ---------------------------------------------------------------------------

AGENT_ICONS: dict[str, str] = {
    "claude": "\U0001f7e3",   # purple circle
    "codex": "\U0001f7e2",    # green circle
    "gemini": "\U0001f535",   # blue circle
    "brain": "\U0001f9e0",    # brain
}

# ---------------------------------------------------------------------------
# Cat expressions (legacy fallback)
# ---------------------------------------------------------------------------

CAT_EXPRESSIONS = ["o.o", "-.-", "^.^", "o.o"]

# Animation frames — cat expression cycles to show "alive", status text stays fixed
_SPINNER_ANIMATIONS = [
    ["  ∙ ∙ ∙", " ∙∙ ∙ ∙", " ∙∙∙∙ ∙", " ∙∙∙∙∙∙", "  ∙∙∙∙∙", "   ∙∙∙∙", "    ∙∙∙", "     ∙∙", "      ∙", "  ∙ ∙ ∙"],
    [" ░▒▓██▓▒░", " ▒▓██▓▒░░", " ▓██▓▒░░▒", " ██▓▒░░▒▓", " █▓▒░░▒▓█", " ▓▒░░▒▓██"],
    [" ◐ ", " ◓ ", " ◑ ", " ◒ "],
    [" ⠋ ", " ⠙ ", " ⠹ ", " ⠸ ", " ⠼ ", " ⠴ ", " ⠦ ", " ⠧ ", " ⠇ ", " ⠏ "],
]


def _legacy_spinner_frames(
    agent: str,
    task_desc: str,
    phases: list[str],
    pet_frames: list[str] | None = None,
) -> tuple[list[str], int]:
    """Legacy spinner implementation used as fallback."""
    icon = AGENT_ICONS.get(agent.lower(), "\U0001f7e3")
    frames: list[str] = []
    anim = _SPINNER_ANIMATIONS[1]  # wave animation

    for i in range(len(anim)):
        wave = anim[i % len(anim)]
        if pet_frames:
            sprite = pet_frames[i % len(pet_frames)]
            frame = (
                f"```\n"
                f"{sprite}\n"
                f"```\n"
                f"{icon}{wave}\n"
                f"\u2192 {task_desc[:40]}..."
            )
        else:
            expr = CAT_EXPRESSIONS[i % len(CAT_EXPRESSIONS)]
            frame = (
                f"```\n"
                f" /\\_/\\\n"
                f"( {expr} )  {agent}\n"
                f" > ^ <\n"
                f"```\n"
                f"{icon}{wave}\n"
                f"\u2192 {task_desc[:40]}..."
            )
        frames.append(frame)

    return frames, 5000


def _legacy_processing_frames(pet_portrait: str | None = None) -> tuple[list[str], int]:
    """Legacy processing implementation used as fallback."""
    anim = _SPINNER_ANIMATIONS[3]  # braille dots spinner
    frames: list[str] = []

    for i, dot in enumerate(anim):
        if pet_portrait:
            frame = (
                f"```\n"
                f"{pet_portrait}\n"
                f"```\n"
                f"\U0001f9e0{dot} routing..."
            )
        else:
            expr = CAT_EXPRESSIONS[i % len(CAT_EXPRESSIONS)]
            frame = (
                f"```\n"
                f" /\\_/\\\n"
                f"( {expr} )  thinking\n"
                f" > ^ <\n"
                f"```\n"
                f"\U0001f9e0{dot} routing..."
            )
        frames.append(frame)

    return frames, 3000


def build_spinner_frames(
    agent: str,
    task_desc: str,
    phases: list[str],
    pet_frames: list[str] | None = None,
) -> tuple[list[str], int]:
    """Build animated frames that show activity, not fake progress.

    Uses the contextual animation system when available, which provides
    personality-driven narration lines and activity decorations that
    reflect what the agent is actually doing.  Falls back to the legacy
    wave-spinner when *pet_animations* is not importable.

    Returns (list_of_frame_strings, frame_ms).
    """
    if _HAS_PET_ANIMATIONS:
        try:
            frames = build_contextual_frames(
                agent=agent,
                task_desc=task_desc,
                pet_frames=pet_frames,
                num_frames=6,
            )
            return frames, 5000
        except Exception:
            pass
    return _legacy_spinner_frames(agent, task_desc, phases, pet_frames)


def build_processing_frames(pet_portrait: str | None = None) -> tuple[list[str], int]:
    """Build animated 'thinking' frames for the routing phase.

    Uses the contextual animation system when available, with CypherClaw
    routing narrations and thinking decorations.  Falls back to the legacy
    braille-dot spinner when *pet_animations* is not importable.

    Returns (list_of_frame_strings, frame_ms).
    """
    if _HAS_PET_ANIMATIONS:
        try:
            frames = build_thinking_frames(
                pet_portrait=pet_portrait,
                num_frames=6,
            )
            return frames, 3000
        except Exception:
            pass
    return _legacy_processing_frames(pet_portrait)


# ---------------------------------------------------------------------------
# AEAFPlayer
# ---------------------------------------------------------------------------

MIN_FRAME_MS = 3000  # Telegram rate-limit safety floor


class AEAFPlayer:
    """Plays a list of text frames by repeatedly editing a Telegram message."""

    def __init__(
        self,
        frames: list[str],
        frame_ms: int,
        loop: bool,
        message_id: int,
        edit_fn: Callable[[int, str], None],
    ) -> None:
        self.frames = frames
        self.frame_ms = max(frame_ms, MIN_FRAME_MS)
        self.loop = loop
        self.message_id = message_id
        self.edit_fn = edit_fn

        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    # -- internal ----------------------------------------------------------

    def _run(self) -> None:
        """Main playback loop executed on the daemon thread."""
        while not self._stop_event.is_set():
            for frame in self.frames:
                if self._stop_event.is_set():
                    return
                self.edit_fn(self.message_id, frame)
                if self._stop_event.wait(self.frame_ms / 1000):
                    return
            if not self.loop:
                return

    # -- public API --------------------------------------------------------

    def start(self) -> None:
        """Launch the playback daemon thread."""
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Signal the playback thread to stop and join with a 3 s timeout."""
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=3)
