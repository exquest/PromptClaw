Create the AEAF Telegram animation player for CypherClaw.

File to create: /Users/anthony/Programming/PromptClaw/my-claw/tools/glyphweave/player.py

This file provides an `AEAFPlayer` class that plays frame-based animations by editing a Telegram message repeatedly.

Use the Animation class from /Users/anthony/Programming/PromptClaw/my-claw/tools/glyphweave/dsl.py which provides:
- `Animation(width, height, frame_ms, loop)` — create animation
- `animation.add_frame(canvas)` — append a Canvas as a frame
- `animation.to_aeaf()` — export as AEAF v1 text format

Requirements:

1. `AEAFPlayer` class:
   - `__init__(self, frames: list[str], frame_ms: int, loop: bool, message_id: int, edit_fn: Callable[[int, str], None])`
   - `start()` — launches a daemon thread that iterates frames, calling edit_fn(message_id, frame_text) per frame, then sleeping frame_ms/1000 seconds
   - `stop()` — sets a threading.Event to stop the loop, joins the thread with 3s timeout
   - Minimum frame_ms enforced at 3000 (Telegram rate limit safety)
   - If loop=True, cycles frames forever until stop() called
   - If loop=False, plays once then stops

2. `build_spinner_frames(agent: str, task_desc: str, phases: list[str]) -> tuple[list[str], int]`:
   - Returns (list_of_frame_strings, frame_ms)
   - Each frame is a composed scene using Canvas:
     - Cat face (cycling through expressions: o.o, -.-, ^.^, o.o)
     - Agent icon (🟣 claude, 🟢 codex, 🔵 gemini, 🧠 brain)
     - Elapsed time placeholder (use {elapsed} that caller replaces, or just show phase)
     - Progress bar: ▓ for completed phases, ░ for remaining
     - Current phase text: "→ {phase}..."
   - One frame per phase, so len(frames) == len(phases)
   - frame_ms = 5000 (5 seconds per frame, safe for Telegram)

3. `build_processing_frames() -> tuple[list[str], int]`:
   - 4 simple frames showing the cat "thinking"
   - Cycle through cat expressions with "🦀 processing..." text
   - frame_ms = 3000

Example frame output:
```
 /\_/\
( o.o )  🟣 claude
 > ^ <   12s
━━━━━━━━━━━━━━━
▓▓░░░
→ reading context...
```

Keep frames under 300 characters each.
Use only Python stdlib + the Canvas from dsl.py.
Threading must be daemon threads for clean shutdown.
