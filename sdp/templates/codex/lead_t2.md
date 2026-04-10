<!--
  sdp-cli agent-specific template for codex
  Edit this file to tune how codex handles lead_t2.md.
  The shipped default lives at src/sdp/prompts/templates/lead_t2.md.
  Delete this file to revert to the default.
-->
# Task {{ task_id }}: {{ task_description }}

{% if acceptance_criteria %}
## Acceptance Criteria

{{ acceptance_criteria }}
{% endif %}

**Tier:** {{ tier }}

## Instructions

Work directly. Do not write a specification file or a phase summary.

1. Read the likely entrypoint files and nearby tests, not the whole repo.
2. Implement the smallest viable solution first.
3. Add or update tests around the changed behavior.
4. Run focused checks while iterating, then the full validation below.
5. Commit each logical unit once it passes. Do not wait until the very end.

## Defaults

- If the task is clear, code first and add tests immediately after.
- Prefer explicit file paths and existing patterns over open-ended exploration.
- Fix the task; do not refactor adjacent code unless required.
- Record assumptions or follow-up risks in `ESCALATIONS.md` instead of blocking.

## Rules

- Stay in scope and keep changes minimal.
- Follow project conventions from `AGENTS.md`.
- Do not stop with uncommitted tracked changes.
- Use commit format: `<type>(scope): summary [{{ task_id }}]`

## Validation

Run before final commit:
```bash
pip install -e '.[dev]'
pytest tests/ -x --tb=short
ruff check src/ tests/
mypy src/
```
