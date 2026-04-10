<!--
  sdp-cli agent-specific template for codex
  Edit this file to tune how codex handles lead_t1.md.
  The shipped default lives at src/sdp/prompts/templates/lead_t1.md.
  Delete this file to revert to the default.
-->
# Task {{ task_id }}: {{ task_description }}

{% if acceptance_criteria %}
## Acceptance Criteria

{{ acceptance_criteria }}
{% endif %}

**Tier:** {{ tier }}

## Instructions

Handle this directly. Skip broad discovery and do not write a spec.

1. Read only the file(s) you expect to change and the closest relevant tests.
2. Make the smallest change that satisfies the task.
3. Add or update a regression test when behavior changes.
4. Run focused validation, then broader checks if needed.
5. Commit as soon as the change works: `<type>(scope): summary [{{ task_id }}]`

## Rules

- Stay in scope; no unrelated cleanup.
- Follow existing patterns and type hints.
- Record blocking assumptions in `ESCALATIONS.md`.
- Do not finish with uncommitted changes.

## Validation

Run before committing:
```bash
pip install -e '.[dev]'
pytest tests/ -x --tb=short
ruff check src/ tests/
mypy src/
```
