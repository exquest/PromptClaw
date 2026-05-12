<!--
  sdp-cli agent-specific template for codex
  Edit this file to tune how codex handles no_work_retry.md.
  The shipped default lives at src/sdp/prompts/templates/no_work_retry.md.
  Delete this file to revert to the default.
-->
# Retry: Task {{ task_id }}

**Task:** {{ task_description }}

## Problem

Your previous attempt produced **zero work**. For Codex this usually means too much exploration and not enough implementation.

## Instructions

1. Re-read the task and choose the smallest concrete change that moves it forward.
2. Read only the files you will touch and the closest relevant tests.
3. Make one working slice quickly and commit it immediately: `<type>(scope): summary [{{ task_id }}]`
4. Continue in small increments, committing each logical improvement.
5. Finish with validation:
   ```bash
   pip install -e '.[dev]'
   pytest tests/ -x --tb=short
   ruff check src/ tests/
   mypy src/
   ```

## Rules

- Do not restart with a broad repo survey or a spec file.
- If the task is ambiguous, make the safest reasonable assumption and log it in `ESCALATIONS.md`.
- A small committed slice is better than another zero-work attempt.
- Do not finish with zero commits.
